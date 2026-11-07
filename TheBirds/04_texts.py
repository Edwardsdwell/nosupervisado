"""Paso 4: textos y referencias científicas multifuente."""
import argparse
import html
import re
import time
from urllib.parse import quote

from tqdm import tqdm
from common import connect, http, log


WIKI_DISAMBIG = (
    "may refer to",
    "puede referirse a",
    "puede hacer referencia",
)


def clean_text(value):
    if not value:
        return ""
    value = re.sub(r"<[^>]+>", " ", str(value))
    value = html.unescape(value)
    return re.sub(r"\s+", " ", value).strip()


def reconstruct_abstract(index):
    """Reconstruye el resumen de OpenAlex desde su índice invertido."""
    if not isinstance(index, dict):
        return ""

    words = {}
    for word, positions in index.items():
        for position in positions:
            words[position] = word

    return " ".join(words[p] for p in sorted(words))


def save_text(con, taxon_key, source, language, title, url,
              license_name, content):
    if not content.strip():
        return False

    con.execute("""
        INSERT INTO texts
            (taxon_key, source, language, title, url, license, content)
        VALUES (%s, %s, %s, %s, %s, %s, %s)
        ON CONFLICT (taxon_key, source, language)
        DO UPDATE SET
            title = EXCLUDED.title,
            url = EXCLUDED.url,
            license = EXCLUDED.license,
            content = EXCLUDED.content
    """, (
        taxon_key, source, language, title[:500] if title else None,
        url, license_name, content
    ))
    return True


def mark_done(con, task, key):
    con.execute("""
        INSERT INTO ingest_progress (task, key)
        VALUES (%s, %s)
        ON CONFLICT (task, key)
        DO UPDATE SET done_at = now()
    """, (task, str(key)))


def fetch_wikipedia(session, scientific_name, lang):
    params = {
        "action": "query",
        "format": "json",
        "formatversion": 2,
        "prop": "extracts",
        "exintro": 1,
        "explaintext": 1,
        "redirects": 1,
        "titles": scientific_name,
    }

    response = session.get(
        f"https://{lang}.wikipedia.org/w/api.php",
        params=params,
        timeout=45
    )
    response.raise_for_status()

    pages = response.json().get("query", {}).get("pages", [])
    if not pages:
        return None

    page = pages[0]
    title = page.get("title", "")
    content = page.get("extract", "").strip()

    if page.get("missing") or len(content) < 80:
        return None

    if any(x in content[:300].lower() for x in WIKI_DISAMBIG):
        return None

    url = (
        f"https://{lang}.wikipedia.org/wiki/"
        f"{quote(title.replace(' ', '_'))}"
    )
    return title, url, content


def fetch_openalex(session, scientific_name, mailto=None):
    params = {
        "search": f'"{scientific_name}"',
        "per-page": 5,
        "sort": "relevance_score:desc",
    }
    if mailto:
        params["mailto"] = mailto

    response = session.get(
        "https://api.openalex.org/works",
        params=params,
        timeout=45
    )
    response.raise_for_status()

    results = response.json().get("results", [])
    if not results:
        return None

    # Preferir trabajos cuyo título mencione el nombre científico.
    target = scientific_name.lower()
    results.sort(
        key=lambda item: (
            target in (item.get("title") or "").lower(),
            item.get("relevance_score") or 0
        ),
        reverse=True
    )

    work = results[0]
    title = clean_text(work.get("title"))
    abstract = reconstruct_abstract(
        work.get("abstract_inverted_index")
    )

    authors = [
        clean_text(a.get("author", {}).get("display_name"))
        for a in work.get("authorships", [])[:8]
    ]
    authors = [a for a in authors if a]

    year = work.get("publication_year")
    doi = work.get("doi")
    venue = (
        work.get("primary_location", {})
        .get("source", {}) or {}
    ).get("display_name")

    metadata = [
        f"Título: {title}",
        f"Autores: {'; '.join(authors)}" if authors else "",
        f"Año: {year}" if year else "",
        f"Publicación: {venue}" if venue else "",
        f"DOI: {doi}" if doi else "",
    ]

    content = "\n".join(x for x in metadata if x)
    if abstract:
        content += "\n\nResumen del artículo:\n" + abstract
    else:
        content += (
            "\n\nNo se obtuvo el resumen. "
            "Este registro contiene únicamente metadatos bibliográficos."
        )

    url = doi or work.get("id")
    if doi and doi.startswith("https://doi.org/"):
        url = doi
    elif doi:
        url = f"https://doi.org/{doi}"

    if not url:
        url = work.get("id")

    if not title or not url:
        return None

    return title, url, content


def fetch_crossref(session, scientific_name, mailto=None):
    params = {
        "query.title": scientific_name,
        "rows": 5,
        "select": "title,author,DOI,published,container-title,abstract,type",
    }
    if mailto:
        params["mailto"] = mailto

    response = session.get(
        "https://api.crossref.org/works",
        params=params,
        timeout=45
    )
    response.raise_for_status()

    items = response.json().get("message", {}).get("items", [])
    if not items:
        return None

    target = scientific_name.lower()
    items.sort(
        key=lambda item: target in " ".join(
            item.get("title", [])
        ).lower(),
        reverse=True
    )

    item = items[0]
    title = clean_text(" ".join(item.get("title", [])))
    doi = item.get("DOI")

    if not title or not doi:
        return None

    authors = []
    for author in item.get("author", [])[:8]:
        name = " ".join(filter(None, [
            author.get("given"), author.get("family")
        ]))
        if name:
            authors.append(name)

    published = item.get("published", {}).get("date-parts", [[]])
    year = published[0][0] if published and published[0] else None
    journal = clean_text(
        " ".join(item.get("container-title", []))
    )
    abstract = clean_text(item.get("abstract"))

    metadata = [
        f"Título: {title}",
        f"Autores: {'; '.join(authors)}" if authors else "",
        f"Año: {year}" if year else "",
        f"Revista: {journal}" if journal else "",
        f"DOI: {doi}",
    ]

    content = "\n".join(x for x in metadata if x)
    if abstract:
        content += "\n\nResumen del artículo:\n" + abstract
    else:
        content += (
            "\n\nNo se obtuvo el resumen. "
            "Este registro contiene únicamente metadatos bibliográficos."
        )

    return title, f"https://doi.org/{doi}", content


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--langs", nargs="+", default=["en", "es"]
    )
    parser.add_argument("--workers", type=int, default=2)
    parser.add_argument(
        "--sources",
        nargs="+",
        choices=["wikipedia", "openalex", "crossref"],
        default=["wikipedia", "openalex", "crossref"]
    )
    parser.add_argument(
        "--mailto",
        default="",
        help="Correo para las API académicas; también puede usarse OPENALEX_EMAIL."
    )
    args = parser.parse_args()

    con = connect()
    session = http(pool=args.workers)
    mailto = args.mailto.strip()

    taxa = {
        row[0]: row[1]
        for row in con.execute("""
            SELECT t.taxon_key, t.canonical_name
            FROM taxa t
            JOIN dataset_scope ds USING (taxon_key)
            WHERE t.canonical_name IS NOT NULL
        """).fetchall()
    }

    log.info("Especies para textos: %d", len(taxa))

    try:
        for source in args.sources:
            if source == "wikipedia":
                for lang in args.langs:
                    task = f"text_{lang}"
                    for key, scientific_name in tqdm(
                        taxa.items(), desc=f"Wikipedia {lang}"
                    ):
                        # Si ya existe el texto, no repetir la consulta.
                        exists = con.execute("""
                            SELECT 1 FROM texts
                            WHERE taxon_key = %s
                              AND source = 'wikipedia'
                              AND language = %s
                        """, (key, lang)).fetchone()

                        if exists:
                            continue

                        try:
                            result = fetch_wikipedia(
                                session, scientific_name, lang
                            )
                            if result:
                                title, url, content = result
                                save_text(
                                    con, key, "wikipedia", lang,
                                    title, url, "CC-BY-SA-4.0", content
                                )

                                # El título se conserva como nombre común
                                # solo si difiere del nombre científico.
                                if title.lower() != scientific_name.lower():
                                    con.execute("""
                                        INSERT INTO vernacular_names
                                            (taxon_key, language, name, source)
                                        VALUES (%s, %s, %s, 'wikipedia')
                                        ON CONFLICT DO NOTHING
                                    """, (key, lang, title[:200]))

                            mark_done(con, task, key)
                            con.commit()

                        except Exception as exc:
                            con.rollback()
                            log.warning(
                                "Wikipedia %s (%s): %s",
                                scientific_name, lang, exc
                            )

            else:
                task = f"text_{source}"

                for key, scientific_name in tqdm(
                    taxa.items(), desc=source
                ):
                    exists = con.execute("""
                        SELECT 1 FROM texts
                        WHERE taxon_key = %s AND source = %s
                    """, (key, source)).fetchone()

                    if exists:
                        continue

                    try:
                        if source == "openalex":
                            result = fetch_openalex(
                                session, scientific_name, mailto
                            )
                        else:
                            result = fetch_crossref(
                                session, scientific_name, mailto
                            )

                        if result:
                            title, url, content = result
                            save_text(
                                con, key, source, "und",
                                title, url, None, content
                            )
                            log.info(
                                "%s: referencia encontrada para %s",
                                source, scientific_name
                            )
                        else:
                            log.info(
                                "%s: sin resultados para %s",
                                source, scientific_name
                            )

                        # Solo se marca si la consulta HTTP terminó bien.
                        mark_done(con, task, key)
                        con.commit()
                        time.sleep(0.15)

                    except Exception as exc:
                        con.rollback()
                        log.warning(
                            "%s (%s): %s",
                            source, scientific_name, exc
                        )

    finally:
        session.close()
        con.close()

    log.info("Recopilación multifuente terminada.")


if __name__ == "__main__":
    main()