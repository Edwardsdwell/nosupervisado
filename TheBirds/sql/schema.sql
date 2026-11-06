CREATE EXTENSION IF NOT EXISTS postgis;

CREATE TABLE IF NOT EXISTS taxa (
  taxon_key BIGINT PRIMARY KEY,              -- GBIF backbone speciesKey
  scientific_name TEXT NOT NULL,
  canonical_name TEXT,
  genus TEXT, family TEXT, "order" TEXT
);
CREATE INDEX IF NOT EXISTS taxa_family_idx ON taxa(family);
CREATE INDEX IF NOT EXISTS taxa_canon_idx ON taxa(canonical_name);

-- Delimita la colección de trabajo: evita que el pipeline procese toda la taxonomía de Aves.
CREATE TABLE IF NOT EXISTS dataset_scope (
  taxon_key BIGINT PRIMARY KEY REFERENCES taxa ON DELETE CASCADE,
  selection_seed BIGINT NOT NULL,
  selected_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE TABLE IF NOT EXISTS vernacular_names (
  taxon_key BIGINT REFERENCES taxa ON DELETE CASCADE,
  language TEXT NOT NULL,                    -- en, es, pt, fr, de
  name TEXT NOT NULL,
  source TEXT,
  PRIMARY KEY (taxon_key, language, name)
);

CREATE TABLE IF NOT EXISTS observations (
  obs_id TEXT PRIMARY KEY,                   -- 'gbif:<occurrenceKey>'
  source TEXT NOT NULL DEFAULT 'gbif',
  source_id TEXT NOT NULL,
  dataset_key TEXT,
  taxon_key BIGINT NOT NULL REFERENCES taxa,
  lat DOUBLE PRECISION, lon DOUBLE PRECISION,
  geog geography(Point,4326),
  coord_uncertainty_m DOUBLE PRECISION,
  country_code TEXT, continent TEXT,
  event_date TIMESTAMP,
  event_has_time BOOLEAN DEFAULT FALSE,
  observer_hash TEXT,
  basis_of_record TEXT,
  iucn_category TEXT,
  sensitive BOOLEAN NOT NULL DEFAULT FALSE,
  split_observer TEXT,                       -- train/val/test por observador
  split_geo TEXT                             -- train/val/test por bloque espacial
);
CREATE INDEX IF NOT EXISTS obs_taxon_idx ON observations(taxon_key);
CREATE INDEX IF NOT EXISTS obs_geog_idx ON observations USING GIST(geog);
CREATE INDEX IF NOT EXISTS obs_date_idx ON observations(event_date);

CREATE TABLE IF NOT EXISTS media (
  media_id BIGSERIAL PRIMARY KEY,
  obs_id TEXT NOT NULL REFERENCES observations ON DELETE CASCADE,
  type TEXT NOT NULL CHECK (type IN ('image','audio')),
  url_original TEXT NOT NULL,
  license TEXT, rights_holder TEXT,
  file_path TEXT,                            -- relativo a DATA_DIR
  sha256 TEXT, bytes BIGINT,
  width INT, height INT, duration_s DOUBLE PRECISION, sample_rate INT,
  download_status TEXT NOT NULL DEFAULT 'pending'
    CHECK (download_status IN ('pending','working','ok','failed','duplicate')),
  attempts INT NOT NULL DEFAULT 0,
  error TEXT,
  UNIQUE (obs_id, url_original)
);
CREATE INDEX IF NOT EXISTS media_status_idx ON media(type, download_status);
CREATE INDEX IF NOT EXISTS media_obs_idx ON media(obs_id);
CREATE UNIQUE INDEX IF NOT EXISTS media_sha_uq ON media(sha256) WHERE download_status='ok';

CREATE TABLE IF NOT EXISTS media_quality (
  media_id BIGINT PRIMARY KEY REFERENCES media ON DELETE CASCADE,
  blur_score DOUBLE PRECISION, brightness DOUBLE PRECISION, contrast DOUBLE PRECISION,
  phash TEXT, dup_of BIGINT,
  snr_proxy_db DOUBLE PRECISION, clip_ratio DOUBLE PRECISION,
  silence_ratio DOUBLE PRECISION, lowfreq_ratio DOUBLE PRECISION,
  flags JSONB,
  computed_at TIMESTAMPTZ DEFAULT now()
);

CREATE TABLE IF NOT EXISTS texts (
  text_id BIGSERIAL PRIMARY KEY,
  taxon_key BIGINT NOT NULL REFERENCES taxa ON DELETE CASCADE,
  source TEXT NOT NULL, language TEXT NOT NULL,
  title TEXT, url TEXT, license TEXT, content TEXT NOT NULL,
  UNIQUE (taxon_key, source, language)
);

CREATE TABLE IF NOT EXISTS pairs (
  pair_id BIGSERIAL PRIMARY KEY,
  image_media_id BIGINT NOT NULL REFERENCES media ON DELETE CASCADE,
  audio_media_id BIGINT NOT NULL REFERENCES media ON DELETE CASCADE,
  taxon_key BIGINT NOT NULL,
  distance_km DOUBLE PRECISION, days_apart DOUBLE PRECISION,
  method TEXT, confidence DOUBLE PRECISION
);
CREATE INDEX IF NOT EXISTS pairs_taxon_idx ON pairs(taxon_key);

CREATE TABLE IF NOT EXISTS env_covariates (
  obs_id TEXT PRIMARY KEY REFERENCES observations ON DELETE CASCADE,
  elevation_m DOUBLE PRECISION,
  bio1_mean_temp_c DOUBLE PRECISION,
  bio4_temp_seasonality DOUBLE PRECISION,
  bio12_annual_precip_mm DOUBLE PRECISION,
  hour_local SMALLINT, day_of_year SMALLINT
);

CREATE TABLE IF NOT EXISTS annotations (
  media_id BIGINT NOT NULL REFERENCES media ON DELETE CASCADE,
  annotator TEXT NOT NULL,
  label TEXT CHECK (label IN ('clean','noise')),
  noise_types TEXT[],
  call_type TEXT,
  notes TEXT,
  created_at TIMESTAMPTZ DEFAULT now(),
  PRIMARY KEY (media_id, annotator)
);

CREATE TABLE IF NOT EXISTS ingest_progress (
  task TEXT NOT NULL, key TEXT NOT NULL,
  done_at TIMESTAMPTZ DEFAULT now(),
  PRIMARY KEY (task, key)
);
