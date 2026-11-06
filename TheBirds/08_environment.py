"""Paso 8: covariables ambientales (WorldClim 2.1, 10 arcmin) + hora y día del año.

Descarga los rasters una sola vez con --download (~cientos de MB). Verifica la URL vigente en worldclim.org.
"""
import argparse, tempfile, zipfile, os, pathlib
import rasterio
from common import connect, http, log, DATA_DIR

WC = DATA_DIR / "worldclim"
BASE = "https://geodata.ucdavis.edu/climate/worldclim/2_1/base"
LAYERS = {"bio1_mean_temp_c": "wc2.1_10m_bio_1.tif", "bio4_temp_seasonality": "wc2.1_10m_bio_4.tif",
          "bio12_annual_precip_mm": "wc2.1_10m_bio_12.tif", "elevation_m": "wc2.1_10m_elev.tif"}


def download():
    WC.mkdir(parents=True, exist_ok=True)
    s = http()
    for zname in ("wc2.1_10m_bio.zip", "wc2.1_10m_elev.zip"):
        log.info("Descargando %s ...", zname)
        with s.get(f"{BASE}/{zname}", stream=True, timeout=(20, 600)) as r:
            r.raise_for_status()
            with tempfile.NamedTemporaryFile(suffix=".zip", delete=False) as tmp:
                for chunk in r.iter_content(1 << 20):
                    if chunk: tmp.write(chunk)
                tmp_path = tmp.name
        try:
            with zipfile.ZipFile(tmp_path) as z:
                for n in z.namelist():
                    if pathlib.PurePosixPath(n).name in LAYERS.values():
                        z.extract(n, WC)
        finally:
            os.unlink(tmp_path)


def sample(src, coords):
    out = []
    for v in src.sample(coords):
        x = float(v[0])
        out.append(None if (src.nodata is not None and x == src.nodata) or x < -1e30 else x)
    return out


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--download", action="store_true")
    ap.add_argument("--batch", type=int, default=1000)
    a = ap.parse_args()
    if a.download:
        download()
    con = connect()
    srcs = {k: rasterio.open(WC / f) for k, f in LAYERS.items()}
    while True:
        rows = con.execute("""SELECT o.obs_id, o.lat, o.lon, o.event_date, o.event_has_time FROM observations o JOIN dataset_scope ds USING (taxon_key)
            WHERE NOT EXISTS (SELECT 1 FROM env_covariates e WHERE e.obs_id=o.obs_id)
              AND EXISTS (SELECT 1 FROM media m WHERE m.obs_id=o.obs_id AND m.download_status='ok')
              AND o.lat IS NOT NULL LIMIT %s""", (a.batch,)).fetchall()
        if not rows:
            break
        coords = [(r[2], r[1]) for r in rows]  # (lon, lat)
        vals = {k: sample(src, coords) for k, src in srcs.items()}
        out = []
        for i, (obs_id, lat, lon, dt, has_time) in enumerate(rows):
            out.append((obs_id, vals["elevation_m"][i], vals["bio1_mean_temp_c"][i],
                        vals["bio4_temp_seasonality"][i], vals["bio12_annual_precip_mm"][i],
                        dt.hour if dt and has_time else None, dt.timetuple().tm_yday if dt else None))
        with con.cursor() as cur:
            cur.executemany("""INSERT INTO env_covariates
                (obs_id, elevation_m, bio1_mean_temp_c, bio4_temp_seasonality, bio12_annual_precip_mm,
                 hour_local, day_of_year)
                VALUES (%s,%s,%s,%s,%s,%s,%s) ON CONFLICT DO NOTHING""", out)
        con.commit()
        log.info("Covariables calculadas: %d", len(out))
    for s in srcs.values():
        s.close()


if __name__ == "__main__":
    main()
