# Panel de control del dataset de aves

## Requisitos
- Python 3.13 (el mismo intérprete donde ya funciona `psycopg`).
- PostgreSQL 18 en `127.0.0.1:5434`, base `aves_db`, PostGIS habilitado.
- Archivo `.env` existente y configurado. No se sobrescribe ni se incluye en este paquete.

## Instalación
Desde la carpeta `aves_dataset` en la terminal integrada de VS Code:

```powershell
python -m pip install -r requirements-dashboard.txt
```

## Arranque
```powershell
python -m streamlit run .\app.py
```

Se abrirá el navegador en la dirección local que indique Streamlit (normalmente `http://localhost:8501`). También puedes ejecutar `iniciar_panel.ps1`.

## Módulos
- **Resumen:** conteos de tablas, estado de medios y almacenamiento registrado.
- **Pipeline y descargas:** lanza cada etapa existente, observa el registro y detiene el proceso. El pipeline completo detiene la secuencia si una etapa falla.
- **Base de datos / CRUD:** consulta tablas del proyecto, edita celdas, inserta registros mediante JSON y elimina filas con confirmación. `spatial_ref_sys` es de solo lectura.
- **Modelo relacional:** genera el diagrama desde las claves foráneas reales, descarga Mermaid y el SQL.
- **Explorador geográfico:** mapa de observaciones; las coordenadas sensibles se redondean a 0,1 grados.
- **Exportación:** CSV/Parquet para tablas; GeoJSON, GeoPackage, KML y KMZ para observaciones. También ejecuta la exportación oficial del proyecto (Parquet + manifiesto + atribuciones).
- **Validación y bitácora:** muestra el informe y los registros locales de los procesos del panel.

## Precauciones
- El panel se diseñó para uso local y no incorpora autenticación web. No lo expongas a Internet ni uses `--server.address 0.0.0.0`.
- Las operaciones CRUD son directas sobre PostgreSQL. Haz respaldo antes de eliminaciones masivas.
- La etapa `init` crea tablas con `IF NOT EXISTS`; no borra datos existentes. `pairs_splits` reconstruye pares y particiones según la lógica del script original.
- La exportación geográfica mantiene la generalización de coordenadas sensibles. Para el conjunto completo, usa preferentemente `09_export.py`, que además aplica filtros de alcance y licencia.
- El pipeline completo ejecuta todas las etapas estándar salvo la descarga ambiental opcional. Esa etapa se lanza por separado.
- La interfaz consulta el esquema real; si alguna tabla aún no existe, no la inventa.
