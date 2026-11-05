"""Plataforma unificada de aprendizaje no supervisado.   Ejecutar:  streamlit run app.py"""
from pathlib import Path

import streamlit as st

from config import CFG
from ui import pages

st.set_page_config(page_title="Aprendizaje no supervisado", layout="wide")
st.markdown(f"<style>{(Path(__file__).parent / 'ui' / 'styles.css').read_text(encoding='utf-8')}</style>", unsafe_allow_html=True)


@st.cache_resource(show_spinner=False)
def motor():
    from core.engine import Motor

    return Motor(CFG)


pages.render(motor())
