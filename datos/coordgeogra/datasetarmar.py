import os
import requests
import pandas as pd
import geopandas as gpd

# Subcarpeta de salida (ajustada para ruta relativa o absoluta según prefieras)
output_dir = r"datos\coordgeogra"
os.makedirs(output_dir, exist_ok=True)

print("--- Descargando datos de coordenadas de Mapaches (Procyon lotor) ---")

# API de GBIF para Procyon lotor (Mapache común)
url = "https://api.gbif.org/v1/occurrence/search"
params = {
    "scientificName": "Procyon lotor",
    "hasCoordinate": "true",
    "limit": 1500  # Cantidad de registros para el experimento
}

response = requests.get(url, params=params)
data = response.json()

# Extraer coordenadas e información clave
records = []
for item in data.get('results', []):
    lat = item.get('decimalLatitude')
    lon = item.get('decimalLongitude')
    country = item.get('country')
    year = item.get('year')
    
    if lat and lon:
        records.append({
            'especie': 'Procyon lotor',
            'latitud': lat,
            'longitud': lon,
            'pais': country,
            'anio': year
        })

# Convertir a DataFrame de Pandas
df_mapaches = pd.DataFrame(records)

# Convertir a GeoDataFrame con geometrías de PUNTOS (CRS WGS84 estándar para coordenadas GPS)
gdf_mapaches = gpd.GeoDataFrame(
    df_mapaches, 
    geometry=gpd.points_from_xy(df_mapaches.longitud, df_mapaches.latitud),
    crs="EPSG:4326"
)

# Rutas de salida para formatos geoespaciales puros
geojson_out = os.path.join(output_dir, "coordenadas_mapaches.geojson")
gpkg_out = os.path.join(output_dir, "coordenadas_mapaches.gpkg")

# Guardar en formatos dedicados para coordenadas (sin CSV)
gdf_mapaches.to_file(geojson_out, driver="GeoJSON")
gdf_mapaches.to_file(gpkg_out, driver="GPKG")

print(f"¡Éxito! Se procesaron {len(df_mapaches)} coordenadas de mapaches.")
print(f" -> Formato GeoJSON puro guardado en: {geojson_out}")
print(f" -> Formato GeoPackage espacial guardado en: {gpkg_out}")