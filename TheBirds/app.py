"""Panel local de control del dataset de aves."""
from __future__ import annotations
import os, sys, json, time, signal, subprocess, zipfile, io, xml.etree.ElementTree as ET
from pathlib import Path
from datetime import datetime
import pandas as pd
import streamlit as st
import psycopg
from psycopg import sql
from common import BASE_DIR, DATA_DIR, connect
from dashboard_db import (APP_TABLES, READ_ONLY, get_tables, table_columns, primary_keys,
                          fetch_table, update_rows, delete_rows, insert_row, overview, relationships)

st.set_page_config(page_title="Aves Dataset Control Center", page_icon="🪶", layout="wide")

# Estilo sobrio, sin dependencias externas.
st.markdown("""<style>
.block-container{padding-top:1.4rem;max-width:1600px}
[data-testid="stMetric"]{background:var(--secondary-background-color);padding:14px 16px;border-radius:12px;border:1px solid rgba(128,128,128,.15)}
.small-muted{color:var(--text-color);opacity:.68;font-size:.86rem}
</style>""", unsafe_allow_html=True)

st.title("🪶 Aves Dataset Control Center")
st.caption("Administración local · PostgreSQL 18 + PostGIS · Descargas, datos, modelo relacional y exportación")

# La conexión se resuelve desde common.py y el .env del proyecto.
try:
    con = connect(autocommit=True)
    server, db, user, port = con.execute("SELECT version(), current_database(), current_user, inet_server_port()").fetchone()
    postgis = con.execute("SELECT PostGIS_Full_Version()").fetchone()[0]
    connected = True
except Exception as exc:
    connected = False
    conn_error = str(exc)
    con = None

with st.sidebar:
    st.header("Control del proyecto")
    st.caption(f"Proyecto: `{BASE_DIR}`")
    if connected:
        st.success(f"Conectado · {db} · puerto {port}")
        st.caption("PostgreSQL 18 / PostGIS activo")
    else:
        st.error("Sin conexión a PostgreSQL")
        st.code(conn_error)
    st.divider()
    page = st.radio("Módulos", ["Resumen", "Pipeline y descargas", "Base de datos / CRUD", "Modelo relacional", "Explorador geográfico", "Exportación", "Validación y bitácora"], label_visibility="visible")
    st.divider()
    st.caption("Los procesos se ejecutan con el mismo intérprete de Python que inició Streamlit.")

if not connected:
    st.warning("No se puede cargar el panel porque no hay conexión a la base de datos. Comprueba `.env` y ejecuta `00_check_connection.py`.")
    st.stop()

# Estado del proceso iniciado desde esta sesión.
if "job" not in st.session_state:
    st.session_state.job = None
if "job_log" not in st.session_state:
    st.session_state.job_log = ""


def process_status():
    p = st.session_state.job
    if not p:
        return None
    code = p.poll()
    return "ejecutando" if code is None else ("completado" if code == 0 else f"fallido ({code})")


def start_job(stage=None, all_steps=False, workers=4, batch=20, max_gb=1.5, max_taxa=100, seed=20261106, langs=None):
    if process_status() == "ejecutando":
        st.error("Ya hay un proceso activo. Espera o cancélalo antes de iniciar otro.")
        return
    logdir = DATA_DIR / "logs"
    logdir.mkdir(parents=True, exist_ok=True)
    logpath = logdir / f"panel_{datetime.now():%Y%m%d_%H%M%S}.log"
    cmd = [sys.executable, "-u", str(BASE_DIR / "run_pipeline.py"), "--workers", str(workers),
           "--batch", str(batch), "--max-gb", str(max_gb), "--max-taxa", str(max_taxa), "--seed", str(seed)]
    if all_steps:
        cmd.append("--all")
    else:
        cmd += ["--stage", stage]
    if langs:
        cmd += ["--langs", *langs]
    fh = open(logpath, "w", encoding="utf-8")
    proc = subprocess.Popen(cmd, cwd=BASE_DIR, stdout=fh, stderr=subprocess.STDOUT,
                            creationflags=getattr(subprocess, "CREATE_NEW_PROCESS_GROUP", 0))
    st.session_state.job = proc
    st.session_state.job_log = str(logpath)
    st.session_state.job_log_handle = fh
    st.success(f"Proceso iniciado: {stage or 'pipeline completo'}")


def stop_job():
    p = st.session_state.job
    if p and p.poll() is None:
        p.terminate()
        st.warning("Se solicitó la detención del proceso. El script puede necesitar unos segundos para cerrar.")


def read_log():
    p = Path(st.session_state.job_log) if st.session_state.job_log else None
    if not p or not p.exists():
        return "Aún no hay salida de proceso."
    try:
        return p.read_text(encoding="utf-8", errors="replace")[-24000:]
    except Exception as e:
        return str(e)


def export_dataframe(df, fmt, stem):
    if fmt == "CSV":
        return df.to_csv(index=False).encode("utf-8-sig"), "csv", "text/csv"
    if fmt == "Parquet":
        b = io.BytesIO(); df.to_parquet(b, index=False); return b.getvalue(), "parquet", "application/octet-stream"
    if fmt in ("GeoJSON", "KML", "KMZ", "GeoPackage"):
        if not {"lat", "lon"}.issubset(df.columns):
            raise ValueError("La tabla debe contener columnas lat y lon.")
        from shapely.geometry import Point, mapping
        from shapely.geometry import shape
        valid = df.dropna(subset=["lat", "lon"]).copy()
        features = []
        for _, r in valid.iterrows():
            props = {k: (None if pd.isna(v) else (v.isoformat() if hasattr(v, "isoformat") else v.item() if hasattr(v, "item") else v))
                     for k, v in r.items() if k not in ("lat", "lon")}
            features.append({"type":"Feature", "geometry":mapping(Point(float(r.lon), float(r.lat))), "properties":props})
        gj = {"type":"FeatureCollection", "features":features}
        if fmt == "GeoJSON":
            return json.dumps(gj, ensure_ascii=False, default=str).encode(), "geojson", "application/geo+json"
        if fmt == "GeoPackage":
            import geopandas as gpd
            gdf = gpd.GeoDataFrame(valid, geometry=gpd.points_from_xy(valid.lon, valid.lat), crs="EPSG:4326")
            b=io.BytesIO();
            # GeoPackage writer expects a path; use a temporary file.
            import tempfile
            fd, tmpname = tempfile.mkstemp(suffix=".gpkg")
            os.close(fd)
            try:
                gdf.to_file(tmpname, driver="GPKG", layer=stem)
                data = Path(tmpname).read_bytes()
            finally:
                try: os.unlink(tmpname)
                except OSError: pass
            return data, "gpkg", "application/geopackage+sqlite3"
        kml = ET.Element("kml", xmlns="http://www.opengis.net/kml/2.2")
        doc = ET.SubElement(kml, "Document")
        for f in features:
            pm=ET.SubElement(doc,"Placemark")
            name=ET.SubElement(pm,"name"); name.text=str(f["properties"].get("scientific_name") or f["properties"].get("obs_id") or "Observación")
            desc=ET.SubElement(pm,"description"); desc.text=json.dumps(f["properties"], ensure_ascii=False, default=str)
            pt=ET.SubElement(ET.SubElement(pm,"Point"),"coordinates")
            pt.text=f"{f['geometry']['coordinates'][0]},{f['geometry']['coordinates'][1]},0"
        raw=ET.tostring(kml, encoding="utf-8", xml_declaration=True)
        if fmt == "KML": return raw, "kml", "application/vnd.google-earth.kml+xml"
        b=io.BytesIO()
        with zipfile.ZipFile(b,"w",zipfile.ZIP_DEFLATED) as z: z.writestr(f"{stem}.kml",raw)
        return b.getvalue(), "kmz", "application/vnd.google-earth.kmz"
    raise ValueError("Formato no soportado")

if page == "Resumen":
    st.subheader("Estado general")
    try:
        counts = overview(con)
        cols = st.columns(4)
        for col, (label, key) in zip(cols, [("Especies", "taxa"), ("Observaciones", "observations"), ("Medios", "media"), ("Pares", "pairs")]):
            val = counts.get(key)
            col.metric(label, "—" if val is None else f"{val:,}")
        st.markdown("#### Registros por tabla")
        stat_df = pd.DataFrame([{"Tabla":k,"Registros":v} for k,v in counts.items() if v is not None])
        st.dataframe(stat_df, use_container_width=True, hide_index=True)
        st.markdown("#### Descargas multimedia")
        if counts.get("media") is not None and counts["media"]:
            media_stats = pd.DataFrame(con.execute("SELECT type, download_status, count(*) AS n FROM media GROUP BY 1,2 ORDER BY 1,2").fetchall(), columns=["Tipo","Estado","Cantidad"])
            st.dataframe(media_stats, use_container_width=True, hide_index=True)
            by_status = media_stats.pivot(index="type", columns="download_status", values="n").fillna(0)
            st.bar_chart(by_status)
            size = con.execute("SELECT coalesce(sum(bytes),0) FROM media WHERE download_status='ok'").fetchone()[0]
            st.metric("Medios descargados", f"{size/1024**3:.3f} GB", help="Suma de bytes registrados en la tabla media")
        else:
            st.info("Aún no hay registros multimedia. Inicializa el esquema y ejecuta las etapas del pipeline.")
    except Exception as e:
        st.warning(f"El esquema todavía no está inicializado o faltan tablas: {e}")
    st.caption(f"Carpeta de datos: `{DATA_DIR}`")

elif page == "Pipeline y descargas":
    st.subheader("Ejecución de etapas")
    st.info("Las etapas se ejecutan usando los scripts existentes. El panel no modifica su lógica de descarga.")
    status = process_status()
    c1,c2,c3 = st.columns(3)
    c1.metric("Estado", status or "inactivo")
    c2.metric("Intérprete", Path(sys.executable).name)
    c3.metric("Registro", Path(st.session_state.job_log).name if st.session_state.job_log else "—")
    with st.expander("Parámetros", expanded=True):
        a,b,c,d = st.columns(4)
        workers = a.number_input("Trabajadores", 1, 16, 4)
        batch = b.number_input("Lote", 1, 500, 20)
        max_gb = c.number_input("Límite multimedia (GB)", 0.1, 20.0, 1.5, 0.1)
        max_taxa = d.number_input("Máximo de especies", 1, 1000, 100)
        seed = st.number_input("Semilla de selección", value=20261106)
        langs = st.multiselect("Idiomas de textos", ["es","en","pt","fr","de"], default=["es","en"])
    stages = [
        ("init","Inicializar esquema"), ("taxonomy","Seleccionar especies"),
        ("occurrences_image","Consultar ocurrencias de imágenes"), ("occurrences_audio","Consultar ocurrencias de audio"),
        ("texts","Recopilar textos"), ("download_image","Descargar imágenes"), ("download_audio","Descargar audios"),
        ("quality","Evaluar calidad multimedia"), ("pairs_splits","Crear pares y particiones"),
        ("environment","Datos ambientales (opcional)"), ("export","Exportación Parquet estándar"), ("validate","Validación final")]
    st.warning("La opción de pipeline completo incluye inicialización. Úsala solo si sabes que no hay datos previos que deban preservarse.")
    if status == "ejecutando":
        if st.button("Detener proceso", type="secondary"): stop_job()
    else:
        st.markdown("**Ejecutar una etapa**")
        grid = st.columns(3)
        for i,(key,label) in enumerate(stages):
            if grid[i%3].button(label, key=f"run_{key}", use_container_width=True):
                start_job(stage=key, workers=workers, batch=batch, max_gb=max_gb, max_taxa=max_taxa, seed=seed, langs=langs)
                st.rerun()
        if st.button("Ejecutar pipeline completo", type="primary", use_container_width=True):
            start_job(all_steps=True, workers=workers, batch=batch, max_gb=max_gb, max_taxa=max_taxa, seed=seed, langs=langs)
            st.rerun()
    st.markdown("#### Salida del proceso")
    st.code(read_log(), language="text")
    if st.button("Actualizar estado y registro"):
        st.rerun()
    if status in ("completado",) or (status and status.startswith("fallido")):
        st.caption("El proceso terminó. Revisa el registro antes de repetir la etapa.")

elif page == "Base de datos / CRUD":
    st.subheader("Explorador y mantenimiento de tablas")
    tables = [t for t in get_tables(con) if t in APP_TABLES or t in READ_ONLY]
    if not tables:
        st.warning("No hay tablas del proyecto. Ejecuta primero `01_init_db.py`.")
    else:
        table = st.selectbox("Tabla", tables)
        cols_meta = table_columns(con, table)
        pks = primary_keys(con, table)
        limit = st.select_slider("Filas a mostrar", options=[100,250,500,1000,2500], value=500)
        df = fetch_table(con, table, limit)
        st.caption(f"{len(df):,} filas mostradas · Clave primaria: {', '.join(pks) or 'no definida'}")
        if table in READ_ONLY or table not in APP_TABLES or not pks:
            st.dataframe(df, use_container_width=True, hide_index=True)
            st.info("Esta tabla se muestra en modo de solo lectura.")
        else:
            st.caption("Edita celdas y pulsa Guardar cambios. Las claves primarias no se modifican desde el editor.")
            edited = st.data_editor(df, use_container_width=True, hide_index=True, num_rows="fixed",
                disabled=pks, key=f"editor_{table}")
            if st.button("Guardar cambios", type="primary"):
                try:
                    n = update_rows(con, table, df, edited)
                    st.success(f"Cambios guardados: {n} fila(s).")
                    st.session_state.pop(f"editor_{table}", None)
                    st.rerun()
                except Exception as e: st.error(f"No se pudieron guardar los cambios: {e}")
            st.divider()
            with st.expander("Insertar registro"):
                st.caption("Introduce un objeto JSON. Omite columnas autogeneradas o con valores por defecto.")
                json_text = st.text_area("Registro JSON", value="{}", height=120, key=f"insert_{table}")
                if st.button("Insertar", key=f"insert_btn_{table}"):
                    try:
                        payload = json.loads(json_text)
                        if not isinstance(payload, dict): raise ValueError("El JSON debe ser un objeto.")
                        insert_row(con, table, payload)
                        st.success("Registro insertado."); st.rerun()
                    except Exception as e: st.error(f"No se pudo insertar: {e}")
            with st.expander("Eliminar registros"):
                if len(pks) == 1 and pks[0] in df.columns:
                    keys = st.multiselect(f"Selecciona {pks[0]} para eliminar", df[pks[0]].dropna().tolist(), key=f"del_{table}")
                    confirm = st.checkbox("Confirmo que deseo eliminar definitivamente estos registros", key=f"confirm_{table}")
                    if st.button("Eliminar seleccionados", disabled=not(keys and confirm), type="secondary"):
                        try:
                            n=delete_rows(con, table, keys); st.success(f"Eliminados: {n}"); st.rerun()
                        except Exception as e: st.error(f"Error al eliminar: {e}")
                else:
                    st.info("La eliminación requiere una clave primaria simple.")

elif page == "Modelo relacional":
    st.subheader("Modelo relacional detectado desde PostgreSQL")
    rels = relationships(con)
    tabs = [t for t in get_tables(con) if t in APP_TABLES]
    if not tabs:
        st.info("Inicializa el esquema para generar el modelo relacional.")
    else:
        lines = ["erDiagram"]
        dot = ["digraph schema {", "rankdir=LR;", "node [shape=record, fontsize=10];"]
        for t in tabs:
            cols = table_columns(con,t); pk = primary_keys(con,t)
            fields = "\\l".join([f"{r[0]} : {r[2]}{' PK' if r[0] in pk else ''}" for r in cols]) + "\\l"
            dot.append(f'"{t}" [label="{{{t}|{fields}}}"];')
            lines.append(f"  {t} {{")
            for r in cols: lines.append(f"    {r[2]} {r[0]}{' PK' if r[0] in pk else ''}")
            lines.append("  }")
        for child,col,parent,pcol in rels:
            if child in tabs and parent in tabs:
                lines.append(f"  {parent} ||--o{{ {child} : \"{col}\"")
                dot.append(f'"{parent}" -> "{child}" [label="{col} → {pcol}"];')
        dot.append("}")
        st.caption(f"{len(tabs)} tablas · {len(rels)} relaciones de clave foránea")
        st.graphviz_chart("\n".join(dot), use_container_width=True)
        st.download_button("Descargar modelo Mermaid ER", "\n".join(lines), "modelo_relacional.mmd", "text/plain")
        st.download_button("Descargar esquema SQL", (BASE_DIR/"sql"/"schema.sql").read_text(encoding="utf-8"), "schema.sql", "text/plain")
        st.markdown("#### Relaciones detectadas")
        st.dataframe(pd.DataFrame(rels, columns=["Tabla hija","Campo","Tabla padre","Campo padre"]), use_container_width=True, hide_index=True)

elif page == "Explorador geográfico":
    st.subheader("Distribución espacial de observaciones")
    if not all(t in get_tables(con) for t in ["observations","taxa"]):
        st.info("Inicializa el esquema y carga ocurrencias para habilitar el mapa.")
    else:
        total = con.execute("SELECT count(*) FROM observations WHERE lat IS NOT NULL AND lon IS NOT NULL").fetchone()[0]
        st.metric("Observaciones georreferenciadas", f"{total:,}")
        if total:
            species = con.execute("SELECT DISTINCT t.scientific_name FROM taxa t JOIN observations o USING(taxon_key) ORDER BY 1").fetchall()
            opts = [x[0] for x in species]
            chosen = st.multiselect("Filtrar especies", opts)
            query = """SELECT o.obs_id, t.scientific_name, o.continent, o.country_code, o.event_date,
                CASE WHEN o.sensitive THEN round(o.lat::numeric,1)::float8 ELSE o.lat END lat,
                CASE WHEN o.sensitive THEN round(o.lon::numeric,1)::float8 ELSE o.lon END lon
                FROM observations o JOIN taxa t USING(taxon_key) WHERE o.lat IS NOT NULL AND o.lon IS NOT NULL"""
            params=[]
            if chosen:
                query += " AND t.scientific_name = ANY(%s)"; params.append(chosen)
            query += " ORDER BY o.event_date DESC NULLS LAST LIMIT 5000"
            geo = pd.DataFrame(con.execute(query,params).fetchall(), columns=["obs_id","species","continent","country","date","lat","lon"])
            st.caption(f"Mostrando {len(geo):,} puntos como máximo. Coordenadas sensibles redondeadas a 0,1°.")
            st.map(geo.rename(columns={"lat":"latitude","lon":"longitude"})[["latitude","longitude"]].dropna())
            st.dataframe(geo, use_container_width=True, hide_index=True)

elif page == "Exportación":
    st.subheader("Exportar datos")
    existing = [t for t in APP_TABLES if t in get_tables(con)]
    if not existing:
        st.info("No hay tablas inicializadas.")
    else:
        table = st.selectbox("Tabla o conjunto", existing, key="export_table")
        formats = ["CSV","Parquet"]
        if table == "observations": formats += ["GeoJSON","GeoPackage","KML","KMZ"]
        fmt = st.selectbox("Formato", formats)
        max_rows = st.number_input("Máximo de filas (0 = todas)", min_value=0, value=0, step=1000)
        include_sensitive = st.checkbox("Mantener coordenadas generalizadas para registros sensibles", value=True, disabled=True)
        if st.button("Preparar exportación", type="primary"):
            try:
                q = sql.SQL("SELECT * FROM {}".format('"'+table+'"'))
                if table == "observations":
                    q = sql.SQL("""SELECT obs_id, source, source_id, dataset_key, taxon_key,
                        CASE WHEN sensitive THEN round(lat::numeric,1)::float8 ELSE lat END lat,
                        CASE WHEN sensitive THEN round(lon::numeric,1)::float8 ELSE lon END lon,
                        coord_uncertainty_m,country_code,continent,event_date,event_has_time,observer_hash,
                        basis_of_record,iucn_category,sensitive,split_observer,split_geo FROM observations""")
                if max_rows: q += sql.SQL(" LIMIT %s")
                cur=con.execute(q,(max_rows,) if max_rows else ())
                df=pd.DataFrame(cur.fetchall(),columns=[d.name for d in cur.description])
                data,ext,mime=export_dataframe(df,fmt,table)
                st.download_button("Descargar archivo",data,f"{table}.{ext}",mime)
                st.success(f"Exportación preparada: {len(df):,} filas.")
            except Exception as e: st.error(f"No se pudo exportar: {e}")
        st.divider()
        st.markdown("#### Exportación estándar del proyecto")
        st.caption("Genera Parquet, manifest.json y ATTRIBUTION.csv con las reglas de privacidad y licencias del script oficial.")
        if st.button("Ejecutar 09_export.py"):
            start_job(stage="export"); st.rerun()
        expdir=DATA_DIR/"export"
        if expdir.exists():
            for f in sorted(expdir.glob("*")):
                st.write(f"`{f.name}` · {f.stat().st_size/1024:.1f} KB")
                if f.is_file() and f.suffix.lower() in (".csv", ".parquet", ".json"):
                    st.caption(str(f))

elif page == "Validación y bitácora":
    st.subheader("Validación y registros de ejecución")
    report=DATA_DIR/"validation_report.json"
    if report.exists():
        try:
            data=json.loads(report.read_text(encoding="utf-8"))
            st.json(data)
            st.download_button("Descargar informe JSON", report.read_bytes(), "validation_report.json", "application/json")
        except Exception as e: st.error(f"No se pudo leer el informe: {e}")
    else: st.info("Todavía no existe validation_report.json. Ejecuta la etapa Validación final.")
    logdir=DATA_DIR/"logs"
    if logdir.exists():
        logs=sorted(logdir.glob("*.log"), key=lambda x:x.stat().st_mtime, reverse=True)
        st.markdown("#### Historial de procesos")
        if logs:
            chosen=st.selectbox("Registro", logs, format_func=lambda x:x.name)
            st.code(chosen.read_text(encoding="utf-8",errors="replace")[-30000:], language="text")
        else: st.caption("No hay registros del panel.")

try:
    con.close()
except Exception:
    pass
