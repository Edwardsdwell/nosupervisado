"""Configuración centralizada (req. 16, 17, 29, 35, 36, 46, 195).

Los valores por defecto viven aquí; se pueden sobrescribir con un archivo `config.toml`
en la raíz del proyecto o con variables de entorno `NS_<CLAVE>` (p. ej. NS_MAX_AUDIO_MB=40).
Todas las rutas son relativas a la raíz del proyecto.
"""
from __future__ import annotations

import os
import tomllib
from dataclasses import dataclass, field, fields
from pathlib import Path

ROOT = Path(__file__).resolve().parent


@dataclass
class Config:
    # --- rutas (relativas a ROOT) ---------------------------------------------------
    store: str = "data_store"
    db: str = "data_store/fauna.db"

    # --- adquisición (req. 29, 33, 35, 36, 173, 193) -------------------------------
    max_audio_mb: int = 80
    max_imagen_mb: int = 25
    max_texto_mb: int = 50
    chunk_bytes: int = 65_536
    pausa_descarga_s: float = 1.0
    reintentos: int = 3
    espera_base_s: float = 2.0            # espera incremental: base * 2**intento
    timeout_s: int = 30
    max_redirecciones: int = 4
    permitir_privadas: bool = False        # solo para pruebas: desactiva el bloqueo de IP privadas
    max_registros_gbif: int = 300          # tamaño de página de GBIF
    max_archivos_carga: int = 500

    # --- audio (req. 44-47) ---------------------------------------------------------
    audio_sr: int = 22_050
    audio_ventana_s: float = 1.0
    audio_salto_s: float = 0.5
    audio_n_mfcc: int = 20
    audio_max_s: int = 300                 # duración máxima decodificada por archivo

    # --- granularidad: qué es «una muestra» ----------------------------------------
    # "fragmentos": parches de imagen / ventanas de audio (muchas muestras por archivo)
    # "archivo":    un vector de descriptores por imagen o por audio (una muestra = un ejemplar)
    img_granularidad: str = "fragmentos"
    audio_granularidad: str = "fragmentos"

    # --- imágenes (req. 48-51) ------------------------------------------------------
    img_lado: int = 256
    img_parche: int = 32
    img_reducido: int = 8

    # --- texto (req. 54, 55) --------------------------------------------------------
    txt_max_terminos: int = 400
    txt_min_len: int = 60
    txt_oraciones: int = 4

    # --- geografía (req. 60) ----------------------------------------------------------
    geo_proyeccion: str = "auto"           # "local" (equirectangular, km) | "esfera" (xyz, km) | "auto" (según la extensión)
    geo_extension_local_deg: float = 8.0   # por encima de esta extensión «auto» pasa a esfera

    # --- preparación y rendimiento (req. 64, 65, 181-186, 190) ----------------------
    max_muestras: int = 3000
    semilla: int = 0
    lote: int = 8                          # archivos procesados por lote
    max_denso_mb: int = 512                # tope al convertir una matriz dispersa a densa
    max_distancias_mb: int = 256           # tope para matrices de distancias (jerárquico): por encima se submuestrea
    max_trabajadores: int = 2
    max_puntos_grafico: int = 20_000

    # --- multimedia (req. 143, 145, 146) --------------------------------------------
    miniatura_px: int = 360
    clip_audio_s: int = 20
    animaciones: bool = True               # fondo animado (req. 155)

    # ------------------------------------------------------------------ rutas
    def ruta(self, rel: str) -> Path:
        if Path(rel).is_absolute():                        # ruta absoluta: decisión explícita del usuario en la configuración
            return Path(rel)
        p = (ROOT / rel).resolve()
        if ROOT not in p.parents and p != ROOT:
            raise ValueError(f"Ruta fuera del proyecto: {rel}")
        return p

    @property
    def store_dir(self) -> Path:
        return self.ruta(self.store)

    @property
    def db_path(self) -> Path:
        return self.ruta(self.db)

    def subdir(self, *partes: str) -> Path:
        d = self.store_dir.joinpath(*partes)
        d.mkdir(parents=True, exist_ok=True)
        return d


def cargar_config(archivo: str | Path | None = None) -> Config:
    cfg = Config()
    ruta = Path(archivo) if archivo else ROOT / "config.toml"
    if ruta.is_file():
        datos = tomllib.loads(ruta.read_text(encoding="utf-8"))
        for f in fields(Config):
            if f.name in datos:
                setattr(cfg, f.name, type(getattr(cfg, f.name))(datos[f.name]))
    for f in fields(Config):
        env = os.environ.get(f"NS_{f.name.upper()}")
        if env is not None:
            actual = getattr(cfg, f.name)
            setattr(cfg, f.name, (env.lower() in ("1", "true", "si", "sí")) if isinstance(actual, bool) else type(actual)(env))
    return cfg


def secreto(nombre: str, defecto: str | None = None) -> str | None:
    """Claves API y tokens: solo desde variables de entorno o `.env` (req. 195), nunca en el código."""
    if nombre in os.environ:
        return os.environ[nombre]
    env = ROOT / ".env"
    if env.is_file():
        for linea in env.read_text(encoding="utf-8").splitlines():
            if "=" in linea and not linea.lstrip().startswith("#"):
                k, v = linea.split("=", 1)
                if k.strip() == nombre:
                    return v.strip().strip("'\"")
    return defecto


CFG = cargar_config()
