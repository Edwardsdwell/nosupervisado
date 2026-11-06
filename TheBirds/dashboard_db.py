"""Acceso de solo lectura/CRUD controlado para el panel local."""
from __future__ import annotations
import math
import pandas as pd
import psycopg
from psycopg import sql
from common import connect

APP_TABLES = [
    "taxa", "dataset_scope", "vernacular_names", "observations", "media",
    "media_quality", "texts", "pairs", "env_covariates", "annotations", "ingest_progress"
]
READ_ONLY = {"spatial_ref_sys"}


def table_exists(con, table: str) -> bool:
    return con.execute("SELECT to_regclass(%s)", (f"public.{table}",)).fetchone()[0] is not None


def get_tables(con):
    rows = con.execute("""
        SELECT table_name FROM information_schema.tables
        WHERE table_schema='public' AND table_type='BASE TABLE'
        ORDER BY table_name
    """).fetchall()
    return [r[0] for r in rows]


def table_columns(con, table):
    return con.execute("""
        SELECT column_name, data_type, udt_name, is_nullable, column_default
        FROM information_schema.columns
        WHERE table_schema='public' AND table_name=%s ORDER BY ordinal_position
    """, (table,)).fetchall()


def primary_keys(con, table):
    return [r[0] for r in con.execute("""
        SELECT kcu.column_name FROM information_schema.table_constraints tc
        JOIN information_schema.key_column_usage kcu
          ON tc.constraint_name=kcu.constraint_name AND tc.table_schema=kcu.table_schema
        WHERE tc.table_schema='public' AND tc.table_name=%s AND tc.constraint_type='PRIMARY KEY'
        ORDER BY kcu.ordinal_position
    """, (table,)).fetchall()]


def fetch_table(con, table, limit=500):
    if table not in APP_TABLES and table not in READ_ONLY:
        raise ValueError("Tabla no autorizada")
    cur = con.execute(sql.SQL("SELECT * FROM {} LIMIT %s").format(sql.Identifier(table)), (limit,))
    return pd.DataFrame(cur.fetchall(), columns=[d.name for d in cur.description])


def _clean(v):
    if v is None:
        return None
    if hasattr(v, "item"):
        try: v = v.item()
        except Exception: pass
    if pd.isna(v) if not isinstance(v, (list, dict, tuple)) else False:
        return None
    if isinstance(v, pd.Timestamp):
        return v.to_pydatetime()
    return v


def update_rows(con, table, before: pd.DataFrame, after: pd.DataFrame):
    if table not in APP_TABLES or table in READ_ONLY:
        raise ValueError("Tabla no editable")
    pks = primary_keys(con, table)
    if not pks:
        raise ValueError("La tabla no tiene clave primaria; edición deshabilitada")
    cols = [c for c in before.columns if c not in pks]
    count = 0
    with con.transaction():
        for idx in range(min(len(before), len(after))):
            old, new = before.iloc[idx], after.iloc[idx]
            changed = [c for c in cols if _clean(old[c]) != _clean(new[c])]
            if not changed:
                continue
            assignments = sql.SQL(", ").join(sql.SQL("{} = %s").format(sql.Identifier(c)) for c in changed)
            where = sql.SQL(" AND ").join(sql.SQL("{} IS NOT DISTINCT FROM %s").format(sql.Identifier(k)) for k in pks)
            vals = [_clean(new[c]) for c in changed] + [_clean(old[k]) for k in pks]
            con.execute(sql.SQL("UPDATE {} SET {} WHERE {}").format(sql.Identifier(table), assignments, where), vals)
            count += 1
    return count


def delete_rows(con, table, keys):
    if table not in APP_TABLES or table in READ_ONLY:
        raise ValueError("Tabla no editable")
    pks = primary_keys(con, table)
    if len(pks) != 1:
        raise ValueError("La eliminación desde el panel requiere una clave primaria simple")
    with con.transaction():
        cur = con.execute(sql.SQL("DELETE FROM {} WHERE {} = ANY(%s)").format(
            sql.Identifier(table), sql.Identifier(pks[0])), (keys,))
    return cur.rowcount


def insert_row(con, table, payload: dict):
    if table not in APP_TABLES or table in READ_ONLY:
        raise ValueError("Tabla no editable")
    cols_meta = {r[0]: r for r in table_columns(con, table)}
    if not payload or any(k not in cols_meta for k in payload):
        raise ValueError("Campos vacíos o no reconocidos")
    from psycopg.types.json import Jsonb
    names, vals = [], []
    for k, v in payload.items():
        if v == "":
            v = None
        meta = cols_meta[k]
        if v is not None and meta[2] == "jsonb" and isinstance(v, (dict, list)):
            v = Jsonb(v)
        names.append(sql.Identifier(k)); vals.append(v)
    q = sql.SQL("INSERT INTO {} ({}) VALUES ({}) RETURNING *").format(
        sql.Identifier(table), sql.SQL(",").join(names),
        sql.SQL(",").join(sql.Placeholder() for _ in vals))
    with con.transaction():
        row = con.execute(q, vals).fetchone()
    return row


def overview(con):
    out = {}
    for t in APP_TABLES:
        if table_exists(con, t):
            out[t] = con.execute(sql.SQL("SELECT count(*) FROM {}").format(sql.Identifier(t))).fetchone()[0]
        else:
            out[t] = None
    return out


def relationships(con):
    return con.execute("""
        SELECT tc.table_name, kcu.column_name, ccu.table_name AS foreign_table,
               ccu.column_name AS foreign_column
        FROM information_schema.table_constraints tc
        JOIN information_schema.key_column_usage kcu
          ON tc.constraint_name=kcu.constraint_name AND tc.table_schema=kcu.table_schema
        JOIN information_schema.constraint_column_usage ccu
          ON ccu.constraint_name=tc.constraint_name AND ccu.table_schema=tc.table_schema
        WHERE tc.constraint_type='FOREIGN KEY' AND tc.table_schema='public'
        ORDER BY tc.table_name, kcu.column_name
    """).fetchall()
