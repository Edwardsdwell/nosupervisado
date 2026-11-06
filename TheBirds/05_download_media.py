"""Descarga comprimida y reanudable con presupuesto global de almacenamiento."""
import argparse, io, os, subprocess, tempfile, pathlib
from concurrent.futures import ThreadPoolExecutor
import psycopg, soundfile as sf
from PIL import Image, ImageOps
from common import (connect, http, log, sha256_file, DATA_DIR, IMG_MAX_SIDE,
                    WEBP_QUALITY, AUDIO_MAX_SECONDS, AUDIO_FORMAT, AUDIO_BITRATE,
                    MAX_MEDIA_GB, DOWNLOAD_WORKERS, DOWNLOAD_BATCH)

S = http(8)
MAX_IMG_BYTES, MAX_AUDIO_BYTES = 15 * 2**20, 30 * 2**20
CLAIM = """
WITH c AS (SELECT media_id FROM media WHERE download_status='pending' AND type=%s AND attempts<3
           ORDER BY media_id LIMIT %s FOR UPDATE SKIP LOCKED)
UPDATE media m SET download_status='working', attempts=m.attempts+1 FROM c WHERE m.media_id=c.media_id
RETURNING m.media_id, m.url_original, (SELECT taxon_key FROM observations o WHERE o.obs_id=m.obs_id)
"""

def get_bytes(url, limit):
    import io
    buf, n = io.BytesIO(), 0
    with S.get(url, stream=True, timeout=(10, 60)) as r:
        r.raise_for_status()
        cl = r.headers.get("Content-Length")
        if cl and int(cl) > limit: raise ValueError("archivo de origen supera el límite")
        for ch in r.iter_content(1 << 16):
            if not ch: continue
            n += len(ch)
            if n > limit: raise ValueError("archivo de origen supera el límite")
            buf.write(ch)
    buf.seek(0)
    return buf

def do_image(media_id, url, taxon):
    urls = [url]
    if "inaturalist-open-data" in url and "/original." in url:
        urls = [url.replace("/original.", "/medium."), url.replace("/original.", "/large."), url]
    buf, last = None, None
    for u in urls:
        try: buf = get_bytes(u, MAX_IMG_BYTES); break
        except Exception as e: last = e
    if buf is None: raise last
    with Image.open(buf) as source:
        im = ImageOps.exif_transpose(source).convert("RGB")
        im.thumbnail((IMG_MAX_SIDE, IMG_MAX_SIDE), Image.Resampling.LANCZOS)
        rel = f"images/{taxon}/{media_id}.webp"
        path = DATA_DIR / rel
        path.parent.mkdir(parents=True, exist_ok=True)
        im.save(path, "WEBP", quality=WEBP_QUALITY, method=6)
    return dict(file_path=rel, sha=sha256_file(path), bytes=path.stat().st_size,
                width=im.width, height=im.height, duration=None, sr=None)

def do_audio(media_id, url, taxon):
    ext = pathlib.Path(url.split("?")[0]).suffix or ".bin"
    tmp = tempfile.NamedTemporaryFile(suffix=ext, delete=False)
    out_path = None
    try:
        n = 0
        with S.get(url, stream=True, timeout=(10, 60)) as r:
            r.raise_for_status()
            cl = r.headers.get("Content-Length")
            if cl and int(cl) > MAX_AUDIO_BYTES: raise ValueError("audio de origen supera el límite")
            for ch in r.iter_content(1 << 16):
                if not ch: continue
                n += len(ch)
                if n > MAX_AUDIO_BYTES: raise ValueError("audio de origen supera el límite")
                tmp.write(ch)
        tmp.close()
        if AUDIO_FORMAT not in ("ogg", "flac"): raise ValueError("AUDIO_FORMAT debe ser ogg o flac")
        out_ext = AUDIO_FORMAT
        rel = f"audio/{taxon}/{media_id}.{out_ext}"
        out_path = DATA_DIR / rel
        out_path.parent.mkdir(parents=True, exist_ok=True)
        cmd = ["ffmpeg", "-nostdin", "-y", "-v", "error", "-i", tmp.name, "-t", str(AUDIO_MAX_SECONDS),
               "-vn", "-ac", "1", "-ar", "32000"]
        cmd += ["-c:a", "libvorbis", "-b:a", AUDIO_BITRATE] if out_ext == "ogg" else ["-c:a", "flac", "-compression_level", "5"]
        subprocess.run(cmd + [str(out_path)], check=True, capture_output=True, timeout=240)
        info = sf.info(str(out_path))
        return dict(file_path=rel, sha=sha256_file(out_path), bytes=out_path.stat().st_size,
                    width=None, height=None, duration=info.duration, sr=info.samplerate)
    except Exception:
        if out_path: out_path.unlink(missing_ok=True)
        raise
    finally:
        try: os.unlink(tmp.name)
        except FileNotFoundError: pass

def work(args):
    kind, media_id, url, taxon = args
    try: return media_id, (do_image if kind == "image" else do_audio)(media_id, url, taxon), None
    except Exception as e: return media_id, None, str(e)[:300]

def disk_media_bytes():
    total = 0
    for folder in (DATA_DIR / "images", DATA_DIR / "audio"):
        if folder.exists():
            total += sum(p.stat().st_size for p in folder.rglob("*") if p.is_file())
    return total

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--type", choices=["image", "audio"], required=True)
    ap.add_argument("--workers", type=int, default=DOWNLOAD_WORKERS)
    ap.add_argument("--batch", type=int, default=DOWNLOAD_BATCH)
    ap.add_argument("--max-items", type=int, default=None, help="máximo de medios procesados correctamente en esta ejecución")
    ap.add_argument("--max-total-gb", type=float, default=MAX_MEDIA_GB, help="presupuesto total de medios comprimidos")
    a = ap.parse_args()
    if a.max_total_gb <= 0 or a.workers < 1 or a.batch < 1: ap.error("presupuesto, workers y batch deben ser positivos")
    con = connect()
    # Un cierre abrupto no deja trabajos bloqueados para siempre.
    con.execute("UPDATE media SET download_status='pending' WHERE download_status='working'")
    con.execute("UPDATE media SET download_status='pending', error=NULL WHERE error='storage_budget_reached' AND download_status='failed'")
    con.commit()
    budget = int(a.max_total_gb * 1024**3)
    used = max(int(con.execute("SELECT COALESCE(sum(bytes),0) FROM media WHERE download_status='ok'").fetchone()[0]), disk_media_bytes())
    log.info("Almacenamiento multimedia: %.1f / %.1f GB", used/1024**3, a.max_total_gb)
    completed = 0
    stop = used >= budget
    with ThreadPoolExecutor(max_workers=a.workers) as ex:
        while not stop:
            if a.max_items is not None and completed >= a.max_items: break
            take = min(a.batch, a.max_items-completed) if a.max_items is not None else a.batch
            rows = con.execute(CLAIM, (a.type, take)).fetchall()
            con.commit()
            if not rows: break
            results = list(ex.map(work, [(a.type, *r) for r in rows]))
            for idx, (media_id, res, err) in enumerate(results):
                if err:
                    con.execute("""UPDATE media SET error=%s,
                        download_status=CASE WHEN attempts>=3 THEN 'failed' ELSE 'pending' END WHERE media_id=%s""", (err, media_id))
                elif stop or used + int(res["bytes"]) > budget:
                    (DATA_DIR / res["file_path"]).unlink(missing_ok=True)
                    con.execute("UPDATE media SET download_status='pending', error='storage_budget_reached' WHERE media_id=%s", (media_id,))
                    stop = True
                else:
                    try:
                        con.execute("""UPDATE media SET download_status='ok', file_path=%s, sha256=%s, bytes=%s,
                            width=%s, height=%s, duration_s=%s, sample_rate=%s, error=NULL WHERE media_id=%s""",
                            (res["file_path"], res["sha"], res["bytes"], res["width"], res["height"], res["duration"], res["sr"], media_id))
                        con.commit()
                        used += int(res["bytes"]); completed += 1
                    except psycopg.errors.UniqueViolation:
                        con.rollback()
                        (DATA_DIR / res["file_path"]).unlink(missing_ok=True)
                        con.execute("UPDATE media SET download_status='duplicate', sha256=NULL, error=NULL WHERE media_id=%s", (media_id,))
                con.commit()
            if stop:
                # El resto del lote ya fue marcado working; se devuelve a pending para una ejecución futura.
                con.execute("UPDATE media SET download_status='pending' WHERE type=%s AND download_status='working'", (a.type,))
                con.commit()
                break
            log.info("Correctos en esta ejecución: %d; total comprimido: %.1f MB", completed, used/2**20)
    log.info("Fin. Correctos nuevos: %d; almacenamiento multimedia: %.1f / %.1f GB", completed, used/1024**3, a.max_total_gb)

if __name__ == "__main__":
    main()
