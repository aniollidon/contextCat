import os
import re
import json
import pickle
from collections import defaultdict
from typing import Dict, Set, Tuple, Optional, List

import requests


class DiccionariFull:
    """
    Diccionari complet sense filtre de freqüència, pensat per a accés ràpid i missatges d'error detallats.

    Dades principals (totes normalitzades a minúscules):
    - forma_to_lemmas: dict forma -> tuple(lemmas base) [pot haver-hi múltiples lemes per una forma]
    - lemma_to_forms: dict lema  -> tuple(formes)
    - lemma_categories: dict lema -> tuple(codis categoria de 2 lletres, p.ex. 'NC','VM','RG'...)
    - lemma_freq: dict lema -> freqüència (int, 0 per defecte si no trobat)
    - forma_primary: dict forma -> lema triat com a principal (per defecte, el de freq més alta)

    Útil per:
    - comprovar si una paraula és adverbi, determinant, etc.
    - mesurar si una paraula és massa poc comuna segons un llindar.
    """

    DATA_DIR = "data"
    FULL_CACHE_FILE = "diccionari_full.pkl"

    # Fonts
    FREQ_URL = (
        "https://raw.githubusercontent.com/Softcatala/catalan-dict-tools/refs/heads/master/frequencies/"
        "frequencies-dict-lemmas.txt"
    )
    DICCIONARI_URLS = [
        (
            "lt",
            "https://raw.githubusercontent.com/Softcatala/catalan-dict-tools/master/resultats/lt/diccionari.txt",
        ),
    ]

    # Categories permeses pel joc (igual que Diccionari.es_categoria_valida -> 'NC' i 'VM')
    ALLOWED_CAT2 = {"NC", "VM"}

    # Mapeig de codis (2 lletres) a etiqueta humana (Català)
    CAT2_LABELS = {
        "NC": "un nom comú",
        "NP": "un nom propi",
        "VM": "un verb",
        "VA": "un verb auxiliar",
        "VS": "un verb ser/estar",
        "AQ": "un adjectiu",
        "RG": "un adverbi",
        "RB": "un adverbi",
        "SP": "una preposició",
        "CC": "una conjunció coordinada",
        "CS": "una conjunció subordinada",
        "DI": "un determinant",
        "DA": "un determinant",
        "PP": "un pronom",
        "PD": "un pronom",
        "Z": "un numeral",
        "I": "una interjecció",
    }

    def __init__(
        self,
        forma_to_lemmas: Dict[str, Tuple[str, ...]],
        lemma_to_forms: Dict[str, Tuple[str, ...]],
        lemma_categories: Dict[str, Tuple[str, ...]],
        lemma_freq: Dict[str, int],
        forma_primary: Dict[str, str],
    ):
        self.forma_to_lemmas = forma_to_lemmas
        self.lemma_to_forms = lemma_to_forms
        self.lemma_categories = lemma_categories
        self.lemma_freq = lemma_freq
        self.forma_primary = forma_primary

        # Caches efímers (no serialitzats) per velocitat d'accés (sets per membership O(1))
        self._forma_to_lemmas_set = {
            f: set(lemes) for f, lemes in self.forma_to_lemmas.items()
        }
        self._lemma_categories_set = {
            l: set(cats) for l, cats in self.lemma_categories.items()
        }

    # ------------------------------ Construcció i càrrega ------------------------------
    @staticmethod
    def _normalitzar_paraula(paraula: str) -> str:
        return paraula.lower().strip()

    @staticmethod
    def _normalitzar_lema(lema: str) -> str:
        # Elimina sufix numèric (lema1, lema2 -> lema) per unificar variants numèriques
        return re.sub(r"\d+$", "", lema.lower().strip())

    @classmethod
    def _descarregar(cls, url: str) -> str:
        r = requests.get(url)
        r.raise_for_status()
        return r.text

    @classmethod
    def _processar_diccionari_text(
        cls, contingut: str
    ) -> Tuple[Dict[str, Set[str]], Dict[str, Set[str]], Dict[str, Set[str]]]:
        """
        Retorna:
          - forma_to_lemmas_set: flexió -> {lemes base}
          - lemma_to_forms_set: lema -> {flexions}
          - lemma_categories_set: lema -> {cats2}
        No filtra per categoria; només retalla a 2 lletres i unifica lemes numerats.
        """
        forma_to_lemmas_set: Dict[str, Set[str]] = defaultdict(set)
        lemma_to_forms_set: Dict[str, Set[str]] = defaultdict(set)
        lemma_categories_set: Dict[str, Set[str]] = defaultdict(set)

        for linia in contingut.splitlines():
            linia = linia.strip()
            if not linia:
                continue
            parts = linia.split(" ")
            if len(parts) < 3:
                continue
            forma = cls._normalitzar_paraula(parts[0])
            lema_raw = parts[1]
            categoria = parts[2]

            lema = cls._normalitzar_lema(lema_raw)
            cat2 = categoria[:2]

            forma_to_lemmas_set[forma].add(lema)
            lemma_to_forms_set[lema].add(forma)
            if cat2:
                lemma_categories_set[lema].add(cat2)

        return forma_to_lemmas_set, lemma_to_forms_set, lemma_categories_set

    @classmethod
    def _obtenir_freq_lemes(cls) -> Dict[str, int]:
        txt = cls._descarregar(cls.FREQ_URL)
        out: Dict[str, int] = {}
        for linia in txt.splitlines():
            linia = linia.strip()
            if not linia:
                continue
            parts = linia.split(",")
            if len(parts) != 2:
                continue
            lema = cls._normalitzar_lema(parts[0])
            try:
                out[lema] = int(parts[1].strip())
            except ValueError:
                continue
        return out

    @classmethod
    def obtenir_diccionari_full(cls, use_cache: bool = True) -> "DiccionariFull":
        """Construeix (o carrega) el diccionari complet i el retorna."""
        os.makedirs(cls.DATA_DIR, exist_ok=True)
        cache_path = os.path.join(cls.DATA_DIR, cls.FULL_CACHE_FILE)

        if use_cache and os.path.exists(cache_path):
            with open(cache_path, "rb") as f:
                return pickle.load(f)

        # 1) Descarrega i processa totes les fonts de diccionari
        forma_to_lemmas_set: Dict[str, Set[str]] = defaultdict(set)
        lemma_to_forms_set: Dict[str, Set[str]] = defaultdict(set)
        lemma_categories_set: Dict[str, Set[str]] = defaultdict(set)

        for nom, url in cls.DICCIONARI_URLS:
            txt = cls._descarregar(url)
            f2l, l2f, lcats = cls._processar_diccionari_text(txt)
            # Fusiona
            for k, v in f2l.items():
                forma_to_lemmas_set[k].update(v)
            for k, v in l2f.items():
                lemma_to_forms_set[k].update(v)
            for k, v in lcats.items():
                lemma_categories_set[k].update(v)

        # 2) Freqüències per lema
        lemma_freq = cls._obtenir_freq_lemes()

        # 3) Aplica exclusions (si existeixen) sobre FORMES i marca LEMES exclosos
        forms_exc, lemmas_exc = cls._load_exclusions_json()
        if forms_exc:
            for f in list(forms_exc):
                lems = forma_to_lemmas_set.get(f)
                if not lems:
                    continue
                for l in lems:
                    if l in lemma_to_forms_set:
                        lemma_to_forms_set[l].discard(f)
                forma_to_lemmas_set.pop(f, None)

        excluded_lemmas_set = set(lemmas_exc or [])

        # 4) Determina lema principal per forma (freq més alta; si empat, ordre alfabètic)
        forma_primary: Dict[str, str] = {}
        for forma, lemes in forma_to_lemmas_set.items():
            if not lemes:
                continue
            # Evita preferir un lema exclòs quan hi ha alternativa
            candidates = [l for l in lemes if l not in excluded_lemmas_set]
            pool = candidates if candidates else list(lemes)
            best = None
            best_freq = -1
            for l in pool:
                f = lemma_freq.get(l, 0)
                if f > best_freq or (f == best_freq and (best is None or l < best)):
                    best = l
                    best_freq = f
            if best is None:
                best = sorted(pool)[0]
            forma_primary[forma] = best

        # 5) Converteix a tuples per reduir overhead i millorar pickling
        forma_to_lemmas = {k: tuple(sorted(v)) for k, v in forma_to_lemmas_set.items()}
        lemma_to_forms = {k: tuple(sorted(v)) for k, v in lemma_to_forms_set.items()}
        lemma_categories = {k: tuple(sorted(v)) for k, v in lemma_categories_set.items()}

        inst = cls(forma_to_lemmas, lemma_to_forms, lemma_categories, lemma_freq, forma_primary)

        # Guarda llistes d'exclosos a la instància (no esborrem els lemes, però els marquem invàlids)
        inst.excluded_lemmas = excluded_lemmas_set

        # Desa a disc
        with open(cache_path, "wb") as f:
            pickle.dump(inst, f, protocol=pickle.HIGHEST_PROTOCOL)

        return inst

    # API de càrrega directa (si ja existeix el pkl)
    @classmethod
    def load(cls, path: Optional[str] = None) -> "DiccionariFull":
        path = path or os.path.join(cls.DATA_DIR, cls.FULL_CACHE_FILE)
        with open(path, "rb") as f:
            return pickle.load(f)

    def save(self, path: Optional[str] = None) -> None:
        path = path or os.path.join(self.DATA_DIR, self.FULL_CACHE_FILE)
        os.makedirs(os.path.dirname(path), exist_ok=True)
        with open(path, "wb") as f:
            pickle.dump(self, f, protocol=pickle.HIGHEST_PROTOCOL)

    # ------------------------------ Consultes i validació ------------------------------
    def info(self, paraula: str) -> dict:
        """
        Retorna informació detallada d'una paraula/flexió:
          {
            'word': str,
            'known_form': bool,
            'lemmas': [str],
            'primary_lemma': str|None,
            'is_inflection': bool|None,
            'lemma_categories': {lema: [cat2, ...]},
            'lemma_freq': {lema: int}
          }
        """
        w = self._normalitzar_paraula(paraula)
        raw_lemes = list(self.forma_to_lemmas.get(w, ()))
        # Si la paraula és també un lema, restringeix als lemes propis (només ella mateixa)
        if w in raw_lemes:
            lemes = [w]
        else:
            lemes = raw_lemes
        known = len(lemes) > 0
        primary = self.forma_primary.get(w)
        is_inflection = None
        if known and primary is not None:
            is_inflection = w != primary

        lcats = {l: list(self.lemma_categories.get(l, ())) for l in lemes}
        lfreq = {l: int(self.lemma_freq.get(l, 0)) for l in lemes}

        return {
            "word": w,
            "known_form": known,
            "lemmas": lemes,
            "primary_lemma": primary,
            "is_inflection": is_inflection,
            "lemma_categories": lcats,
            "lemma_freq": lfreq,
            "excluded_lemmas": sorted(list(getattr(self, "excluded_lemmas", set()) & set(lemes))) if lemes else [],
        }

    def _cat2_label(self, cat2: str) -> str:
        return self.CAT2_LABELS.get(cat2, f"categoria '{cat2}'")

    def reason_invalid_category(self, paraula: str) -> Optional[str]:
        """Si la paraula existeix però cap dels seus lemes té categoria permesa, retorna missatge d'error."""
        w = self._normalitzar_paraula(paraula)
        lemes = set(self._forma_to_lemmas_set.get(w, set()))
        if w in lemes:
            # només el lema propi
            lemes = {w}
        # Ignora lemes exclosos per decidir la categoria
        excl = getattr(self, "excluded_lemmas", set())
        lemes = {l for l in lemes if l not in excl}
        if not lemes:
            return None  # Desconeguda: que ho gestioni qui crida
        # Comprova si algun lema és permès
        for l in lemes:
            cats = self._lemma_categories_set.get(l, set())
            if any(c in self.ALLOWED_CAT2 for c in cats):
                return None
        # No hi ha cap lema permès; construeix etiqueta predominant per feedback
        # Tria la categoria més freqüent entre els candidats per mostrar al missatge
        counter: Dict[str, int] = defaultdict(int)
        for l in lemes:
            for c in self._lemma_categories_set.get(l, set()):
                counter[c] += 1
        if counter:
            # primera per major nombre i, si empat, ordre alfabètic
            cat2 = sorted(counter.items(), key=lambda kv: (-kv[1], kv[0]))[0][0]
            label = self._cat2_label(cat2)
            return f"Aquesta paraula és {label}. Introdueix un nom o verb comú."
        # Sense categories (cas estrany)
        return "Aquesta paraula no és vàlida. Només es permeten noms i verbs comuns."

    def reason_too_uncommon(self, paraula: str, freq_min: int) -> Optional[str]:
        """
        Si la paraula existeix però tots els lemes candidats tenen freq < freq_min, retorna missatge.
        """
        w = self._normalitzar_paraula(paraula)
        lemes = set(self._forma_to_lemmas_set.get(w, set()))
        if w in lemes:
            lemes = {w}
        # Ignora lemes exclosos per a la comprovació de freqüència
        excl = getattr(self, "excluded_lemmas", set())
        lemes = {l for l in lemes if l not in excl}
        if not lemes:
            return None
        best = 0
        for l in lemes:
            best = max(best, int(self.lemma_freq.get(l, 0)))
        if best < freq_min:
            return "Aquesta paraula no participa del joc, busca'n una de més comuna."
        return None

    def explain_invalid(self, paraula: str, freq_min: int) -> Optional[str]:
        """
        Dona una explicació curta si la paraula no és acceptable pel joc, ordenant per prioritat:
        1) Lema exclòs explícitament
        2) Categoria no permesa
        3) Freqüència massa baixa
        Retorna None si no hi ha motiu d'invalidesa (segons aquests criteris).
        """
        # Si no existeix al diccionari complet
        w = self._normalitzar_paraula(paraula)
        if w not in self.forma_to_lemmas:
            return "Aquesta paraula no existeix al diccionari català. Assegura't que està ben escrita."
        # 1) Lema exclòs?
        excl = getattr(self, "excluded_lemmas", set())
        lemes_all = set(self._forma_to_lemmas_set.get(w, set()))
        if w in lemes_all:
            lemes_all = {w}
        if lemes_all and all(l in excl for l in lemes_all):
            return "Aquesta paraula no és vàlida. Només s'accepten els noms i verbs comuns de la normativa actual."
        msg = self.reason_invalid_category(w)
        if msg:
            return msg
        msg = self.reason_too_uncommon(w, freq_min)
        if msg:
            return msg
        return None

    # ------------------------------ Exclusions helpers ------------------------------
    @classmethod
    def _load_exclusions_json(cls) -> Tuple[Set[str], Set[str]]:
        """Llegeix data/exclusions.json si existeix i retorna (formes, lemes).
        Format esperat: {"lemmas": [...], "formes": [...]};
        Compatibilitat: si és una llista, es considera llista de lemes.
        """
        path = os.path.join(cls.DATA_DIR, "exclusions.json")
        if not os.path.exists(path):
            return set(), set()
        try:
            with open(path, "r", encoding="utf-8") as f:
                data = json.load(f)
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


if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser(description="Genera/consulta el diccionari complet sense filtre")
    parser.add_argument("--rebuild", action="store_true", help="Força reconstrucció i desat a data/diccionari_full.pkl")
    parser.add_argument("--word", type=str, default=None, help="Consulta info d'una paraula")
    parser.add_argument("--freq-min", type=int, default=20, help="Llindar de freqüència per comprovar 'massa poc comuna'")
    args = parser.parse_args()

    if args.rebuild:
        d = DiccionariFull.obtenir_diccionari_full(use_cache=False)
        d.save()  # a data/diccionari_full.pkl
        print("Generat i desat: data/diccionari_full.pkl")
    else:
        # Carrega si existeix; si no, construeix
        path = os.path.join(DiccionariFull.DATA_DIR, DiccionariFull.FULL_CACHE_FILE)
        if os.path.exists(path):
            d = DiccionariFull.load(path)
        else:
            d = DiccionariFull.obtenir_diccionari_full(use_cache=False)

    if args.word:
        info = d.info(args.word)
        print(json.dumps(info, ensure_ascii=False, indent=2))
        reason = d.explain_invalid(args.word, args.freq_min)
        if reason:
            print("reason:", reason)
