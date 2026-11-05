"""Conectores de biodiversidad: iNaturalist y Xeno-canto.

La API se consulta bajo demanda (no es streaming). Se guardan metadatos y URLs;
los archivos multimedia quedan pendientes hasta que el usuario decide descargarlos.
No se filtran ni interpretan licencias: se conserva la licencia declarada en origen.
"""
from __future__ import annotations

import os
import time
from urllib.parse import urlparse

from core.errors import ErrorDatos
from . import db
from .validacion import validar_coordenada

INAT_URL = "https://api.inaturalist.org/v1/observations"
XC_URL = "https://xeno-canto.org/api/3/recordings"
HDR = {"User-Agent": "BiodiversidadNoSupervisada/2.0 (academic research)"}
INAT_TAXA = {"Aves": 3, "Amphibia": 20978}


def _get_json(url, params, timeout=40, get=None):
    import requests
    client = get or requests.get
    last = None
    for intento in range(4):
        try:
            r = client(url, params=params, headers=HDR, timeout=timeout)
            if r.status_code == 429:
                time.sleep(min(30, 2 ** (intento + 1)))
                continue
            r.raise_for_status()
            return r.json()
        except Exception as exc:
            last = exc
            if intento < 3:
                time.sleep(2 ** intento)
    raise ErrorDatos("No se pudo consultar la fuente externa", str(last))


def _texto(con, eid, campo, valor):
    valor = str(valor or "").strip()
    if valor:
        con.execute("INSERT OR IGNORE INTO texts(event_id,field,original,normalized,lang) VALUES(?,?,?,?,?)",
                    (eid, campo, valor, None, None))


def _evento(con, eid, source, source_id, species=None, genus=None, family=None,
            class_name=None, observed=None, dataset=None, license_=None, link_type="event"):
    con.execute("""INSERT OR IGNORE INTO events
        (event_id,source,source_id,origin,observed_raw,species,genus,family,class,
         dataset_key,license,link_type,status,created_utc)
        VALUES(?,?,?,'real',?,?,?,?,?,?,?,?, 'ok',?)""",
        (eid, source, str(source_id), observed, species, genus, family, class_name,
         dataset, license_, link_type, db.now()))


def _geo(con, eid, lat, lon, uncertainty=None, country=None, locality=None):
    if lat in (None, "") or lon in (None, ""):
        return
    a, b, motivo = validar_coordenada(lat, lon)
    con.execute("""INSERT OR IGNORE INTO geo
        (event_id,lat,lon,crs,uncertainty_m,country,locality,geo_status,motivo)
        VALUES(?,?,?,?,?,?,?,?,?)""",
        (eid, a if not motivo else lat, b if not motivo else lon, "EPSG:4326",
         uncertainty, country, locality, "invalido" if motivo else "present", motivo))


def _medio(con, tabla, id_, eid, url, license_=None, creator=None):
    if not url:
        return
    col = "audio_id" if tabla == "audio" else "image_id"
    con.execute(f"""INSERT OR IGNORE INTO {tabla}
        ({col},event_id,url,license,creator,download_status)
        VALUES(?,?,?,?,?,?)""", (id_, eid, url, license_, creator, db.PENDIENTE))


def recolectar_inaturalist(con, objetivo=150, taxa=None, paginas_max=5, pausa=1.05, ctx=None, get=None):
    """Importa observaciones con foto y/o sonido; cada consulta busca una modalidad por separado."""
    taxa = taxa or INAT_TAXA
    total = 0
    # Consultas separadas: nunca exigir que una observación tenga ambas modalidades.
    for taxon_name, taxon_id in taxa.items():
        for modalidad, filtro in (("foto", {"photos": "true"}), ("audio", {"sounds": "true"})):
            if total >= objetivo:
                break
            agregados = 0
            for page in range(1, paginas_max + 1):
                if agregados >= max(1, objetivo // max(1, len(taxa) * 2)):
                    break
                params = {"taxon_id": taxon_id, "quality_grade": "research",
                          "has[]": "geo", "per_page": 200, "page": page,
                          "order_by": "observed_on", "order": "desc",
                          "fields": "id,observed_on,observed_on_string,location,place_guess,description,uri,taxon,photos,sounds,quality_grade,geoprivacy,private_geo,positional_accuracy"}
                params.update(filtro)
                t0 = time.time()
                data = _get_json(INAT_URL, params, get=get)
                rows = data.get("results", [])
                con.execute("INSERT INTO ingest_log VALUES(?,?,?,?,?,?,?)",
                            (db.now(), "iNaturalist", f"{taxon_name}/{modalidad}/page={page}", "ok", len(rows), time.time()-t0, ""))
                for o in rows:
                    tax = o.get("taxon") or {}
                    sp = tax.get("name") or tax.get("preferred_common_name") or "sin identificar"
                    eid = f"inat:{o['id']}"
                    _evento(con, eid, "iNaturalist", o["id"], sp, tax.get("iconic_taxon_name"),
                            None, tax.get("iconic_taxon_name"), o.get("observed_on"),
                            license_=None, link_type="event")
                    loc = o.get("location")
                    if isinstance(loc, str) and "," in loc:
                        lat, lon = loc.split(",", 1)
                        _geo(con, eid, lat, lon, o.get("positional_accuracy"), locality=o.get("place_guess"))
                    _texto(con, eid, "description", o.get("description"))
                    _texto(con, eid, "place_guess", o.get("place_guess"))
                    _texto(con, eid, "taxon_name", sp)
                    _texto(con, eid, "observation_url", o.get("uri"))
                    for j, ph in enumerate(o.get("photos") or []):
                        # Medium URL: se conserva URL, no se descarga el original en esta fase.
                        u = ph.get("url") or ""
                        if u:
                            u = u.replace("/square.", "/medium.").replace("/small.", "/medium.")
                            _medio(con, "images", f"{eid}:p{ph.get('id',j)}", eid, u,
                                   ph.get("license_code"), ph.get("attribution"))
                    for j, snd in enumerate(o.get("sounds") or []):
                        u = snd.get("file_url") or snd.get("file") or snd.get("url")
                        _medio(con, "audio", f"{eid}:s{snd.get('id',j)}", eid, u,
                               snd.get("license_code"), snd.get("attribution"))
                    agregados += 1
                    total += 1
                    if total >= objetivo:
                        break
                con.commit()
                if not rows or total >= objetivo:
                    break
                time.sleep(pausa)
    return total


def recolectar_xenocanto(con, objetivo=100, api_key=None, query="grp:birds",
                         queries=None, paginas_max=5, ctx=None, get=None):
    """Importa grabaciones y las enlaza por especie, nunca como el mismo evento fotográfico."""
    api_key = api_key or os.getenv("NS_XENO_CANTO_API_KEY")
    if not api_key:
        return {"agregados": 0, "omitido": "Falta NS_XENO_CANTO_API_KEY o una clave de API de Xeno-canto."}
    consultas = list(dict.fromkeys(queries or [query]))
    total = 0
    cuota = max(1, objetivo // max(1, len(consultas)))
    for q in consultas:
        if total >= objetivo:
            break
        for page in range(1, paginas_max + 1):
            params = {"query": q, "key": api_key, "page": page}
            t0 = time.time()
            data = _get_json(XC_URL, params, get=get)
            rows = data.get("recordings") or []
            con.execute("INSERT INTO ingest_log VALUES(?,?,?,?,?,?,?)",
                        (db.now(), "Xeno-canto", f"{q}/page={page}", "ok", len(rows), time.time()-t0, ""))
            agregados_consulta = 0
            for rec in rows:
                rid = str(rec.get("id") or "")
                if not rid:
                    continue
                genus, species = rec.get("gen") or "", rec.get("sp") or ""
                scientific = (genus + " " + species).strip() or rec.get("en") or "sin identificar"
                eid = f"xc:{rid}"
                _evento(con, eid, "Xeno-canto", rid, scientific, genus,
                        class_name=None, observed=rec.get("date"), dataset="Xeno-canto",
                        license_=rec.get("lic"), link_type="species")
                file_url = rec.get("file") or f"https://xeno-canto.org/{rid}/download"
                _medio(con, "audio", f"{eid}:audio", eid, file_url, rec.get("lic"), rec.get("rec"))
                _geo(con, eid, rec.get("lat"), rec.get("lng"), locality=rec.get("loc"))
                for field, label in (("loc","localidad"),("type","tipo_canto"),("rmk","observaciones"),
                                     ("en","nombre_comun"),("gen","genero"),("sp","epiteto"),
                                     ("url","fuente_url"),("sono","sonograma_url")):
                    _texto(con, eid, label, rec.get(field))
                total += 1
                agregados_consulta += 1
                if total >= objetivo or agregados_consulta >= cuota:
                    break
            con.commit()
            if not rows or total >= objetivo or agregados_consulta >= cuota:
                break
            time.sleep(1.0)
    return {"agregados": total, "omitido": None}


def recolectar_multifuente(con, objetivo=250, api_key=None, ctx=None):
    """Ejecuta fuentes independientes; los fallos de una no cancelan las demás."""
    informe = {}
    # Primero ocurrencias, luego grabaciones por género de anfibios disponibles en el corpus.
    try:
        from . import collect
        n = collect.recolectar(con, objetivo=max(1, objetivo // 3), ctx=ctx)
        informe["GBIF"] = {"agregados": n}
    except Exception as exc:
        informe["GBIF"] = {"agregados": 0, "error": str(exc)}
    try:
        informe["iNaturalist"] = {"agregados": recolectar_inaturalist(con, objetivo=max(1, objetivo // 2), ctx=ctx)}
    except Exception as exc:
        informe["iNaturalist"] = {"agregados": 0, "error": str(exc)}
    try:
        generos = [r[0] for r in con.execute(
            "SELECT DISTINCT genus FROM events WHERE class='Amphibia' AND genus IS NOT NULL AND TRIM(genus)<>'' ORDER BY genus LIMIT 12"
        )]
        consultas = ["grp:birds"] + [f"gen:{g}" for g in generos]
        informe["Xeno-canto"] = recolectar_xenocanto(
            con, objetivo=max(1, objetivo // 3), api_key=api_key, queries=consultas
        )
    except Exception as exc:
        informe["Xeno-canto"] = {"agregados": 0, "error": str(exc)}
    db.auditar(con, "ingesta_multifuente", informe, sum(v.get("agregados", 0) for v in informe.values()))
    con.commit()
    return informe
