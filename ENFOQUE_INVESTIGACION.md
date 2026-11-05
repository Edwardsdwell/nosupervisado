# Enfoque de investigación

## Título propuesto
**Descubrimiento no supervisado de patrones taxonómicos y detección de anomalías en datos multimodales de biodiversidad**

## Planteamiento del problema
Los repositorios de biodiversidad almacenan evidencia de las observaciones en formatos heterogéneos: fotografías, sonidos, descripciones y coordenadas. Estos datos suelen estar incompletos y distribuidos entre plataformas. No siempre se conoce qué modalidad representa mejor las diferencias entre especies ni cómo detectar registros atípicos antes de utilizarlos en análisis posteriores.

El problema no consiste en construir un clasificador que ya conozca las especies, sino en determinar si los patrones presentes en los datos permiten formar agrupamientos coherentes con la taxonomía y si los métodos no supervisados pueden señalar registros que merecen revisión.

## Objetivo general
Evaluar la capacidad de métodos de aprendizaje no supervisado para descubrir agrupamientos taxonómicos y detectar anomalías en registros de biodiversidad, comparando información acústica, visual, textual y geográfica procedente de repositorios abiertos.

## Objetivos específicos
1. Integrar observaciones de distintas fuentes conservando identificadores, procedencia, fecha, taxonomía, coordenadas, textos y referencias a medios.
2. Extraer características numéricas de audio, imagen, texto y geografía, manteniendo separadas las modalidades y registrando su disponibilidad.
3. Aplicar algoritmos no supervisados a cada modalidad por separado y a subconjuntos multimodales comparables.
4. Evaluar los agrupamientos con métricas internas y con ARI/NMI frente a especie, género y clase, sin utilizar esas etiquetas durante el agrupamiento.
5. Comparar el aporte individual y complementario de cada modalidad.
6. Detectar observaciones atípicas o inconsistentes mediante métodos de densidad, distancia y reglas de calidad.
7. Medir la cobertura y ausencia de cada modalidad para identificar sesgos de muestreo.

## Preguntas de investigación
- ¿Qué modalidad genera agrupamientos con mayor concordancia con la taxonomía conocida?
- ¿La combinación de modalidades mejora la separación respecto de utilizarlas individualmente?
- ¿Qué anomalías pueden señalarse sin etiquetas previas de error?
- ¿Cómo afecta la ausencia de una modalidad a los resultados?

## Qué problema resuelve
La plataforma ayuda a decidir qué evidencia conviene recolectar para estudiar biodiversidad, permite explorar estructuras que no se ven fácilmente en registros individuales y prioriza registros potencialmente problemáticos para revisión. No reemplaza la identificación taxonómica de especialistas ni determina por sí sola que un registro sea falso.

## Fuentes y papel de cada una
- **iNaturalist:** eventos de observación con taxón, fecha, coordenadas, descripción, fotografías y, en algunos casos, sonido. La unidad principal es el evento.
- **GBIF:** ocurrencias agregadas de múltiples instituciones y proyectos, con taxonomía, coordenadas, fecha, localidad, observaciones y enlaces a medios. La unidad principal es la ocurrencia.
- **Xeno-canto:** grabaciones de aves con especie, fecha, localidad, coordenadas y metadatos acústicos. Sus grabaciones se relacionan por especie y no se deben tratar como si fueran el mismo evento de una fotografía.
- **Wikipedia y GBIF Species:** descripciones generales y nombres comunes que enriquecen el texto a nivel de especie, no de observación.

No hay una fuente única que garantice las cuatro modalidades para cada observación. La adquisición es bajo demanda, no streaming.

## Dos niveles de comparación
**A. Por evento:** utilizar el mismo evento cuando hay dos o más modalidades asociadas. Es el diseño más riguroso para comparar audio, imagen, texto y geografía, aunque el número de casos puede ser pequeño.

**B. Por especie:** resumir las características por especie para unir, por ejemplo, imágenes de observaciones de iNaturalist con grabaciones de Xeno-canto. Aumenta la cobertura, pero la relación es taxonómica, no temporal ni espacial. Reportar por separado ambas evaluaciones.

## Métricas
- Internas: silueta (mayor es mejor), Davies-Bouldin (menor es mejor), Calinski-Harabasz (mayor es mejor).
- Externas: ARI y NMI frente a especie, género y clase. Son evaluación posterior; las etiquetas no forman parte de las variables de entrada.
- Anomalías: porcentaje marcado como ruido, revisión de coordenadas, integridad de medios, duplicados, ausencia de metadatos y concordancia de taxonomía. Una alerta no demuestra un error.

## Almacenamiento
La ingesta guarda metadatos y URL; no descarga medios automáticamente. Los archivos se descargan solo cuando se solicita, se deduplican por SHA-256 y se transforman en características. Los medios y cachés pueden permanecer fuera del ZIP. Los originales no se eliminan automáticamente.

## Consideraciones que deben declararse
- Xeno-canto aporta principalmente aves; las búsquedas de anfibios por género son oportunistas y no garantizan cobertura equivalente.
- Las descripciones de Wikipedia/GBIF son contexto por especie.
- Las coordenadas pueden estar generalizadas o tener incertidumbre.
- Los repositorios presentan sesgos geográficos y taxonómicos.
- Las licencias se conservan como metadatos y no se filtran en la adquisición ni en la descarga; su revisión y decisión de uso quedan a cargo del usuario.
