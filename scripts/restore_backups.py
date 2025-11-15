#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
Restaura tots els fitxers d'una carpeta 'bak' cap a la carpeta 'words'.

Per defecte:
  - Origen: data/words/bak
  - Destí:  data/words

Per cada fitxer a l'origen, si acaba en '.bak' se n'elimina l'extensió
per al nom de destí i se sobreescriu.

Ús:
  python scripts/restore_backups.py               # usa valors per defecte
  python scripts/restore_backups.py --src SRC --dst DST
"""

from __future__ import annotations
from pathlib import Path
import argparse
import shutil


def restore_backups(src: Path, dst: Path) -> int:
    if not src.exists() or not src.is_dir():
        print(f"Carpeta d'origen inexistent o no vàlida: {src}")
        return 1
    dst.mkdir(parents=True, exist_ok=True)

    count = 0
    for p in sorted(src.iterdir()):
        if not p.is_file():
            continue
        name = p.name
        if name.endswith('.bak'):
            name = name[:-4]
        target = dst / name
        shutil.copyfile(p, target)
        count += 1
        print(f"Restaurat: {p.name} -> {target.name}")
    print(f"Total restaurats: {count}")
    return 0


def main() -> int:
    root = Path(__file__).resolve().parent.parent
    p = argparse.ArgumentParser(description="Restaura backups (.bak) a la carpeta words")
    p.add_argument("--src", type=Path, default=root / "data" / "words" / "bak", help="Carpeta d'origen (per defecte: data/words/bak)")
    p.add_argument("--dst", type=Path, default=root / "data" / "words", help="Carpeta de destí (per defecte: data/words)")
    args = p.parse_args()
    return restore_backups(args.src, args.dst)


if __name__ == "__main__":
    raise SystemExit(main())
