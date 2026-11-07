
"""Ejecutor secuencial del pipeline TheBirds."""
import argparse
import os
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent


def commands(args):
    w = str(args.workers)
    b = str(args.batch)
    cap = str(args.max_gb)

    steps = {
        "init": ["01_init_db.py"],
        "taxonomy": [
            "02_taxonomy.py", "--max-taxa", str(args.max_taxa),
            "--seed", str(args.seed), "--workers", w
        ],
        "occurrences_image": [
            "03_occurrences.py", "--media", "image", "--workers", w
        ],
        "occurrences_audio": [
            "03_occurrences.py", "--media", "audio", "--workers", w
        ],
        "texts": ["04_texts.py", "--langs", *args.langs],
        "download_image": [
            "05_download_media.py", "--type", "image",
            "--workers", w, "--batch", b, "--max-total-gb", cap
        ],
        "download_audio": [
            "05_download_media.py", "--type", "audio",
            "--workers", w, "--batch", b, "--max-total-gb", cap
        ],
        "media_import": ["05b_import_media_to_db.py"],
        "quality": ["06_quality.py", "--workers", w],
        "pairs_splits": [
            "07_pairs_and_splits.py",
            "--radius-km", str(args.radius_km),
            "--days", str(args.days)
        ],
        "environment": [
            "08_environment.py", "--download", "--batch", "1000"
        ],
        "export": ["09_export.py"],
        "validate": ["11_validate.py"],
    }

    all_order = [
        "init",
        "taxonomy",
        "occurrences_image",
        "occurrences_audio",
        "texts",
        "download_image",
        "download_audio",
        "media_import",
        "quality",
        "pairs_splits",
        "environment",
        "export",
        "validate",
    ]

    return steps, all_order


def main():
    p = argparse.ArgumentParser(
        description="Control secuencial del dataset multimodal de aves."
    )

    p.add_argument("--stage", default="")
    p.add_argument("--all", action="store_true")
    p.add_argument("--workers", type=int, default=4)
    p.add_argument("--batch", type=int, default=20)
    p.add_argument("--max-gb", type=float, default=1.5)
    p.add_argument("--max-taxa", type=int, default=100)
    p.add_argument("--seed", type=int, default=20261106)
    p.add_argument("--langs", nargs="+", default=["es", "en"])
    p.add_argument("--radius-km", type=float, default=5)
    p.add_argument("--days", type=int, default=7)

    args = p.parse_args()
    steps, order = commands(args)

    if args.all and args.stage:
        p.error("Usa --all o --stage, no ambos.")

    if not args.all and not args.stage:
        p.error("Debes indicar --stage NOMBRE o --all.")

    selected = order if args.all else [args.stage]

    for name in selected:
        if name not in steps:
            print(f"Etapa desconocida: {name}", flush=True)
            return 2

        script = ROOT / steps[name][0]

        if not script.exists():
            print(f"No existe el script: {script}", flush=True)
            return 2

        cmd = [sys.executable, "-u", *steps[name]]

        print(
            "\n" + "=" * 72
            + f"\nINICIO: {name}\n$ {' '.join(cmd)}\n"
            + "=" * 72,
            flush=True
        )

        result = subprocess.run(
            cmd,
            cwd=ROOT,
            env=os.environ.copy()
        )

        print(
            f"FIN: {name} | código de salida: {result.returncode}",
            flush=True
        )

        if result.returncode != 0:
            print(
                f"PIPELINE DETENIDO en {name}. "
                "No se ejecutan las etapas siguientes.",
                flush=True
            )
            return result.returncode

    print("\nPIPELINE COMPLETADO", flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
