# Plataforma unificada de aprendizaje no supervisado
Una sola aplicación (Streamlit) que adquiere, valida, procesa y analiza **audio, imágenes, texto y coordenadas**
con las **12 opciones algorítmicas** y las **13 comparativas** , más dos comparativas nuevas
(varios algoritmos / varios valores de un parámetro). Implementa la especificación de 200 requerimientos.

## Puesta en marcha

**Windows** (PowerShell o CMD, dentro de la carpeta del proyecto):
```bat
python -m venv .venv
.venv\Scripts\activate
pip install -r requirements.txt
streamlit run app.py
```

* Python **3.11 o superior**.
* **ffmpeg** en el PATH para leer y validar los audios **M4A** (más de la mitad de fauna_sonora). 
* Pruebas: `python -m pytest tests -q` (135 pruebas).

Sin importar nada también funciona: pestaña **Datos** → subir archivos, indicar una carpeta, pegar una URL o recolectar de GBIF.

## Calidad de datos (pestaña «Calidad e inventario»)

* **Inventario**: cada registro (audio, imagen, texto, punto, documento) como **válido / inválido / pendiente**, con su motivo y su identificador de origen (GBIF). Filtrable y exportable a CSV.
* **Informe de calidad por modalidad**: formatos, duraciones, resoluciones, longitud de textos, idioma, cobertura geográfica, completitud por evento, licencias y recomendaciones. Exportable a Markdown + CSV.
* **Verificar integridad**: comprueba que cada archivo válido exista, no esté vacío, se pueda abrir y coincida con su SHA-256.
* **Enriquecer textos** (requiere internet): descripciones de especies de Wikipedia y GBIF, con fuente y licencia.
* **Auditoría**: registro de importaciones, ingestas, verificaciones e informes.

## Qué es una muestra (barra lateral)

* **Fragmentos** (por defecto): parches de 32×32 px de cada imagen y ventanas de 1 s de cada audio.
* **Archivo completo**: un vector por imagen (79 descriptores de color, textura y composición) o por grabación (87 descriptores).
  Así cada muestra es un ejemplar con su especie y su clase, y los resultados se pueden **validar externamente** (ARI/NMI frente a Aves/Amphibia).

## Estructura (sección 6 de la especificación)

| Carpeta | Contenido |
|---|---|
| `app.py`, `config.py` | interfaz única; configuración central (`config.toml` / variables `NS_*`) |
| `core/` | `engine` (Motor), `registry` (registro extensible), `results` (Datos/Res/Param), `cache`, `tasks`, `errors` |
| `data/` | `db` (SQLite), `storage` (SHA-256), `validacion`, `integridad`, `inventario`, `enriquecer`, `download`, `collect` (GBIF), `loaders/{audio,image,text,geo}` |
| `ml/` | `algorithms` (12), `comparisons` (13 + ranking/sensibilidad/estabilidad), `recomendaciones`, `preprocessing`, `metrics`, `catalogo` |
| `visualization/` | `charts`, `maps`, `media`, `widgets` + `web/` (orbita, galería, mapa, audio, texto, hero…) |
| `ui/` | `pages.py`, `paneles.py` (calidad, grupos, sugerencias, comparación de ejecuciones), `styles.css` |
| `data_store/` | `raw/` originales · `derived/` miniaturas y clips · `cache/` características y resultados · `results/` |

## Decisiones
* **Se retiró Tkinter** (`interfaz.py`) y se fusionaron `app.py` y `app(1).py` (eran idénticos): una sola interfaz.
* **Cuatro tipos reales:** audio, imágenes, texto y geografía (no tabulares/temporales genéricos).
* **Descargar ≠ analizar:** `data/download.py` no importa librosa, PIL ni scikit-learn. Las características se calculan al pedirlas y se guardan por SHA-256 + parámetros + versión.
* **TF-IDF disperso** de punta a punta; solo se densifica (con tope de MB) para algoritmos que lo exigen.
* **Coordenadas:** proyección local en km solo si la extensión es pequeña; con puntos de todo el mundo (como los 68 de GBIF) usa coordenadas xyz sobre la esfera y avisa.
* **LDA discriminante** queda marcado como método supervisado/heredado; LDA de Dirichlet es el temático.
* Registro perezoso: listar los algoritmos no importa scikit-learn, Plotly ni UMAP (hay una prueba).

## Añadir un algoritmo sin tocar el núcleo
```python
from core.registry import registrar
from core.results import Param, Res
def mi_metodo(datos, X, p): return Res("informe", Z=X[:, :2], ejes=["a", "b"])
registrar("Mi método", mi_metodo, [Param("k", "k", 3, 2, 10)], tipos=("audio", "img"), descripcion="…", min_muestras=10)
```
La interfaz genera los controles sola. `retirar("Mi método")` lo quita.

## Trazabilidad requerimiento → implementación
| Módulo | Req. | Dónde | Pruebas |
|---|---|---|---|
| I Arquitectura | 1–20 | `core/*`, `config.py`, `ui/pages.py` | `test_algorithms` (registro, perezoso), `test_integration` |
| II Adquisición | 21–40 | `core/engine.ingerir*`, `data/download.py`, `data/collect.py`, `data/storage.py` | `test_storage` |
| III Tipos de datos | 41–60 | `data/loaders/*` | `test_loaders` |
| IV Preparación | 61–80 | `ml/preprocessing.py`, `core/results.Datos` | `test_algorithms` |
| V Algoritmos | 81–100 | `ml/algorithms.py`, `ml/catalogo.py`, `core/registry.py` | `test_algorithms` |
| VI Comparativas | 101–120 | `ml/comparisons.py`, `core/engine.exportar` | `test_integration` |
| VII Gráficos | 121–140 | `visualization/charts.py`, `ui/pages.mostrar_algoritmo` | `test_performance` |
| VIII Multimedia | 141–160 | `visualization/media.py`, `widgets.py`, `web/` | prueba de interfaz manual |
| IX Base y almacenamiento | 161–180 | `data/db.py`, `data/storage.py`, `core/cache.py` | `test_storage`, `test_integration` |
| X Rendimiento y seguridad | 181–200 | `core/tasks.py`, `data/download.py`, `tests/` | `test_performance`, `test_storage` |

### Limitaciones conocidas (honestas)
* **Cancelación cooperativa:** se comprueba entre archivos, lotes, valores de k y descargas; un `fit` de scikit-learn ya iniciado termina antes de cancelarse.
* **Req. 186:** el paralelismo es entre tareas (máx. configurable); no se añadió paralelismo interno.
* **PNG** requiere `kaleido` (opcional); HTML interactivo siempre está disponible.
* El monitoreo de memoria usa `psutil` si está instalado, y `resource` en Linux/macOS.
* `tests/` no incluye pruebas automáticas de los widgets web (se comprobó la interfaz en un navegador automatizado).
* **Enriquecer textos** se probó con respuestas simuladas; necesita internet en el equipo donde se ejecute.
* Ver `CAMBIOS.md` para el detalle de lo hecho y lo pendiente respecto de las notas del equipo.


---

# Enfoque científico: biodiversidad multimodal y control de calidad

## Problema de investigación

Las colecciones de biodiversidad reúnen observaciones heterogéneas: fotografías, grabaciones, descripciones y ubicaciones geográficas. Sin embargo, estos datos suelen estar distribuidos entre repositorios y no siempre están completos. Esto dificulta comparar qué tipo de evidencia representa mejor las diferencias entre especies y detectar registros atípicos antes de utilizarlos.

La plataforma se orienta a estudiar esa estructura sin utilizar las etiquetas taxonómicas para construir los grupos. Las etiquetas conocidas (especie, género y clase) se reservan para la evaluación posterior.

Objetivo general
Evaluar la capacidad de algoritmos de aprendizaje no supervisado para descubrir patrones en registros de biodiversidad y detectar anomalías mediante características multimodales.

Objetivo específico 1 — Descubrimiento de patrones
Muestra comparable
- Audio e imagen sobre los mismos eventos.
- Texto y geografía mediante subconjuntos comparables.
- K-Means, clustering jerárquico, GMM, DBSCAN y HDBSCAN.
- ARI, NMI y métricas internas.
Objetivo específico 2 — Control de calidad
Corpus completo
- Todos los registros disponibles.
- Análisis independiente por modalidad.
- Detección de ruido, distancias e inconsistencias.
- Identificación de registros que requieren revisión.

Resultados esperados
1. Determinar qué modalidad presenta mayor capacidad de agrupamiento taxonómico.
2. Identificar qué información adicional aporta cada modalidad.
3. Detectar registros sospechosos que podrían afectar la calidad de los datos.
4. Establecer qué algoritmos son más adecuados para cada tipo de información.

## Preguntas de investigación

- ¿Qué modalidad produce agrupamientos que mejor coinciden con las categorías taxonómicas conocidas?
- ¿La combinación de modalidades mejora la separación respecto del uso individual?
- ¿Qué tipos de anomalías pueden detectarse sin etiquetas de error?
- ¿En qué medida la falta de fotografías, audios, textos o coordenadas sesga los resultados?

## Fuentes conectadas

| Fuente | Aporta | Nivel de relación |
|---|---|---|
| iNaturalist API | Observaciones, taxón, fecha, descripción, coordenadas, fotos y, cuando existen, sonidos | Evento de observación |
| GBIF Occurrence API | Ocurrencias, taxonomía, coordenadas, fecha, localidad, observaciones y referencias multimedia | Evento de ocurrencia |
| Xeno-canto API v3 | Grabaciones, especie, género, fecha, localidad, coordenadas y metadatos acústicos | Muestra acústica asociada a especie; no equivale a la observación fotográfica |
| Wikipedia + GBIF Species API | Descripciones generales, nombres comunes y contexto textual por especie | Especie |

Las APIs se consultan bajo demanda; no son flujos de streaming. iNaturalist recomienda alrededor de una solicitud por segundo y no más de 10.000 solicitudes diarias. Xeno-canto API v3 requiere una clave. GBIF limita las páginas de búsqueda a 300 registros y las búsquedas a 100.000 resultados; para volúmenes superiores dispone de descargas asíncronas. La aplicación usa cuotas pequeñas y paginación limitada.

**Importante:** no existe una fuente que garantice las cuatro modalidades para cada observación. iNaturalist y GBIF son las fuentes principales de eventos georreferenciados; Xeno-canto amplía especialmente la cobertura acústica a nivel de especie. Las uniones por especie no deben interpretarse como si audio y foto fueran del mismo individuo, fecha o lugar.

## Diseño experimental recomendado

### Experimento A — Comparación por evento

Utilizar únicamente observaciones de iNaturalist/GBIF que tengan dos o más modalidades asociadas al mismo evento. Comparar las modalidades disponibles sobre la misma selección de eventos. Esta es la comparación más estricta, pero su tamaño estará limitado por la intersección real de medios.

### Experimento B — Comparación por especie

Agrupar o resumir las características de cada modalidad por especie. Permite incorporar grabaciones de Xeno-canto aunque no correspondan al mismo evento que una foto. Comparar las especies comunes a las modalidades y reportar explícitamente cuántas muestras contribuyeron a cada especie.

No mezclar en una sola tabla de evaluación muestras por evento con muestras por especie. El campo `link_type` distingue las relaciones: `event` para evidencia de la misma observación y `species` para evidencia enlazada taxonómicamente.

### Validación del objetivo 1

- Interna: silueta (mayor es mejor), Davies-Bouldin (menor es mejor) y Calinski-Harabasz (mayor es mejor).
- Externa: ARI y NMI frente a especie, género y clase. Se calculan después de agrupar; no se entregan como variables de entrada.
- Comparación justa: mismas especies, mismo subconjunto de eventos cuando corresponda, misma semilla y parámetros documentados.
- No interpretar ARI/NMI altos como prueba de que el modelo identifica correctamente cualquier especie fuera del conjunto evaluado.

### Validación del objetivo 2

La detección de anomalías debe combinar:
- Ruido detectado por DBSCAN/HDBSCAN/OPTICS.
- Coordenadas inválidas, incertidumbre geográfica elevada o puntos espacialmente aislados.
- Medios que no se pueden descargar, decodificar o validar.
- Descripciones vacías, demasiado cortas o discordantes con la taxonomía.
- Duplicados, metadatos incompletos y desbalance por especie/fuente.

Una observación marcada como atípica no es automáticamente un error biológico. Se trata de una alerta para revisión. Para estimar precisión y sensibilidad, se recomienda crear un pequeño conjunto de casos revisados manualmente y/o inyectar anomalías controladas (coordenadas intercambiadas, fechas imposibles, archivos corruptos) como prueba técnica separada.

## Estrategia de almacenamiento ligero

1. La ingesta inicial guarda metadatos, URL, identificador de origen y licencia declarada; no descarga los medios.
2. El usuario inicia la descarga de medios pendientes cuando decide qué subconjunto analizar.
3. El almacén usa SHA-256 para deduplicar archivos.
4. Audio e imagen se procesan para producir características; las matrices derivadas y sus cachés son mucho más pequeñas que los originales.
5. El análisis puede trabajar con características y manifiestos. Los archivos multimedia pueden mantenerse fuera del ZIP y excluidos del control de versiones.
6. El ZIP de entrega debe incluir código, pruebas, documentación y, si se desea, una base pequeña de metadatos; no debe incluir `data_store/raw/`, temporales ni cachés regenerables.

No se eliminan automáticamente los originales: primero se debe comprobar que las características se calcularon correctamente y que el manifiesto permite reconstruir la procedencia.

## Configuración de Xeno-canto

La clave se puede introducir desde la interfaz en la sección de ingesta o definir como variable de entorno:

- Windows PowerShell: `$env:NS_XENO_CANTO_API_KEY="TU_CLAVE"`
- Linux/macOS: `export NS_XENO_CANTO_API_KEY="TU_CLAVE"`

No se escribe la clave en SQLite, el código ni el repositorio.

## Uso

1. Instalar dependencias con `pip install -r requirements.txt`.
2. Ejecutar `streamlit run app.py`.
3. Abrir **Datos → Ingesta multimodal desde fuentes externas**.
4. Consultar las fuentes. Si no se proporciona la clave Xeno-canto, esa fuente se informa como omitida; iNaturalist y GBIF siguen funcionando.
5. Revisar la cobertura por modalidad y los registros pendientes.
6. Descargar un subconjunto razonable de medios y ejecutar el análisis correspondiente.

## Limitaciones que deben declararse en el informe

- La cobertura de audio es desigual: Xeno-canto consulta grabaciones de aves y, cuando ya hay géneros de anfibios en el corpus, intenta búsquedas por género. La cobertura de anfibios puede ser mucho menor y debe reportarse.
- Las descripciones por especie de Wikipedia/GBIF son contexto taxonómico, no texto escrito durante la observación.
- Las coordenadas pueden ser aproximadas, generalizadas u ocultas.
- Una misma especie puede tener múltiples variedades, edades, sexos, comportamientos y condiciones ambientales; un grupo visual o acústico no necesariamente equivale a una especie.
- Las fuentes tienen sesgos geográficos, taxonómicos y de participación ciudadana.
- Las APIs y sus cuotas pueden cambiar. La ingesta registra fuente, consulta y cantidad recibida para hacer el proceso auditable.
