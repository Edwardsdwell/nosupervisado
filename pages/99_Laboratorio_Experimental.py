# ============================================================
# LABORATORIO EXPERIMENTAL DE BIODIVERSIDAD  ·  v2
# Bioacústica | Visión por computador | NLP | Geoespacial
# ------------------------------------------------------------
# Requisitos base : streamlit numpy pandas scipy plotly pillow
# Opcionales      : soundfile librosa noisereduce rembg
#                   scikit-learn spacy (+ es_core_news_sm)
# Ejecutar        : streamlit run laboratorio_biodiversidad.py
# ============================================================

import html
import io
import re
import unicodedata
import warnings
import wave
from collections import Counter
from datetime import datetime
from pathlib import Path

import numpy as np
import pandas as pd
import plotly.express as px
import plotly.graph_objects as go
import streamlit as st
from PIL import Image, ImageDraw, ImageEnhance, ImageFilter, ImageOps
from scipy import ndimage, signal

warnings.filterwarnings("ignore")

# ============================================================
# 1. CONFIGURACIÓN Y PALETA
# ============================================================

st.set_page_config(
    page_title="Laboratorio Experimental | Biodiversidad",
    page_icon="🌿",
    layout="wide",
)

for _k, _v in {
    "theme.base": "light",
    "theme.primaryColor": "#16806A",
    "theme.backgroundColor": "#F3F7F4",
    "theme.secondaryBackgroundColor": "#E9F2EC",
    "theme.textColor": "#1B2B22",
}.items():
    try:
        st._config.set_option(_k, _v)
    except Exception:
        pass

# Regla de contraste: texto SIEMPRE oscuro sobre superficies claras
# y texto SIEMPRE claro sobre superficies oscuras (barra lateral, hero).
PALETA = {
    "fondo": "#F3F7F4",
    "superficie": "#FFFFFF",
    "superficie_alt": "#E9F2EC",
    "borde": "#C5D5CB",
    "texto": "#1B2B22",
    "texto_suave": "#46594D",
    "oscuro": "#14281F",
    "bosque": "#2F5D46",
    "verde": "#3F7D5C",
    "oliva": "#8A9A5B",
    "aguamarina": "#7FFFD4",
    "aqua_medio": "#3CCFA5",
    "aqua_profundo": "#16806A",
    "ocre": "#B08A3E",
    "marron": "#5A4126",
    "azul": "#5B84A8",
}

SECUENCIA = [
    PALETA["bosque"], PALETA["aqua_medio"], PALETA["ocre"],
    PALETA["azul"], PALETA["oliva"], PALETA["aqua_profundo"],
    PALETA["marron"], "#6FA287", "#C7A15A", "#2D8FA3",
]

ESCALA_ESPECTRO = [
    [0.0, "#0B1A14"], [0.35, "#1F5C4A"], [0.65, "#3CCFA5"], [1.0, "#E6FFF6"]
]
ESCALA_BOSQUE = [[0.0, "#0B1A14"], [0.5, "#3F7D5C"], [1.0, "#F1FBF5"]]
ESCALA_DENSIDAD = [[0.0, "#EAF3EE"], [0.5, "#7FFFD4"], [1.0, "#14463A"]]
ESCALA_TREEMAP = [[0.0, "#E6FFF6"], [0.5, "#7FFFD4"], [1.0, "#3CCFA5"]]

ESCALAS_ESPECTRO = {
    "Aguamarina": ESCALA_ESPECTRO,
    "Bosque": ESCALA_BOSQUE,
    "Tierra": "Earth",
    "Viridis": "Viridis",
}

_raiz = ":root{" + "".join(
    f"--{k.replace('_', '-')}:{v};" for k, v in PALETA.items()
) + "}"

CSS = """
:root { color-scheme: light; }
.stApp {
    background: linear-gradient(180deg, var(--fondo) 0%, #E4EFE9 100%);
    color: var(--texto);
}
header[data-testid="stHeader"] { background: transparent; }
.block-container { padding-top: 1.6rem; max-width: 1280px; }

h1, h2, h3, h4, h5 { color: var(--oscuro) !important; letter-spacing: -0.01em; }
h2 { border-bottom: 3px solid var(--aguamarina); display: inline-block; padding-bottom: .25rem; }
[data-testid="stMarkdownContainer"] p,
[data-testid="stMarkdownContainer"] li { color: var(--texto); }
[data-testid="stCaptionContainer"],
[data-testid="stCaptionContainer"] * { color: var(--texto-suave) !important; }
label, label p, [data-testid="stWidgetLabel"], [data-testid="stWidgetLabel"] p {
    color: var(--texto) !important; font-weight: 500;
}
::selection { background: var(--aguamarina); color: var(--oscuro); }

/* ---------- Hero ---------- */
.hero {
    background: linear-gradient(120deg, var(--oscuro) 0%, var(--bosque) 60%, var(--aqua-profundo) 100%);
    border-radius: 16px; padding: 1.6rem 2rem; margin-bottom: 1rem;
    border-left: 8px solid var(--aguamarina);
    box-shadow: 0 8px 24px rgba(20,40,31,.18);
}
.hero-title { color: #E6FFF6; font-size: 2rem; font-weight: 700; line-height: 1.2; }
.hero-sub { color: #BFE9D9; margin: .35rem 0 .9rem 0; font-size: 1rem; }
.chip {
    display: inline-block; margin: 0 .4rem .3rem 0; padding: .2rem .75rem;
    border-radius: 999px; font-size: .82rem; font-weight: 600;
    background: rgba(127,255,212,.18); color: #C9FFEC;
    border: 1px solid rgba(127,255,212,.55);
}
.kwic {
    background: var(--superficie); color: var(--texto);
    border: 1px solid var(--borde); border-radius: 8px;
    padding: .4rem .7rem; margin-bottom: .35rem; font-size: .93rem;
}
.kwic mark {
    background: var(--aguamarina); color: var(--oscuro);
    padding: 0 .35rem; border-radius: 4px; font-weight: 700;
}

/* ---------- Métricas ---------- */
div[data-testid="stMetric"] {
    background: var(--superficie); border: 1px solid var(--borde);
    border-left: 5px solid var(--aqua-medio); padding: 14px 16px;
    border-radius: 10px; box-shadow: 0 2px 8px rgba(20,40,31,.06);
}
div[data-testid="stMetric"] [data-testid="stMetricLabel"],
div[data-testid="stMetric"] [data-testid="stMetricLabel"] * { color: var(--texto-suave) !important; }
div[data-testid="stMetric"] [data-testid="stMetricValue"],
div[data-testid="stMetric"] [data-testid="stMetricValue"] * { color: var(--oscuro) !important; }

/* ---------- Botones ---------- */
div.stButton > button, div.stDownloadButton > button {
    background: linear-gradient(135deg, var(--bosque), var(--aqua-profundo));
    color: #FFFFFF !important; border: none; border-radius: 8px;
    font-weight: 600; transition: all .15s ease;
}
div.stButton > button *, div.stDownloadButton > button * { color: #FFFFFF !important; }
div.stButton > button:hover, div.stDownloadButton > button:hover {
    background: var(--aguamarina); box-shadow: 0 4px 14px rgba(60,207,165,.45);
    transform: translateY(-1px);
}
div.stButton > button:hover *, div.stDownloadButton > button:hover * { color: var(--oscuro) !important; }

/* ---------- Entradas ---------- */
input, textarea,
[data-baseweb="input"], [data-baseweb="base-input"], [data-baseweb="textarea"],
[data-baseweb="select"] > div {
    background: #FFFFFF !important; color: var(--texto) !important;
    border-color: var(--borde) !important;
}
[data-baseweb="select"] *, [data-baseweb="select"] svg { color: var(--texto) !important; fill: var(--texto) !important; }
[data-baseweb="popover"], [data-baseweb="popover"] ul, [data-baseweb="menu"] { background: #FFFFFF !important; }
[data-baseweb="popover"] li, [data-baseweb="popover"] li * { color: var(--texto) !important; }
[data-baseweb="popover"] li:hover { background: var(--superficie-alt) !important; }
[data-baseweb="tag"] { background: var(--superficie-alt) !important; }
[data-baseweb="tag"] * { color: var(--oscuro) !important; }
[data-testid="stNumberInput"] button { background: var(--superficie-alt) !important; }
[data-testid="stNumberInput"] button * { color: var(--oscuro) !important; fill: var(--oscuro) !important; }
div[role="radiogroup"] label *, [data-testid="stCheckbox"] label *, [data-testid="stToggle"] label * { color: var(--texto) !important; }
[data-testid="stSliderThumbValue"], [data-testid="stSliderThumbValue"] * { color: var(--aqua-profundo) !important; font-weight: 700; }
[data-testid="stTickBarMin"], [data-testid="stTickBarMax"] { color: var(--texto-suave) !important; }
div[data-baseweb="slider"] div[role="slider"] { background: var(--aqua-profundo) !important; box-shadow: 0 0 0 4px rgba(127,255,212,.5) !important; }

[data-testid="stFileUploaderDropzone"] {
    background: var(--superficie-alt) !important; border: 2px dashed var(--aqua-medio) !important; border-radius: 12px;
}
[data-testid="stFileUploaderDropzone"] * { color: var(--texto) !important; }
[data-testid="stFileUploaderDropzone"] button,
[data-testid="stFileUploaderDropzone"] button * {
    background: var(--bosque) !important; color: #FFFFFF !important;
}

/* ---------- Pestañas ---------- */
.stTabs [data-baseweb="tab-list"] { gap: .3rem; border-bottom: 1px solid var(--borde); }
.stTabs [data-baseweb="tab"] { color: var(--texto-suave) !important; font-weight: 600; background: transparent; }
.stTabs [data-baseweb="tab"] * { color: var(--texto-suave) !important; }
.stTabs [aria-selected="true"], .stTabs [aria-selected="true"] * { color: var(--bosque) !important; }
.stTabs [data-baseweb="tab-highlight"] { background: var(--aqua-medio) !important; height: 3px; }

/* ---------- Alertas, expanders, tablas ---------- */
div[data-testid="stAlert"] {
    background: var(--superficie-alt) !important; border: 1px solid var(--borde);
    border-left: 5px solid var(--aqua-medio); border-radius: 10px;
}
div[data-testid="stAlert"] * { color: var(--texto) !important; }
[data-testid="stExpander"] details {
    background: var(--superficie); border: 1px solid var(--borde); border-radius: 10px;
}
[data-testid="stExpander"] summary, [data-testid="stExpander"] summary * { color: var(--oscuro) !important; }
[data-testid="stDataFrame"] { border: 1px solid var(--borde); border-radius: 10px; overflow: hidden; }
hr { border-color: var(--borde) !important; }

/* ---------- Barra lateral (fondo oscuro → texto claro) ---------- */
section[data-testid="stSidebar"] {
    background: linear-gradient(180deg, var(--oscuro) 0%, var(--bosque) 100%);
}
section[data-testid="stSidebar"] .sb-title {
    color: var(--aguamarina) !important; font-size: 1.25rem; font-weight: 700; margin-bottom: .4rem;
}
section[data-testid="stSidebar"] label, section[data-testid="stSidebar"] label p,
section[data-testid="stSidebar"] [data-testid="stWidgetLabel"] p,
section[data-testid="stSidebar"] [data-testid="stMarkdownContainer"] p,
section[data-testid="stSidebar"] [data-testid="stToggle"] label * { color: #E9F2EC !important; }
section[data-testid="stSidebar"] [data-testid="stCaptionContainer"],
section[data-testid="stSidebar"] [data-testid="stCaptionContainer"] * { color: #BFE9D9 !important; }
section[data-testid="stSidebar"] input, section[data-testid="stSidebar"] textarea,
section[data-testid="stSidebar"] [data-baseweb="select"] * { color: var(--texto) !important; }
section[data-testid="stSidebar"] [data-testid="stSliderThumbValue"],
section[data-testid="stSidebar"] [data-testid="stSliderThumbValue"] * { color: var(--aguamarina) !important; }
section[data-testid="stSidebar"] [data-testid="stTickBarMin"],
section[data-testid="stSidebar"] [data-testid="stTickBarMax"] { color: #BFE9D9 !important; }
section[data-testid="stSidebar"] div[data-testid="stMetric"] {
    background: rgba(255,255,255,.08); border: 1px solid rgba(127,255,212,.4);
    border-left: 5px solid var(--aguamarina);
}
section[data-testid="stSidebar"] div[data-testid="stMetric"] *,
section[data-testid="stSidebar"] div[data-testid="stMetric"] [data-testid="stMetricLabel"] *,
section[data-testid="stSidebar"] div[data-testid="stMetric"] [data-testid="stMetricValue"] * { color: #E6FFF6 !important; }
section[data-testid="stSidebar"] [data-testid="stExpander"] details {
    background: rgba(255,255,255,.07); border: 1px solid rgba(127,255,212,.35);
}
section[data-testid="stSidebar"] [data-testid="stExpander"] summary,
section[data-testid="stSidebar"] [data-testid="stExpander"] summary *,
section[data-testid="stSidebar"] [data-testid="stExpander"] * { color: #E9F2EC !important; }
section[data-testid="stSidebar"] hr { border-color: rgba(127,255,212,.3) !important; }
"""

st.markdown(f"<style>{_raiz}{CSS}</style>", unsafe_allow_html=True)

_V = tuple(int(x) for x in re.findall(r"\d+", st.__version__)[:2])
ANCHO_NUEVO = _V >= (1, 50)


# ============================================================
# 2. FUNCIONES GENERALES
# ============================================================

def mostrar_fig(fig, **kw):
    if ANCHO_NUEVO:
        st.plotly_chart(fig, width="stretch", **kw)
    else:
        st.plotly_chart(fig, use_container_width=True, **kw)


def mostrar_df(df, **kw):
    if ANCHO_NUEVO:
        st.dataframe(df, width="stretch", hide_index=True, **kw)
    else:
        st.dataframe(df, use_container_width=True, hide_index=True, **kw)


def mostrar_img(img, caption=None):
    if ANCHO_NUEVO:
        st.image(img, caption=caption, width="stretch")
    else:
        st.image(img, caption=caption, use_container_width=True)


def rgba(hex_color, alfa):
    h = hex_color.lstrip("#")
    r, g, b = int(h[0:2], 16), int(h[2:4], 16), int(h[4:6], 16)
    return f"rgba({r},{g},{b},{alfa})"


def estilo_fig(fig, altura=None, titulo=None):
    """Aplica estilo con contraste garantizado (texto oscuro sobre fondo claro)."""
    fig.update_layout(
        template="plotly_white",
        paper_bgcolor="rgba(255,255,255,0)",
        plot_bgcolor="#FFFFFF",
        font=dict(color=PALETA["texto"], family="Inter, Segoe UI, sans-serif"),
        colorway=SECUENCIA,
        margin=dict(l=10, r=10, t=50 if titulo else 20, b=10),
        hoverlabel=dict(bgcolor=PALETA["oscuro"], font_color="#E6FFF6"),
        legend=dict(font=dict(color=PALETA["texto"])),
    )
    if altura:
        fig.update_layout(height=altura)
    if titulo:
        fig.update_layout(title=dict(text=titulo, font=dict(color=PALETA["oscuro"], size=16)))
    fig.update_xaxes(gridcolor="#E3ECE6", linecolor=PALETA["borde"],
                     tickfont=dict(color=PALETA["texto"]),
                     title_font=dict(color=PALETA["texto_suave"]))
    fig.update_yaxes(gridcolor="#E3ECE6", linecolor=PALETA["borde"],
                     tickfont=dict(color=PALETA["texto"]),
                     title_font=dict(color=PALETA["texto_suave"]))
    return fig


def registrar(evento):
    st.session_state.setdefault("bitacora", [])
    st.session_state.bitacora.append(
        {"hora": datetime.now().strftime("%H:%M:%S"), "evento": evento}
    )


def dependencia(nombre):
    try:
        return __import__(nombre)
    except ImportError:
        return None


def aviso_dependencia(nombre, comando=None):
    st.warning(
        f"Esta función necesita `{nombre}`. "
        + (f"Instálala con: `{comando}`" if comando else "")
    )


def descargar_csv(df, index=False):
    return df.to_csv(index=index, encoding="utf-8-sig").encode("utf-8-sig")


def ayuda(texto):
    if st.session_state.get("mostrar_ayuda", True):
        st.caption("💡 " + texto)


def normalizar_texto(texto):
    texto = str(texto).lower()
    texto = unicodedata.normalize("NFKC", texto)
    texto = re.sub(r"https?://\S+|www\.\S+", " ", texto)
    texto = re.sub(r"[^\w\sáéíóúüñ]", " ", texto)
    texto = re.sub(r"\s+", " ", texto)
    return texto.strip()


def detectar_columna(columnas, claves, defecto):
    for c in columnas:
        if any(k in str(c).lower() for k in claves):
            return c
    return defecto


# ============================================================
# 3. AUDIO: utilidades
# ============================================================

def leer_audio(archivo):
    """Decodifica con SoundFile; si falla, usa Librosa (MP3 requiere FFmpeg)."""
    contenido = archivo.getvalue()
    try:
        import soundfile as sf
        audio, frecuencia = sf.read(io.BytesIO(contenido), dtype="float32")
    except Exception:
        try:
            import librosa
            audio, frecuencia = librosa.load(io.BytesIO(contenido), sr=None, mono=False)
            if audio.ndim == 2:
                audio = audio.mean(axis=0)
        except Exception as e:
            raise ValueError(
                "No se pudo decodificar el audio. Comprueba que el archivo "
                "sea válido y que FFmpeg esté instalado para MP3."
            ) from e

    if audio.ndim == 2:
        audio = audio.mean(axis=1)
    audio = np.asarray(audio, dtype=np.float32)
    if audio.size == 0:
        raise ValueError("El audio está vacío.")
    if not np.all(np.isfinite(audio)):
        raise ValueError("El audio contiene valores no válidos.")
    return audio, int(frecuencia)


def audio_wav_bytes(audio, frecuencia):
    """WAV PCM16 con la librería estándar (sin dependencias)."""
    a = np.clip(np.asarray(audio, dtype=np.float32), -1, 1)
    pcm = (a * 32767).astype("<i2")
    buffer = io.BytesIO()
    with wave.open(buffer, "wb") as w:
        w.setnchannels(1)
        w.setsampwidth(2)
        w.setframerate(int(frecuencia))
        w.writeframes(pcm.tobytes())
    return buffer.getvalue()


def limitar_audio(audio):
    audio = np.asarray(audio, dtype=np.float32)
    if audio.size == 0:
        return audio
    pico = np.max(np.abs(audio))
    if pico > 1:
        audio = audio / pico
    return np.clip(audio, -1, 1)


def generar_audio_demo(fs=22050, dur=6.0, seed=7):
    """Cantos sintéticos (barridos de frecuencia) sobre ruido de fondo."""
    rng = np.random.default_rng(seed)
    t = np.arange(int(fs * dur)) / fs
    y = 0.03 * rng.standard_normal(t.size) + 0.02 * np.sin(2 * np.pi * 60 * t)
    for ini, f0, f1, d in [
        (0.8, 2500, 4200, 0.35), (1.6, 3000, 5200, 0.25),
        (2.4, 2200, 3800, 0.40), (3.9, 3500, 6000, 0.30),
        (4.6, 2800, 4500, 0.50),
    ]:
        m = (t >= ini) & (t < ini + d)
        tt = t[m] - ini
        fase = 2 * np.pi * (f0 * tt + 0.5 * (f1 - f0) / d * tt ** 2)
        y[m] += 0.5 * np.sin(np.pi * tt / d) ** 2 * np.sin(fase)
    return limitar_audio(y), fs


def envolvente(x, puntos=3000):
    n = len(x)
    if n <= puntos * 2:
        return np.arange(n), x, x
    bloque = n // puntos
    r = x[: bloque * puntos].reshape(puntos, bloque)
    return np.arange(puntos) * bloque + bloque / 2, r.min(axis=1), r.max(axis=1)


def figura_onda(original, procesado, fs, ini, fin, altura):
    fig = go.Figure()
    for señal, nombre, color, alfa in [
        (original, "Original", "#8FA79A", 0.35),
        (procesado, "Procesado", PALETA["aqua_profundo"], 0.55),
    ]:
        idx, mn, mx = envolvente(señal)
        t = idx / fs
        fig.add_trace(go.Scatter(x=t, y=mx, mode="lines", line=dict(width=0),
                                 showlegend=False, hoverinfo="skip"))
        fig.add_trace(go.Scatter(x=t, y=mn, mode="lines", name=nombre,
                                 line=dict(width=1, color=color),
                                 fill="tonexty", fillcolor=rgba(color, alfa)))
    fig.add_vrect(x0=ini, x1=fin, fillcolor=rgba(PALETA["aguamarina"], 0.28), line_width=0)
    fig.update_xaxes(title="Tiempo (s)", rangeslider=dict(visible=True, thickness=0.08))
    fig.update_yaxes(title="Amplitud", range=[-1.05, 1.05])
    return estilo_fig(fig, altura)


def calcular_espectrograma(x, fs, nperseg, solape, fmax, piso_db):
    nperseg = int(min(nperseg, len(x)))
    if nperseg < 16:
        return None
    nover = min(int(nperseg * solape), nperseg - 1)
    f, t, Z = signal.stft(x, fs=fs, nperseg=nperseg, noverlap=nover)
    mag = np.abs(Z)
    db = 20 * np.log10(mag / (mag.max() + 1e-12) + 1e-12)
    db = np.clip(db, piso_db, 0)
    sel = f <= fmax
    f, db = f[sel], db[sel]
    paso = max(1, db.shape[1] // 1200)
    return f, t[::paso], db[:, ::paso]


def detectar_eventos(x, fs, f_min, f_max, delta_db, dur_min_ms, hueco_ms):
    nyq = fs / 2
    f_max = min(f_max, nyq * 0.95)
    y = x
    if 0 < f_min < f_max:
        try:
            sos = signal.butter(4, [f_min / nyq, f_max / nyq], btype="bandpass", output="sos")
            y = signal.sosfiltfilt(sos, x)
        except Exception:
            y = x
    ventana = max(16, int(fs * 0.02))
    salto = max(1, ventana // 2)
    if len(y) < ventana * 2:
        return pd.DataFrame(), None, None, None
    marcos = np.lib.stride_tricks.sliding_window_view(y, ventana)[::salto]
    rms = np.sqrt((marcos ** 2).mean(axis=1))
    db = 20 * np.log10(rms + 1e-9)
    t = (np.arange(len(db)) * salto + ventana / 2) / fs
    umbral = float(np.median(db) + delta_db)
    activo = db > umbral

    cambios = np.diff(np.concatenate([[0], activo.astype(int), [0]]))
    inicios = np.where(cambios == 1)[0]
    finales = np.where(cambios == -1)[0] - 1
    hueco = max(0, int(hueco_ms / 1000 * fs / salto))
    regiones = []
    for a, b in zip(inicios, finales):
        if regiones and a - regiones[-1][1] - 1 <= hueco:
            regiones[-1][1] = b
        else:
            regiones.append([a, b])

    filas = []
    for a, b in regiones:
        t0 = a * salto / fs
        t1 = (b * salto + ventana) / fs
        if (t1 - t0) * 1000 < dur_min_ms:
            continue
        seg = y[int(t0 * fs): int(t1 * fs)]
        f_dom = np.nan
        if len(seg) >= 16:
            n = max(len(seg), 2048)
            esp = np.abs(np.fft.rfft(seg * np.hanning(len(seg)), n=n))
            frec = np.fft.rfftfreq(n, 1 / fs)
            m = (frec >= max(f_min, 1)) & (frec <= f_max)
            if m.any():
                f_dom = float(frec[m][np.argmax(esp[m])])
        filas.append({
            "inicio_s": round(t0, 3), "fin_s": round(t1, 3),
            "duracion_s": round(t1 - t0, 3),
            "pico_db": round(float(db[a: b + 1].max()), 1),
            "frecuencia_dominante_hz": round(f_dom, 1) if np.isfinite(f_dom) else np.nan,
        })
    return pd.DataFrame(filas), t, db, umbral


# ============================================================
# 4. PANEL DE AUDIO
# ============================================================

def panel_audio():
    st.header("Laboratorio de bioacústica")
    st.write(
        "Análisis de señales acústicas: forma de onda interactiva, filtrado, "
        "reducción de ruido, detección automática de eventos y espectrogramas."
    )

    c_up, c_demo = st.columns([3, 1])
    with c_up:
        archivo = st.file_uploader(
            "Selecciona un archivo de audio",
            type=["mp3", "wav", "flac", "ogg"], key="audio_upload",
        )
    with c_demo:
        st.write("")
        usar_demo = st.toggle("Señal de demostración", key="demo_audio",
                              help="Cantos sintéticos con ruido, para probar sin archivo.")

    try:
        if archivo:
            audio_original, fs = leer_audio(archivo)
            audio_original = limitar_audio(audio_original)
            id_fuente = f"{archivo.name}-{archivo.size}"
            bytes_orig = archivo.getvalue()
            mime = {".mp3": "audio/mpeg", ".wav": "audio/wav",
                    ".flac": "audio/flac", ".ogg": "audio/ogg"}.get(
                Path(archivo.name).suffix.lower())
        elif usar_demo:
            audio_original, fs = generar_audio_demo()
            id_fuente = "demo"
            bytes_orig = audio_wav_bytes(audio_original, fs)
            mime = "audio/wav"
        else:
            st.info("Sube un archivo de audio o activa la señal de demostración para comenzar.")
            return
    except Exception as e:
        st.error(f"No se pudo leer el audio: {e}")
        return

    # Estado de procesamiento (con historial para deshacer)
    if st.session_state.get("audio_id") != id_fuente:
        st.session_state.audio_id = id_fuente
        st.session_state.audio_resultado = audio_original.copy()
        st.session_state.audio_historial = []
        st.session_state.pop("hpss", None)
        registrar(f"Audio cargado: {id_fuente}")

    def aplicar(nuevo, etiqueta):
        st.session_state.audio_historial.append(st.session_state.audio_resultado.copy())
        st.session_state.audio_historial = st.session_state.audio_historial[-8:]
        st.session_state.audio_resultado = limitar_audio(nuevo)
        st.session_state.pop("hpss", None)
        registrar(f"Audio · {etiqueta}")
        st.toast(f"{etiqueta} aplicado ✔", icon="🌿")
        st.rerun()

    audio = st.session_state.audio_resultado
    duracion = len(audio) / fs
    nyq = fs / 2

    c1, c2, c3, c4 = st.columns(4)
    c1.metric("Duración", f"{duracion:.2f} s")
    c2.metric("Frecuencia de muestreo", f"{fs:,} Hz")
    c3.metric("Muestras", f"{len(audio):,}")
    c4.metric("Pasos aplicados", len(st.session_state.audio_historial))

    st.audio(bytes_orig, format=mime)

    # Rango de análisis compartido por todas las pestañas internas
    ini, fin = st.slider(
        "Rango de análisis (s)", 0.0, float(duracion), (0.0, float(duracion)),
        step=0.01, key=f"rango_{len(audio)}",
        help="Define el fragmento para espectrograma, eventos, características y recorte.",
    )
    i0, i1 = int(ini * fs), max(int(fin * fs), int(ini * fs) + 2)
    segmento = audio[i0:i1]

    t_onda, t_proc, t_spec, t_evt, t_feat = st.tabs([
        "Forma de onda", "Procesado", "Espectrograma", "Eventos", "Características y exportación"
    ])

    # ---------------- Forma de onda ----------------
    with t_onda:
        mostrar_fig(figura_onda(audio_original, audio, fs, ini, fin, 380))
        ayuda("La zona aguamarina es el rango de análisis. Usa el control inferior "
              "del gráfico para hacer zoom en el tiempo.")

    # ---------------- Procesado ----------------
    with t_proc:
        b1, b2, _ = st.columns([1, 1, 3])
        with b1:
            if st.button("↩ Deshacer", key="a_deshacer",
                         disabled=not st.session_state.audio_historial):
                st.session_state.audio_resultado = st.session_state.audio_historial.pop()
                registrar("Audio · deshacer")
                st.rerun()
        with b2:
            if st.button("⟲ Restaurar original", key="a_restaurar"):
                st.session_state.audio_resultado = audio_original.copy()
                st.session_state.audio_historial = []
                registrar("Audio · restaurar original")
                st.rerun()

        st.subheader("1. Filtrado frecuencial")
        tipo = st.selectbox("Tipo de filtro",
                            ["Sin filtro", "Pasa bajos", "Pasa altos", "Pasa banda"],
                            key="f_tipo")
        if tipo != "Sin filtro":
            if nyq <= 2:
                st.error("Frecuencia de muestreo insuficiente.")
            else:
                tope = max(2, int(nyq * 0.95))
                btype, limites = None, None
                if tipo in ("Pasa bajos", "Pasa altos"):
                    defecto = 3000 if tipo == "Pasa bajos" else 300
                    corte = st.slider("Frecuencia de corte (Hz)", 1, tope,
                                      max(1, min(defecto, tope)), key="f_corte")
                    limites = corte / nyq
                    btype = "lowpass" if tipo == "Pasa bajos" else "highpass"
                else:
                    ca, cb = st.columns(2)
                    inferior = ca.number_input("Frecuencia inferior (Hz)", min_value=1,
                                               max_value=max(2, int(nyq * 0.94)),
                                               value=max(1, min(500, int(nyq * 0.2))),
                                               key="f_inf")
                    superior = cb.number_input("Frecuencia superior (Hz)",
                                               min_value=int(inferior) + 1,
                                               max_value=max(int(inferior) + 1, tope),
                                               value=max(int(inferior) + 1, min(5000, int(nyq * 0.8))),
                                               key="f_sup")
                    limites = [inferior / nyq, min(superior / nyq, 0.999)]
                    btype = "bandpass"
                orden = st.slider("Orden del filtro", 1, 8, 4, key="f_orden")
                if st.button("Aplicar filtro", key="a_filtro"):
                    try:
                        sos = signal.butter(orden, limites, btype=btype, output="sos")
                        aplicar(signal.sosfiltfilt(sos, audio), f"Filtro {tipo.lower()}")
                    except Exception as e:
                        st.error(f"Error de filtrado: {e}")

        st.subheader("2. Reducción de ruido")
        ayuda("La calidad depende de que el perfil de ruido represente bien el fondo.")
        modo = st.radio("Método", ["Reducción automática", "Utilizar fragmento inicial como ruido"],
                        key="r_modo", horizontal=True)
        cn1, cn2 = st.columns(2)
        dur_ruido = cn1.number_input("Duración del fragmento de ruido (s)", min_value=0.05,
                                     max_value=float(max(0.05, duracion)),
                                     value=min(1.0, float(duracion)), step=0.1, key="r_dur")
        prop = cn2.slider("Intensidad de reducción", 0.3, 1.0, 0.9, 0.05, key="r_prop")
        if st.button("Reducir ruido", key="a_ruido"):
            nr = dependencia("noisereduce")
            if nr is None:
                aviso_dependencia("noisereduce", "pip install noisereduce")
            else:
                try:
                    if modo.startswith("Utilizar"):
                        n_ruido = max(1, min(len(audio), int(dur_ruido * fs)))
                        res = nr.reduce_noise(y=audio, y_noise=audio[:n_ruido], sr=fs,
                                              prop_decrease=prop)
                    else:
                        res = nr.reduce_noise(y=audio, sr=fs, prop_decrease=prop)
                    aplicar(res, "Reducción de ruido")
                except Exception as e:
                    st.error(f"Error: {e}")

        st.subheader("3. Amplitud, fundidos y recorte")
        g1, g2, g3 = st.columns(3)
        with g1:
            if st.button("Normalizar amplitud", key="a_norm"):
                pico = np.max(np.abs(audio))
                if pico > 0:
                    aplicar(audio / pico * 0.95, "Normalización")
                else:
                    st.warning("La señal contiene solamente silencio.")
        with g2:
            ganancia = st.slider("Ganancia (dB)", -24, 24, 0, key="a_ganancia")
            if st.button("Aplicar ganancia", key="a_gan_btn") and ganancia != 0:
                aplicar(audio * 10 ** (ganancia / 20), f"Ganancia {ganancia:+d} dB")
        with g3:
            fade_in = st.slider("Fundido de entrada (ms)", 0, 2000, 100, 50, key="a_fin")
            fade_out = st.slider("Fundido de salida (ms)", 0, 2000, 100, 50, key="a_fout")
            if st.button("Aplicar fundidos", key="a_fade"):
                y = audio.copy()
                ni = min(len(y), int(fade_in / 1000 * fs))
                no = min(len(y), int(fade_out / 1000 * fs))
                if ni > 1:
                    y[:ni] *= np.linspace(0, 1, ni)
                if no > 1:
                    y[-no:] *= np.linspace(1, 0, no)
                aplicar(y, "Fundidos")
        if st.button("✂ Recortar al rango de análisis", key="a_recorte"):
            if len(segmento) / fs >= 0.05:
                aplicar(segmento, f"Recorte {ini:.2f}–{fin:.2f} s")
            else:
                st.warning("El rango seleccionado es demasiado corto.")

        st.subheader("4. Separación armónica-percusiva")
        ayuda("HPSS separa componentes tonales y transitorios; no identifica especies "
              "ni separa individuos. Se procesan como máximo 30 s.")
        margen = st.slider("Margen de separación", 1.0, 5.0, 1.0, 0.5, key="h_margen")
        if st.button("Ejecutar HPSS", key="a_hpss"):
            librosa = dependencia("librosa")
            if librosa is None:
                aviso_dependencia("librosa", "pip install librosa")
            else:
                try:
                    with st.spinner("Separando componentes…"):
                        corto = audio[: int(30 * fs)]
                        S = librosa.stft(corto)
                        arm, per = librosa.decompose.hpss(S, margin=margen)
                        st.session_state.hpss = (
                            librosa.istft(arm), librosa.istft(per)
                        )
                    registrar("Audio · HPSS")
                except Exception as e:
                    st.error(f"Error HPSS: {e}")
        if "hpss" in st.session_state:
            a, p = st.session_state.hpss
            h1, h2 = st.columns(2)
            with h1:
                st.write("**Componente armónica**")
                st.audio(audio_wav_bytes(a, fs), format="audio/wav")
            with h2:
                st.write("**Componente percusiva**")
                st.audio(audio_wav_bytes(p, fs), format="audio/wav")

    # ---------------- Espectrograma ----------------
    with t_spec:
        s1, s2, s3, s4 = st.columns(4)
        nperseg = s1.selectbox("Ventana FFT", [256, 512, 1024, 2048, 4096], index=3, key="s_nfft")
        solape = s2.slider("Solape", 0.0, 0.95, 0.5, 0.05, key="s_solape")
        fmax = s3.slider("Frecuencia máxima (Hz)", 100, int(nyq), int(min(nyq, 10000)),
                         key="s_fmax")
        piso = s4.slider("Rango dinámico (dB)", -120, -20, -80, key="s_piso")
        p1, p2 = st.columns(2)
        escala = p1.selectbox("Paleta", list(ESCALAS_ESPECTRO), key="s_paleta")
        mostrar_dom = p2.toggle("Superponer frecuencia dominante", value=False, key="s_dom")

        res = calcular_espectrograma(segmento, fs, nperseg, solape, fmax, piso)
        if res is None:
            st.warning("El fragmento es demasiado corto para el espectrograma.")
        else:
            f, t, db = res
            fig = go.Figure(go.Heatmap(
                z=db, x=t + ini, y=f, colorscale=ESCALAS_ESPECTRO[escala],
                zmin=piso, zmax=0,
                colorbar=dict(title=dict(text="dB", font=dict(color=PALETA["texto"])),
                              tickfont=dict(color=PALETA["texto"])),
            ))
            if mostrar_dom:
                fig.add_trace(go.Scatter(x=t + ini, y=f[np.argmax(db, axis=0)], mode="lines",
                                         name="Dominante",
                                         line=dict(color="#FFB703", width=2, dash="dot")))
            fig.update_xaxes(title="Tiempo (s)")
            fig.update_yaxes(title="Frecuencia (Hz)")
            mostrar_fig(estilo_fig(fig, st.session_state.get("altura_graf", 440)))
            ayuda("Haz zoom arrastrando sobre el gráfico; doble clic para restablecer.")

    # ---------------- Eventos ----------------
    with t_evt:
        st.subheader("Detección automática de eventos acústicos")
        ayuda("Detecta tramos donde la energía en la banda elegida supera el ruido "
              "de fondo (mediana) por un margen en dB.")
        e1, e2, e3, e4 = st.columns(4)
        banda = e1.slider("Banda de interés (Hz)", 50, int(nyq * 0.95),
                          (min(1000, int(nyq * 0.2)), int(min(nyq * 0.9, 8000))), key="e_banda")
        delta = e2.slider("Umbral sobre ruido (dB)", 3, 40, 12, key="e_delta")
        dmin = e3.slider("Duración mínima (ms)", 10, 1000, 80, 10, key="e_dmin")
        hueco = e4.slider("Unir huecos ≤ (ms)", 0, 500, 60, 10, key="e_hueco")

        df_ev, t_env, db_env, umbral = detectar_eventos(
            segmento, fs, banda[0], banda[1], delta, dmin, hueco)
        if t_env is None:
            st.warning("Fragmento demasiado corto para detectar eventos.")
        else:
            if not df_ev.empty:
                df_ev[["inicio_s", "fin_s"]] += ini
            fig = go.Figure(go.Scatter(x=t_env + ini, y=db_env, mode="lines", name="Energía (dB)",
                                       line=dict(color=PALETA["bosque"], width=1.6)))
            fig.add_hline(y=umbral, line_dash="dash", line_color=PALETA["ocre"],
                          annotation_text="umbral", annotation_font_color=PALETA["marron"])
            for _, fila in df_ev.iterrows():
                fig.add_vrect(x0=fila.inicio_s, x1=fila.fin_s,
                              fillcolor=rgba(PALETA["aguamarina"], 0.4), line_width=0)
            fig.update_xaxes(title="Tiempo (s)")
            fig.update_yaxes(title="Energía (dB)")
            mostrar_fig(estilo_fig(fig, 340))

            m1, m2, m3, m4 = st.columns(4)
            m1.metric("Eventos", len(df_ev))
            seg_dur = max(len(segmento) / fs, 1e-9)
            m2.metric("Tasa", f"{len(df_ev) / seg_dur * 60:.1f} /min")
            m3.metric("Duración media", f"{df_ev.duracion_s.mean():.2f} s" if len(df_ev) else "—")
            m4.metric("Tiempo activo",
                      f"{df_ev.duracion_s.sum() / seg_dur * 100:.1f} %" if len(df_ev) else "—")

            if len(df_ev):
                df_ev = df_ev.assign(tam_punto=df_ev["pico_db"] - df_ev["pico_db"].min() + 8)
                fig2 = px.scatter(
                    df_ev, x="duracion_s", y="frecuencia_dominante_hz", size="tam_punto",
                    color="pico_db", color_continuous_scale=ESCALA_DENSIDAD,
                    hover_data=["inicio_s", "fin_s", "pico_db"],
                    labels={"duracion_s": "Duración (s)",
                            "frecuencia_dominante_hz": "Frecuencia dominante (Hz)",
                            "pico_db": "Pico (dB)"},
                )
                fig2.update_traces(marker=dict(line=dict(width=1, color=PALETA["oscuro"])))
                mostrar_fig(estilo_fig(fig2, 320, "Perfil de los eventos"))
                mostrar_df(df_ev)
                st.download_button("Descargar eventos (CSV)", descargar_csv(df_ev),
                                   "eventos_acusticos.csv", "text/csv", key="d_eventos")
            else:
                st.info("Sin eventos con estos parámetros. Prueba a reducir el umbral.")

    # ---------------- Características y exportación ----------------
    with t_feat:
        st.subheader("Características acústicas del rango seleccionado")
        rms = float(np.sqrt(np.mean(segmento ** 2)))
        cruces = float(np.mean(np.abs(np.diff(np.sign(segmento))) / 2)) if len(segmento) > 1 else 0.0
        frecs, esp = signal.periodogram(segmento, fs)
        dominante = float(frecs[np.argmax(esp)])
        centroide = float(np.sum(frecs * esp) / (np.sum(esp) + 1e-12))
        acum = np.cumsum(esp) / (np.sum(esp) + 1e-12)
        rolloff = float(frecs[np.searchsorted(acum, 0.85)])
        p = esp / (np.sum(esp) + 1e-12)
        entropia = float(-np.sum(p * np.log2(p + 1e-12)) / np.log2(len(p) + 1e-12))

        caracteristicas = pd.DataFrame({
            "Característica": ["RMS", "Cruces por cero", "Frecuencia dominante (Hz)",
                               "Centroide espectral (Hz)", "Roll-off 85 % (Hz)",
                               "Entropía espectral (0-1)"],
            "Valor": [rms, cruces, dominante, centroide, rolloff, entropia],
        })
        mostrar_df(caracteristicas)

        limites_b = [0, 500, 1000, 2000, 4000, 8000, nyq + 1]
        nombres_b, energias = [], []
        for lo, hi in zip(limites_b[:-1], limites_b[1:]):
            if lo >= nyq:
                break
            m = (frecs >= lo) & (frecs < hi)
            energias.append(float(esp[m].sum()))
            nombres_b.append(f"{int(lo)}–{int(min(hi, nyq))} Hz")
        tot = sum(energias) + 1e-12
        df_b = pd.DataFrame({"Banda": nombres_b, "Energía (%)": [e / tot * 100 for e in energias]})
        fig = px.bar(df_b, x="Banda", y="Energía (%)", color="Energía (%)",
                     color_continuous_scale=ESCALA_DENSIDAD)
        fig.update_layout(coloraxis_showscale=False)
        mostrar_fig(estilo_fig(fig, 300, "Distribución de energía por banda"))

        st.subheader("Exportación")
        audio_final = limitar_audio(st.session_state.audio_resultado)
        wav = audio_wav_bytes(audio_final, fs)
        st.audio(wav, format="audio/wav")
        d1, d2 = st.columns(2)
        d1.download_button("Descargar audio procesado", wav, "audio_procesado.wav",
                           "audio/wav", key="d_audio")
        d2.download_button("Descargar características", descargar_csv(caracteristicas),
                           "caracteristicas_acusticas.csv", "text/csv", key="d_feat")


# ============================================================
# 5. IMÁGENES: utilidades
# ============================================================

def generar_imagen_demo(ancho=720, alto=460, seed=3):
    rng = np.random.default_rng(seed)
    y = np.linspace(0, 1, alto)[:, None, None]
    arriba = np.array([200, 225, 215], dtype=np.float32)
    abajo = np.array([112, 86, 56], dtype=np.float32)
    base = arriba * (1 - y) + abajo * y
    base = np.repeat(base, ancho, axis=1)
    base += rng.normal(0, 4, base.shape)
    img = Image.fromarray(np.clip(base, 0, 255).astype(np.uint8))
    d = ImageDraw.Draw(img)
    for _ in range(55):
        cx, cy = rng.integers(0, ancho), rng.integers(int(alto * 0.15), alto)
        rx, ry = rng.integers(25, 70), rng.integers(10, 30)
        col = (int(rng.integers(30, 80)), int(rng.integers(110, 190)), int(rng.integers(50, 100)))
        d.ellipse([cx - rx, cy - ry, cx + rx, cy + ry], fill=col)
    for _ in range(4):
        cx, cy = rng.integers(60, ancho - 60), rng.integers(80, alto - 60)
        d.ellipse([cx - 14, cy - 9, cx + 14, cy + 9], fill=(226, 120, 30))
        d.ellipse([cx + 10, cy - 5, cx + 20, cy + 5], fill=(60, 30, 15))
    return img.filter(ImageFilter.GaussianBlur(0.8))


def otsu(valores):
    hist, bordes = np.histogram(valores, bins=256)
    centros = (bordes[:-1] + bordes[1:]) / 2
    w1 = np.cumsum(hist)
    w2 = np.cumsum(hist[::-1])[::-1]
    m1 = np.cumsum(hist * centros) / np.maximum(w1, 1)
    m2 = (np.cumsum((hist * centros)[::-1]) / np.maximum(np.cumsum(hist[::-1]), 1))[::-1]
    varianza = w1[:-1] * w2[1:] * (m1[:-1] - m2[1:]) ** 2
    return float(centros[:-1][np.argmax(varianza)])


PRESETS_TONO = {
    "Verde (vegetación)": (60, 170),
    "Aguamarina": (140, 190),
    "Marrón / suelo": (10, 50),
    "Azul / agua": (180, 260),
    "Personalizado": (0, 360),
}


# ============================================================
# 6. PANEL DE IMÁGENES
# ============================================================

def panel_imagen():
    st.header("Laboratorio de visión por computador")
    st.write(
        "Evaluación de calidad, ajustes, segmentación por color, conteo de objetos, "
        "índice de vegetación y paleta dominante."
    )

    c_up, c_demo = st.columns([3, 1])
    with c_up:
        archivo = st.file_uploader("Selecciona una imagen", type=["jpg", "jpeg", "png", "webp"],
                                   key="image_upload")
    with c_demo:
        st.write("")
        usar_demo = st.toggle("Imagen de demostración", key="demo_img",
                              help="Escena sintética con hojas e insectos.")

    try:
        if archivo:
            imagen = Image.open(archivo).convert("RGB")
            id_img = f"{archivo.name}-{archivo.size}"
        elif usar_demo:
            imagen = generar_imagen_demo()
            id_img = "demo"
        else:
            st.info("Sube una imagen o activa la imagen de demostración para comenzar.")
            return
    except Exception as e:
        st.error(f"Error al abrir la imagen: {e}")
        return

    if max(imagen.size) > 2400:
        imagen.thumbnail((2400, 2400))
        st.caption("La imagen se redujo a 2400 px para mantener la fluidez.")

    imagen_np = np.array(imagen)
    ancho, alto = imagen.size

    t_cal, t_aj, t_seg, t_veg, t_comp = st.tabs([
        "Calidad", "Ajustes y transformaciones", "Segmentación y objetos",
        "Vegetación y paleta", "Comparador"
    ])

    # ---------------- Calidad ----------------
    with t_cal:
        izq, der = st.columns([1, 1])
        with izq:
            mostrar_img(imagen, "Imagen original")
        with der:
            gris = imagen_np.mean(axis=2)
            brillo = float(imagen_np.mean())
            contraste = float(imagen_np.std())
            nitidez = float(ndimage.laplace(gris).var())
            sat = float(np.mean(imagen_np.max(axis=2) >= 250) * 100)
            osc = float(np.mean(imagen_np.max(axis=2) <= 5) * 100)
            m1, m2, m3 = st.columns(3)
            m1.metric("Ancho", f"{ancho} px")
            m2.metric("Alto", f"{alto} px")
            m3.metric("Brillo", f"{brillo:.1f}")
            m4, m5, m6 = st.columns(3)
            m4.metric("Contraste", f"{contraste:.1f}")
            m5.metric("Nitidez (Laplaciano)", f"{nitidez:.1f}")
            m6.metric("Megapíxeles", f"{ancho * alto / 1e6:.2f}")
            if sat > 5:
                st.warning(f"{sat:.1f} % de píxeles saturados (posible sobreexposición).")
            if osc > 20:
                st.warning(f"{osc:.1f} % de píxeles muy oscuros (posible subexposición).")
            if sat <= 5 and osc <= 20:
                st.success("Exposición dentro de rangos razonables.")

        fig = go.Figure()
        for i, (nombre, color) in enumerate([("Rojo", "#C0392B"), ("Verde", "#2E8B57"),
                                             ("Azul", "#3B6EA5")]):
            h, _ = np.histogram(imagen_np[..., i], bins=64, range=(0, 255))
            fig.add_trace(go.Scatter(x=np.linspace(0, 255, 64), y=h, name=nombre, mode="lines",
                                     line=dict(color=color, width=2),
                                     fill="tozeroy", fillcolor=rgba(color, 0.15)))
        fig.update_xaxes(title="Intensidad")
        fig.update_yaxes(title="Píxeles")
        mostrar_fig(estilo_fig(fig, 300, "Histograma por canal"))

    # ---------------- Ajustes ----------------
    with t_aj:
        ctrl, vista = st.columns([1, 2])
        with ctrl:
            auto = st.toggle("Autocontraste", key="i_auto")
            f_b = st.slider("Brillo", 0.1, 2.5, 1.0, 0.05, key="i_b")
            f_c = st.slider("Contraste", 0.1, 2.5, 1.0, 0.05, key="i_c")
            f_s = st.slider("Saturación", 0.0, 3.0, 1.0, 0.05, key="i_s")
            f_n = st.slider("Nitidez", 0.0, 3.0, 1.0, 0.1, key="i_n")
            filtro = st.selectbox("Filtro", ["Ninguno", "Suavizar", "Realzar bordes", "Detalle"],
                                  key="i_filtro")
            angulo = st.slider("Rotación (°)", -180, 180, 0, key="i_rot")
            fh, fv, bn = st.columns(3)
            volt_h = fh.checkbox("Espejo H", key="i_fh")
            volt_v = fv.checkbox("Espejo V", key="i_fv")
            a_gris = bn.checkbox("Grises", key="i_gris")
            with st.expander("Recorte (%)"):
                r_izq = st.slider("Izquierda", 0, 45, 0, key="i_ri")
                r_der = st.slider("Derecha", 0, 45, 0, key="i_rd")
                r_sup = st.slider("Superior", 0, 45, 0, key="i_rs")
                r_inf = st.slider("Inferior", 0, 45, 0, key="i_rb")

        img = imagen.crop((int(ancho * r_izq / 100), int(alto * r_sup / 100),
                           int(ancho * (1 - r_der / 100)), int(alto * (1 - r_inf / 100))))
        if auto:
            img = ImageOps.autocontrast(img, cutoff=1)
        img = ImageEnhance.Brightness(img).enhance(f_b)
        img = ImageEnhance.Contrast(img).enhance(f_c)
        img = ImageEnhance.Color(img).enhance(f_s)
        img = ImageEnhance.Sharpness(img).enhance(f_n)
        if filtro == "Suavizar":
            img = img.filter(ImageFilter.GaussianBlur(1.2))
        elif filtro == "Realzar bordes":
            img = img.filter(ImageFilter.EDGE_ENHANCE_MORE)
        elif filtro == "Detalle":
            img = img.filter(ImageFilter.DETAIL)
        if angulo:
            img = img.rotate(-angulo, expand=True, fillcolor=(20, 30, 25))
        if volt_h:
            img = ImageOps.mirror(img)
        if volt_v:
            img = ImageOps.flip(img)
        if a_gris:
            img = ImageOps.grayscale(img).convert("RGB")
        ajustada = img

        with vista:
            mostrar_img(ajustada, "Imagen ajustada")
            buf = io.BytesIO()
            ajustada.save(buf, format="PNG")
            st.download_button("Descargar imagen ajustada", buf.getvalue(),
                               "imagen_ajustada.png", "image/png", key="d_img_aj")
        ayuda("La imagen ajustada es la base para segmentación, vegetación y paleta.")

    ajustada_np = np.array(ajustada)

    # ---------------- Segmentación ----------------
    with t_seg:
        st.subheader("Segmentación por color (HSV)")
        preset = st.selectbox("Preajuste", list(PRESETS_TONO), key="h_preset")
        p0, p1 = PRESETS_TONO[preset]
        s1, s2, s3, s4 = st.columns(4)
        tono = s1.slider("Tono (°)", 0, 360, (p0, p1), key=f"h_tono_{preset}")
        s_min = s2.slider("Saturación mínima", 0, 255, 40, key="h_sat")
        v_min = s3.slider("Valor mínimo", 0, 255, 30, key="h_val")
        k = s4.slider("Limpieza de ruido (px)", 1, 9, 3, 2, key="h_k")

        hsv = np.array(ajustada.convert("HSV"))
        h0, h1 = tono[0] / 360 * 255, tono[1] / 360 * 255
        mascara = ((hsv[..., 0] >= h0) & (hsv[..., 0] <= h1)
                   & (hsv[..., 1] >= s_min) & (hsv[..., 2] >= v_min))
        m_img = Image.fromarray((mascara * 255).astype(np.uint8))
        if k > 1:
            m_img = m_img.filter(ImageFilter.MinFilter(k)).filter(ImageFilter.MaxFilter(k))
        mascara = np.array(m_img) > 127

        superposicion = ajustada_np.copy().astype(np.float32)
        aqua = np.array([127, 255, 212], dtype=np.float32)
        superposicion[mascara] = 0.45 * superposicion[mascara] + 0.55 * aqua
        superposicion[~mascara] *= 0.65
        aislado = np.where(mascara[..., None], ajustada_np, 0).astype(np.uint8)

        v1, v2, v3 = st.columns(3)
        with v1:
            mostrar_img(m_img, "Máscara")
        with v2:
            mostrar_img(superposicion.astype(np.uint8), "Superposición")
        with v3:
            mostrar_img(aislado, "Aislado")

        cobertura = float(mascara.mean() * 100)
        etiquetas, n_obj = ndimage.label(mascara)
        a1, a2 = st.columns(2)
        a1.metric("Cobertura del color", f"{cobertura:.1f} %")
        area_min = a2.slider("Área mínima de objeto (px)", 1, 5000, 150, key="h_area")

        if 0 < n_obj < 5000:
            ids = np.arange(1, n_obj + 1)
            areas = ndimage.sum(mascara, etiquetas, ids)
            cms = ndimage.center_of_mass(mascara, etiquetas, ids)
            tabla = pd.DataFrame({
                "objeto": ids, "area_px": areas.astype(int),
                "centro_x": [round(c[1]) for c in cms], "centro_y": [round(c[0]) for c in cms],
            })
            tabla = tabla[tabla.area_px >= area_min].sort_values("area_px", ascending=False)
            st.metric("Objetos detectados", len(tabla))
            if len(tabla):
                fig = px.histogram(tabla, x="area_px", nbins=20,
                                   labels={"area_px": "Área (px)"},
                                   color_discrete_sequence=[PALETA["aqua_profundo"]])
                mostrar_fig(estilo_fig(fig, 260, "Distribución de tamaños"))
                mostrar_df(tabla.head(25))
                st.download_button("Descargar objetos (CSV)", descargar_csv(tabla),
                                   "objetos_segmentados.csv", "text/csv", key="d_obj")
        elif n_obj >= 5000:
            st.warning("Demasiados fragmentos: aumenta la limpieza de ruido.")

        buf_m = io.BytesIO()
        m_img.save(buf_m, format="PNG")
        st.download_button("Descargar máscara", buf_m.getvalue(), "mascara_hsv.png",
                           "image/png", key="d_mask")

        st.subheader("Eliminación de fondo")
        ayuda("Conserva la imagen original: eliminar el fondo puede borrar contexto ecológico.")
        if st.button("Eliminar fondo", key="i_rembg"):
            rembg = dependencia("rembg")
            if rembg is None:
                aviso_dependencia("rembg", "pip install rembg")
            else:
                try:
                    with st.spinner("Procesando…"):
                        st.session_state.rembg_img = (id_img, rembg.remove(ajustada))
                    registrar("Imagen · eliminación de fondo")
                except Exception as e:
                    st.error(f"Error: {e}")
        if st.session_state.get("rembg_img", (None,))[0] == id_img:
            res = st.session_state.rembg_img[1]
            mostrar_img(res, "Resultado sin fondo")
            salida = io.BytesIO()
            res.save(salida, format="PNG")
            st.download_button("Descargar imagen sin fondo", salida.getvalue(),
                               "imagen_sin_fondo.png", "image/png", key="d_rembg")

    # ---------------- Vegetación y paleta ----------------
    with t_veg:
        st.subheader("Índice de verdor (ExG)")
        ayuda("ExG = 2G − R − B sobre canales normalizados. Útil como indicador "
              "relativo de verdor en imágenes RGB.")
        a = ajustada_np.astype(np.float32)
        s = a.sum(axis=2) + 1e-6
        exg = 2 * a[..., 1] / s - a[..., 0] / s - a[..., 2] / s

        auto_u = st.toggle("Umbral automático (Otsu)", value=True, key="v_otsu")
        if auto_u:
            umbral = otsu(exg.ravel())
            st.caption(f"Umbral calculado: {umbral:.3f}")
        else:
            umbral = st.slider("Umbral ExG", -0.5, 1.0, 0.1, 0.01, key="v_umbral")

        paso = max(1, max(exg.shape) // 600)
        e1, e2 = st.columns(2)
        with e1:
            fig = px.imshow(exg[::paso, ::paso], color_continuous_scale=ESCALA_DENSIDAD,
                            aspect="equal", labels={"color": "ExG"})
            fig.update_xaxes(visible=False)
            fig.update_yaxes(visible=False)
            mostrar_fig(estilo_fig(fig, 340, "Mapa de verdor"))
        with e2:
            binaria = exg > umbral
            fig = px.imshow(binaria[::paso, ::paso].astype(int),
                            color_continuous_scale=[[0, "#EAF3EE"], [1, "#16806A"]],
                            aspect="equal")
            fig.update_coloraxes(showscale=False)
            fig.update_xaxes(visible=False)
            fig.update_yaxes(visible=False)
            mostrar_fig(estilo_fig(fig, 340, "Vegetación (binaria)"))
        st.metric("Cobertura vegetal estimada", f"{binaria.mean() * 100:.1f} %")

        st.subheader("Paleta dominante")
        k_col = st.slider("Número de colores", 3, 10, 6, key="v_k")
        peq = ajustada.resize((200, max(1, int(200 * ajustada.height / ajustada.width))))
        q = peq.quantize(colors=k_col, method=Image.Quantize.MEDIANCUT)
        pal = q.getpalette()[: k_col * 3]
        conteos = sorted(q.getcolors(), reverse=True)
        total = sum(c for c, _ in conteos)
        hexes = ["#%02x%02x%02x" % tuple(pal[i * 3: i * 3 + 3]) for _, i in conteos]
        df_pal = pd.DataFrame({"Color": hexes, "Proporción (%)": [c / total * 100 for c, _ in conteos]})
        fig = go.Figure(go.Bar(
            x=df_pal["Proporción (%)"], y=df_pal["Color"], orientation="h",
            marker=dict(color=df_pal["Color"], line=dict(color=PALETA["oscuro"], width=1)),
            text=[f"{v:.1f} %" for v in df_pal["Proporción (%)"]], textposition="outside",
            textfont=dict(color=PALETA["texto"]),
        ))
        fig.update_yaxes(autorange="reversed")
        fig.update_xaxes(title="Proporción (%)")
        mostrar_fig(estilo_fig(fig, 320))
        st.download_button("Descargar paleta (CSV)", descargar_csv(df_pal),
                           "paleta_dominante.csv", "text/csv", key="d_pal")

    # ---------------- Comparador ----------------
    with t_comp:
        st.subheader("Cortina antes / después")
        pos = st.slider("Posición de la cortina (%)", 0, 100, 50, key="c_pos")
        base = imagen.resize(ajustada.size)
        corte = int(ajustada.width * pos / 100)
        lienzo = ajustada.copy()
        lienzo.paste(base.crop((0, 0, corte, ajustada.height)), (0, 0))
        d = ImageDraw.Draw(lienzo)
        d.line([(corte, 0), (corte, ajustada.height)], fill=(127, 255, 212), width=4)
        mostrar_img(lienzo, "Izquierda: original  ·  Derecha: ajustada")


# ============================================================
# 7. TEXTO: utilidades
# ============================================================

TEXTO_EJEMPLO = """El oso andino habita los bosques nublados de los Yungas y depende de bromelias y frutos.
La vicuña pastorea en el altiplano boliviano y su fibra es muy valorada por las comunidades.
El lobo de crin recorre sabanas y pastizales de los llanos, donde la ganadería reduce su hábitat.
La barba azul es un guacamaye endémico de los llanos de Moxos y se encuentra en peligro crítico.
Los bosques nublados capturan agua de la neblina y regulan los caudales de los ríos andinos.
La deforestación y los incendios fragmentan el hábitat de aves, mamíferos y anfibios.
Los monitoreos acústicos permiten registrar cantos de aves y anfibios sin perturbar su hábitat.
Las comunidades locales participan en el monitoreo de fauna con cámaras trampa y grabadoras.
El cambio climático desplaza el hábitat de especies de montaña hacia mayores altitudes."""

STOPWORDS_BASE = {
    "de", "la", "el", "los", "las", "un", "una", "unos", "unas", "y", "o", "en",
    "con", "por", "para", "que", "se", "del", "al", "es", "son", "como", "su",
    "sus", "a", "lo", "sin", "muy", "donde", "sobre", "entre", "mayores",
}


def documentos_de(texto):
    return [l.strip() for l in texto.splitlines() if l.strip()]


# ============================================================
# 8. PANEL DE TEXTO
# ============================================================

def panel_texto():
    st.header("Laboratorio de procesamiento de texto")
    st.write(
        "Normalización, frecuencias, n-gramas, concordancias (KWIC), TF-IDF, "
        "similitud, modelado de temas y entidades. Cada línea se trata como un documento."
    )

    cu, cd = st.columns([3, 1])
    with cu:
        archivo = st.file_uploader("Selecciona TXT o CSV", type=["txt", "csv"], key="text_upload")
    with cd:
        st.write("")
        st.button("Cargar texto de ejemplo", key="t_demo",
                  on_click=lambda: st.session_state.update(texto_area=TEXTO_EJEMPLO))

    if archivo:
        try:
            nuevo, id_t = "", f"{archivo.name}-{archivo.size}"
            if archivo.name.lower().endswith(".txt"):
                nuevo = archivo.getvalue().decode("utf-8-sig", errors="replace")
            else:
                df = pd.read_csv(archivo)
                if len(df.columns) == 0:
                    st.warning("El CSV no contiene columnas.")
                else:
                    columna = st.selectbox("Columna de texto", df.columns, key="t_col")
                    nuevo = "\n".join(df[columna].dropna().astype(str))
                    id_t += f"-{columna}"
            if nuevo and st.session_state.get("texto_id") != id_t:
                st.session_state.texto_id = id_t
                st.session_state.texto_area = nuevo
        except Exception as e:
            st.error(f"Error al leer archivo: {e}")

    texto = st.text_area("Texto para analizar", height=200, key="texto_area")

    if not texto.strip():
        st.info("Escribe o pega texto, sube un archivo o carga el ejemplo.")
        return

    # Parámetros globales
    p1, p2 = st.columns([2, 1])
    stop_usuario = p1.text_input("Stopwords adicionales (separadas por comas)",
                                 value="muy, donde", key="t_stop")
    min_len = p2.slider("Longitud mínima de palabra", 1, 6, 2, key="t_minlen")
    stopwords = STOPWORDS_BASE | {p.strip().lower() for p in stop_usuario.split(",") if p.strip()}

    limpio = normalizar_texto(texto)
    tokens = limpio.split()
    filtrados = [t for t in tokens if t not in stopwords and len(t) >= min_len]
    docs = documentos_de(texto)

    t_res, t_frec, t_ng, t_tf, t_tem = st.tabs([
        "Resumen", "Frecuencias", "N-gramas y contexto", "TF-IDF y similitud", "Temas y entidades"
    ])

    with t_res:
        c1, c2, c3, c4 = st.columns(4)
        c1.metric("Tokens", len(tokens))
        c2.metric("Tokens filtrados", len(filtrados))
        c3.metric("Términos únicos", len(set(filtrados)))
        c4.metric("Documentos (líneas)", len(docs))
        c5, c6 = st.columns(2)
        c5.metric("Diversidad léxica (TTR)",
                  f"{len(set(filtrados)) / max(len(filtrados), 1):.2f}")
        c6.metric("Longitud media de palabra",
                  f"{np.mean([len(t) for t in filtrados]):.1f}" if filtrados else "—")
        with st.expander("Ver texto normalizado"):
            st.write(limpio[:3000] + ("…" if len(limpio) > 3000 else ""))

    with t_frec:
        top = st.slider("Palabras a mostrar", 5, 50, 20, key="t_top")
        vista = st.radio("Vista", ["Barras", "Treemap", "Tabla"], horizontal=True, key="t_vista")
        frec_df = pd.DataFrame(Counter(filtrados).most_common(top), columns=["Palabra", "Frecuencia"])
        if frec_df.empty:
            st.info("No hay palabras tras el filtrado.")
        else:
            if vista == "Barras":
                fig = px.bar(frec_df, x="Frecuencia", y="Palabra", orientation="h",
                             color="Frecuencia", color_continuous_scale=ESCALA_DENSIDAD)
                fig.update_layout(yaxis={"categoryorder": "total ascending"},
                                  coloraxis_showscale=False)
                mostrar_fig(estilo_fig(fig, max(320, top * 22)))
            elif vista == "Treemap":
                fig = px.treemap(frec_df, path=["Palabra"], values="Frecuencia",
                                 color="Frecuencia", color_continuous_scale=ESCALA_TREEMAP)
                fig.update_traces(textfont=dict(color=PALETA["oscuro"], size=16),
                                  marker=dict(line=dict(color="#FFFFFF", width=2)))
                fig.update_layout(coloraxis_showscale=False)
                mostrar_fig(estilo_fig(fig, 460))
            else:
                mostrar_df(frec_df)
            st.download_button("Descargar frecuencias", descargar_csv(frec_df),
                               "frecuencias.csv", "text/csv", key="d_frec")

    with t_ng:
        n = st.selectbox("Tamaño del n-grama", [1, 2, 3], index=1, key="t_n")
        ngramas = [tuple(filtrados[i:i + n]) for i in range(len(filtrados) - n + 1)]
        df_ng = pd.DataFrame([{"N-grama": " ".join(k), "Frecuencia": v}
                              for k, v in Counter(ngramas).most_common(25)])
        mostrar_df(df_ng)

        st.subheader("Concordancias (KWIC)")
        q1, q2, q3 = st.columns([2, 1, 1])
        consulta = normalizar_texto(q1.text_input("Buscar palabra", key="t_kwic"))
        ventana = q2.slider("Contexto (palabras)", 2, 12, 5, key="t_vent")
        parcial = q3.checkbox("Coincidencia parcial", value=True, key="t_parcial")
        if consulta:
            filas = []
            for i, t in enumerate(tokens):
                if (t.startswith(consulta) if parcial else t == consulta):
                    izq = " ".join(tokens[max(0, i - ventana): i])
                    der = " ".join(tokens[i + 1: i + 1 + ventana])
                    filas.append(f"<div class='kwic'>{html.escape(izq)} "
                                 f"<mark>{html.escape(t)}</mark> {html.escape(der)}</div>")
            if filas:
                st.caption(f"{len(filas)} coincidencias")
                st.markdown("".join(filas[:40]), unsafe_allow_html=True)
            else:
                st.info("Sin coincidencias.")

    with t_tf:
        if len(docs) < 2:
            st.info("Se necesitan al menos dos documentos (líneas) para TF-IDF y similitud.")
        else:
            try:
                from sklearn.feature_extraction.text import TfidfVectorizer
                from sklearn.metrics.pairwise import cosine_similarity

                vec = TfidfVectorizer(max_features=1000, ngram_range=(1, 2),
                                      preprocessor=normalizar_texto, stop_words=list(stopwords))
                matriz = vec.fit_transform(docs)
                nombres = vec.get_feature_names_out()
                st.write(f"**{matriz.shape[0]}** documentos · **{matriz.shape[1]}** términos")

                sel = st.selectbox("Documento a inspeccionar", range(len(docs)),
                                   format_func=lambda i: f"{i + 1}. {docs[i][:70]}", key="t_doc")
                fila = matriz[sel].toarray().ravel()
                orden = fila.argsort()[::-1][:12]
                df_top = pd.DataFrame({"Término": nombres[orden], "TF-IDF": fila[orden]})
                df_top = df_top[df_top["TF-IDF"] > 0]
                fig = px.bar(df_top, x="TF-IDF", y="Término", orientation="h",
                             color_discrete_sequence=[PALETA["aqua_profundo"]])
                fig.update_layout(yaxis={"categoryorder": "total ascending"})
                mostrar_fig(estilo_fig(fig, 340, "Términos más distintivos del documento"))

                sim = cosine_similarity(matriz)
                fig = px.imshow(sim, color_continuous_scale=ESCALA_DENSIDAD, aspect="auto",
                                labels={"x": "Documento", "y": "Documento", "color": "Similitud"},
                                x=[str(i + 1) for i in range(len(docs))],
                                y=[str(i + 1) for i in range(len(docs))])
                mostrar_fig(estilo_fig(fig, 420, "Matriz de similitud coseno"))

                parecidos = np.argsort(sim[sel])[::-1]
                parecidos = [i for i in parecidos if i != sel][:3]
                st.write("**Documentos más similares:**")
                for i in parecidos:
                    st.markdown(f"<div class='kwic'><b>{sim[sel, i]:.2f}</b> · "
                                f"{html.escape(docs[i])}</div>", unsafe_allow_html=True)

                tfidf_df = pd.DataFrame(matriz.toarray(), columns=nombres)
                st.download_button("Descargar matriz TF-IDF", descargar_csv(tfidf_df),
                                   "matriz_tfidf.csv", "text/csv", key="d_tfidf")
            except ImportError:
                aviso_dependencia("scikit-learn", "pip install scikit-learn")
            except Exception as e:
                st.error(f"Error TF-IDF: {e}")

    with t_tem:
        st.subheader("Modelado de temas (LDA)")
        n_temas = st.slider("Número de temas", 2, 10, 3, key="t_temas")
        if st.toggle("Ejecutar LDA", key="t_lda"):
            try:
                from sklearn.decomposition import LatentDirichletAllocation
                from sklearn.feature_extraction.text import CountVectorizer

                if len(docs) < 2:
                    st.warning("Se requieren al menos dos documentos.")
                else:
                    vec = CountVectorizer(stop_words=list(stopwords), max_features=1000,
                                          preprocessor=normalizar_texto)
                    matriz = vec.fit_transform(docs)
                    if matriz.shape[1] == 0:
                        st.warning("No existen términos suficientes.")
                    else:
                        lda = LatentDirichletAllocation(n_components=n_temas, random_state=42,
                                                        max_iter=15).fit(matriz)
                        nombres = vec.get_feature_names_out()
                        filas, pesos = [], []
                        for i, tema in enumerate(lda.components_):
                            idx = tema.argsort()[-10:][::-1]
                            filas.append({"Tema": i + 1, "Palabras": ", ".join(nombres[idx])})
                            pesos.append(tema[idx[0]])
                        mostrar_df(pd.DataFrame(filas))
                        asign = lda.transform(matriz).argmax(axis=1) + 1
                        cuenta = pd.Series(asign).value_counts().sort_index().reset_index()
                        cuenta.columns = ["Tema", "Documentos"]
                        cuenta["Tema"] = cuenta["Tema"].astype(str)
                        fig = px.bar(cuenta, x="Tema", y="Documentos", color="Tema")
                        fig.update_layout(showlegend=False)
                        mostrar_fig(estilo_fig(fig, 280, "Documentos por tema dominante"))
            except ImportError:
                aviso_dependencia("scikit-learn", "pip install scikit-learn")
            except Exception as e:
                st.error(f"Error LDA: {e}")

        st.subheader("Reconocimiento de entidades")
        if st.toggle("Detectar entidades", key="t_ner"):
            try:
                import spacy
                nlp = spacy.load("es_core_news_sm")
                doc = nlp(texto)
                ents = pd.DataFrame([{"Entidad": e.text, "Categoría": e.label_} for e in doc.ents])
                if ents.empty:
                    st.info("No se encontraron entidades.")
                else:
                    resumen = ents.groupby("Categoría").size().reset_index(name="Cantidad")
                    fig = px.bar(resumen, x="Categoría", y="Cantidad", color="Categoría")
                    fig.update_layout(showlegend=False)
                    mostrar_fig(estilo_fig(fig, 260))
                    mostrar_df(ents)
                    st.download_button("Descargar entidades", descargar_csv(ents),
                                       "entidades.csv", "text/csv", key="d_ents")
            except ImportError:
                aviso_dependencia("spacy", "pip install spacy")
            except OSError:
                st.warning("Instala el modelo español con: "
                           "`python -m spacy download es_core_news_sm`")
            except Exception as e:
                st.error(f"Error NER: {e}")


# ============================================================
# 9. GEO: utilidades
# ============================================================

RADIO_TIERRA_KM = 6371.0088


def generar_geo_demo(seed=11):
    rng = np.random.default_rng(seed)
    centros = [("Altiplano", -16.5, -68.15, 0.35, 90), ("Valles", -17.4, -66.15, 0.25, 70),
               ("Llanos", -17.8, -63.2, 0.40, 110), ("Yungas", -16.2, -67.7, 0.15, 60)]
    especies = ["Vicugna vicugna", "Tremarctos ornatus", "Chrysocyon brachyurus",
                "Rhea pennata", "Ara glaucogularis"]
    filas = []
    for region, la, lo, dispersion, n in centros:
        for _ in range(n):
            filas.append([rng.choice(especies), region,
                          la + rng.normal(0, dispersion), lo + rng.normal(0, dispersion)])
    for _ in range(15):
        filas.append([rng.choice(especies), "Disperso",
                      rng.uniform(-21.5, -10.5), rng.uniform(-68.5, -58.5)])
    df = pd.DataFrame(filas, columns=["especie", "region", "latitud", "longitud"])
    df["altitud_m"] = rng.integers(150, 4600, len(df))
    df["fecha"] = pd.to_datetime("2022-01-01") + pd.to_timedelta(rng.integers(0, 1400, len(df)), "D")
    # Errores intencionales para practicar la validación
    df.loc[3, ["latitud", "longitud"]] = [-68.2, -16.4]
    df.loc[10, ["latitud", "longitud"]] = [-67.9, -16.0]
    df.loc[20, ["latitud", "longitud"]] = [123.0, -66.0]
    df.loc[30, ["latitud", "longitud"]] = [0.0, 0.0]
    df.loc[40, ["latitud", "longitud"]] = [df.loc[41, "latitud"], df.loc[41, "longitud"]]
    return df


def zoom_desde_extension(lat_rng, lon_rng):
    ext = max(lat_rng, lon_rng, 0.01)
    return float(np.clip(np.log2(360 / ext) - 0.4, 1, 16))


def mapa_puntos(df, color, tam, estilo, altura, hover):
    centro = dict(lat=float(df["_lat"].mean()), lon=float(df["_lon"].mean()))
    zoom = zoom_desde_extension(df["_lat"].max() - df["_lat"].min(),
                                df["_lon"].max() - df["_lon"].min())
    kw = dict(lat="_lat", lon="_lon", color=color, zoom=zoom, center=centro,
              height=altura, hover_data=hover, color_discrete_sequence=SECUENCIA)
    if hasattr(px, "scatter_map"):
        fig = px.scatter_map(df, map_style=estilo, **kw)
    else:
        fig = px.scatter_mapbox(df, mapbox_style=estilo, **kw)
    fig.update_traces(marker=dict(size=tam))
    fig.update_layout(margin=dict(l=0, r=0, t=0, b=0), paper_bgcolor="rgba(0,0,0,0)",
                      legend=dict(bgcolor="rgba(255,255,255,0.9)", font=dict(color=PALETA["texto"])))
    return fig


# ============================================================
# 10. PANEL GEOESPACIAL
# ============================================================

def panel_geo():
    st.header("Laboratorio de inteligencia geoespacial")
    st.write(
        "Validación de coordenadas, mapas interactivos, densidad, agrupamiento "
        "espacial y patrón de distribución."
    )

    cu, cd = st.columns([3, 1])
    with cu:
        archivo = st.file_uploader("Selecciona un CSV de coordenadas", type=["csv"], key="geo_upload")
    with cd:
        st.write("")
        usar_demo = st.toggle("Datos de demostración", key="demo_geo",
                              help="Observaciones sintéticas con errores intencionales.")
    try:
        if archivo:
            df_geo = pd.read_csv(archivo)
        elif usar_demo:
            df_geo = generar_geo_demo()
        else:
            st.info("Sube un CSV o activa los datos de demostración para comenzar.")
            return
    except Exception as e:
        st.error(f"No se pudo leer el CSV: {e}")
        return

    if len(df_geo.columns) < 2:
        st.error("El CSV necesita al menos dos columnas.")
        return

    try:
        columnas = list(df_geo.columns)
        def_lat = detectar_columna(columnas, ["lat"], columnas[0])
        def_lon = detectar_columna(columnas, ["lon", "lng", "long"], columnas[min(1, len(columnas) - 1)])
        s1, s2 = st.columns(2)
        col_lat = s1.selectbox("Columna de latitud", columnas, index=columnas.index(def_lat), key="g_lat")
        col_lon = s2.selectbox("Columna de longitud", columnas, index=columnas.index(def_lon), key="g_lon")

        df = df_geo.copy()
        df["_lat"] = pd.to_numeric(df[col_lat], errors="coerce")
        df["_lon"] = pd.to_numeric(df[col_lon], errors="coerce")

        lat_ok = df["_lat"].between(-90, 90)
        lon_ok = df["_lon"].between(-180, 180)
        df["posible_intercambio"] = (~lat_ok & df["_lon"].between(-90, 90)
                                     & df["_lat"].between(-180, 180))

        t_val, t_map, t_den, t_clu, t_vec = st.tabs([
            "Validación", "Mapa", "Densidad", "Agrupamiento", "Vecindad y exportación"
        ])

        # ---------------- Validación ----------------
        with t_val:
            o1, o2 = st.columns(2)
            corregir = o1.toggle("Corregir intercambios lat/lon", key="g_corr",
                                 help="Intercambia filas con latitud fuera de rango.")
            quitar_dup = o2.toggle("Excluir duplicados exactos", key="g_dup")
            if corregir:
                m = df["posible_intercambio"]
                df.loc[m, ["_lat", "_lon"]] = df.loc[m, ["_lon", "_lat"]].to_numpy()
                lat_ok = df["_lat"].between(-90, 90)
                lon_ok = df["_lon"].between(-180, 180)
            cero = (df["_lat"] == 0) & (df["_lon"] == 0)
            validas = df["_lat"].notna() & df["_lon"].notna() & lat_ok & lon_ok & ~cero
            duplicado = df.duplicated(subset=["_lat", "_lon"], keep="first") & validas
            if quitar_dup:
                validas &= ~duplicado
            df["coordenada_valida"] = validas
            df["duplicado"] = duplicado

            m1, m2, m3, m4, m5 = st.columns(5)
            m1.metric("Registros", len(df))
            m2.metric("Válidos", int(validas.sum()))
            m3.metric("Inválidos", int((~validas).sum()))
            m4.metric("Posibles intercambios", int(df["posible_intercambio"].sum()))
            m5.metric("Duplicados", int(duplicado.sum()))
            if int(cero.sum()):
                st.warning(f"{int(cero.sum())} registros en (0, 0): suele indicar datos faltantes.")

            with st.expander("Ver registros con problemas"):
                problemas = df.loc[~validas | df["posible_intercambio"] | duplicado]
                if problemas.empty:
                    st.success("No se detectaron problemas.")
                else:
                    mostrar_df(problemas.drop(columns=["_lat", "_lon"]).head(200))
            mostrar_df(df_geo.head(20))

        # Filtro categórico opcional
        candidatas = [c for c in df_geo.columns
                      if c not in (col_lat, col_lon)
                      and df_geo[c].dtype == object and 1 < df_geo[c].nunique() <= 40]
        df_val = df.loc[validas].copy()
        if candidatas:
            with st.expander("Filtrar observaciones"):
                f_col = st.selectbox("Columna", ["Sin filtro"] + candidatas, key="g_fcol")
                if f_col != "Sin filtro":
                    valores = sorted(df_val[f_col].dropna().astype(str).unique())
                    elegidos = st.multiselect("Valores", valores, default=valores, key="g_fval")
                    df_val = df_val[df_val[f_col].astype(str).isin(elegidos)]
        st.caption(f"Registros activos para el análisis: **{len(df_val)}**")

        if df_val.empty:
            for t in (t_map, t_den, t_clu, t_vec):
                with t:
                    st.warning("No existen coordenadas válidas.")
            return

        # ---------------- Mapa ----------------
        with t_map:
            q1, q2, q3 = st.columns(3)
            opciones_color = ["Ninguno"] + candidatas
            color_por = q1.selectbox("Colorear por", opciones_color, key="g_color")
            tam = q2.slider("Tamaño de punto", 3, 20, 8, key="g_tam")
            estilo = q3.selectbox("Estilo de mapa", ["open-street-map", "carto-positron"], key="g_estilo")
            hover = [c for c in df_geo.columns if c not in (col_lat, col_lon)][:4]
            fig = mapa_puntos(df_val, None if color_por == "Ninguno" else color_por,
                              tam, estilo, 560, hover)
            if color_por == "Ninguno":
                fig.update_traces(marker=dict(color=PALETA["aqua_profundo"]))
            mostrar_fig(fig)
            ayuda("Pasa el cursor sobre un punto para ver sus atributos; usa la rueda para zoom.")

        # ---------------- Densidad ----------------
        with t_den:
            resolucion = st.slider("Resolución (celdas)", 5, 60, 20, key="g_res")
            fig = px.density_heatmap(df_val, x="_lon", y="_lat", nbinsx=resolucion,
                                     nbinsy=resolucion, color_continuous_scale=ESCALA_DENSIDAD,
                                     labels={"_lon": "Longitud", "_lat": "Latitud"})
            mostrar_fig(estilo_fig(fig, 460))
            if st.toggle("Mapa de calor sobre el territorio", key="g_calor"):
                radio = st.slider("Radio (px)", 5, 60, 20, key="g_radio")
                centro = dict(lat=float(df_val["_lat"].mean()), lon=float(df_val["_lon"].mean()))
                zoom = zoom_desde_extension(df_val["_lat"].max() - df_val["_lat"].min(),
                                            df_val["_lon"].max() - df_val["_lon"].min())
                if hasattr(px, "density_map"):
                    fm = px.density_map(df_val, lat="_lat", lon="_lon", radius=radio, zoom=zoom,
                                        center=centro, map_style="open-street-map",
                                        color_continuous_scale=ESCALA_DENSIDAD, height=520)
                else:
                    fm = px.density_mapbox(df_val, lat="_lat", lon="_lon", radius=radio, zoom=zoom,
                                           center=centro, mapbox_style="open-street-map",
                                           color_continuous_scale=ESCALA_DENSIDAD, height=520)
                fm.update_layout(margin=dict(l=0, r=0, t=0, b=0))
                mostrar_fig(fm)
            st.caption("La densidad de registros no equivale necesariamente a "
                       "densidad de biodiversidad: refleja también el esfuerzo de muestreo.")

        # ---------------- Agrupamiento ----------------
        with t_clu:
            try:
                from sklearn.cluster import DBSCAN
                from sklearn.neighbors import BallTree
            except ImportError:
                aviso_dependencia("scikit-learn", "pip install scikit-learn")
                DBSCAN = BallTree = None

            if DBSCAN is not None:
                r1, r2 = st.columns(2)
                radio_km = r1.slider("Radio de vecindad (km)", 0.1, 150.0, 15.0, 0.1, key="g_eps")
                minimo = r2.slider("Mínimo de puntos", 2, 30, 5, key="g_min")
                coords = np.radians(df_val[["_lat", "_lon"]].to_numpy())

                if len(df_val) > minimo:
                    arbol = BallTree(coords, metric="haversine")
                    dk = np.sort(arbol.query(coords, k=minimo)[0][:, -1] * RADIO_TIERRA_KM)
                    fig = go.Figure(go.Scatter(y=dk, mode="lines",
                                               line=dict(color=PALETA["bosque"], width=2)))
                    fig.add_hline(y=radio_km, line_dash="dash", line_color=PALETA["ocre"],
                                  annotation_text="radio elegido",
                                  annotation_font_color=PALETA["marron"])
                    fig.update_xaxes(title="Puntos ordenados")
                    fig.update_yaxes(title=f"Distancia al vecino nº {minimo} (km)")
                    mostrar_fig(estilo_fig(fig, 280, "Curva k-distancia (el «codo» sugiere el radio)"))

                if st.toggle("Calcular agrupamiento DBSCAN", key="g_dbscan"):
                    if len(df_val) < minimo:
                        st.warning("No hay suficientes puntos.")
                    elif len(df_val) > 50000:
                        st.warning("Demasiados puntos para el cálculo interactivo.")
                    else:
                        etiquetas = DBSCAN(eps=radio_km / RADIO_TIERRA_KM, min_samples=minimo,
                                           metric="haversine", algorithm="ball_tree").fit_predict(coords)
                        df_val["cluster"] = np.where(etiquetas == -1, "Ruido",
                                                     ["Grupo " + str(e + 1) for e in etiquetas])
                        grupos = len(set(etiquetas) - {-1})
                        ruido = int(np.sum(etiquetas == -1))
                        k1, k2, k3 = st.columns(3)
                        k1.metric("Grupos", grupos)
                        k2.metric("Puntos de ruido", ruido)
                        k3.metric("% agrupado", f"{(1 - ruido / len(df_val)) * 100:.1f} %")

                        fig = mapa_puntos(df_val, "cluster", 8, "open-street-map", 520, None)
                        for tr in fig.data:
                            if tr.name == "Ruido":
                                tr.marker.color = "#8C9A92"
                                tr.marker.opacity = 0.55
                        mostrar_fig(fig)

                        resumen = (df_val[df_val.cluster != "Ruido"].groupby("cluster")
                                   .agg(puntos=("_lat", "size"), lat_centro=("_lat", "mean"),
                                        lon_centro=("_lon", "mean")).reset_index())
                        if len(resumen):
                            mostrar_df(resumen.round(4))
                        st.session_state.geo_clusters = df_val["cluster"]
                        st.download_button("Descargar agrupamiento",
                                           descargar_csv(df_val.drop(columns=["_lat", "_lon"])),
                                           "dbscan_geografico.csv", "text/csv", key="d_dbscan")
                        registrar(f"Geo · DBSCAN: {grupos} grupos")

        # ---------------- Vecindad y exportación ----------------
        with t_vec:
            if len(df_val) < 2:
                st.warning("Se requieren al menos dos puntos.")
            else:
                try:
                    from sklearn.neighbors import BallTree
                    coords = np.radians(df_val[["_lat", "_lon"]].to_numpy())
                    dist, _ = BallTree(coords, metric="haversine").query(coords, k=2)
                    dkm = dist[:, 1] * RADIO_TIERRA_KM
                    df_dist = pd.DataFrame({"indice_original": df_val.index,
                                            "distancia_vecino_km": dkm})

                    v1, v2, v3 = st.columns(3)
                    v1.metric("Distancia media", f"{dkm.mean():.2f} km")
                    v2.metric("Mediana", f"{np.median(dkm):.2f} km")
                    v3.metric("Máxima", f"{dkm.max():.2f} km")

                    fig = px.histogram(df_dist, x="distancia_vecino_km", nbins=30,
                                       color_discrete_sequence=[PALETA["aqua_profundo"]],
                                       labels={"distancia_vecino_km": "Distancia al vecino (km)"})
                    mostrar_fig(estilo_fig(fig, 300, "Distancia al vecino más cercano"))

                    lat_km = (df_val["_lat"].max() - df_val["_lat"].min()) * 111.32
                    lon_km = ((df_val["_lon"].max() - df_val["_lon"].min()) * 111.32
                              * np.cos(np.radians(df_val["_lat"].mean())))
                    area = max(lat_km * lon_km, 1e-6)
                    esperado = 0.5 / np.sqrt(len(df_val) / area)
                    R = float(dkm.mean() / esperado)
                    patron = ("agrupado" if R < 0.9 else "disperso" if R > 1.1 else "cercano al azar")
                    st.metric("Índice de Clark-Evans (R)", f"{R:.2f}", help="R<1 agrupado; R≈1 azar; R>1 disperso")
                    st.caption(f"Patrón espacial: **{patron}**. Calculado sobre el rectángulo "
                               "envolvente, por lo que es sensible a los efectos de borde.")

                    st.subheader("Exportación")
                    e1, e2 = st.columns(2)
                    e1.download_button("Descargar distancias", descargar_csv(df_dist),
                                       "distancias.csv", "text/csv", key="d_dist")
                    exportable = df.drop(columns=["_lat", "_lon"]).copy()
                    exportable["latitud_limpia"] = df["_lat"]
                    exportable["longitud_limpia"] = df["_lon"]
                    e2.download_button("Descargar coordenadas validadas", descargar_csv(exportable),
                                       "coordenadas_validadas.csv", "text/csv", key="d_geo_val")
                except ImportError:
                    aviso_dependencia("scikit-learn", "pip install scikit-learn")
    except Exception as e:
        st.error(f"Error geoespacial: {e}")


# ============================================================
# 11. BARRA LATERAL (controles globales)
# ============================================================

with st.sidebar:
    st.markdown("<div class='sb-title'>🌿 Panel de control</div>", unsafe_allow_html=True)
    st.slider("Altura de gráficos", 300, 700, 440, 20, key="altura_graf")
    st.toggle("Mostrar ayudas contextuales", value=True, key="mostrar_ayuda")
    st.divider()

# ============================================================
# 12. ENCABEZADO
# ============================================================

st.markdown(
    """
    <div class="hero">
      <div class="hero-title">🌿 Laboratorio experimental de biodiversidad</div>
      <div class="hero-sub">Entorno de experimentación para el procesamiento y análisis
      multimodal de información biológica.</div>
      <span class="chip">Bioacústica</span><span class="chip">Visión por computador</span>
      <span class="chip">Procesamiento de texto</span><span class="chip">Inteligencia geoespacial</span>
    </div>
    """,
    unsafe_allow_html=True,
)
st.info("Los procedimientos experimentales generan resultados derivados. "
        "Los archivos originales no se sobrescriben.")

# ============================================================
# 13. NAVEGACIÓN
# ============================================================

tab_audio, tab_imagen, tab_texto, tab_geo = st.tabs([
    "Bioacústica", "Visión por computador", "Procesamiento de texto", "Inteligencia geoespacial"
])

with tab_audio:
    panel_audio()
with tab_imagen:
    panel_imagen()
with tab_texto:
    panel_texto()
with tab_geo:
    panel_geo()

# ============================================================
# 14. BITÁCORA (barra lateral) Y PIE
# ============================================================

with st.sidebar:
    bit = st.session_state.get("bitacora", [])
    st.metric("Operaciones registradas", len(bit))
    with st.expander("Bitácora de sesión", expanded=False):
        if bit:
            for r in reversed(bit[-25:]):
                st.markdown(f"`{r['hora']}` {r['evento']}")
        else:
            st.caption("Aún no hay operaciones.")
    if bit:
        st.download_button("Descargar bitácora", descargar_csv(pd.DataFrame(bit)),
                           "bitacora_sesion.csv", "text/csv", key="d_bitacora")
        if st.button("Limpiar bitácora", key="b_limpiar"):
            st.session_state.bitacora = []
            st.rerun()

st.divider()
st.caption(
    "Laboratorio experimental de biodiversidad | Los resultados son derivados "
    "y no sustituyen los registros originales."
)