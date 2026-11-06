"""Diagnóstico no destructivo de la conexión configurada."""
from common import connect
with connect() as con:
    print("PostgreSQL:", con.execute("SELECT version()").fetchone()[0])
    print("Base/usuario/puerto:", con.execute("SELECT current_database(), current_user, inet_server_port()").fetchone())
    try: print("PostGIS:", con.execute("SELECT PostGIS_Full_Version()").fetchone()[0])
    except Exception as e: print("PostGIS no disponible en esta base:", e)
