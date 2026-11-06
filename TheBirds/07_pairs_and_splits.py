"""Paso 7: pares imagen<->audio (pseudo-observaciones) y particiones sin fuga (por observador y por bloque geográfico)."""
import argparse
from common import connect, log

SAME_OBS = """
INSERT INTO pairs (image_media_id, audio_media_id, taxon_key, distance_km, days_apart, method, confidence)
SELECT i.media_id, a.media_id, oa.taxon_key, 0, 0, 'same_observation', 1.0
FROM media a JOIN media i ON i.obs_id=a.obs_id AND i.type='image' AND i.download_status='ok'
JOIN observations oa ON oa.obs_id=a.obs_id
JOIN dataset_scope ds ON ds.taxon_key=oa.taxon_key
WHERE a.type='audio' AND a.download_status='ok'"""

SPATIOTEMPORAL = """
INSERT INTO pairs (image_media_id, audio_media_id, taxon_key, distance_km, days_apart, method, confidence)
SELECT DISTINCT ON (a.media_id)
  i.media_id, a.media_id, oa.taxon_key,
  ST_Distance(oi.geog, oa.geog)/1000.0,
  abs(extract(epoch FROM (oi.event_date - oa.event_date)))/86400.0,
  'spatiotemporal',
  0.8*GREATEST(0, 1 - 0.5*ST_Distance(oi.geog, oa.geog)/%(r)s
                    - 0.5*abs(extract(epoch FROM (oi.event_date - oa.event_date)))/86400.0/%(d)s)
FROM media a
JOIN observations oa ON oa.obs_id=a.obs_id
JOIN dataset_scope ds ON ds.taxon_key=oa.taxon_key
JOIN observations oi ON oi.taxon_key=oa.taxon_key AND oi.obs_id<>oa.obs_id
  AND ST_DWithin(oi.geog, oa.geog, %(r)s)
  AND oi.event_date BETWEEN oa.event_date - make_interval(days => %(d)s)
                        AND oa.event_date + make_interval(days => %(d)s)
JOIN media i ON i.obs_id=oi.obs_id AND i.type='image' AND i.download_status='ok'
WHERE a.type='audio' AND a.download_status='ok'
  AND oa.event_date IS NOT NULL AND oi.event_date IS NOT NULL
  AND NOT EXISTS (SELECT 1 FROM pairs p WHERE p.audio_media_id=a.media_id)
ORDER BY a.media_id, ST_Distance(oi.geog, oa.geog),
         abs(extract(epoch FROM (oi.event_date - oa.event_date)))"""

SPLIT_OBS = """UPDATE observations SET split_observer = CASE
  WHEN (hashtext(coalesce(observer_hash, obs_id))::bigint & 2147483647) % 100 < 80 THEN 'train'
  WHEN (hashtext(coalesce(observer_hash, obs_id))::bigint & 2147483647) % 100 < 90 THEN 'val'
  ELSE 'test' END WHERE taxon_key IN (SELECT taxon_key FROM dataset_scope)"""

SPLIT_GEO = """UPDATE observations SET split_geo = CASE
  WHEN (hashtext(floor(lat/5)::text || ':' || floor(lon/5)::text)::bigint & 2147483647) % 100 < 80 THEN 'train'
  WHEN (hashtext(floor(lat/5)::text || ':' || floor(lon/5)::text)::bigint & 2147483647) % 100 < 90 THEN 'val'
  ELSE 'test' END WHERE lat IS NOT NULL AND lon IS NOT NULL
  AND taxon_key IN (SELECT taxon_key FROM dataset_scope)"""



def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--radius-km", type=float, default=5)
    ap.add_argument("--days", type=int, default=7)
    a = ap.parse_args()
    con = connect()
    con.execute("TRUNCATE pairs RESTART IDENTITY")
    con.execute(SAME_OBS)
    con.execute(SPATIOTEMPORAL, {"r": a.radius_km * 1000.0, "d": a.days})
    n = con.execute("SELECT method, count(*) FROM pairs GROUP BY method").fetchall()
    log.info("Pares: %s", n)
    con.execute(SPLIT_OBS)
    con.execute(SPLIT_GEO)
    con.commit()
    log.info("Particiones asignadas (split_observer, split_geo).")


if __name__ == "__main__":
    main()
