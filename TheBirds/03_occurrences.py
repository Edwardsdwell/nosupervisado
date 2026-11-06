"""Paso 3: ingesta de observaciones + URLs de medios desde GBIF (solo metadatos; no descarga archivos).

Muestreo estratificado: por especie y por continente (K por continente), con offset aleatorio
y máximo 2 registros por observador, para reducir el sesgo geográfico y de observador.
Reanudable: guarda progreso por especie en ingest_progress.
"""
import argparse, random
from collections import Counter
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime
from tqdm import tqdm
from common import (connect, http, log, normalize_license, observer_hash,
                    GBIF, INAT_DATASET, XC_DATASET, IMAGE_PER_CONTINENT,
                    AUDIO_PER_CONTINENT, DOWNLOAD_WORKERS)

CONTINENTS = ["AFRICA", "ANTARCTICA", "ASIA", "EUROPE", "NORTH_AMERICA", "OCEANIA", "SOUTH_AMERICA"]
TYPE_MAP = {"image": "StillImage", "audio": "Sound"}
WINDOW = 300          # registros leídos por consulta antes de muestrear
MAX_PER_OBSERVER = 1

INS_OBS = """INSERT INTO observations
 (obs_id, source_id, dataset_key, taxon_key, lat, lon, geog, coord_uncertainty_m, country_code, continent,
  event_date, event_has_time, observer_hash, basis_of_record, iucn_category, sensitive)
 VALUES (%s,%s,%s,%s,%s,%s, ST_SetSRID(ST_MakePoint(%s,%s),4326)::geography, %s,%s,%s,%s,%s,%s,%s,%s,%s)
 ON CONFLICT (obs_id) DO NOTHING"""
INS_MEDIA = """INSERT INTO media (obs_id, type, url_original, license, rights_holder)
 VALUES (%s,%s,%s,%s,%s) ON CONFLICT (obs_id, url_original) DO NOTHING"""


def base_params(kind, taxon_key, continent):
    p = {"taxonKey": taxon_key, "continent": continent, "mediaType": TYPE_MAP[kind],
         "hasCoordinate": "true", "hasGeospatialIssue": "false", "occurrenceStatus": "PRESENT"}
    if kind == "image":
        p.update(datasetKey=[INAT_DATASET], basisOfRecord="HUMAN_OBSERVATION",
                 license=["CC0_1_0", "CC_BY_4_0"])
    else:  # audio: Xeno-canto + sonidos de iNaturalist; la licencia se filtra después (XC usa mucho BY-NC-SA)
        p.update(datasetKey=[XC_DATASET, INAT_DATASET])
    return p


def parse_date(v):
    if not v:
        return None, False
    try:
        d = datetime.fromisoformat(v.split("/")[0].replace("Z", "+00:00"))
        return d.replace(tzinfo=None), ("T" in v)
    except ValueError:
        return None, False


def to_rows(o, kind, taxon_key):
    gtype = TYPE_MAP[kind]
    meds = []
    for m in o.get("media", []):
        if m.get("type") != gtype or not m.get("identifier"):
            continue
        lic = normalize_license(m.get("license")) or normalize_license(o.get("license"))
        if not lic:
            continue
        holder = (m.get("rightsHolder") or m.get("creator") or o.get("rightsHolder") or o.get("recordedBy") or "")[:300]
        meds.append((m["identifier"], lic, holder))
    if not meds or o.get("decimalLatitude") is None or o.get("decimalLongitude") is None:
        return None
    dt, has_time = parse_date(o.get("eventDate"))
    iucn = o.get("iucnRedListCategory")
    sensitive = iucn in ("CR", "EN") or bool(o.get("dataGeneralizations")) or bool(o.get("informationWithheld"))
    lat, lon = o["decimalLatitude"], o["decimalLongitude"]
    obs = (f"gbif:{o['key']}", str(o["key"]), o.get("datasetKey"), taxon_key, lat, lon, lon, lat,
           o.get("coordinateUncertaintyInMeters"), o.get("countryCode"), o.get("continent"),
           dt, has_time, observer_hash(o.get("recordedBy") or f"anon-{o['key']}"),
           o.get("basisOfRecord"), iucn, sensitive)
    return obs, meds[:1]


def fetch_taxon(s, kind, taxon_key, per_cont):
    rng, out = random.Random((int(taxon_key) * 31) + (1 if kind == "image" else 2)), []
    for c in CONTINENTS:
        p = base_params(kind, taxon_key, c)
        cnt = s.get(f"{GBIF}/occurrence/search", params={**p, "limit": 0}, timeout=60).json().get("count", 0)
        if not cnt:
            continue
        offset = rng.randint(0, max(0, min(cnt, 100000) - WINDOW))  # GBIF limita offset+limit a 100 000
        recs = s.get(f"{GBIF}/occurrence/search", params={**p, "limit": WINDOW, "offset": offset},
                     timeout=60).json().get("results", [])
        rng.shuffle(recs)
        per_obs, picked = Counter(), 0
        for o in recs:
            who = o.get("recordedBy") or o["key"]
            if per_obs[who] >= MAX_PER_OBSERVER:
                continue
            row = to_rows(o, kind, taxon_key)
            if row:
                out.append(row)
                per_obs[who] += 1
                picked += 1
                if picked >= per_cont:
                    break
    return out


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--media", choices=["image", "audio"], required=True)
    ap.add_argument("--per-continent", type=int, default=None, help="default: 5 imágenes / 2 audios")
    ap.add_argument("--max-taxa", type=int, default=None, help="para pruebas piloto")
    ap.add_argument("--workers", type=int, default=DOWNLOAD_WORKERS)
    a = ap.parse_args()
    per_cont = a.per_continent if a.per_continent is not None else (IMAGE_PER_CONTINENT if a.media == "image" else AUDIO_PER_CONTINENT)
    task = f"occ_{a.media}"
    con, s = connect(), http()
    done = {r[0] for r in con.execute("SELECT key FROM ingest_progress WHERE task=%s", (task,))}
    taxa = [r[0] for r in con.execute("SELECT ds.taxon_key FROM dataset_scope ds ORDER BY ds.taxon_key") if str(r[0]) not in done]
    if a.max_taxa:
        taxa = taxa[:a.max_taxa]
    if not taxa and con.execute("SELECT count(*) FROM dataset_scope").fetchone()[0] == 0:
        raise RuntimeError("No hay especies seleccionadas. Ejecuta primero 02_taxonomy.py.")
    log.info("Especies pendientes (%s): %d; máximo por continente: %d", a.media, len(taxa), per_cont)
    with ThreadPoolExecutor(a.workers) as ex:
        futs = {ex.submit(fetch_taxon, s, a.media, k, per_cont): k for k in taxa}
        for f in tqdm(as_completed(futs), total=len(futs)):
            k = futs[f]
            try:
                items = f.result()
            except Exception as e:
                log.warning("taxon %s falló: %s", k, e)
                continue
            with con.cursor() as cur:
                for obs, meds in items:
                    cur.execute(INS_OBS, obs)
                    cur.executemany(INS_MEDIA, [(obs[0], a.media, *m) for m in meds])
                cur.execute("INSERT INTO ingest_progress (task,key) VALUES (%s,%s) ON CONFLICT DO NOTHING", (task, str(k)))
            con.commit()


if __name__ == "__main__":
    main()
