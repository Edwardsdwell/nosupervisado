"""Paso 4: texto multilingüe (introducción de Wikipedia en en/es) + nombres comunes derivados del título."""
import argparse
from urllib.parse import quote
from concurrent.futures import ThreadPoolExecutor, as_completed
from tqdm import tqdm
from common import connect, http, log

DISAMBIG = ("may refer to", "puede referirse a", "puede hacer referencia")


def fetch_batch(s, lang, titles):
    params = {"action": "query", "format": "json", "formatversion": 2, "prop": "extracts",
              "exintro": 1, "explaintext": 1, "exlimit": "max", "redirects": 1, "titles": "|".join(titles)}
    url = f"https://{lang}.wikipedia.org/w/api.php"
    norm, redir, pages = {}, {}, {}
    while True:
        r = s.get(url, params=params, timeout=60).json()
        q = r.get("query", {})
        norm.update({x["from"]: x["to"] for x in q.get("normalized", [])})
        redir.update({x["from"]: x["to"] for x in q.get("redirects", [])})
        for p in q.get("pages", []):
            if p.get("extract") or p["title"] not in pages:
                pages[p["title"]] = p
        if "continue" in r:
            params.update(r["continue"])
        else:
            break
    out = []
    for orig in titles:
        t = norm.get(orig, orig)
        t = redir.get(t, t)
        p = pages.get(t)
        if not p or p.get("missing") or not p.get("extract"):
            continue
        txt = p["extract"].strip()
        if len(txt) < 80 or any(d in txt[:300].lower() for d in DISAMBIG):
            continue
        out.append((orig, t, txt))
    return lang, out


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--langs", nargs="+", default=["en", "es"])
    ap.add_argument("--workers", type=int, default=3)
    a = ap.parse_args()
    con, s = connect(), http()
    taxa = {r[1]: r[0] for r in con.execute(
        "SELECT t.taxon_key, t.canonical_name FROM taxa t JOIN dataset_scope ds USING (taxon_key) WHERE t.canonical_name IS NOT NULL")}
    names = sorted(taxa)
    jobs = []
    for lang in a.langs:
        done = {r[0] for r in con.execute("SELECT key FROM ingest_progress WHERE task=%s", (f"text_{lang}",))}
        todo = [n for n in names if str(taxa[n]) not in done]
        jobs += [(lang, todo[i:i + 20]) for i in range(0, len(todo), 20)]
    with ThreadPoolExecutor(a.workers) as ex:
        futs = {ex.submit(fetch_batch, s, l, t): (l, t) for l, t in jobs}
        for f in tqdm(as_completed(futs), total=len(futs), desc="wikipedia"):
            lang, titles = futs[f]
            try:
                _, found = f.result()
            except Exception as e:
                log.warning("lote falló: %s", e)
                continue
            with con.cursor() as cur:
                for orig, title, txt in found:
                    k = taxa[orig]
                    cur.execute("""INSERT INTO texts (taxon_key, source, language, title, url, license, content)
                                   VALUES (%s,'wikipedia',%s,%s,%s,'CC-BY-SA-4.0',%s)
                                   ON CONFLICT (taxon_key, source, language) DO NOTHING""",
                                (k, lang, title, f"https://{lang}.wikipedia.org/wiki/{quote(title.replace(' ', '_'))}", txt))
                    if title.lower() != orig.lower():  # el título del artículo suele ser el nombre común
                        cur.execute("""INSERT INTO vernacular_names (taxon_key, language, name, source)
                                       VALUES (%s,%s,%s,'wikipedia') ON CONFLICT DO NOTHING""", (k, lang, title[:200]))
                for t in titles:
                    cur.execute("INSERT INTO ingest_progress (task,key) VALUES (%s,%s) ON CONFLICT DO NOTHING",
                                (f"text_{lang}", str(taxa[t])))
            con.commit()


if __name__ == "__main__":
    main()
