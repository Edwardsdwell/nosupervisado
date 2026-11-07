"""Paso 9: exporta el dataset final a Parquet (metadatos) + manifiesto, y valida integridad.

Salida en <DATA_DIR>/export/: media.parquet, observations.parquet, texts.parquet, pairs.parquet,
taxa.parquet, vernacular_names.parquet, annotations.parquet, manifest.json, ATTRIBUTION.csv.

Privacidad: las observaciones marcadas como sensibles (especies CR/EN o con coordenadas generalizadas)
se exportan con coordenadas redondeadas a 0.1 grado (~11 km). observer_hash ya está anonimizado con sal.
Los archivos de audio/imagen se quedan en DATA_DIR/images y DATA_DIR/audio (rutas relativas en media.file_path).
"""
import argparse, json
from datetime import datetime, timezone
import pandas as pd
from common import connect, log, DATA_DIR

OUT = DATA_DIR / "TheBirds" / "export"
QUERIES = {
    "taxa": "SELECT t.* FROM taxa t JOIN dataset_scope ds USING (taxon_key)",
    "vernacular_names": "SELECT v.* FROM vernacular_names v JOIN dataset_scope ds USING (taxon_key)",
    "observations": """SELECT o.obs_id, o.source, o.source_id, o.dataset_key, o.taxon_key,
        CASE WHEN o.sensitive THEN round(o.lat::numeric,1)::float8 ELSE o.lat END AS lat,
        CASE WHEN o.sensitive THEN round(o.lon::numeric,1)::float8 ELSE o.lon END AS lon,
        o.coord_uncertainty_m, o.country_code, o.continent, o.event_date, o.event_has_time,
        o.observer_hash, o.basis_of_record, o.iucn_category, o.sensitive, o.split_observer, o.split_geo,
        e.elevation_m, e.bio1_mean_temp_c, e.bio4_temp_seasonality, e.bio12_annual_precip_mm,
        e.hour_local, e.day_of_year
        FROM observations o JOIN dataset_scope ds USING (taxon_key) LEFT JOIN env_covariates e USING (obs_id)
        WHERE EXISTS (SELECT 1 FROM media m WHERE m.obs_id=o.obs_id AND m.download_status='ok')""",
    "media": """SELECT m.media_id, m.obs_id, m.type, m.url_original, m.license, m.rights_holder, m.file_path,
        m.sha256, m.bytes, m.width, m.height, m.duration_s, m.sample_rate,
        q.blur_score, q.brightness, q.contrast, q.phash, q.dup_of, q.snr_proxy_db, q.clip_ratio,
        q.silence_ratio, q.lowfreq_ratio, q.flags::text AS flags
        FROM media m JOIN observations o USING (obs_id) JOIN dataset_scope ds USING (taxon_key)
        LEFT JOIN media_quality q USING (media_id) WHERE m.download_status='ok'""",
    "texts": "SELECT t.* FROM texts t JOIN dataset_scope ds USING (taxon_key)",
    "pairs": "SELECT p.* FROM pairs p JOIN dataset_scope ds ON ds.taxon_key=p.taxon_key",
    "annotations": "SELECT a.media_id, a.annotator, a.label, a.noise_types, a.call_type, a.notes, a.created_at FROM annotations a JOIN media m USING (media_id) JOIN observations o USING (obs_id) JOIN dataset_scope ds ON ds.taxon_key=o.taxon_key",
}


def validate(con):
    problems = []
    missing = []
    for mid, rel in con.execute("SELECT media_id, file_path FROM media WHERE download_status='ok'"):
        if not rel or not (DATA_DIR / rel).exists():
            missing.append(mid)
    if missing:
        problems.append(f"{len(missing)} medios 'ok' sin archivo en disco (p.ej. {missing[:5]})")
    n = con.execute("SELECT count(*) FROM media WHERE download_status='ok' AND license IS NULL").fetchone()[0]
    if n:
        problems.append(f"{n} medios sin licencia")
    return problems


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--exclude-nc", action="store_true",
                    help="excluye medios con licencias NC (para uso comercial)")
    ap.add_argument("--skip-validate", action="store_true")
    a = ap.parse_args()
    con = connect()
    OUT.mkdir(parents=True, exist_ok=True)
    if not a.skip_validate:
        for p in validate(con):
            log.warning("VALIDACIÓN: %s", p)
    counts = {}
    for name, q in QUERIES.items():
        cur = con.execute(q)
        df = pd.DataFrame(cur.fetchall(), columns=[c.name for c in cur.description])
        if name == "media" and a.exclude_nc:
            df = df[~df["license"].fillna("").str.contains("NC")]
        counts[name] = len(df)
        df.to_parquet(OUT / f"{name}.parquet", index=False)
        log.info("%s: %d filas", name, len(df))
    media = pd.read_parquet(OUT / "media.parquet")
    media[["media_id", "obs_id", "type", "license", "rights_holder", "url_original"]].to_csv(
        OUT / "ATTRIBUTION.csv", index=False)
    stats = {
        "media_by_type": media["type"].value_counts().to_dict(),
        "bytes_total": int(media["bytes"].fillna(0).sum()),
        "licenses": media["license"].value_counts().to_dict(),
    }
    manifest = {"created_at": datetime.now(timezone.utc).isoformat(), "rows": counts, "stats": stats,
                "exclude_nc": a.exclude_nc,
                "notes": "Cada archivo conserva la licencia de su fuente; ver ATTRIBUTION.csv. "
                         "Texto de Wikipedia: CC-BY-SA-4.0."}
    (OUT / "manifest.json").write_text(json.dumps(manifest, indent=2, ensure_ascii=False))
    log.info("Exportado en %s (%.1f MB de medios)", OUT, stats["bytes_total"] / 2**20)


if __name__ == "__main__":
    main()
