#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
Funcions:
- Fonts d'exclusió (Softcatalà exclusions.txt i/o fitxer local)
- Filtre de formes no alfabètiques (descarta formes que no són exclusivament lletres)
- Filtre per categories (per defecte comencen per D/P/R/S/C/I), amb opció de definir manualment els prefixos
	de categories a excloure (separats per comes) utilitzant DiccionariFull
"""

from __future__ import annotations
import argparse
import json
import os
import re
from collections import defaultdict
from dataclasses import dataclass
from pathlib import Path
from typing import Dict, Iterable, List, Optional, Set, Tuple


# Poosa al path l'arrel del projecte
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
ROOT = Path(__file__).resolve().parent.parent


from diccionari_full import DiccionariFull  

EXCLUSIONS_URL = (
	"https://raw.githubusercontent.com/Softcatala/catalan-dict-tools/refs/heads/master/"
	"fdic-to-hunspell/dades/exclusions.txt"
)

# Categories a excloure per prefix (D, P, R, S, C, I)
# Qualsevol categoria que comenci per aquests prefixos serà exclosa
DISALLOWED_CAT_PREFIX = {"D", "P", "R", "S", "C", "I"}


@dataclass
class Changes:
	excluded_forms: Set[str]
	excluded_lemmas: Set[str]
	reasons_formes: Dict[str, Set[str]]  # forma -> {motiu, ...}
	reasons_lemmas: Dict[str, Set[str]]  # lema  -> {motiu, ...}


def _load_exclusions_bimodal(url: Optional[str], local_file: Optional[Path]) -> Tuple[Set[str], Set[str]]:
	"""Carrega exclusions des d'URL i/o fitxer local, separant FORMES i LEMES.
	El format accepta comentaris que canvien el mode:
	  #EXCLOU FORMA ... -> les línies següents són FORMES
	  #EXCLOU LEMA  ... -> les línies següents són LEMES
	Si no hi ha cap indicació, per defecte es consideren FORMES.
	Retorna (formes, lemes).
	"""
	def parse_text(txt: str) -> Tuple[Set[str], Set[str]]:
		fset: Set[str] = set()
		lset: Set[str] = set()
		mode = "forma"  # per defecte formes
		for raw in txt.splitlines():
			line = raw.strip()
			if not line:
				continue
			if line.startswith("#"):
				marker = line.upper()
				if "EXCLOU" in marker and "LEMA" in marker:
					mode = "lema"
				elif "EXCLOU" in marker and "FORMA" in marker:
					mode = "forma"
				continue
			w = line.lower()
			if mode == "lema":
				lset.add(w)
			else:
				fset.add(w)
		return fset, lset

	forms: Set[str] = set()
	lemmas: Set[str] = set()
	if url:
		try:
			import requests
			r = requests.get(url, timeout=15)
			r.raise_for_status()
			fset, lset = parse_text(r.text)
			forms.update(fset)
			lemmas.update(lset)
		except Exception as e:  # pragma: no cover
			print(f"AVÍS: No s'ha pogut descarregar exclusions des de {url}: {e}")
	if local_file and local_file.exists():
		try:
			with local_file.open(encoding="utf-8") as f:
				txt = f.read()
			fset, lset = parse_text(txt)
			forms.update(fset)
			lemmas.update(lset)
		except Exception as e:  # pragma: no cover
			print(f"AVÍS: No s'ha pogut llegir exclusions locals {local_file}: {e}")
	return forms, lemmas


def _is_alpha_catalan(word: str, allow: str = "") -> bool:
	"""Retorna True si tots els caràcters són lletres (unicode) o estan a allow.
	El punt volat (·) sempre és permès. Exemple d'allow: "'-" si es volen permetre apòstrofs o guions.
	"""
	if not word:
		return False
	allowed = {"·"} | set(allow)
	for ch in word:
		if ch in allowed:
			continue
		if not ch.isalpha():
			return False
	return True


def compute_exclusions(
	apply_list: bool,
	apply_nonalpha: bool,
	apply_categories: bool,
	exclusions_url: Optional[str],
	exclusions_file: Optional[Path],
	allow_chars: str,
	disallowed_prefixes: Optional[Set[str]] = None,
) -> Changes:
	"""Calcula exclusions utilitzant com a base el pickle de DiccionariFull (data/diccionari_full.pkl).
	D'aquí obtenim totes les formes i les categories.
	"""
	from diccionari_full import DiccionariFull

	# Carrega el diccionari complet des de pickle (o el genera si cal)
	full_path = ROOT / "data" / DiccionariFull.FULL_CACHE_FILE
	if full_path.exists():
		full = DiccionariFull.load(str(full_path))
	else:
		# Pot requerir xarxa; un cop generat, queda en pickle
		full = DiccionariFull.obtenir_diccionari_full(use_cache=False)
		full.save(str(full_path))

	# Universe de formes a avaluar: totes les formes conegudes al diccionari complet
	formes_universe = list(full.forma_to_lemmas.keys())
	lemmas_universe = set(full.lemma_to_forms.keys())

	excluded_forms: Set[str] = set()
	excluded_lemmas: Set[str] = set()
	reasons_formes: Dict[str, Set[str]] = defaultdict(set)
	reasons_lemmas: Dict[str, Set[str]] = defaultdict(set)

	# 1) Llista d'exclusions oficial i/o local
	if apply_list:
		list_forms, list_lemmas = _load_exclusions_bimodal(exclusions_url, exclusions_file)
		# FORMES
		for w in list_forms:
			if w in full.forma_to_lemmas:
				excluded_forms.add(w)
				reasons_formes[w].add("llista-official-forma")
		# LEMES
		for l in list_lemmas:
			if l in lemmas_universe:
				excluded_lemmas.add(l)
				reasons_lemmas[l].add("llista-official-lema")

	# 2) No alfabètiques
	if apply_nonalpha:
		for forma in formes_universe:
			if not _is_alpha_catalan(forma, allow=allow_chars):
				excluded_forms.add(forma)
				reasons_formes[forma].add("no-alfabètica")

	# 3) Categories (via DiccionariFull)
	if apply_categories:
		try:
			# Prefixos efectius: els passats per flag o els per defecte
			effective_prefixes: Set[str] = set(disallowed_prefixes) if disallowed_prefixes else set(DISALLOWED_CAT_PREFIX)
			for lemma in lemmas_universe:
				all_cats: Set[str] = set(full.lemma_categories.get(lemma, ()))
				if not all_cats:
					continue
				# Si alguna categoria comença amb algun prefix prohibit -> exclou LEMA
				if any(any(c.startswith(p) for p in effective_prefixes) for c in all_cats):
					excluded_lemmas.add(lemma)
					reasons_lemmas[lemma].add("categoria-" + "-".join(sorted(all_cats)))
		except Exception as e:  # pragma: no cover
			print(f"AVÍS: No s'ha pogut aplicar filtre per categories: {e}")

	return Changes(
		excluded_forms=excluded_forms,
		excluded_lemmas=excluded_lemmas,
		reasons_formes=reasons_formes,
		reasons_lemmas=reasons_lemmas,
	)


def save_exclusions_summary(path: Path, changes: Changes) -> None:
	path.parent.mkdir(parents=True, exist_ok=True)
	# Nota: ara el fitxer de resum es defineix des de main() per escriure 'excluded_lemmas'.
	# Mantenim aquesta funció com a utilitat genèrica si calgués en el futur.
	payload = {
		"excluded": sorted(changes.excluded_forms),
		"reasons": {k: sorted(list(v)) for k, v in changes.reasons.items()},
	}
	path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")


def main(argv: Optional[Iterable[str]] = None) -> int:
	parser = argparse.ArgumentParser(description="Exclou paraules del diccionari i rànquings amb filtres independents")
	# Selecció de filtres
	parser.add_argument("--from-exclusions-list", action="store_true", help="Aplica la llista oficial d'exclusions (Softcatalà)")
	parser.add_argument("--exclude-nonalphabetic", action="store_true", help="Exclou formes que no són 100% lletres o punts volats (·)")
	parser.add_argument("--exclude-categories", action="store_true", help="Exclou segons categories que COMENCEN per determinats prefixos via DiccionariFull")
	parser.add_argument(
		"--disallow-categories",
		type=str,
		default=None,
		help=(
			"Prefixos o codis de categories separats per comes per excloure (p.ex. D,P,R,S,C,I o NC,VM). "
			"Si no s'especifica, s'usen els per defecte: D,P,R,S, C, I."
		),
	)
	parser.add_argument("--allow-chars", default="", help="Caràcters addicionals permesos (el punt volat · ja es permet sempre)")
	# Origen de dades
	parser.add_argument("--exclusions-url", default=EXCLUSIONS_URL, help="URL de la llista d'exclusions")
	parser.add_argument("--exclusions-file", type=Path, default=None, help="Fitxer local extra amb paraules a excloure (una per línia)")
	# Execució
	parser.add_argument("--save-summary", action="store_true", help="Desa data/exclusions_why.json amb el detall")
	parser.add_argument("--print-limit", type=int, default=50, help="Límit d'impressió de paraules exclosas (0 = totes)")

	args = parser.parse_args(list(argv) if argv is not None else None)

	# Calcula exclusions segons flags
	# Construeix el conjunt de prefixos des del flag (si s'ha especificat)
	user_prefixes: Optional[Set[str]] = None
	if args.disallow_categories:
		tokens = [t.strip() for t in args.disallow_categories.split(",")]
		user_prefixes = {t for t in tokens if t}

	changes = compute_exclusions(
		apply_list=args.from_exclusions_list,
		apply_nonalpha=args.exclude_nonalphabetic,
		apply_categories=args.exclude_categories,
		exclusions_url=args.exclusions_url,
		exclusions_file=args.exclusions_file,
		allow_chars=args.allow_chars,
		disallowed_prefixes=user_prefixes,
	)

	# Carrega el diccionari reduït i filtra perquè només entri el que ja existeix al diccionari
	from diccionari import Diccionari
	reduced_path = ROOT / "data" / "diccionari.json"
	try:
		dicc_reduced = Diccionari.load(str(reduced_path))
		reduced_forms: Set[str] = set(dicc_reduced.mapping_flexions_multi.keys()) | set(dicc_reduced.mapping_flexions.keys())
	except Exception as e:
		print(f"AVÍS: No s'ha pogut carregar el diccionari reduït ({reduced_path}): {e}")
		reduced_forms = set()

	# 1) Formes: filtra al diccionari reduït
	filtered_excluded_forms: List[str] = sorted(w for w in changes.excluded_forms if w in reduced_forms)
	# 2) Lemes: filtra a lemes del diccionari reduït
	reduced_lemmas: Set[str] = set(dicc_reduced.canoniques.keys())
	filtered_excluded_lemmas: List[str] = sorted(l for l in changes.excluded_lemmas if l in reduced_lemmas)

	# 3) Motius: separem per formes i per lemes.
	reasons_formes_filtered: Dict[str, Set[str]] = {f: changes.reasons_formes.get(f, set()) for f in filtered_excluded_forms}
	reasons_lemmas_filtered: Dict[str, Set[str]] = {l: changes.reasons_lemmas.get(l, set()) for l in filtered_excluded_lemmas}

	# 4) Impressió
	total_lemmas = len(filtered_excluded_lemmas)
	total_forms = len(filtered_excluded_forms)
	print(f"Detectats {total_lemmas} lemes i {total_forms} formes per excloure (després de filtrar pel diccionari reduït).")
	# Mostra llista simple (prioritza lemes; després formes si hi ha marge)
	limit = args.print_limit
	to_show_lemmas = list(filtered_excluded_lemmas)
	to_show_forms = list(filtered_excluded_forms)
	if limit > 0:
		to_show_lemmas = to_show_lemmas[:limit]
		leftover = max(0, limit - len(to_show_lemmas))
		to_show_forms = to_show_forms[:leftover] if leftover > 0 else []
	if to_show_lemmas:
		print("Lemes exclosos:")
		print("\n".join(to_show_lemmas))
		if limit > 0 and total_lemmas > len(to_show_lemmas):
			print(f"... i {total_lemmas - len(to_show_lemmas)} més")
	if to_show_forms:
		print("Formes excloses:")
		print("\n".join(to_show_forms))
		if limit > 0 and total_forms > len(to_show_forms):
			print(f"... i {total_forms - len(to_show_forms)} més")

	# Resum per motiu
	# Resum per motiu, separat
	if reasons_lemmas_filtered:
		by_reason_lemmas: Dict[str, int] = defaultdict(int)
		for _w, rs in reasons_lemmas_filtered.items():
			for r in rs:
				by_reason_lemmas[r] += 1
		print("\nResum per motiu (lemes):")
		for r, n in sorted(by_reason_lemmas.items(), key=lambda kv: (-kv[1], kv[0])):
			print(f"- {r}: {n}")
	if reasons_formes_filtered:
		by_reason_forms: Dict[str, int] = defaultdict(int)
		for _w, rs in reasons_formes_filtered.items():
			for r in rs:
				by_reason_forms[r] += 1
		print("\nResum per motiu (formes):")
		for r, n in sorted(by_reason_forms.items(), key=lambda kv: (-kv[1], kv[0])):
			print(f"- {r}: {n}")

	# Desa fitxers de sortida
	out_dir = ROOT / "data"
	out_dir.mkdir(parents=True, exist_ok=True)
	# 1) Fitxer principal: objecte amb llistes 'lemmas' i 'formes'
	exclusions_obj = {
		"lemmas": filtered_excluded_lemmas,
		"formes": filtered_excluded_forms,
	}
	exclusions_list_path = out_dir / "exclusions.tmp.json"
	exclusions_list_path.write_text(json.dumps(exclusions_obj, ensure_ascii=False, indent=2), encoding="utf-8")
	print("S'ha desat la llista d'exclusions (lemmas/formes) a data/exclusions.tmp.json")

	# 2) Si es demana, fitxer de detalls a exclusions_why.json
	if args.save_summary:
		summary_payload = {
			"lemmas": filtered_excluded_lemmas,
			"formes": filtered_excluded_forms,
			"reasons_lemmas": {k: sorted(list(v)) for k, v in reasons_lemmas_filtered.items()},
			"reasons_formes": {k: sorted(list(v)) for k, v in reasons_formes_filtered.items()},
		}
		(out_dir / "exclusions_why.json").write_text(json.dumps(summary_payload, ensure_ascii=False, indent=2), encoding="utf-8")
		print("S'ha desat el resum a data/exclusions_why.json")

	return 0


if __name__ == "__main__":
	raise SystemExit(main())







