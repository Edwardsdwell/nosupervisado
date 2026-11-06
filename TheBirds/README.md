# Dataset multimodal propio de aves — PostgreSQL 18 + PostGIS

Pipeline reproducible para construir un dataset inicial de **100 especies** con imagen, audio, texto, coordenadas y variables ambientales. Los metadatos se almacenan en PostgreSQL 18/PostGIS; los binarios se guardan en disco y PostgreSQL conserva rutas, hashes, licencias y métricas. No se almacenan imágenes ni audios como BLOB.

## 1. Diseño compacto

- 100 especies seleccionadas aleatoriamente desde GBIF con semilla reproducible (`SPECIES_SEED`). La selección queda registrada en `dataset_scope` y `data/species_selection.csv`.
- Muestreo por especie y continente: 2 imágenes y 1 audio como máximo por continente; máximo 1 medio por observación y 1 registro por observador en la consulta.
- Imágenes: WebP, lado máximo 512 px, calidad 82; se prefiere el derivado `medium` de iNaturalist.
- Audio: OGG Vorbis, mono, 32 kHz, 48 kbit/s, máximo 30 s.
- Presupuesto inicial de archivos multimedia: 1.5 GB (`MAX_MEDIA_GB`). El descargador detiene la ejecución al llegar al presupuesto y deja el resto pendiente.
- Descargas por lotes pequeños, 4 trabajadores por defecto y reanudación desde PostgreSQL.
- WorldClim es opcional y no se descarga en el flujo mínimo.

El máximo teórico de la selección inicial es 2.100 registros multimedia (100 × 7 continentes × 3 medios), antes de disponibilidad, filtros de licencia, observaciones repetidas y el presupuesto de disco. No es una promesa de que existan esos registros.

## 2. Requisitos

- Windows 10/11 x64.
- PostgreSQL 18 nativo y PostGIS instalado para esa misma instalación de PostgreSQL 18.
- Python 3.11+ recomendado (el pipeline también usa psycopg 3 y dependencias científicas).
- FFmpeg disponible en `PATH` para convertir audio. Comprueba con `ffmpeg -version`.
- Espacio para la base de datos y 1.5 GB de medios, además de espacio temporal y copias de seguridad.

No ejecutes `docker compose up` para esta configuración nativa. El archivo `docker-compose.yml` se conserva como alternativa aislada, no forma parte del flujo principal.

## 3. Crear rol y base de datos en PostgreSQL 18

Primero identifica el puerto real de PostgreSQL 18. Si PostgreSQL 17 ya usa 5432, PostgreSQL 18 suele configurarse en otro puerto (por ejemplo 5433), pero confirma el valor en `postgresql.conf` (`port`). No asumas que es 5433.

En PowerShell, usa el `psql.exe` de PostgreSQL 18 (ajusta el puerto):

```powershell
& "C:\Program Files\PostgreSQL\18\bin\psql.exe" -h 127.0.0.1 -p 5433 -U postgres -d postgres
```

En `psql`, crea un rol y una base nuevos para este proyecto (si aún no existen):

```sql
CREATE ROLE aves LOGIN PASSWORD 'CAMBIA_ESTA_CLAVE';
CREATE DATABASE aves_birds OWNER aves;
```

Si el rol ya existe, no repitas `CREATE ROLE`; cambia su contraseña solo si sabes que es necesario. Conecta a `aves_birds` y habilita PostGIS:

```sql
\c aves_birds
CREATE EXTENSION postgis;
SELECT version(), PostGIS_Full_Version();
```

No borres ni reutilices automáticamente `aves_db` de PostgreSQL 17 ni el volumen de Docker. Esta configuración crea una base nueva y aislada en PostgreSQL 18.

## 4. Configurar Python

En la carpeta del proyecto:

```powershell
Copy-Item .env.example .env
notepad .env
```

Edita `DATABASE_URL` con el puerto real de PostgreSQL 18, la contraseña creada y `aves_birds`. Cambia `USER_AGENT` por un contacto real y `OBSERVER_SALT` por una cadena aleatoria privada de al menos 32 caracteres. No publiques `.env` ni la sal.

Instala dependencias:

```powershell
python -m pip install -r requirements.txt
ffmpeg -version
```

`common.py` carga `.env` desde la carpeta del propio proyecto, independientemente del directorio actual.

## 5. Ejecución por etapas

Desde la carpeta que contiene `common.py`:

```powershell
python 01_init_db.py
python 02_taxonomy.py --max-taxa 100 --seed 20261106
python 03_occurrences.py --media image
python 03_occurrences.py --media audio
python 04_texts.py --langs es en
python 05_download_media.py --type image --workers 4 --batch 20 --max-total-gb 1.5
python 05_download_media.py --type audio --workers 4 --batch 20 --max-total-gb 1.5
python 06_quality.py --workers 4
python 07_pairs_and_splits.py
python 09_export.py
python 11_validate.py
```

`02_taxonomy.py` no descarga toda la taxonomía. Si ya existe `dataset_scope`, conserva esa selección. Para cambiarla explícitamente: `python 02_taxonomy.py --max-taxa 100 --seed 20261106 --reset-selection`. Esto no borra observaciones ni medios anteriores; si cambias la selección después de una ingesta, los datos previos permanecen en la base pero quedan fuera del alcance nuevo.

El descargador consulta el presupuesto ya ocupado en medios exitosos. Si alcanza el límite, deja los pendientes en estado `pending`; puedes reanudar después elevando `MAX_MEDIA_GB` o usando `--max-total-gb`. El presupuesto controla los binarios multimedia descargados, no el tamaño total de PostgreSQL, los índices, el sistema operativo ni los rásteres ambientales.

## 6. Ambiente (opcional)

WorldClim 2.1 puede consumir espacio adicional. No lo descargues durante el primer piloto. Cuando hayas medido el tamaño y quieras añadir covariables:

```powershell
python 08_environment.py --download --batch 1000
```

Verifica la disponibilidad y condiciones vigentes de los archivos en WorldClim antes de ejecutar. Los ZIP se descargan a un temporal en disco, no se mantienen completos en RAM.

## 7. Validación y salidas

`11_validate.py` verifica servidor PostgreSQL 18, PostGIS, número de especies, archivos existentes, límite de imágenes, duración/frecuencia de audio, licencias y presupuesto multimedia. Genera `data/validation_report.json`.

`09_export.py` produce Parquet, `manifest.json` y `ATTRIBUTION.csv` en `data/export/`. Los archivos originales comprimidos permanecen en `data/images/` y `data/audio/`.

## 8. Licencias, privacidad y límites científicos

- Cada medio conserva su licencia y titular; no se descargan medios sin licencia CC reconocible.
- Para redistribución o uso comercial, revisa individualmente las licencias y atribuciones; `--exclude-nc` excluye licencias NC del Parquet exportado, pero no elimina los archivos de disco ni sustituye una revisión legal.
- Wikipedia se almacena como texto CC-BY-SA-4.0 con URL y atribución.
- Los observadores se anonimizan con una sal privada. No compartas `.env`.
- Coordenadas de especies CR/EN o registros generalizados se redondean en la exportación.
- Los pares `spatiotemporal` son pseudo-pares, no prueba de que imagen y audio correspondan al mismo individuo.
- `split_geo` es preferible para evaluar generalización espacial; evita mezclar ubicaciones cercanas entre entrenamiento y prueba.

## 9. Copias de seguridad

Antes de cambios de esquema o de migraciones, realiza un `pg_dump` desde PostgreSQL 18. Los medios se respaldan por separado copiando `DATA_DIR`; una copia de la base sin la carpeta de medios no constituye una copia completa del dataset.
