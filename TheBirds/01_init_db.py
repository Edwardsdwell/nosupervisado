"""Inicializa el esquema. Falla pronto si Python no está conectado a PostgreSQL 18 + PostGIS."""
import pathlib
from common import connect, log

with connect() as con:
    row = con.execute("SELECT current_setting('server_version_num')::int, version()").fetchone()
    major = row[0] // 10000
    if major != 18:
        raise RuntimeError(f"Se requiere PostgreSQL 18 nativo; la conexión llegó a PostgreSQL {major}: {row[1]}")
    try:
        con.execute("CREATE EXTENSION IF NOT EXISTS postgis")
        postgis = con.execute("SELECT PostGIS_Full_Version()").fetchone()[0]
    except Exception as e:
        raise RuntimeError("PostGIS no está instalado para este servidor PostgreSQL 18. Instala PostGIS compatible y vuelve a ejecutar.") from e
    sql = (pathlib.Path(__file__).resolve().parent / "sql" / "schema.sql").read_text(encoding="utf-8")
    con.execute(sql)
log.info("PostgreSQL 18 y %s: esquema creado/actualizado.", postgis)
