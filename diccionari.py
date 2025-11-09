
import os
import json
import pickle
import random
import re
import requests
from collections import defaultdict
from typing import Dict, Set, Tuple, Optional

class Diccionari:
    CACHE_FILE = "diccionari_cache.pkl"
    DATA_DIR = "data"
    FREQ_URL = "https://raw.githubusercontent.com/Softcatala/catalan-dict-tools/refs/heads/master/frequencies/frequencies-dict-lemmas.txt"
    DICCIONARI_URLS = [
        ("lt", "https://raw.githubusercontent.com/Softcatala/catalan-dict-tools/master/resultats/lt/diccionari.txt"),
        # Afegiu més diccionaris si cal
    ]

    def __init__(self,
                 mapping_flexions_multi: Dict[str, Set[str]],
                 canoniques: Dict[str, Set[str]],
                 freq: Optional[Dict[str, int]] = None,
                 lema_categories: Optional[Dict[str, Set[str]]] = None):
        self.mapping_flexions_multi = mapping_flexions_multi  # flexió -> conjunt de lemes
        self.canoniques = canoniques  # lema base -> conjunt de flexions
        self.lema_categories = lema_categories or defaultdict(set)
        self.freq = freq or {}

    @classmethod
    def normalitzar_paraula(cls, paraula: str) -> str:
        return paraula.lower().strip()

    @classmethod
    def descarregar_diccionari(cls, url: str) -> str:
        response = requests.get(url)
        return response.text

    @classmethod
    def es_categoria_valida(cls, categoria: str) -> bool:
        return categoria.startswith(('NC', 'VM'))

    @classmethod
    def processar_diccionari(cls, contingut: str) -> Tuple[Dict[str, Set[str]], Dict[str, Set[str]], Dict[str, Set[str]]]:
        """Processa el text del diccionari permetent múltiples lemes per forma.

        Uneix lemes numerats (lema1, lema2) al lema base per poder aplicar freqüències,
        i permet múltiples lectures (p.ex. nom i verb) via mapping_flexions_multi.
        """
        mapping_flexions_multi: Dict[str, Set[str]] = defaultdict(set)
        formes_canoniques: defaultdict[str, Set[str]] = defaultdict(set)
        lema_categories: Dict[str, Set[str]] = defaultdict(set)

        def normalitzar_lema(lema: str) -> str:
            return re.sub(r"\d+$", "", lema)

        for linia in contingut.split('\n'):
            if not linia.strip():
                continue
            parts = linia.split(' ')
            if len(parts) < 3:
                continue
            paraula = parts[0].lower()
            lema_original = parts[1].lower()
            categoria = parts[2]
            if not cls.es_categoria_valida(categoria):
                continue
            lema_base = normalitzar_lema(lema_original)
            lema_categories[lema_base].add(categoria[:2])
            mapping_flexions_multi[paraula].add(lema_base)
            formes_canoniques[lema_base].add(paraula)
        return dict(mapping_flexions_multi), dict(formes_canoniques), dict(lema_categories)

    @classmethod
    def obtenir_freq_lemes(cls, freq_url: Optional[str] = None) -> Dict[str, int]:
        freq_url = freq_url or cls.FREQ_URL
        print(f"Descarregant freqüències de lemes des de {freq_url}...")
        contingut = cls.descarregar_diccionari(freq_url)
        freq_lemes = {}
        for linia in contingut.splitlines():
            if not linia.strip():
                continue
            parts = linia.split(",")
            if len(parts) != 2:
                continue
            lema = parts[0].strip().lower()
            try:
                freq = int(parts[1].strip())
            except ValueError:
                continue
            freq_lemes[lema] = freq
        return freq_lemes

    @classmethod
    def filtrar_diccionari_per_frequencia(cls, mapping_flexions_multi, canoniques, freq_lemes, freq_min=20):
        canoniques_filtrades = {lema: flexions for lema, flexions in canoniques.items() if freq_lemes.get(lema, 0) >= freq_min}
        # Filtra mapping_flexions_multi per mantenir només lemes vàlids
        mapping_filtrat = {}
        for flexio, lemes in mapping_flexions_multi.items():
            lemes_valids = {l for l in lemes if l in canoniques_filtrades}
            if lemes_valids:
                mapping_filtrat[flexio] = lemes_valids
        freq_filtrat = {lema: freq_lemes.get(lema, 0) for lema in canoniques_filtrades}
        print(f"Paraules filtrades per freqüència >= {freq_min}: {len(mapping_filtrat)} flexions, {len(canoniques_filtrades)} lemes.")
        return mapping_filtrat, canoniques_filtrades, freq_filtrat

    @classmethod
    def obtenir_diccionari(cls, freq_min=20, use_cache=True):
        os.makedirs(cls.DATA_DIR, exist_ok=True)
        cache_file_path = os.path.join(cls.DATA_DIR, cls.CACHE_FILE)
        if use_cache and os.path.exists(cache_file_path):
            print(f"Carregant diccionari des del cache: {cache_file_path}")
            with open(cache_file_path, 'rb') as f:
                diccionaris_data = pickle.load(f)
            # Només un diccionari
            if len(diccionaris_data) == 1:
                mapping_multi, canoniques, lema_cats = list(diccionaris_data.values())[0]
                freq_lemes = cls.obtenir_freq_lemes()
                mapping_multi_filtrat, canoniques, freq_filtrat = cls.filtrar_diccionari_per_frequencia(mapping_multi, canoniques, freq_lemes, freq_min)
                lemes_valids = set(canoniques.keys())
                lema_cats_filtrat = {l: lema_cats.get(l, set()) for l in lemes_valids}
                # Aplica exclusions (formes/lemes) si existeix data/exclusions.json
                formes_exc, lemes_exc = cls._load_exclusions_json()
                if formes_exc or lemes_exc:
                    cls._apply_exclusions_to_data(canoniques, mapping_multi_filtrat, lema_cats_filtrat, freq_filtrat, formes_exc, lemes_exc)
                return cls(mapping_multi_filtrat, canoniques, freq_filtrat, lema_cats_filtrat)
            # Si n'hi ha més, cal adaptar-ho
            raise NotImplementedError("Només es suporta un diccionari per ara.")
        print("Generant diccionaris des de les fonts...")
        diccionaris_data = {}
        for nom, url in cls.DICCIONARI_URLS:
            print(f"Descarregant {nom}...")
            contingut = cls.descarregar_diccionari(url)
            mapping_multi, canoniques, lema_cats = cls.processar_diccionari(contingut)
            diccionaris_data[nom] = (mapping_multi, canoniques, lema_cats)
        with open(cache_file_path, 'wb') as f:
            print(f"Desant diccionaris al cache: {cache_file_path}")
            pickle.dump(diccionaris_data, f)
        # Només un diccionari
        if len(diccionaris_data) == 1:
            mapping_multi, canoniques, lema_cats = list(diccionaris_data.values())[0]
            freq_lemes = cls.obtenir_freq_lemes()
            mapping_multi_filtrat, canoniques, freq_filtrat = cls.filtrar_diccionari_per_frequencia(mapping_multi, canoniques, freq_lemes, freq_min)
            lemes_valids = set(canoniques.keys())
            lema_cats_filtrat = {l: lema_cats.get(l, set()) for l in lemes_valids}
            # Aplica exclusions (formes/lemes) si existeix data/exclusions.json
            formes_exc, lemes_exc = cls._load_exclusions_json()
            if formes_exc or lemes_exc:
                cls._apply_exclusions_to_data(canoniques, mapping_multi_filtrat, lema_cats_filtrat, freq_filtrat, formes_exc, lemes_exc)
            return cls(mapping_multi_filtrat, canoniques, freq_filtrat, lema_cats_filtrat)
        raise NotImplementedError("Només es suporta un diccionari per ara.")

    def save(self, path: str):
        os.makedirs(os.path.dirname(path), exist_ok=True)
        with open(path, 'w', encoding='utf-8') as f:
            json.dump({
                'mapping_flexions_multi': {k: list(v) for k, v in self.mapping_flexions_multi.items()},
                'canoniques': {k: list(v) for k, v in self.canoniques.items()},
                'lema_categories': {k: list(v) for k, v in self.lema_categories.items()},
                'freq': self.freq
            }, f, ensure_ascii=False, indent=2)

    @classmethod
    def load(cls, path: str):
        with open(path, 'r', encoding='utf-8') as f:
            data = json.load(f)
        return cls(
            mapping_flexions_multi={k: set(v) for k, v in data['mapping_flexions_multi'].items()},
            canoniques={k: set(v) for k, v in data['canoniques'].items()},
            freq=data.get('freq', {}),
            lema_categories={k: set(v) for k, v in data.get('lema_categories', {}).items()}
        )

    def lema(self, flexio: str) -> Optional[str]:
        """Retorna el primer lema per compatibilitat (pot ser arbitrari si n'hi ha múltiples)."""
        lemes = self.mapping_flexions_multi.get(flexio, set())
        return next(iter(lemes), None)

    def lemes(self, flexio: str) -> Set[str]:
        """Tots els lemes possibles per a una flexió."""
        return self.mapping_flexions_multi.get(flexio, set())

    def categories_lema(self, lema: str) -> Set[str]:
        return self.lema_categories.get(lema, set())

    def freq_lema(self, lema: str) -> int:
        return self.freq.get(lema, 0)

    def totes_les_lemes(self, freq_min: int = 0):
        return [lema for lema in self.canoniques if self.freq_lema(lema) >= freq_min]

    def totes_les_flexions(self, lema: str):
        return list(self.canoniques.get(lema, []))

    def obtenir_paraula_aleatoria(self, freq_min=2000, seed=None) -> str:
        candidats = self.totes_les_lemes(freq_min)
        if not candidats:
            raise ValueError(f"No s'ha trobat cap paraula amb freqüència >= {freq_min}")
        rnd = random.Random(seed) if seed is not None else random
        return rnd.choice(candidats)

    def _gestionar_pronominalitzacio(self, paraula_norm: str) -> Tuple[Optional[str], bool]:
        """Gestiona la pronomització verbal (paraules acabades en "-se" o "'s").
        
        Retorna lema_verb si la paraula és una forma pronominal vàlida,
        o None si no ho és.
        """
        paraula_sense_pronom = None
        if paraula_norm.endswith("-se"):
            paraula_sense_pronom = paraula_norm[:-3]  # Treu "-se"
        elif paraula_norm.endswith("'s"):
            paraula_sense_pronom = paraula_norm[:-2]  # Treu "'s"
        
        if not paraula_sense_pronom:
            return None
        
        # Comprova si la paraula sense pronom existeix al diccionari
        if paraula_sense_pronom not in self.mapping_flexions_multi:
            return None
        
        lemes = self.mapping_flexions_multi[paraula_sense_pronom]
        # Filtra només els lemes que són verbs (categoria 'VM')
        lemes_verbs = [lema for lema in lemes if 'VM' in self.categories_lema(lema)]
        
        if not lemes_verbs:
            return None
        
        # Comprova si el lema (infinitiu) permet aquesta forma pronominal
        for lema_verb in lemes_verbs:
            if paraula_norm.endswith("-se") and lema_verb.endswith("r"):
                # Acceptem [lema]-se si el lema acaba en 'r'
                return lema_verb
            elif paraula_norm.endswith("'s") and lema_verb.endswith("e"):
                # Acceptem [lema]'s si el lema acaba en 'e'
                return lema_verb

        return None

    def obtenir_forma_canonica(self, paraula: str) -> Tuple[Optional[str], bool]:
        paraula_norm = self.normalitzar_paraula(paraula)
        # Si tenim múltiples lemes, prioritzar el que coincideix exactament amb la forma
        if paraula_norm in self.mapping_flexions_multi:
            lemes = self.mapping_flexions_multi[paraula_norm]

            # Si el set de lemes està buit, retornar None (cas anòmal però possible)
            if not lemes:
                return None, False
                
            if paraula_norm in lemes:
                forma_canonica = paraula_norm
            else:
                # Prioritza noms (NC) sobre verbs (VM), i després el més freqüent
                def prioritat_lema(lema):
                    categories = self.categories_lema(lema)
                    te_nom = 'NC' in categories
                    te_verb = 'VM' in categories
                    freq = self.freq_lema(lema)
                    # Retorna (prioritat_categoria, freqüència)
                    # Noms tenen prioritat 1, verbs prioritat 0
                    return (1 if te_nom else 0, freq)
                
                forma_canonica = max(lemes, key=prioritat_lema)
            es_flexio = paraula_norm != forma_canonica
            return forma_canonica, es_flexio        
            
        # Gestió de pronomització verbal (paraules acabades en "-se" o "'s")
        lema_verb = self._gestionar_pronominalitzacio(paraula_norm)
        if lema_verb:
            return lema_verb, True

        return None, False

    # ------------------------------ Exclusions (formes i lemes) ------------------------------
    @classmethod
    def _load_exclusions_json(cls) -> Tuple[Set[str], Set[str]]:
        """Llegeix data/exclusions.json si existeix i retorna (formes, lemes).
        Format nou esperat: {"lemmas": [...], "formes": [...]}.
        Compatibilitat: si és una llista, es considera llista de lemes.
        """
        path = os.path.join(cls.DATA_DIR, "exclusions.json")
        if not os.path.exists(path):
            return set(), set()
        try:
            with open(path, 'r', encoding='utf-8') as f:
                data = json.load(f)
        except Exception:
            return set(), set()
        formas: Set[str] = set()
        lemas: Set[str] = set()
        if isinstance(data, dict):
            forml = data.get('formes') or []
            leml = data.get('lemmas') or []
            if isinstance(forml, list):
                formas = {str(x).lower() for x in forml}
            if isinstance(leml, list):
                lemas = {str(x).lower() for x in leml}
        elif isinstance(data, list):
            lemas = {str(x).lower() for x in data}
        return formas, lemas

    @staticmethod
    def _apply_exclusions_to_data(
        canoniques: Dict[str, Set[str]],
        mapping_flexions_multi: Dict[str, Set[str]],
        lema_categories: Dict[str, Set[str]],
        freq: Dict[str, int],
        forms_to_exclude: Set[str],
        lemmas_to_exclude: Set[str],
    ) -> None:
        # 1) Exclou lemes
        if lemmas_to_exclude:
            # Elimina lemes de canòniques, categories i freq
            for l in lemmas_to_exclude:
                canoniques.pop(l, None)
                lema_categories.pop(l, None)
                freq.pop(l, None)
            # Elimina lemes de mapping_flexions_multi
            for f in list(mapping_flexions_multi.keys()):
                lemes = mapping_flexions_multi[f]
                lemes.difference_update(lemmas_to_exclude)
                if not lemes:
                    del mapping_flexions_multi[f]

        # 2) Exclou formes
        if forms_to_exclude:
            for f in forms_to_exclude:
                mapping_flexions_multi.pop(f, None)
            # Treu formes de canòniques; elimina lemes que quedin buits
            for l in list(canoniques.keys()):
                s = canoniques[l]
                if s & forms_to_exclude:
                    s.difference_update(forms_to_exclude)
                    if not s:
                        del canoniques[l]
                        lema_categories.pop(l, None)
                        freq.pop(l, None)
