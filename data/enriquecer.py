"""Enriquecimiento de textos: descripciones de cada especie desde Wikipedia y GBIF (requiere internet).

Los textos de GBIF por evento suelen ser solo localidades («Winter Park, Florida, USA»): poco contenido para
TF-IDF y LDA. Aquí se obtiene, por especie, el resumen de Wikipedia (es/en, licencia CC BY-SA) y las
descripciones y nombres comunes de GBIF, y se guardan en `species_texts` con su fuente, URL y licencia.
Las peticiones se pueden sustituir (`get=`) para probar sin red.
"""
from __future__ import annotations

import re
import time
from html import unescape
from urllib.parse import quote

from . import db

HDR = {"User-Agent": "nosupervisado/1.0 (proyecto academico UMSA)"}
GBIF = "https://api.gbif.org/v1"
WIKI = "https://{lang}.wikipedia.org/api/rest_v1/page/summary/{titulo}"
LIC_WIKI = "CC BY-SA 4.0"


def _get_json(url, params=None, timeout=30):
    import requests

    r = requests.get(url, params=params, headers=HDR, timeout=timeout)
    if r.status_code == 404:
        return None
    r.raise_for_status()
    return r.json()


def limpiar_html(t: str) -> str:
    t = re.sub(r"<[^>]+>", " ", unescape(t or ""))
    return re.sub(r"\s+", " ", t).strip()


def wikipedia(especie: str, lang: str, get=_get_json) -> tuple[str, str] | None:
    j = get(WIKI.format(lang=lang, titulo=quote(especie.replace(" ", "_"))))
    if not j or j.get("type") == "disambiguation" or not (j.get("extract") or "").strip():
        return None
    url = (j.get("content_urls") or {}).get("desktop", {}).get("page") or WIKI.format(lang=lang, titulo=especie)
    return j["extract"].strip(), url


def gbif(especie: str, get=_get_json) -> list[tuple[str, str, str, str]]:
    """[(fuente, idioma, texto, url)] con descripciones y nombres comunes de GBIF."""
    m = get(f"{GBIF}/species/match", {"name": especie})
    key = (m or {}).get("usageKey")
    if not key:
        return []
    out = []
    d = get(f"{GBIF}/species/{key}/descriptions", {"limit": 20}) or {}
    for i, r in enumerate(d.get("results", [])):
        t = limpiar_html(r.get("description"))
        if len(t) >= 40:
            out.append((f"gbif_desc_{i}", (r.get("language") or "")[:3], t, f"https://www.gbif.org/species/{key}"))
    v = get(f"{GBIF}/species/{key}/vernacularNames", {"limit": 100}) or {}
    nombres: dict[str, set] = {}
    for r in v.get("results", []):
        nombres.setdefault((r.get("language") or "?")[:3], set()).add(r.get("vernacularName", "").strip())
    for lang, ns in nombres.items():
        ns = sorted(n for n in ns if n)
        if ns:
            out.append(("gbif_nombres", lang, f"Nombres comunes de {especie}: " + ", ".join(ns[:40]) + ".", f"https://www.gbif.org/species/{key}"))
    return out


def enriquecer(con, idiomas=("es", "en"), get=_get_json, pausa: float = 0.3, ctx=None, solo_nuevas: bool = True) -> dict:
    especies = [r[0] for r in con.execute("SELECT DISTINCT species FROM events WHERE species IS NOT NULL AND TRIM(species)<>'' ORDER BY 1")]
    if solo_nuevas:
        ya = {r[0] for r in con.execute("SELECT DISTINCT species FROM species_texts")}
        especies = [e for e in especies if e not in ya]
    rep = dict(especies=len(especies), nuevos=0, sin_resultado=[], errores=[])
    for i, e in enumerate(especies):
        if ctx is not None:
            ctx.punto(i / max(len(especies), 1), f"Especie {i + 1}/{len(especies)}: {e}")
        filas = []
        try:
            for lang in idiomas:
                w = wikipedia(e, lang, get)
                if w:
                    filas.append((e, f"wikipedia_{lang}", lang, w[0], w[1], LIC_WIKI))
            filas += [(e, f, lang, t, url, "según GBIF") for f, lang, t, url in gbif(e, get)]
        except Exception as ex:  # noqa: BLE001 - una especie que falla no detiene las demás
            rep["errores"].append((e, str(ex)[:120]))
            continue
        if not filas:
            rep["sin_resultado"].append(e)
        for f in filas:
            cur = con.execute("INSERT OR IGNORE INTO species_texts(species,source,lang,text,url,license,retrieved_utc) VALUES(?,?,?,?,?,?,?)",
                              (*f, db.now()))
            rep["nuevos"] += max(cur.rowcount, 0)
        con.commit()
        if pausa:
            time.sleep(pausa)
    db.auditar(con, "enriquecer_textos", dict(especies=rep["especies"], nuevos=rep["nuevos"], errores=len(rep["errores"])), rep["nuevos"])
    con.commit()
    return rep
