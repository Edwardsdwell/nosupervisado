"""Paso 6: métricas de calidad/ruido por medio + casi-duplicados (phash).

Las banderas (flags) son heurísticas con umbrales ajustables: sirven como etiquetas débiles de ruido;
valídalas con tus anotaciones manuales (paso 9).
"""
import argparse
from concurrent.futures import ThreadPoolExecutor
import numpy as np, cv2, imagehash, soundfile as sf
from PIL import Image
from psycopg.types.json import Jsonb
from tqdm import tqdm
from common import connect, log, DATA_DIR


def img_metrics(path, w, h):
    g = cv2.imread(str(path), cv2.IMREAD_GRAYSCALE)
    if g is None:  # OpenCV puede no leer WebP en algunas compilaciones
        with Image.open(path) as im:
            g = np.array(im.convert("L"))
    blur = float(cv2.Laplacian(g, cv2.CV_64F).var())
    bright, contrast = float(g.mean()), float(g.std())
    with Image.open(path) as im:
        ph = str(imagehash.phash(im))
    flags = {"blurry": blur < 50, "dark": bright < 40, "overexposed": bright > 220,
             "low_contrast": contrast < 20, "small": min(w or 0, h or 0) < 200}
    return dict(blur_score=blur, brightness=bright, contrast=contrast, phash=ph), flags


def audio_metrics(path):
    x, sr = sf.read(str(path), dtype="float32", always_2d=False)
    if x.ndim > 1:
        x = x.mean(1)
    frame, hop = 2048, 1024
    n = (len(x) - frame) // hop + 1
    if n < 3:
        return {}, {"too_short": True}
    idx = np.arange(frame)[None, :] + hop * np.arange(n)[:, None]
    db = 20 * np.log10(np.sqrt((x[idx] ** 2).mean(1)) + 1e-9)
    snr = float(np.percentile(db, 90) - np.percentile(db, 10))   # proxy, no es un SNR real
    silence = float((db < -60).mean())
    clip = float((np.abs(x) >= 0.999).mean())
    spec = np.abs(np.fft.rfft(x)) ** 2
    low = float(spec[np.fft.rfftfreq(len(x), 1 / sr) < 300].sum() / (spec.sum() + 1e-12))
    flags = {"low_dynamic_range": snr < 6, "clipped": clip > 0.01,
             "wind_like": low > 0.5, "mostly_silent": silence > 0.8}
    return dict(snr_proxy_db=snr, clip_ratio=clip, silence_ratio=silence, lowfreq_ratio=low), flags


def work(row):
    media_id, typ, rel, w, h = row
    try:
        path = DATA_DIR / rel
        m, f = img_metrics(path, w, h) if typ == "image" else audio_metrics(path)
        return media_id, m, f, None
    except Exception as e:
        return media_id, None, None, str(e)


COLS = ["blur_score", "brightness", "contrast", "phash", "snr_proxy_db", "clip_ratio", "silence_ratio", "lowfreq_ratio"]


def mark_duplicates(con, hamming=4):
    rows = con.execute("""SELECT o.taxon_key, q.media_id, q.phash FROM media_quality q
        JOIN media m USING (media_id) JOIN observations o ON o.obs_id=m.obs_id
        WHERE m.type='image' AND m.download_status='ok' AND q.phash IS NOT NULL
          AND EXISTS (SELECT 1 FROM dataset_scope ds WHERE ds.taxon_key=o.taxon_key)
        ORDER BY o.taxon_key, q.media_id""").fetchall()
    groups = {}
    for k, mid, ph in rows:
        groups.setdefault(k, []).append((mid, int(ph, 16)))
    n = 0
    for items in groups.values():
        ids = [i for i, _ in items]
        vals = np.array([v for _, v in items], dtype=np.uint64)
        seen = set()
        for i in range(len(ids)):
            if ids[i] in seen:
                continue
            xor = vals[i + 1:] ^ vals[i]
            hd = np.unpackbits(xor.view(np.uint8)).reshape(-1, 64).sum(1) if len(xor) else []
            for j, d in enumerate(hd):
                if d <= hamming and ids[i + 1 + j] not in seen:
                    seen.add(ids[i + 1 + j])
                    con.execute("UPDATE media_quality SET dup_of=%s WHERE media_id=%s", (ids[i], ids[i + 1 + j]))
                    n += 1
    con.commit()
    log.info("Casi-duplicados marcados: %d", n)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--workers", type=int, default=4)
    a = ap.parse_args()
    con = connect()
    rows = con.execute("""SELECT m.media_id, m.type, m.file_path, m.width, m.height FROM media m
        LEFT JOIN media_quality q USING (media_id)
        WHERE m.download_status='ok' AND q.media_id IS NULL
          AND EXISTS (SELECT 1 FROM observations o JOIN dataset_scope ds USING (taxon_key) WHERE o.obs_id=m.obs_id)""").fetchall()
    log.info("Medios por evaluar: %d", len(rows))
    with ThreadPoolExecutor(a.workers) as ex:
        for media_id, m, f, err in tqdm(ex.map(work, rows), total=len(rows)):
            if err:
                con.execute("INSERT INTO media_quality (media_id, flags) VALUES (%s,%s) ON CONFLICT DO NOTHING",
                            (media_id, Jsonb({"unreadable": True, "error": err[:200]})))
            else:
                vals = [m.get(c) for c in COLS]
                con.execute(f"""INSERT INTO media_quality (media_id, {','.join(COLS)}, flags)
                                VALUES (%s,{','.join(['%s'] * len(COLS))},%s) ON CONFLICT DO NOTHING""",
                            (media_id, *vals, Jsonb(f)))
            con.commit()
    mark_duplicates(con)


if __name__ == "__main__":
    main()
