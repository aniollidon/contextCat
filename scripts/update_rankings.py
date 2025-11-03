#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
Actualitza fitxers de rànquing perquè s'alineïn amb el diccionari reduït actual.

Comportament:
- Per a cada fitxer de rànquing (.json) indicat o dins d'una carpeta indicada:
  - Elimina del rànquing les paraules (claus) que no són lemes vàlids al diccionari reduït.
    - Si una paraula no és al diccionari reduït però tampoc està marcada com a EXCLOSA al fitxer d'exclusions,
    demana a l'usuari què vol fer:
      * [r] retirar del rànquing (per defecte)
      * [k] mantenir-la al rànquing
      * [e] excloure el seu lema afegint-lo a data/exclusions.json (llista de "lemmas") i retirar-la del rànquing

Ús:
  python scripts/update_rankings.py path\o\carpeta\o\fitxer.json [--dry-run] [--yes]

Notes:
- Es crea una còpia .bak del fitxer abans de sobreescriure'l (excepte en --dry-run).
- Els valors de rànquing existents es conserven (no es reindexen).
"""

from __future__ import annotations
import argparse
import json
from pathlib import Path
from typing import Dict, Tuple, Set, Iterable


# Poosa al path l'arrel del projecte
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
ROOT = Path(__file__).resolve().parent.parent


def _load_exclusions_json() -> Tuple[Set[str], Set[str]]:
    """Retorna (formes, lemes) a partir de data/exclusions.json si existeix.
    Format esperat: {"lemmas": [...], "formes": [...]};
    Compatibilitat: si és una llista, es considera llista de lemes.
    """
    path = ROOT / "data" / "exclusions.json"
    if not path.exists():
        return set(), set()
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return set(), set()
    forms: Set[str] = set()
    lemmas: Set[str] = set()
    if isinstance(data, dict):
        forml = data.get("formes") or []
        leml = data.get("lemmas") or []
        if isinstance(forml, list):
            forms = {str(x).lower() for x in forml}
        if isinstance(leml, list):
            lemmas = {str(x).lower() for x in leml}
    elif isinstance(data, list):
        lemmas = {str(x).lower() for x in data}
    return forms, lemmas


def _save_exclusions_json(forms: Set[str], lemmas: Set[str]) -> None:
    """Desa exclusions a data/exclusions.json en format nou (objecte {lemmas, formes})."""
    path = ROOT / "data" / "exclusions.json"
    payload = {
        "lemmas": sorted(lemmas),
        "formes": sorted(forms),
    }
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")


def _iter_ranking_files(input_path: Path) -> Iterable[Path]:
    if input_path.is_file() and input_path.suffix.lower() == ".json":
        yield input_path
    elif input_path.is_dir():
        for p in sorted(input_path.glob("*.json")):
            if p.is_file():
                yield p
    else:
        raise FileNotFoundError(f"Ruta no vàlida: {input_path}")


def _prompt_action(word: str) -> str:
    prompt = (
        f"La paraula '{word}' no és al diccionari reduït i NO està marcada com a exclosa. Opcions:\n"
        "  [r] retirar del rànquing (per defecte)\n"
        "  [k] mantenir-la al rànquing\n"
        "  [e] excloure el seu lema a data/exclusions.json i retirar-la\n"
        "> "
    )
    try:
        ans = input(prompt).strip().lower()
    except EOFError:
        ans = "r"
    if ans in {"k", "e", "r"}:
        return ans
    return "r"


def process_ranking_file(path: Path, dry_run: bool, auto_yes: bool) -> bool:
    from diccionari import Diccionari

    print(f"Processant rànquing: {path}")
    data = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(data, dict):
        print(" - Format no reconegut (s'espera objecte JSON mapping forma->valor)")
        return False

    # Lemas vàlids al diccionari reduït
    reduced = Diccionari.load(str(ROOT / "data" / "diccionari.json"))
    valid_lemmas: Set[str] = set(reduced.canoniques.keys())

    # Exclusions: només el fitxer d'exclusions és la font de veritat
    exc_forms, exc_lemmas = _load_exclusions_json()
    excluded_lemmas: Set[str] = set(exc_lemmas)

    # Clau del rànquing = lema canònic
    invalid_keys = [k for k in data.keys() if k not in valid_lemmas]
    if not invalid_keys:
        print(" - Cap canvi: totes les paraules ja són vàlides al diccionari reduït")
        return False

    changed = False
    for k in sorted(invalid_keys):
        if k in excluded_lemmas:
            # Exclosa al fitxer d'exclusions -> elimina del rànquing
            print(f" - Eliminant '{k}' (lema exclòs a exclusions.json)")
            if not dry_run:
                data.pop(k, None)
            changed = True
            continue

        # No és al reduït i no està exclòs -> demanar a l'usuari
        action = "r" if auto_yes else _prompt_action(k)
        if action == "k":
            print(f" - Mantenint '{k}'")
            continue
        elif action == "e":
            print(f" - Afegint '{k}' a exclusions (lemmas) i retirant del rànquing")
            excluded_lemmas.add(k)
            if not dry_run:
                # Desa exclusions
                _save_exclusions_json(exc_forms, excluded_lemmas)
                data.pop(k, None)
            changed = True
        else:  # 'r'
            print(f" - Retirant '{k}' del rànquing")
            if not dry_run:
                data.pop(k, None)
            changed = True

    if changed and not dry_run:
        # Reindexa per evitar salts numèrics: 0..N-1 segons ordre original de rànquing
        ordered = sorted(data.items(), key=lambda kv: (kv[1], kv[0]))
        reindexed = {k: i for i, (k, _v) in enumerate(ordered)}

        # Backup i desa
        backup = path.with_suffix(path.suffix + ".bak")
        try:
            backup.write_text(json.dumps(json.loads(path.read_text(encoding="utf-8")), ensure_ascii=False, indent=2), encoding="utf-8")
        except Exception:
            pass
        path.write_text(json.dumps(reindexed, ensure_ascii=False, indent=2), encoding="utf-8")
        print(" - Desat, rànquing reindexat (i còpia .bak creada)")
    elif changed:
        print(" - Canvis no desats (--dry-run)")
    else:
        print(" - Cap canvi efectuat")

    return changed


def main() -> int:
    p = argparse.ArgumentParser(description="Actualitza fitxers de rànquing segons el diccionari reduït")
    p.add_argument("path", type=Path, help="Fitxer .json o carpeta que conté fitxers .json")
    p.add_argument("--dry-run", action="store_true", help="No desa canvis ni exclusions; només mostra")
    p.add_argument("--yes", action="store_true", help="No interactiu: elimina per defecte els no vàlids (manté els ja vàlids)")
    args = p.parse_args()

    target = args.path
    any_changed = False
    for f in _iter_ranking_files(target):
        ch = process_ranking_file(f, dry_run=args.dry_run, auto_yes=args.yes)
        any_changed = any_changed or ch
    return 0 if any_changed or args.dry_run else 0


if __name__ == "__main__":
    raise SystemExit(main())
