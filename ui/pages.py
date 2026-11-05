"""Interfaz única en Streamlit (req. 8, 9, 15, 188-190). No contiene lógica de análisis: delega todo en `core.engine.Motor`."""

from __future__ import annotations

from html import escape

import pandas as pd

import streamlit as st

from core import registry

from core.errors import describir

from data import loaders

from visualization import widgets

from data import db

CFG_PLOT = {"displaylogo": False}

TIPOS = ["img", "audio", "texto", "geo"]

# ------------------------------------------------------------------ utilidades
def parametros(entrada, tipo, key):

    v = {}

    for p in entrada.params:

        if (p.tipos and tipo not in p.tipos) or (p.si and v.get(p.si[0]) != p.si[1]):

            continue

        k = f"{key}_{p.clave}"

        dfl = st.session_state.get("_pendientes", {}).pop(k, p.defecto)  # valor aplicado desde «Sugerir parámetros»

        if p.opciones:

            v[p.clave] = st.selectbox(p.etiqueta, p.opciones, p.opciones.index(dfl if dfl in p.opciones else p.defecto), key=k)

        elif isinstance(p.defecto, float):

            v[p.clave] = st.number_input(p.etiqueta, p.min, p.max, float(dfl), p.paso, format="%.4f" if p.paso < 0.01 else "%.2f", key=k)

        else:

            v[p.clave] = st.slider(p.etiqueta, p.min, p.max, int(dfl), key=k)

    return v

def kpis(d, res):

    cifras = {"Muestras": f"{d.n:,}", "Características": d.X.shape[1], **res.kpis}

    st.markdown('<div class="kpis">' + "".join(f"<div class='kpi'><b>{escape(str(v))}</b><span>{escape(k)}</span></div>" for k, v in cifras.items()) + "</div>",

                unsafe_allow_html=True)

def mostrar_error(e):

    inf = describir(e) if isinstance(e, BaseException) else e

    st.error(f"**{inf['codigo']}** · {inf['mensaje']}")

    if inf.get("detalle"):

        st.caption(inf["detalle"])

def mb(b):

    return f"{b / 2**20:.1f} MB"

# ------------------------------------------------------------------ seguimiento de tareas en segundo plano
def seguimiento(m, clave):

    """Muestra progreso y botón Cancelar mientras la tarea corre; devuelve la tarea terminada (o None)."""

    t = st.session_state.get(clave)

    if t is None:

        return None

    if t.activa:

        @st.fragment(run_every=0.7)

        def _vivo():

            if not t.activa:

                st.rerun()

            st.progress(t.ctx.progreso, text=f"{t.nombre} · {t.ctx.mensaje or 'en curso'} · {t.duracion:.0f} s")

            if st.button("Cancelar", key=f"cancelar_{clave}"):

                m.tareas.cancelar(t.id)

        _vivo()

        return None

    st.session_state.pop(clave)

    if t.estado == "fallida":

        mostrar_error(t.error)

    elif t.estado == "cancelada":

        st.warning("Tarea cancelada: no se modificó ningún archivo ni estado.")

    return t if t.estado == "terminada" else None

# ------------------------------------------------------------------ resultados
def seleccion(d, idx):

    if not len(idx):

        st.caption("Dibuja una caja o un lazo (polígono) sobre el gráfico para ver qué son esas muestras.")

        return

    st.markdown(f"**{len(idx)} muestras seleccionadas**" + (" · se muestran 24" if len(idx) > 24 else ""))

    sub = idx[:24]

    meta = pd.DataFrame([{k: v for k, v in (d.meta[i] if d.meta else {}).items() if k in ("archivo", "event_id", "especie", "clase", "licencia", "creador", "fecha", "campo", "pais")}

                         | {"muestra": d.hover[i]} for i in sub])

    st.dataframe(meta, hide_index=True)

    from visualization import media

    if d.tipo == "img":

        st.image([media.parche(d.recursos[d.ref[i][0]], d.ref[i][1], d.ref[i][2]) for i in sub], width=76)

    elif d.tipo == "audio":

        for i in sub[:3]:

            n, t = d.ref[i]

            st.caption(f"{n} · {t:.1f} s")

            st.audio(media.fragmento_audio_bytes(d.recursos[n], t, 3), format="audio/wav")

    elif d.tipo == "texto":

        for i in sub[:6]:

            st.markdown(f"> {d.ref[i][:320]}{'…' if len(d.ref[i]) > 320 else ''}")

def mostrar_algoritmo(s):

    from visualization import charts as G

    d, res, k = s.datos, s.res, f"{s.tipo}_{s.nombre}"

    st.caption(d.descripcion + (" · ♻ reutilizado de la caché" if s.desde_cache else f" · {s.duracion_s:.1f} s" + (f" · {s.memoria_mb:.0f} MB" if s.memoria_mb else "")))

    for a in d.avisos or []:

        st.warning(a)

    kpis(d, res)

    if res.Z is not None:

        c = st.columns([1.3, 1.4, 1.4, 1, 1])

        vistas = (["Mapa"] if d.mapa is not None else []) + ["2D"] + (["3D"] if res.Z.shape[1] >= 3 else [])

        vista = c[0].radio("Vista", vistas, horizontal=True, key=k + "v")

        colores = ["Grupo" if res.etiquetas is not None else "KMeans"] + (["Archivo"] if len(set(d.origen)) > 1 else []) + ["Variable", "Ninguno"]

        color = c[1].selectbox("Color por", colores, key=k + "c")

        variable, kk = None, 3

        if color == "Variable":

            variable = c[2].selectbox("Variable", d.nombres, key=k + "x")

        elif color == "KMeans":

            kk = c[2].slider("k", 2, 15, 3, key=k + "k")

        tam = c[3].slider("Tamaño", 1, 15, 5, key=k + "t")

        opac = c[4].slider("Opacidad", 0.1, 1.0, 0.8, key=k + "o")

        fig = G.dispersion(d, res, vista, color, tam, opac, variable, kk)

        if vista == "2D":

            ev = st.plotly_chart(fig, theme=None, config=CFG_PLOT, key=k + "m2d", on_select="rerun", selection_mode=("box", "lasso"))

            seleccion(d, G.indices_seleccion(res.Z, ev.selection))

        else:

            st.plotly_chart(fig, theme=None, config=CFG_PLOT, key=k + "m" + vista)

    figuras = list(res.figuras)

    if res.Z is None and figuras:

        f0 = figuras.pop(0)

        st.plotly_chart(f0, theme=None, config=CFG_PLOT, key=k + "f0")

    for i in range(0, len(figuras), 2):

        for j, (col, f) in enumerate(zip(st.columns(2), figuras[i:i + 2])):

            col.plotly_chart(f, theme=None, config=CFG_PLOT, key=f"{k}f{i + j + 1}")

    st.markdown(res.informe)

    if res.tabla is not None:

        st.dataframe(res.tabla, hide_index=True)

    from ui.paneles import explorar_grupos

    explorar_grupos(d, res, k + "_eg")

def mostrar_comparativa(s):

    d, res, k = s.datos, s.res, f"cmp_{s.tipo}_{s.nombre}"

    st.caption(d.descripcion + (" · ♻ reutilizado de la caché" if s.desde_cache else f" · {s.duracion_s:.1f} s"))

    for a in d.avisos or []:

        st.warning(a)

    kpis(d, res)

    st.markdown(res.informe)

    for i, f in enumerate(res.figuras):  # figura suelta = ancho completo; tupla = columnas (original | procesado)

        grupo = f if isinstance(f, tuple) else (f,)

        for j, (col, fig) in enumerate(zip(st.columns(len(grupo)), grupo)):

            col.plotly_chart(fig, theme=None, config=CFG_PLOT, key=f"{k}_f{i}_{j}")

    if res.tabla is not None:

        st.dataframe(res.tabla, hide_index=True)

def descargas(m, s, key):

    from visualization.charts import a_html, a_png

    c = st.columns(3)

    c[0].download_button("Exportar experimento (ZIP)", m.exportar(s), f"{s.run_id}.zip", "application/zip", key=key + "zip")

    if s.res.figuras:

        c[1].download_button("Gráficos (HTML interactivo)", a_html(s.res.figuras), f"{s.run_id}.html", "text/html", key=key + "html")

        primera = next(iter(f for g in s.res.figuras for f in (g if isinstance(g, tuple) else (g,))))

        png = a_png(primera)

        if png:

            c[2].download_button("Primer gráfico (PNG)", png, f"{s.run_id}.png", "image/png", key=key + "png")

        else:

            c[2].caption("PNG: instale `kaleido` (opcional).")

# ------------------------------------------------------------------ pestaña DATOS (adquisición)
def pagina_datos(m):

    r = m.resumen()

    with m.bd() as con:

        conjuntos = db.conjuntos_experimentales(con)

    n_multi = len(conjuntos["multimodal"])

    n_anomalias = len(conjuntos["anomalias"])

    st.subheader("Disponibilidad para los objetivos de investigación")

    c1, c2 = st.columns(2)

    with c1:

        st.metric(

            "Eventos multimodales comparables",

            n_multi,

            help="Eventos con audio e imagen descargados correctamente."

        )

    with c2:

        st.metric(

            "Eventos para control de calidad",

            n_anomalias,

            help="Todos los eventos registrados, incluidos los incompletos."

        )

    kpis_ = {"Eventos": r["eventos"], "Audios": f"{r['audios_ok']}/{r['audios']}", "Imágenes": f"{r['imagenes_ok']}/{r['imagenes']}",

             "Puntos": r["puntos"], "Textos BD": r["textos_bd"], "Locales": r["documentos"], "Inválidos": r.get("invalidos", 0), "Pendientes": r["pendientes"]}

    st.markdown('<div class="kpis">' + "".join(f"<div class='kpi'><b>{v}</b><span>{k}</span></div>" for k, v in kpis_.items()) + "</div>", unsafe_allow_html=True)

    if r["eventos"] == 0 and r["documentos"] == 0:

        st.info("La base está vacía. Importe su proyecto alternativo, suba archivos, indique una carpeta o recolecte registros de GBIF.")

    a, b = st.columns(2)

    with a, st.container(border=True):

        st.subheader("Cargar archivos locales")

        subidos = st.file_uploader("Audio, imágenes, texto (TXT, MD, PDF) o coordenadas (CSV, JSON, GeoJSON)", accept_multiple_files=True, key="subida")

        if st.button("Incorporar archivos", disabled=not subidos, key="bt_subida"):

            inf = m.ingerir([(f.name, f.getvalue()) for f in subidos])

            informe_ingesta(inf)

        carpeta = st.text_input("…o una carpeta del equipo (se incorpora con sus subcarpetas)", key="carpeta", placeholder=r"C:\datos\mis_archivos")

        if st.button("Incorporar carpeta", disabled=not carpeta, key="bt_carpeta"):

            try:

                informe_ingesta(m.ingerir_carpeta(carpeta))

            except Exception as e:  # noqa: BLE001

                mostrar_error(e)

        st.caption("El contenido se guarda por SHA-256: un archivo repetido no se almacena dos veces.")

    with b, st.container(border=True):

        st.subheader("Recursos remotos autorizados")

        url = st.text_input("URL (http/https)", key="url")

        tipo_u = st.selectbox("Tipo", TIPOS, format_func=lambda t: loaders.NOMBRES[t], key="tipo_url")

        if st.button("Descargar URL", disabled=not url, key="bt_url"):

            try:

                informe_ingesta(m.ingerir_url(url, tipo_u))

            except Exception as e:  # noqa: BLE001

                mostrar_error(e)

        st.caption("Se bloquean direcciones privadas, credenciales en la URL y redirecciones inseguras.")

    c, d = st.columns(2)

    with c, st.container(border=True):

        st.subheader("Ingesta multimodal desde fuentes externas")

        obj = st.slider("Límite aproximado de registros nuevos", 30, 600, 180, 30, key="multi_obj")

        xc_key = st.text_input("Clave API de Xeno-canto (opcional)", type="password", key="xc_api_key",

                               help="También puedes definir NS_XENO_CANTO_API_KEY en el entorno. No se guarda en la base de datos.")

        if st.button("Consultar iNaturalist + Xeno-canto + GBIF", key="bt_multifuente"):

            st.session_state["t_multifuente"] = m.lanzar_multifuente(obj, xc_key or None)

        t_multi = seguimiento(m, "t_multifuente")

        if t_multi is not None:

            resultado = t_multi.resultado

            if isinstance(resultado, dict):

                for fuente, info in resultado.items():

                    st.write(f"**{fuente}:** {info.get('agregados', 0)} registros")

                    if info.get("omitido"):

                        st.caption(info["omitido"])

                    if info.get("error"):

                        st.warning(info["error"])

            else:

                st.success(f"Terminado: {resultado}")

        st.divider()

        st.subheader("Descargas de medios pendientes")

        lim = st.number_input("Máx. archivos por descarga (0 = todos)", 0, 5000, 0, key="lim_desc")

        if st.button(f"Descargar pendientes ({r['pendientes']})", disabled=r["pendientes"] == 0, key="bt_desc"):

            st.session_state["t_desc"] = m.lanzar_descarga(None, lim or None)

        t = seguimiento(m, "t_desc")

        if t is not None:

            st.success(f"Terminado: {t.resultado}")

        st.caption("Primero se guardan metadatos y URLs. Los archivos se descargan después y las características se calculan bajo demanda.")

    with d, st.container(border=True):

        st.subheader("Importar el proyecto alternativo")

        ruta = st.text_input("Carpeta del proyecto alternativo (fauna_sonora) o ruta a su fauna.db", key="legado",

                             placeholder=r"C:\Users\...\Downloads\fauna_sonora", help="Puede pegarla con o sin comillas («Copiar como ruta» de Windows).")

        medios = st.checkbox("Copiar también audio e imágenes", True, key="legado_medios")

        if st.button("Importar", disabled=not ruta or getattr(st.session_state.get("t_legado"), "activa", False), key="bt_legado"):

            st.session_state["t_legado"] = m.lanzar_importacion(ruta, medios)

            st.rerun()

        t = seguimiento(m, "t_legado")

        if t is not None:

            st.session_state["rep_legado"] = t.resultado

        if st.session_state.get("rep_legado"):

            from ui.paneles import informe_importacion

            informe_importacion(st.session_state["rep_legado"])

    # ADQUISICIÓN MULTIMODAL DESDE INATURALIST
    with st.container(border=True):

        st.subheader("Adquisición de biodiversidad desde iNaturalist")

        st.markdown("""

        Obtiene observaciones georreferenciadas para comparar

        modalidades y estudiar la calidad de los registros.

        """)

        c1, c2, c3 = st.columns(3)

        with c1:

            cantidad = st.number_input(

                "Número de observaciones",

                min_value=10,

                max_value=1000,

                value=100,

                step=10,

                key="inat_cantidad"

            )

        with c2:
            
            grupos_biologicos = {
                "Aves": "Aves",
                "Anfibios": "Amphibia",
                "Mamíferos": "Mammalia",
                "Reptiles": "Reptilia",
                "Insectos": "Insecta",
                "Arácnidos": "Arachnida",
                "Peces óseos": "Actinopterygii",
                "Moluscos": "Mollusca",
                "Plantas": "Plantae",
                "Hongos": "Fungi"
                }

            grupo = st.selectbox(
                "Grupo biológico",
                list(grupos_biologicos),
                key="inat_grupo"
                
            )
            
            grupo = grupos_biologicos[grupo]

        with c3:

            modalidad = st.selectbox(

                "Modalidad de adquisición",

                ["ambos", "imagen", "audio"],

                format_func=lambda x: {

                    "ambos": "Imagen + audio",

                    "imagen": "Solo imágenes",

                    "audio": "Solo audio"

                }[x],

                key="inat_modalidad"

            )

        st.caption(

            "Los registros se incorporan a la base existente. "

            "Los archivos multimedia quedan pendientes de descarga."

        )

        if st.button(

            "Consultar e incorporar observaciones",

            key="bt_inaturalist"

        ):

            st.session_state["t_inat"] = m.lanzar_inaturalist(

                int(cantidad),

                grupo,

                modalidad

            )

        tarea = seguimiento(m, "t_inat")

        if tarea is not None:

            st.success(

                f"Adquisición finalizada: {tarea.resultado} "

                "observaciones incorporadas."

            )

def informe_ingesta(inf):

    if inf["agregados"]:

        st.success(f"{len(inf['agregados'])} archivos incorporados")

    if inf["duplicados"]:

        st.info(f"{len(inf['duplicados'])} ya existían (mismo contenido) y no se duplicaron")

    for n, motivo in inf["rechazados"]:

        st.warning(f"Rechazado {n}: {motivo}")

    for n, motivo in inf.get("avisos", []):

        st.caption(f"{n}: {motivo}")

# ------------------------------------------------------------------ explorar
def explorar(m, tipo, sel):

    from visualization import media

    if tipo == "img":

        widgets.mostrar("orbit.html", {"imgs": [{"n": r.nombre, "u": media.miniatura(r.ruta)} for r in sel[:14]], "titulo": f"{len(sel)} imágenes"}, 540)

        if len(sel) > 14:

            st.caption("La órbita y la galería muestran las primeras 14 imágenes.")

        with st.expander("Explorador de parches"):

            r = st.selectbox("Imagen", sel, format_func=lambda x: x.nombre, key="parches_img")

            ps = media.parches_png(r.ruta)

            st.image([p for _, _, p in ps], width=64, caption=[f"({y // 32},{x // 32})" for y, x, _ in ps])

    elif tipo == "audio":

        pistas = []

        for r in sel[:8]:

            try:

                pistas.append({"n": r.nombre, "u": media.fragmento_audio(r.ruta)})

            except Exception as e:  # noqa: BLE001

                st.caption(f"{r.nombre}: {e}")

        widgets.mostrar("audio.html", {"pistas": pistas}, 340)

        st.caption("Se reproducen fragmentos de 20 s (no se carga el archivo completo).")

    elif tipo == "texto":

        docs = [{"n": r.nombre, "t": media.texto(r.ruta)} for r in sel[:6] if r.ruta]

        if docs:

            widgets.mostrar("texto.html", {"docs": docs}, 380)

        for r in sel:

            if r.virtual:

                with m.bd() as con:

                    filas = con.execute("SELECT event_id, field, original FROM texts WHERE TRIM(COALESCE(original,''))<>'' LIMIT 200").fetchall()

                st.dataframe(pd.DataFrame([dict(f) for f in filas]), hide_index=True)

    else:

        datos = media.explorador_mapa(sel, m.recursos("img"), m.recursos("audio"), m.cfg)

        widgets.mostrar("mapa.html", datos, 660)

# ------------------------------------------------------------------ panel por tipo
def panel(m, tipo, prep, max_m):

    recursos = m.recursos(tipo)

    if not recursos:

        st.info(f"No hay recursos de {loaders.NOMBRES[tipo].lower()}. Use la pestaña *Datos* para cargarlos o importarlos.")

        return

    a, b = st.columns([1.5, 3])

    modo = a.segmented_control("Modo", ["Explorar", "Calidad", "Algoritmos", "Comparativas", "Multi"], default="Explorar", key=f"{tipo}_modo", label_visibility="collapsed") or "Explorar"

    por = {r.nombre: r for r in recursos}

    nombres = b.multiselect("Recursos", list(por), list(por), key=f"{tipo}_sel", label_visibility="collapsed")

    sel = [por[n] for n in nombres]

    if not sel:

        st.info("Seleccione al menos un recurso.")

        return

    if modo == "Explorar":

        explorar(m, tipo, sel)

    elif modo == "Calidad":

        calidad(m, tipo, sel, max_m)

    elif modo == "Multi":

        multi(m, tipo, sel, prep, max_m)

    else:

        ejecutar_panel(m, tipo, sel, prep, max_m, "comparativa" if modo == "Comparativas" else "algoritmo")

def calidad(m, tipo, sel, max_m):

    if st.button("Calcular resumen de calidad", key=f"{tipo}_cal"):

        try:

            with st.spinner("Extrayendo características (se guardan en caché)…"):

                q = m.calidad(tipo, sel, max_m)

        except Exception as e:  # noqa: BLE001

            mostrar_error(e)

            return

        st.markdown('<div class="kpis">' + "".join(f"<div class='kpi'><b>{v}</b><span>{k}</span></div>" for k, v in

                    {"Muestras": q["muestras"], "Variables": q["variables"], "NaN": q["nan"], "Infinitos": q["inf"], "Constantes": len(q["constantes"]),

                     "Duplicadas": q["duplicados"]}.items()) + "</div>", unsafe_allow_html=True)

        for a_ in q["advertencias"]:

            st.warning(a_)

        if not q["advertencias"]:

            st.success("Sin problemas de calidad detectados.")

        if q["descriptivas"] is not None:

            st.dataframe(q["descriptivas"], hide_index=True)

        else:

            st.caption(f"Matriz dispersa · rango {q['rango']}")

    if st.button("Extraer y guardar características (sin ejecutar algoritmos)", key=f"{tipo}_pre"):

        st.session_state[f"t_pre_{tipo}"] = m.lanzar_precarga(tipo, sel)

    t = seguimiento(m, f"t_pre_{tipo}")

    if t is not None:

        st.success(t.resultado)

def ejecutar_panel(m, tipo, sel, prep, max_m, clase):

    reg = registry.algoritmos(tipo) if clase == "algoritmo" else registry.comparativas(tipo)

    izq, der = st.columns([1.55, 3.4], gap="large")

    with izq, st.container(border=True):

        nombre = st.selectbox("Algoritmo" if clase == "algoritmo" else "Comparativa", list(reg), key=f"{tipo}_{clase}")

        e = reg[nombre]

        st.caption(e.descripcion)

        if e.supervisado or e.notas:

            st.warning(e.notas or "Método supervisado / heredado.")

        vals = parametros(e, tipo, f"{tipo}_{clase}_{nombre}")

        if clase == "algoritmo":

            from ui.paneles import estimacion, sugerir

            sugerir(m, tipo, sel, nombre, e, prep, max_m, f"{tipo}_{clase}_{nombre}", vals)

            estimacion(m, tipo, sel, nombre, max_m)

        archivo = None

        if tipo in e.archivo:

            archivo = st.selectbox("Archivo", sel, format_func=lambda r: r.nombre, key=f"{tipo}_{clase}_{nombre}_arch")

        clave_t = f"t_{tipo}_{clase}"

        corre = getattr(st.session_state.get(clave_t), "activa", False)

        if st.button("Ejecutar", type="primary", key=f"{tipo}_{clase}_run", disabled=corre):

            st.session_state[clave_t] = m.lanzar_ejecucion(tipo, sel, nombre, vals, prep, clase, archivo, max_m)

            st.rerun()

    with der:

        t = seguimiento(m, clave_t)

        if t is not None:

            st.session_state[("sal", tipo, clase)] = t.resultado

        s = st.session_state.get(("sal", tipo, clase))

        if s is None:

            st.info("Ajuste los parámetros y pulse *Ejecutar*. La tarea corre en segundo plano y puede cancelarse.")

            return

        st.subheader(s.nombre)

        (mostrar_algoritmo if clase == "algoritmo" else mostrar_comparativa)(s)

        descargas(m, s, f"{tipo}_{clase}_dl")

def multi(m, tipo, sel, prep, max_m):

    """Varios algoritmos (ranking multicriterio), sensibilidad de un parámetro o estabilidad (req. 101, 102)."""

    agrupadores = [n for n, e in registry.algoritmos(tipo).items() if n in ("Agrupación · KMeans", "Clusterización jerárquica", "DBSCAN · HDBSCAN", "Modelo mixto gaussiano", "Agrupación por escaneo (OPTICS)")]

    izq, der = st.columns([1.55, 3.4], gap="large")

    with izq, st.container(border=True):

        modo = st.radio("Comparar", ["Varios algoritmos", "Sensibilidad de un parámetro", "Estabilidad"], key=f"{tipo}_multi_modo")

        kw = {}

        if modo == "Varios algoritmos":

            todos = st.checkbox("Todos los algoritmos de agrupación (panel general)", key=f"{tipo}_multi_todos")

            algs = agrupadores if todos else st.multiselect("Algoritmos", agrupadores, agrupadores[:3], key=f"{tipo}_multi_algs")

            kw = dict(modo="algoritmos", algoritmos=algs)

        else:

            alg = st.selectbox("Algoritmo", agrupadores, key=f"{tipo}_multi_alg")

            e = registry.obtener(alg)

            base = parametros(e, tipo, f"{tipo}_multi_base_{alg}") if modo == "Estabilidad" else {}

            if modo == "Sensibilidad de un parámetro":

                num = [p for p in e.params if isinstance(p.defecto, (int, float)) and not p.opciones]

                par = st.selectbox("Parámetro", num, format_func=lambda p: p.etiqueta, key=f"{tipo}_multi_par")

                txt = st.text_input("Valores separados por coma", ", ".join(str(x) for x in ([2, 3, 4, 5] if isinstance(par.defecto, int) else [par.defecto, par.defecto * 2])), key=f"{tipo}_multi_vals")

                try:

                    vals = [(int(x) if isinstance(par.defecto, int) else float(x)) for x in txt.split(",") if x.strip()]

                except ValueError:

                    vals = []

                    st.warning("Escriba números separados por coma.")

                kw = dict(modo="parametros", algoritmo=alg, parametro=par.clave, valores=vals)

            else:

                kw = dict(modo="estabilidad", algoritmo=alg, base=base)

        reps = st.slider("Repeticiones de submuestreo (estabilidad)", 2, 10, 3 if modo != "Estabilidad" else 8, key=f"{tipo}_multi_reps")

        est = True if modo == "Estabilidad" else st.checkbox("Medir estabilidad (más lento)", True, key=f"{tipo}_multi_est")

        if st.button("Comparar", type="primary", key=f"{tipo}_multi_run", disabled=getattr(st.session_state.get(f"t_{tipo}_multi"), "activa", False)):

            st.session_state[f"t_{tipo}_multi"] = m.lanzar_comparacion(tipo, sel, prep=prep, max_muestras=max_m, estabilidad=est, repeticiones=reps, **kw)

            st.rerun()

        st.caption("Ranking multicriterio: promedio del puesto en silueta, Davies-Bouldin, Calinski-Harabasz, ruido, equilibrio y estabilidad. "

                   "Las configuraciones con un solo grupo o casi todo ruido se marcan como no comparables.")

    with der:

        t = seguimiento(m, f"t_{tipo}_multi")

        if t is not None:

            st.session_state[("sal", tipo, "multi")] = t.resultado

        s = st.session_state.get(("sal", tipo, "multi"))

        if s is None:

            st.info("Elija qué comparar y pulse *Comparar*.")

            return

        mostrar_comparativa(s)

        descargas(m, s, f"{tipo}_multi_dl")

# ------------------------------------------------------------------ experimentos y sistema
def pagina_experimentos(m):

    h = m.historial(100)

    if h.empty:

        st.info("Todavía no hay ejecuciones registradas.")

        return

    st.dataframe(h.drop(columns=[c for c in ("clave_resultado", "versiones", "huella") if c in h]), hide_index=True)

    from ui.paneles import comparar_ejecuciones

    comparar_ejecuciones(m, h)

    ok = h[h.clave_resultado.notna()]

    if ok.empty:

        return

    r = st.selectbox("Reabrir un resultado guardado", ok.run_id, format_func=lambda i: f"{i} · {ok[ok.run_id == i].nombre.iloc[0]} · {ok[ok.run_id == i].created_utc.iloc[0][:19]}")

    if st.button("Abrir", key="abrir_run"):

        fila = ok[ok.run_id == r].iloc[0]

        g = m.recuperar(fila.clave_resultado)

        if g is None:

            st.warning("El resultado ya no está en la caché; vuelva a ejecutarlo con los mismos parámetros (es reproducible).")

        else:

            from core.engine import Salida

            st.session_state["reabierto"] = Salida(g[0], g[1], r, fila.clave_resultado, fila.nombre, fila.clase, fila.tipo, {}, {}, True)

    s = st.session_state.get("reabierto")

    if s:

        st.subheader(s.nombre)

        (mostrar_algoritmo if s.clase == "algoritmo" else mostrar_comparativa)(s)

        descargas(m, s, "reab")

def pagina_sistema(m):

    e = m.estado_sistema()

    c = st.columns(4)

    c[0].metric("Memoria del proceso", f"{e['memoria_mb']:.0f} MB" if e["memoria_mb"] else "n/d")

    c[1].metric("Tareas activas", e["tareas_activas"])

    c[2].metric("Entradas de caché", e["cache_entradas"])

    c[3].metric("Trabajadores máx.", m.cfg.max_trabajadores)

    st.dataframe(pd.DataFrame([{"almacenamiento": k, "tamaño": mb(v)} for k, v in e["disco"].items()]), hide_index=True)

    a = st.columns(4)

    for col, (txt, que) in zip(a, [("Borrar temporales", "temporales"), ("Borrar miniaturas y clips", "derivados"), ("Borrar caché de resultados", "resultados"), ("Borrar toda la caché", "cache")]):

        if col.button(txt, key=f"lim_{que}"):

            st.success(f"Liberados {mb(m.limpiar(que))}" if que != "temporales" else f"{m.limpiar(que)} temporales eliminados")

    st.caption("Todo lo borrado se regenera bajo demanda; los archivos originales nunca se tocan.")

    if m.tareas.tareas:

        st.dataframe(pd.DataFrame([dict(tarea=t.nombre, estado=t.estado, segundos=round(t.duracion, 1), memoria_mb=t.mem_pico) for t in m.tareas.tareas.values()]), hide_index=True)

# ------------------------------------------------------------------ punto de entrada
def render(m):

    from ml.preprocessing import AUSENTES, ESCALADOS, Prep

    with st.sidebar:

        st.header("Ajustes")

        max_m = st.slider("Máx. muestras", 500, 10000, m.cfg.max_muestras, 500, help="Submuestreo reproducible para mantener ágiles los algoritmos.")

        m.cfg.semilla = st.number_input("Semilla aleatoria", 0, 99999, m.cfg.semilla)

        st.subheader("Preparación")

        prep = Prep(st.selectbox("Escalado", ESCALADOS, help="«auto»: estandariza audio e imágenes y deja TF-IDF y coordenadas sin tocar."),

                    st.selectbox("Valores ausentes", AUSENTES), st.checkbox("Quitar variables constantes", True))

        st.subheader("Qué es una muestra")

        gran = {"Fragmentos (parches / ventanas)": "fragmentos", "Archivo completo (un vector por ejemplar)": "archivo"}

        m.cfg.img_granularidad = gran[st.radio("Imágenes", list(gran), index=list(gran.values()).index(m.cfg.img_granularidad), key="gran_img",

                                               help="«Archivo completo»: color, textura y composición de cada imagen; permite comparar los grupos con la especie o la clase.")]

        m.cfg.audio_granularidad = gran[st.radio("Audio", list(gran), index=list(gran.values()).index(m.cfg.audio_granularidad), key="gran_audio",

                                                 help="«Archivo completo»: media y desviación de los descriptores de todas las ventanas de cada grabación.")]

        with st.expander("Límites de adquisición y de recursos"):

            m.cfg.max_audio_mb = st.number_input("Audio (MB)", 1, 500, m.cfg.max_audio_mb)

            m.cfg.max_imagen_mb = st.number_input("Imagen (MB)", 1, 200, m.cfg.max_imagen_mb)

            m.cfg.max_denso_mb = st.number_input("Máx. matriz densa (MB)", 64, 8192, m.cfg.max_denso_mb, 64,

                                                 help="Tope al convertir TF-IDF disperso a denso.")

            m.cfg.max_distancias_mb = st.number_input("Máx. matriz de distancias (MB)", 32, 4096, m.cfg.max_distancias_mb, 32,

                                                      help="Jerárquico: por encima se construye el árbol con una submuestra.")

        m.cfg.animaciones = st.checkbox("Animaciones", m.cfg.animaciones)

    if m.cfg.animaciones:

        widgets.mostrar("fx.html", alto=0)

        widgets.mostrar("hero.html", {"palabras": [x.upper() for x in loaders.NOMBRES.values()],

                                      "subtitulo": "Investigación de biodiversidad mediante análisis multimodal, descubrimiento de agrupamientos, comparación taxonómica y detección de anomalía. Audio, imágenes, texto y coordenadas con 12 algoritmos no supervisados, 13 comparativas original vs procesado, ranking multicriterio y control de calidad de datos."}, 190)

    else:

        st.title("Descubrimiento de patrones en biodiversidad")

        st.caption("Aprendizaje no supervisado multimodal · Análisis de especies · Detección de anomalías")

    with st.expander("Objetivo general y objetivos específicos", expanded=True):

        st.markdown("""

        ### Objetivo general

        Evaluar la capacidad de diferentes algoritmos de aprendizaje no

        supervisado para descubrir patrones y agrupamientos en registros

        de biodiversidad, mediante el análisis individual y combinado de

        características acústicas, visuales, textuales y geográficas,

        incorporando mecanismos de detección de anomalías y control de

        calidad de datos.

        ### Objetivos específicos

        **1. Caracterización multimodal**

        Extraer y representar características de audio, imágenes, textos

        y coordenadas geográficas de registros de biodiversidad.

        **2. Descubrimiento de agrupamientos**

        Aplicar algoritmos no supervisados para identificar estructuras

        y agrupamientos entre las observaciones.

        **3. Comparación de modalidades**

        Evaluar qué modalidad y combinación de modalidades permite

        recuperar mejor la estructura taxonómica de las especies,

        utilizando ARI y NMI como referencias externas.

        **4. Detección de anomalías**

        Identificar registros atípicos, inconsistencias geográficas,

        características anormales y posibles problemas de calidad.

        **5. Evaluación de calidad**

        Comparar los resultados obtenidos y generar indicadores que

        permitan priorizar la revisión de registros sospechosos.

        """)

    tabs = st.tabs(["Datos", "Calidad e inventario", *[loaders.NOMBRES[t] for t in TIPOS], "Experimentos", "Sistema"])

    from ui.paneles import pagina_calidad

    with tabs[0]:

        protegido(pagina_datos, m)

    with tabs[1]:

        protegido(pagina_calidad, m)

    for tab, t in zip(tabs[2:6], TIPOS):

        with tab:

            protegido(panel, m, t, prep, max_m)

    with tabs[6]:

        protegido(pagina_experimentos, m)

    with tabs[7]:

        protegido(pagina_sistema, m)

def protegido(fn, *args):

    """Una pestaña que falla muestra su error y no tumba el resto de la aplicación (sec. 8)."""

    try:

        fn(*args)

    except st.errors.StreamlitAPIException:

        raise

    except Exception as e:  # noqa: BLE001

        if type(e).__name__ in ("RerunException", "StopException"):

            raise

        mostrar_error(e)

        st.caption("El resto de pestañas sigue funcionando. Si el problema persiste, revise el registro en data_store/results/app.log.")

def recursos_comunes(m, tipo, event_ids):

    """

    Selecciona recursos de una modalidad que pertenecen

    a los mismos eventos del experimento multimodal.

    """

    seleccionados = [

        r for r in m.recursos(tipo)

        if r.meta.get("event_id") in event_ids

    ]

    # Orden estable para facilitar la comparación.
    return sorted(

        seleccionados,

        key=lambda r: (

            r.meta.get("event_id", ""),

            r.nombre

        )

    )
