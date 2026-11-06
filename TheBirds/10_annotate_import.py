"""Utilidad de anotación manual: genera una hoja CSV para etiquetar audios y luego la importa.

  python 10_annotate_import.py --make-sheet hoja.csv --n 200      # muestra aleatoria de audios
  python 10_annotate_import.py --import hoja.csv --annotator ana  # carga las etiquetas rellenadas

Columnas a rellenar: label (clean|noise), noise_types (separados por ';'), call_type, notes.
"""
import argparse, csv
from common import connect, log, DATA_DIR


def make_sheet(con, path, n):
    rows = con.execute("""SELECT m.media_id, m.file_path FROM media m
        WHERE m.type='audio' AND m.download_status='ok'
          AND EXISTS (SELECT 1 FROM observations o JOIN dataset_scope ds USING (taxon_key) WHERE o.obs_id=m.obs_id)
          AND NOT EXISTS (SELECT 1 FROM annotations a WHERE a.media_id=m.media_id)
        ORDER BY random() LIMIT %s""", (n,)).fetchall()
    with open(path, "w", newline="", encoding="utf-8") as f:
        w = csv.writer(f)
        w.writerow(["media_id", "file", "label", "noise_types", "call_type", "notes"])
        for mid, rel in rows:
            w.writerow([mid, str(DATA_DIR / rel), "", "", "", ""])
    log.info("Hoja con %d audios: %s", len(rows), path)


def import_sheet(con, path, annotator):
    n = 0
    with open(path, newline="", encoding="utf-8") as f:
        for r in csv.DictReader(f):
            label = (r.get("label") or "").strip().lower()
            if label not in ("clean", "noise"):
                continue
            nt = [x.strip() for x in (r.get("noise_types") or "").split(";") if x.strip()] or None
            con.execute("""INSERT INTO annotations (media_id, annotator, label, noise_types, call_type, notes)
                VALUES (%s,%s,%s,%s,%s,%s)
                ON CONFLICT (media_id, annotator) DO UPDATE
                SET label=EXCLUDED.label, noise_types=EXCLUDED.noise_types,
                    call_type=EXCLUDED.call_type, notes=EXCLUDED.notes""",
                        (int(r["media_id"]), annotator, label, nt, r.get("call_type") or None, r.get("notes") or None))
            n += 1
    con.commit()
    log.info("Anotaciones importadas: %d", n)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--make-sheet")
    ap.add_argument("--n", type=int, default=200)
    ap.add_argument("--import", dest="imp")
    ap.add_argument("--annotator", default="anon")
    a = ap.parse_args()
    con = connect()
    if a.make_sheet:
        make_sheet(con, a.make_sheet, a.n)
    if a.imp:
        import_sheet(con, a.imp, a.annotator)


if __name__ == "__main__":
    main()
