"""Ejecutor secuencial de etapas. Cada script corre en un proceso hijo independiente."""
import argparse, subprocess, sys, os
from pathlib import Path

ROOT = Path(__file__).resolve().parent


def commands(args):
    w, b, cap = str(args.workers), str(args.batch), str(args.max_gb)
    steps = {
        "init": ["01_init_db.py"],
        "taxonomy": ["02_taxonomy.py", "--max-taxa", str(args.max_taxa), "--seed", str(args.seed), "--workers", w],
        "occurrences_image": ["03_occurrences.py", "--media", "image", "--workers", w],
        "occurrences_audio": ["03_occurrences.py", "--media", "audio", "--workers", w],
        "texts": ["04_texts.py", "--langs", *args.langs],
        "download_image": ["05_download_media.py", "--type", "image", "--workers", w, "--batch", b, "--max-total-gb", cap],
        "download_audio": ["05_download_media.py", "--type", "audio", "--workers", w, "--batch", b, "--max-total-gb", cap],
        "quality": ["06_quality.py", "--workers", w],
        "pairs_splits": ["07_pairs_and_splits.py"],
        "environment": ["08_environment.py", "--download", "--batch", "1000"],
        "export": ["09_export.py"],
        "validate": ["11_validate.py"],
    }
    all_order = ["init", "taxonomy", "occurrences_image", "occurrences_audio", "texts",
                 "download_image", "download_audio", "quality", "pairs_splits", "export", "validate"]
    return steps, all_order


def main():
    p = argparse.ArgumentParser()
    p.add_argument("--stage", default="")
    p.add_argument("--all", action="store_true")
    p.add_argument("--workers", type=int, default=4)
    p.add_argument("--batch", type=int, default=20)
    p.add_argument("--max-gb", type=float, default=1.5)
    p.add_argument("--max-taxa", type=int, default=100)
    p.add_argument("--seed", type=int, default=20261106)
    p.add_argument("--langs", nargs="+", default=["es", "en"])
    args = p.parse_args()
    steps, order = commands(args)
    selected = order if args.all else [args.stage]
    if not args.all and args.stage == "environment":
        pass
    for name in selected:
        if name not in steps:
            print(f"Etapa desconocida: {name}", flush=True); return 2
        cmd = [sys.executable, "-u", *steps[name]]
        print("\n" + "="*72 + f"\nINICIO: {name}\n$ {' '.join(cmd)}\n" + "="*72, flush=True)
        result = subprocess.run(cmd, cwd=ROOT, env=os.environ.copy())
        print(f"FIN: {name} | código de salida: {result.returncode}", flush=True)
        if result.returncode != 0:
            print(f"PIPELINE DETENIDO en {name}; no se ejecutan las etapas siguientes.", flush=True)
            return result.returncode
    print("\nPIPELINE COMPLETADO", flush=True)
    return 0

if __name__ == "__main__":
    raise SystemExit(main())
