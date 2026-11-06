# Cambios de la versión ajustada

- Pipeline dirigido a PostgreSQL 18 nativo; `01_init_db.py` comprueba versión y PostGIS antes de crear tablas.
- `common.py` carga `.env` desde la carpeta del proyecto, elimina credenciales predeterminadas y exige `USER_AGENT` y `OBSERVER_SALT`.
- Nueva tabla `dataset_scope`: solo 100 especies elegidas de forma reproducible se procesan aguas abajo.
- Muestreo reducido a 2 imágenes y 1 audio por especie/continente, máximo 1 medio por observación y 1 observador por consulta.
- Descarga con 4 workers, lotes de 20, archivos fuente limitados, WebP 512 px y OGG mono 32 kHz a 48 kbit/s.
- Presupuesto global configurable de 1.5 GB para binarios multimedia; los archivos restantes quedan pendientes para reanudar.
- WorldClim opcional y descarga de ZIP por streaming a temporal.
- Exportaciones filtradas al alcance seleccionado; se evita exportar accidentalmente taxonomía ajena a la muestra.
- Nuevo `00_check_connection.py` y `11_validate.py` para diagnóstico y validación final.
- No se elimina ni modifica automáticamente ninguna base de datos, volumen Docker o instalación PostgreSQL existente.

## Verificación realizada en el paquete

- Compilación sintáctica de todos los scripts Python (`compileall`).
- Revisión estática de consultas y referencias de tablas.
- No se ejecutaron descargas externas ni conexión a PostgreSQL desde este entorno; la verificación real de PostGIS 18 se hace en el equipo local.
