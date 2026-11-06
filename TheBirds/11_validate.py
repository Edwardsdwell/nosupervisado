"""Validación final de PostgreSQL 18, alcance de 100 especies, archivos y límites."""
import json, sys
from common import (connect, DATA_DIR, MAX_MEDIA_GB, MAX_TAXA, IMG_MAX_SIDE, AUDIO_MAX_SECONDS,
                    IMAGE_PER_CONTINENT, AUDIO_PER_CONTINENT)

def main():
    errors, warnings, stats = [], [], {}
    with connect() as con:
        ver, db, user = con.execute("SELECT current_setting('server_version_num')::int, current_database(), current_user").fetchone()
        major = ver // 10000
        stats.update(postgresql_major=major, database=db, user=user)
        stats["database_size_bytes"] = int(con.execute("SELECT pg_database_size(current_database())").fetchone()[0])
        if major != 18: errors.append(f"Servidor PostgreSQL {major}; se requiere 18")
        try: stats["postgis"] = con.execute("SELECT PostGIS_Full_Version()").fetchone()[0]
        except Exception: errors.append("PostGIS no está habilitado o no está instalado")
        stats["selected_species"] = con.execute("SELECT count(*) FROM dataset_scope").fetchone()[0]
        if stats["selected_species"] != MAX_TAXA: warnings.append(f"La selección tiene {stats['selected_species']} especies; objetivo configurado: {MAX_TAXA}")
        stats["observations"] = con.execute("SELECT count(*) FROM observations").fetchone()[0]
        stats["media_rows"] = con.execute("SELECT count(*) FROM media").fetchone()[0]
        stats["media_ok"] = con.execute("SELECT count(*) FROM media WHERE download_status='ok'").fetchone()[0]
        stats["media_bytes_db"] = int(con.execute("SELECT COALESCE(sum(bytes),0) FROM media WHERE download_status='ok'").fetchone()[0])
        stats["media_gb_db"] = round(stats["media_bytes_db"] / 1024**3, 4)
        if stats["media_bytes_db"] > MAX_MEDIA_GB * 1024**3: errors.append("El total de medios en BD supera MAX_MEDIA_GB")
        disk_bytes = 0
        for folder in (DATA_DIR / "images", DATA_DIR / "audio"):
            if folder.exists(): disk_bytes += sum(p.stat().st_size for p in folder.rglob("*") if p.is_file())
        stats["media_bytes_disk"] = disk_bytes
        if disk_bytes > MAX_MEDIA_GB * 1024**3: errors.append("Los archivos multimedia en disco superan MAX_MEDIA_GB")
        stats["missing_files"] = 0
        for rel, in con.execute("SELECT file_path FROM media WHERE download_status='ok'"):
            if not rel or not (DATA_DIR / rel).is_file(): stats["missing_files"] += 1
        if stats["missing_files"]: errors.append(f"Hay {stats['missing_files']} medios marcados ok sin archivo")
        stats["images_over_limit"] = con.execute("SELECT count(*) FROM media WHERE type='image' AND download_status='ok' AND (width>%s OR height>%s)", (IMG_MAX_SIDE, IMG_MAX_SIDE)).fetchone()[0]
        if stats["images_over_limit"]: errors.append("Hay imágenes que superan IMG_MAX_SIDE")
        stats["audio_over_limit"] = con.execute("SELECT count(*) FROM media WHERE type='audio' AND download_status='ok' AND (duration_s>%s OR sample_rate IS DISTINCT FROM 32000)", (AUDIO_MAX_SECONDS + 0.15, 32000)).fetchone()[0]
        if stats["audio_over_limit"]: errors.append("Hay audios fuera del límite de duración o frecuencia")
        stats["max_images_per_species_continent"] = con.execute("""SELECT COALESCE(max(n),0) FROM (
            SELECT count(*) n FROM media m JOIN observations o USING (obs_id)
            JOIN dataset_scope ds USING (taxon_key) WHERE m.type='image' AND m.download_status='ok'
            GROUP BY o.taxon_key, o.continent) x""").fetchone()[0]
        stats["max_audio_per_species_continent"] = con.execute("""SELECT COALESCE(max(n),0) FROM (
            SELECT count(*) n FROM media m JOIN observations o USING (obs_id)
            JOIN dataset_scope ds USING (taxon_key) WHERE m.type='audio' AND m.download_status='ok'
            GROUP BY o.taxon_key, o.continent) x""").fetchone()[0]
        if stats["max_images_per_species_continent"] > IMAGE_PER_CONTINENT: errors.append("Se excedió el muestreo de imágenes por especie/continente")
        if stats["max_audio_per_species_continent"] > AUDIO_PER_CONTINENT: errors.append("Se excedió el muestreo de audio por especie/continente")
        stats["missing_license"] = con.execute("SELECT count(*) FROM media WHERE download_status='ok' AND (license IS NULL OR btrim(license)='')").fetchone()[0]
        if stats["missing_license"]: errors.append("Hay medios descargados sin licencia")
        stats["duplicate_sha"] = con.execute("SELECT count(*) FROM (SELECT sha256 FROM media WHERE download_status='ok' AND sha256 IS NOT NULL GROUP BY sha256 HAVING count(*)>1) x").fetchone()[0]
        if stats["media_ok"] == 0: warnings.append("Todavía no hay archivos multimedia descargados")
    report = {"ok": not errors, "errors": errors, "warnings": warnings, "stats": stats}
    out = DATA_DIR / "validation_report.json"
    out.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps(report, ensure_ascii=False, indent=2))
    print(f"\nInforme: {out}")
    if errors: sys.exit(1)

if __name__ == "__main__": main()
