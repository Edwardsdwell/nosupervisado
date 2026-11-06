"""Configuración compartida. Rutas relativas al proyecto, no al directorio de ejecución."""
import os, re, hashlib, pathlib, logging
import psycopg, requests
from dotenv import load_dotenv
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry

BASE_DIR = pathlib.Path(__file__).resolve().parent
load_dotenv(BASE_DIR / ".env", override=True)

DATABASE_URL = os.getenv("DATABASE_URL", "").strip()
if not DATABASE_URL:
    raise RuntimeError("Falta DATABASE_URL en .env; configura el PostgreSQL 18 nativo.")

DATA_DIR_RAW = pathlib.Path(os.getenv("DATA_DIR", "./data"))
DATA_DIR = (DATA_DIR_RAW if DATA_DIR_RAW.is_absolute() else BASE_DIR / DATA_DIR_RAW).resolve()
DATA_DIR.mkdir(parents=True, exist_ok=True)

USER_AGENT = os.getenv("USER_AGENT", "").strip()
if not USER_AGENT or "ejemplo.com" in USER_AGENT or "tu-correo" in USER_AGENT:
    raise RuntimeError("Configura USER_AGENT en .env con un contacto real antes de descargar datos.")
OBSERVER_SALT = os.getenv("OBSERVER_SALT", "").strip()
if len(OBSERVER_SALT) < 24 or "cambia" in OBSERVER_SALT.lower():
    raise RuntimeError("Configura OBSERVER_SALT en .env con una cadena aleatoria de al menos 24 caracteres.")

IMG_MAX_SIDE = int(os.getenv("IMG_MAX_SIDE", "512"))
WEBP_QUALITY = int(os.getenv("WEBP_QUALITY", "82"))
AUDIO_MAX_SECONDS = int(os.getenv("AUDIO_MAX_SECONDS", "30"))
AUDIO_FORMAT = os.getenv("AUDIO_FORMAT", "ogg").lower()
AUDIO_BITRATE = os.getenv("AUDIO_BITRATE", "48k")
MAX_MEDIA_GB = float(os.getenv("MAX_MEDIA_GB", "1.5"))
MAX_TAXA = int(os.getenv("MAX_TAXA", "100"))
SPECIES_SEED = int(os.getenv("SPECIES_SEED", "20261106"))
IMAGE_PER_CONTINENT = int(os.getenv("IMAGE_PER_CONTINENT", "2"))
AUDIO_PER_CONTINENT = int(os.getenv("AUDIO_PER_CONTINENT", "1"))
DOWNLOAD_WORKERS = int(os.getenv("DOWNLOAD_WORKERS", "4"))
DOWNLOAD_BATCH = int(os.getenv("DOWNLOAD_BATCH", "20"))

GBIF = "https://api.gbif.org/v1"
BACKBONE = "d7dddbf4-2cf0-4f39-9b2a-bb099caae36c"
INAT_DATASET = "50c9509d-22c7-4a22-a47d-8c48425ef4a7"
XC_DATASET = "b1047888-ae52-4179-9dd5-5448ea342a24"

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
log = logging.getLogger("aves")


def connect(autocommit=False):
    return psycopg.connect(DATABASE_URL, autocommit=autocommit, connect_timeout=10)


def http(pool=4):
    s = requests.Session()
    s.headers["User-Agent"] = USER_AGENT
    retry = Retry(total=5, backoff_factor=1.0, status_forcelist=(429, 500, 502, 503, 504),
                  allowed_methods=("GET", "HEAD"), respect_retry_after_header=True)
    ad = HTTPAdapter(max_retries=retry, pool_connections=pool, pool_maxsize=pool)
    s.mount("https://", ad)
    s.mount("http://", ad)
    return s


def observer_hash(name: str) -> str:
    return hashlib.sha256((OBSERVER_SALT + name).encode("utf-8")).hexdigest()[:16]


def normalize_license(v):
    if not v:
        return None
    low = str(v).strip().lower()
    if "publicdomain/zero" in low or low in ("cc0_1_0", "cc0", "cc0-1.0"):
        return "CC0-1.0"
    m = re.search(r"licenses/([a-z\-]+)/([0-9]+\.[0-9]+)", low)
    if m:
        return f"CC-{m.group(1).upper()}-{m.group(2)}"
    m = re.match(r"cc_([a-z_]+?)_([0-9]+_[0-9]+)$", low)
    if m:
        return f"CC-{m.group(1).upper().replace('_', '-')}-{m.group(2).replace('_', '.')}"
    return None


def sha256_file(path) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()
