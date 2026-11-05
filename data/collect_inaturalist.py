from __future__ import annotations

import time
import requests

from . import db

API = "https://api.inaturalist.org/v2/observations"

HEADERS = {
    "User-Agent": "Biodiversidad-Analisis/1.0 (academic research)"
}


def recolectar_inaturalist(
    con,
    objetivo=100,
    grupo="Aves",
    modalidad="ambos",
    pausa=1.0
):
    """
    Incorpora metadatos de iNaturalist a la base existente.

    modalidad:
        imagen  -> fotografías sin audio
        audio   -> audio sin fotografías
        ambos   -> fotografías y audio en la misma observación

    No descarga archivos multimedia.
    """

    from data.validacion import validar_coordenada

    filtros = {
        "imagen": ("true", "false"),
        "audio": ("false", "true"),
        "ambos": ("true", "true")
    }

    if modalidad not in filtros:
        raise ValueError("Modalidad no válida")

    fotos, sonidos = filtros[modalidad]

    agregados = 0
    pagina = 1

    while agregados < objetivo:

        params = [
            ("per_page", 200),
            ("page", pagina),
            ("geo", "true"),
            ("photos", fotos),
            ("sounds", sonidos),
            ("iconic_taxa[]", grupo),
            ("order_by", "observed_on"),
            ("order", "desc"),
        ]

        respuesta = requests.get(
            API,
            params=params,
            headers=HEADERS,
            timeout=60
        )

        respuesta.raise_for_status()
        datos = respuesta.json()

        resultados = datos.get("results", [])

        if not resultados:
            break

        for r in resultados:

            if agregados >= objetivo:
                break

            eid = f"inat:{r['id']}"

            # Evitar duplicados de la misma observación.
            if con.execute(
                "SELECT 1 FROM events WHERE event_id=?",
                (eid,)
            ).fetchone():
                continue

            taxon = r.get("taxon") or {}

            especie = (
                r.get("species_guess")
                or taxon.get("name")
                or "Desconocida"
            )

            nombre_taxon = taxon.get("name") or especie

            fecha = (
                r.get("observed_on")
                or r.get("time_observed_at")
            )

            con.execute("""
                INSERT INTO events (
                    event_id, source, source_id,
                    observed_raw, species, genus,
                    class, license, link_type,
                    created_utc
                )
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """, (
                eid,
                "inaturalist",
                str(r["id"]),
                fecha,
                especie,
                nombre_taxon.split()[0],
                taxon.get("iconic_taxon_name", grupo),
                r.get("license_code"),
                "confirmed",
                db.now()
            ))

            # Coordenadas
            lat = r.get("latitude")
            lon = r.get("longitude")

            lat, lon, motivo = validar_coordenada(lat, lon)

            con.execute("""
                INSERT INTO geo (
                    event_id, lat, lon, crs,
                    uncertainty_m, locality,
                    geo_status, motivo
                )
                VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            """, (
                eid,
                lat,
                lon,
                "EPSG:4326",
                r.get("positional_accuracy"),
                r.get("place_guess"),
                "invalido" if motivo else "present",
                motivo or None
            ))

            # Información textual
            textos = {
                "description": r.get("description"),
                "locality": r.get("place_guess"),
                "species": especie
            }

            for campo, texto in textos.items():
                if texto:
                    con.execute("""
                        INSERT OR IGNORE INTO texts
                        (event_id, field, original)
                        VALUES (?, ?, ?)
                    """, (eid, campo, str(texto)))

            # Fotografías
            for i, foto in enumerate(r.get("photos") or []):

                url = foto.get("url")

                if not url:
                    continue

                con.execute("""
                    INSERT OR IGNORE INTO images (
                        image_id, event_id, url,
                        license, download_status
                    )
                    VALUES (?, ?, ?, ?, ?)
                """, (
                    f"{eid}:img:{i}",
                    eid,
                    url,
                    foto.get("license_code"),
                    db.PENDIENTE
                ))

            # Grabaciones
            for i, sonido in enumerate(r.get("sounds") or []):

                url = sonido.get("file_url") or sonido.get("url")

                if not url:
                    continue

                con.execute("""
                    INSERT OR IGNORE INTO audio (
                        audio_id, event_id, url,
                        license, download_status
                    )
                    VALUES (?, ?, ?, ?, ?)
                """, (
                    f"{eid}:audio:{i}",
                    eid,
                    url,
                    sonido.get("license_code"),
                    db.PENDIENTE
                ))

            agregados += 1

        con.commit()

        pagina += 1

        time.sleep(pausa)

    db.auditar(
        con,
        "recoleccion_inaturalist",
        f"Grupo={grupo}; modalidad={modalidad}",
        agregados
    )

    con.commit()

    return agregados