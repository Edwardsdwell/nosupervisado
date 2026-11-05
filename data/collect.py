"""Recolección de ocurrencias desde GBIF.

No exige que coincidan audio e imagen ni filtra por licencia. Conserva la licencia
declarada como metadato para revisión posterior. Solo registra URLs; no descarga medios.
"""
from __future__ import annotations

import math
import time

from core.errors import ErrorDatos
from . import db

URL = "https://api.gbif.org/v1/occurrence/search"
HDR = {"User-Agent": "nosupervisado/1.0 (uso academico)"}
PAISES = ["BO", "PE", "EC", "CO", "BR", "MX", "CR", "AR", "CL", "US", "ZA", "AU", "IN", "JP"]
TAXONES = {"Aves": 212, "Amphibia": 131}
CAMPOS_TEXTO = ["occurrenceRemarks", "locality", "habitat", "verbatimLocality"]


def obtener(params, reintentos=4, sesion=None, espera=2.0):
    import requests

    sesion = sesion or requests
    err = ""
    for i in range(reintentos):
        try:
            t = time.time()
            r = sesion.get(URL, params=params, headers=HDR, timeout=60)
            r.raise_for_status()
            return r.json(), time.time() - t
        except Exception as e:  # noqa: BLE001
            err = str(e)
            time.sleep(espera * 2**i)
    raise ErrorDatos("GBIF no respondió", err)


def parametros(pais, taxon, offset, limite=300, media=None):
    # No filtrar por una sola modalidad: GBIF debe devolver ocurrencias con
    # StillImage, Sound o ambas. La ausencia de una modalidad no invalida el evento.
    p = [("hasGeospatialIssue", "false"), ("taxonKey", taxon),
         ("country", pais), ("limit", limite), ("offset", offset)]
    if media:
        p.append(("mediaType", media))
    return p


def guardar(con, r: dict, por_especie: int = 5) -> bool:
    """Inserta una ocurrencia aunque tenga solo una modalidad o solo metadatos.

    No aplica filtros de licencia: conserva el valor original para que el usuario
    realice su propia revisión. Los medios quedan como pendientes, sin descargarse.
    """
    media = r.get("media") or []
    snd = [m for m in media if m.get("type") == "Sound" and m.get("identifier")]
    img = [m for m in media if m.get("type") == "StillImage" and m.get("identifier")]
    sp = r.get("species") or r.get("scientificName")
    if not sp or not r.get("key"):
        return False
    eid = "gbif:" + str(r["key"])
    existe = con.execute("SELECT 1 FROM events WHERE event_id=?", (eid,)).fetchone()
    if not existe:
        if con.execute("SELECT COUNT(*) FROM events WHERE species=?", (sp,)).fetchone()[0] >= por_especie:
            return False
        con.execute("INSERT INTO events(event_id,source,source_id,observed_raw,species,genus,family,class,dataset_key,license,created_utc)"
                    " VALUES(?,?,?,?,?,?,?,?,?,?,?)",
                    (eid, "gbif", str(r["key"]), r.get("eventDate"), sp, r.get("genus"), r.get("family"), r.get("class"),
                     r.get("datasetKey"), r.get("license"), db.now()))
    else:
        # Si se consultó la misma ocurrencia en otra pasada, se completa su metadato.
        con.execute("UPDATE events SET species=COALESCE(species,?), observed_raw=COALESCE(observed_raw,?) WHERE event_id=?",
                    (sp, r.get("eventDate"), eid))

    from .validacion import validar_coordenada
    if r.get("decimalLatitude") is not None and r.get("decimalLongitude") is not None:
        lat, lon, motivo = validar_coordenada(r.get("decimalLatitude"), r.get("decimalLongitude"))
        con.execute("INSERT OR IGNORE INTO geo(event_id,lat,lon,crs,uncertainty_m,country,locality,geo_status,motivo) VALUES(?,?,?,?,?,?,?,?,?)",
                    (eid, lat if not motivo else r.get("decimalLatitude"), lon if not motivo else r.get("decimalLongitude"), "EPSG:4326",
                     r.get("coordinateUncertaintyInMeters"), r.get("countryCode"), r.get("locality"), "invalido" if motivo else "present", motivo or None))
    for f in CAMPOS_TEXTO:
        if r.get(f):
            con.execute("INSERT OR IGNORE INTO texts VALUES(?,?,?,?,?)", (eid, f, str(r[f]), None, None))
    for i, m in enumerate(snd + img):
        d = (m.get("description") or m.get("title") or "").strip()
        if d:
            con.execute("INSERT OR IGNORE INTO texts VALUES(?,?,?,?,?)", (eid, f"media_desc_{i}", d, None, None))
    for pref, tabla, col, lista in (("a", "audio", "audio_id", snd), ("i", "images", "image_id", img)):
        for i, m in enumerate(lista):
            con.execute(f"INSERT OR IGNORE INTO {tabla}({col},event_id,url,license,creator,download_status) VALUES(?,?,?,?,?,?)",
                        (f"{eid}:{pref}{i}", eid, m.get("identifier"), m.get("license") or r.get("license"), m.get("creator"), db.PENDIENTE))
    return not bool(existe)


def recolectar(con, objetivo=50, paises=None, taxones=None, por_especie=20, max_offset=3000, ctx=None, pausa=0.6, get=obtener) -> int:
    """Recolecta ~`objetivo` eventos repartidos entre países y taxones. `get` se puede sustituir en pruebas."""
    paises, taxones = paises or PAISES, taxones or TAXONES
    cuota, total = math.ceil(objetivo / (len(paises) * len(taxones))), 0
    for pais in paises:
        for nombre, taxon in taxones.items():
            got, offset = 0, 0
            while got < cuota and offset < max_offset:
                if ctx is not None:
                    ctx.punto(total / max(objetivo, 1), f"GBIF {pais} {nombre} (offset {offset})")
                datos, lat = get(parametros(pais, taxon, offset))
                con.execute("INSERT INTO ingest_log VALUES(?,?,?,?,?,?,?)",
                            (db.now(), "gbif", f"{pais} {nombre} offset {offset}", "ok", len(datos["results"]), lat, ""))
                for r in datos["results"]:
                    if got >= cuota:
                        break
                    if guardar(con, r, por_especie):
                        got += 1
                        total += 1
                con.commit()
                if datos.get("endOfRecords"):
                    break
                offset += 300
                time.sleep(pausa)
    return total
