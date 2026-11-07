
"""Importa imágenes y audios locales a PostgreSQL mediante BYTEA."""

import argparse
import hashlib
import mimetypes
from pathlib import Path

from common import connect, DATA_DIR


CREATE_TABLE = """
CREATE TABLE IF NOT EXISTS media_content (
    media_id BIGINT PRIMARY KEY
        REFERENCES media(media_id) ON DELETE CASCADE,
    content BYTEA NOT NULL,
    mime_type TEXT NOT NULL,
    size_bytes BIGINT NOT NULL CHECK (size_bytes >= 0),
    sha256 CHAR(64) NOT NULL,
    source_path TEXT,
    imported_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);
"""


def resolve_media_path(file_path):
    """Resuelve una ruta relativa dentro de DATA_DIR y evita salir de ella."""
    if not file_path:
        raise ValueError("file_path vacío")

    root = Path(DATA_DIR).resolve()
    relative = Path(file_path)

    path = relative.resolve() if relative.is_absolute() else (root / relative).resolve()

    try:
        path.relative_to(root)
    except ValueError:
        raise ValueError(f"Ruta fuera de DATA_DIR: {path}")

    return path


def get_mime(path, media_type):
    mime, _ = mimetypes.guess_type(str(path))

    if mime:
        return mime

    return "image/octet-stream" if media_type == "image" else "audio/octet-stream"


def create_table(conn):
    conn.execute(CREATE_TABLE)
    conn.commit()


def import_media(conn, limit=None):
    query = """
        SELECT
            m.media_id,
            m.type,
            m.file_path,
            mc.sha256,
            mc.size_bytes
        FROM media m
        LEFT JOIN media_content mc ON mc.media_id = m.media_id
        WHERE m.download_status = 'ok'
        ORDER BY m.media_id
    """

    if limit is not None:
        query += " LIMIT %s"

    rows = conn.execute(query, (limit,) if limit is not None else ()).fetchall()

    imported = 0
    unchanged = 0
    missing = 0
    errors = 0

    print(f"\nArchivos registrados para importar: {len(rows)}")
    print(f"Directorio multimedia: {DATA_DIR}\n")

    for media_id, media_type, file_path, old_sha, old_size in rows:
        try:
            path = resolve_media_path(file_path)

            if not path.is_file():
                print(f"AUSENTE [{media_id}]: {path}")
                missing += 1
                continue

            # Solo se carga un archivo en memoria cada vez.
            content = path.read_bytes()
            sha = hashlib.sha256(content).hexdigest()
            size = len(content)

            if old_sha and old_sha.strip() == sha and old_size == size:
                unchanged += 1
                continue

            mime = get_mime(path, media_type)

            conn.execute(
                """
                INSERT INTO media_content (
                    media_id, content, mime_type,
                    size_bytes, sha256, source_path
                )
                VALUES (%s, %s, %s, %s, %s, %s)
                ON CONFLICT (media_id) DO UPDATE SET
                    content = EXCLUDED.content,
                    mime_type = EXCLUDED.mime_type,
                    size_bytes = EXCLUDED.size_bytes,
                    sha256 = EXCLUDED.sha256,
                    source_path = EXCLUDED.source_path,
                    imported_at = NOW()
                """,
                (
                    media_id,
                    content,
                    mime,
                    size,
                    sha,
                    str(path)
                )
            )

            # Confirmación individual: un fallo posterior no pierde
            # los archivos que ya fueron importados.
            conn.commit()

            imported += 1
            print(
                f"IMPORTADO [{media_id}] "
                f"{media_type} | {size:,} bytes | {mime}"
            )

        except Exception as exc:
            conn.rollback()
            errors += 1
            print(f"ERROR [{media_id}]: {exc}")

    print("\n========== RESULTADO ==========")
    print("Importados:", imported)
    print("Ya estaban actualizados:", unchanged)
    print("Archivos ausentes:", missing)
    print("Errores:", errors)


def verify_media(conn):
    missing_db = conn.execute(
        """
        SELECT COUNT(*)
        FROM media m
        LEFT JOIN media_content mc ON mc.media_id = m.media_id
        WHERE m.download_status = 'ok'
          AND mc.media_id IS NULL
        """
    ).fetchone()[0]

    rows = conn.execute(
        """
        SELECT
            m.media_id,
            m.type,
            m.file_path,
            mc.content,
            mc.sha256,
            mc.size_bytes
        FROM media m
        JOIN media_content mc ON mc.media_id = m.media_id
        WHERE m.download_status = 'ok'
        ORDER BY m.media_id
        """
    )

    valid = 0
    invalid = 0

    for media_id, media_type, file_path, content, stored_sha, stored_size in rows:
        data = bytes(content)
        actual_sha = hashlib.sha256(data).hexdigest()

        if (
            actual_sha == stored_sha.strip()
            and len(data) == stored_size
        ):
            valid += 1
        else:
            invalid += 1
            print(f"INTEGRIDAD INCORRECTA [{media_id}]")

    total = conn.execute(
        """
        SELECT COUNT(*)
        FROM media_content
        """
    ).fetchone()[0]

    size = conn.execute(
        """
        SELECT COALESCE(SUM(size_bytes), 0)
        FROM media_content
        """
    ).fetchone()[0]

    print("\n========== VERIFICACIÓN ==========")
    print("Registros multimedia en PostgreSQL:", total)
    print("Archivos íntegros:", valid)
    print("Archivos con errores:", invalid)
    print("Registros OK sin contenido en PostgreSQL:", missing_db)
    print(f"Almacenamiento binario: {size:,} bytes ({size / 1024**2:.2f} MiB)")

    if invalid == 0 and missing_db == 0:
        print("\nVERIFICACIÓN CORRECTA.")
    else:
        print("\nVERIFICACIÓN INCOMPLETA. Revisa los registros indicados.")


def main():
    parser = argparse.ArgumentParser(
        description="Importación de imágenes y audios a PostgreSQL."
    )

    parser.add_argument(
        "--verify",
        action="store_true",
        help="Verifica los contenidos binarios ya almacenados."
    )

    parser.add_argument(
        "--limit",
        type=int,
        default=None,
        help="Limita el número de archivos procesados."
    )

    args = parser.parse_args()

    if args.limit is not None and args.limit < 1:
        parser.error("--limit debe ser mayor que cero")

    conn = connect()

    try:
        create_table(conn)

        if args.verify:
            verify_media(conn)
        else:
            import_media(conn, args.limit)

    finally:
        conn.close()


if __name__ == "__main__":
    main()
