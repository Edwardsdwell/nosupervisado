"""Selecciona una muestra reproducible de especies de aves (100 por defecto), no toda Aves."""
import argparse, csv, random
from concurrent.futures import ThreadPoolExecutor, as_completed
from tqdm import tqdm
from common import (connect, http, log, GBIF, BACKBONE, MAX_TAXA,
                    SPECIES_SEED, DOWNLOAD_WORKERS, DATA_DIR)

LANGS = {"eng": "en", "spa": "es", "por": "pt", "fra": "fr", "deu": "de"}


def sample_species(s, n, seed):
    params = {"datasetKey": BACKBONE, "highertaxonKey": 212, "rank": "SPECIES",
              "status": "ACCEPTED", "limit": 0}
    r = s.get(f"{GBIF}/species/search", params=params, timeout=90)
    r.raise_for_status()
    total = int(r.json().get("count", 0))
    if total < n:
        raise RuntimeError(f"GBIF devolvió solo {total} especies; se solicitaron {n}.")
    rng = random.Random(seed)
    candidates = {}
    # GBIF limita la paginación por offset; varias ventanas distribuidas evitan tomar las primeras 100.
    max_offset = max(0, min(total - 1000, 99000))
    offsets = [0] if max_offset == 0 else [rng.randint(0, max_offset) for _ in range(12)]
    for off in offsets:
        q = dict(params, limit=1000, offset=off)
        rr = s.get(f"{GBIF}/species/search", params=q, timeout=90)
        rr.raise_for_status()
        for x in rr.json().get("results", []):
            if x.get("key") and x.get("canonicalName"):
                candidates[int(x["key"])] = x
        if len(candidates) >= n * 5:
            break
    vals = list(candidates.values())
    if len(vals) < n:
        raise RuntimeError(f"Solo se pudieron reunir {len(vals)} especies únicas desde GBIF; no se insertó una selección incompleta.")
    chosen = rng.sample(vals, n)
    chosen.sort(key=lambda x: (x.get("family") or "", x.get("canonicalName") or ""))
    return chosen


def fetch_vern(s, key):
    out = set()
    r = s.get(f"{GBIF}/species/{key}/vernacularNames", params={"limit": 300}, timeout=60)
    r.raise_for_status()
    for v in r.json().get("results", []):
        lang, name = LANGS.get(v.get("language")), v.get("vernacularName")
        if lang and name:
            out.add((key, lang, name.strip()[:200], (v.get("source") or "gbif")[:100]))
    return key, out


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--max-taxa", type=int, default=MAX_TAXA)
    ap.add_argument("--seed", type=int, default=SPECIES_SEED)
    ap.add_argument("--skip-vernacular", action="store_true")
    ap.add_argument("--workers", type=int, default=DOWNLOAD_WORKERS)
    ap.add_argument("--reset-selection", action="store_true", help="sustituye la selección; no borra observaciones ni medios")
    a = ap.parse_args()
    if a.max_taxa < 1 or a.max_taxa > 5000:
        ap.error("--max-taxa debe estar entre 1 y 5000")
    con, s = connect(), http()
    existing = con.execute("SELECT count(*) FROM dataset_scope").fetchone()[0]
    if a.reset_selection:
        con.execute("DELETE FROM dataset_scope")
        con.execute("DELETE FROM ingest_progress WHERE task='taxonomy_selection'")
        con.commit()
        existing = 0
    if existing:
        log.info("Se conserva la selección existente de %d especies. Usa --reset-selection para cambiarla.", existing)
    else:
        chosen = sample_species(s, a.max_taxa, a.seed)
        rows = [(int(x["key"]), x.get("scientificName") or x["canonicalName"], x.get("canonicalName"),
                 x.get("genus"), x.get("family"), x.get("order")) for x in chosen]
        with con.cursor() as cur:
            cur.executemany('''INSERT INTO taxa (taxon_key, scientific_name, canonical_name, genus, family, "order")
                               VALUES (%s,%s,%s,%s,%s,%s) ON CONFLICT (taxon_key) DO UPDATE SET
                               scientific_name=EXCLUDED.scientific_name, canonical_name=EXCLUDED.canonical_name,
                               genus=EXCLUDED.genus, family=EXCLUDED.family, "order"=EXCLUDED."order"''', rows)
            cur.executemany("INSERT INTO dataset_scope (taxon_key, selection_seed) VALUES (%s,%s) ON CONFLICT DO NOTHING",
                            [(r[0], a.seed) for r in rows])
        con.commit()
        DATA_DIR.mkdir(parents=True, exist_ok=True)
        with open(DATA_DIR / "species_selection.csv", "w", newline="", encoding="utf-8-sig") as f:
            w = csv.writer(f); w.writerow(["taxon_key", "scientific_name", "family", "order"])
            w.writerows([(x["key"], x.get("canonicalName"), x.get("family"), x.get("order")) for x in chosen])
        log.info("Selección reproducible guardada: %d especies (seed=%d).", len(rows), a.seed)
    if a.skip_vernacular:
        return
    done = {r[0] for r in con.execute("SELECT key FROM ingest_progress WHERE task='vernacular'")}
    todo = [r[0] for r in con.execute("SELECT ds.taxon_key FROM dataset_scope ds ORDER BY ds.taxon_key") if str(r[0]) not in done]
    with ThreadPoolExecutor(max_workers=a.workers) as ex:
        futs = [ex.submit(fetch_vern, s, k) for k in todo]
        for f in tqdm(as_completed(futs), total=len(futs), desc="nombres vernáculos"):
            try: key, names = f.result()
            except Exception as e:
                log.warning("fallo vernáculos: %s", e); continue
            with con.cursor() as cur:
                cur.executemany("""INSERT INTO vernacular_names (taxon_key, language, name, source)
                                   VALUES (%s,%s,%s,%s) ON CONFLICT DO NOTHING""", list(names))
                cur.execute("INSERT INTO ingest_progress (task,key) VALUES ('vernacular',%s) ON CONFLICT DO NOTHING", (str(key),))
            con.commit()

if __name__ == "__main__":
    main()
