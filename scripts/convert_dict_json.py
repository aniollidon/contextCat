from __future__ import annotations
import argparse
import json
import pickle
from pathlib import Path
from typing import Any

#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
Converteix un fitxer pickle (data/diccionari_full.pkl) a NDJSON.

Simplificat: si el pickle és un DiccionariFull, s'obre el pickle i es fa json.dumps(info(paraula))
per a cada paraula del diccionari (una línia JSON per paraula, format NDJSON). Per altres objectes,
emmagatzema un únic objecte JSON en una sola línia (també vàlid NDJSON).

Atenció: carregar fitxers pickle pot executar codi; només fes-ho si confies en l'origen.
"""

# Poosa al path l'arrel del projecte
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from diccionari_full import DiccionariFull  # noqa: F401 - mantingues-ho en l'espai global



def to_jsonable(obj: Any) -> Any:
    """Converteix recursivament objectes Python a una forma serialitzable en JSON."""
    # Dict: clau JSON ha de ser string
    if isinstance(obj, dict):
        return {str(k): to_jsonable(v) for k, v in obj.items()}
    # Llistes i tuples
    if isinstance(obj, (list, tuple)):
        return [to_jsonable(x) for x in obj]
    # Conjunts
    if isinstance(obj, set):
        return [to_jsonable(x) for x in obj]
    # Path
    if isinstance(obj, Path):
        return str(obj)
    # Numpy
    if np is not None:
        if isinstance(obj, (np.integer, np.floating, np.bool_)):  # type: ignore
            return obj.item()
        if isinstance(obj, np.ndarray):  # type: ignore
            return obj.tolist()
    # Tipus bàsics ja són JSON-serialitzables
    if isinstance(obj, (str, int, float, bool)) or obj is None:
        return obj
    # Fallback: intenta serialitzar directament
    try:
        json.dumps(obj)
        return obj
    except TypeError:
        # Com a últim recurs, converteix a string
        return str(obj)


def convert_pickle_to_json(pkl_path: Path, json_path: Path, compact: bool = False) -> None:
    with pkl_path.open("rb") as f:
        data = pickle.load(f)

    # Si és un DiccionariFull, escriu una línia JSON per paraula amb el resultat de info(paraula)
    try:
        if isinstance(data, DiccionariFull):  # type: ignore[name-defined]
            json_path.parent.mkdir(parents=True, exist_ok=True)
            with json_path.open("w", encoding="utf-8") as out:
                # Itera de manera estable
                for paraula in sorted(data.forma_to_lemmas.keys()):
                    info = data.info(paraula)
                    out.write(json.dumps(info, ensure_ascii=False))
                    out.write("\n")
            return
    except NameError:
        # Si no tenim la classe importada, cau al camí genèric
        pass

    # Camí genèric: bolca l'objecte com una sola línia NDJSON
    jsonable = to_jsonable(data)
    json_path.parent.mkdir(parents=True, exist_ok=True)
    with json_path.open("w", encoding="utf-8") as out:
        out.write(json.dumps(jsonable, ensure_ascii=False, separators=(",", ":") if compact else (",", ":")))
        out.write("\n")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(
        description="Converteix un fitxer .pkl a .json"
    )
    parser.add_argument(
        "input",
        nargs="?",
        default="data/diccionari_full.pkl",
        help="Ruta al fitxer .pkl (per defecte: data/diccionari_full.pkl)",
    )
    parser.add_argument(
        "-o",
        "--output",
        default=None,
    help="Ruta de sortida .ndjson (per defecte: mateix nom amb extensió .ndjson)",
    )
    parser.add_argument(
        "--compact",
        action="store_true",
        help="JSON compacte (sense sagnat)",
    )
    args = parser.parse_args()

    pkl_path = Path(args.input)
    if not pkl_path.exists():
        raise SystemExit(f"No s'ha trobat el fitxer: {pkl_path}")

    json_path = Path(args.output) if args.output else pkl_path.with_suffix(".ndjson")

    convert_pickle_to_json(pkl_path, json_path, compact=args.compact)
    print(f"Desat NDJSON a: {json_path}")