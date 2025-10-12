
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
                 mapping_flexions: Dict[str, str],
                 canoniques: Dict[str, Set[str]],
                 freq: Optional[Dict[str, int]] = None,
                 mapping_flexions_multi: Optional[Dict[str, Set[str]]] = None,
                 lema_categories: Optional[Dict[str, Set[str]]] = None):
        # mapping_flexions es manté per compatibilitat: flexió -> un lema principal
        self.mapping_flexions = mapping_flexions
        self.mapping_flexions_multi = mapping_flexions_multi or {k: {v} for k, v in mapping_flexions.items()}
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
    def processar_diccionari(cls, contingut: str) -> Tuple[Dict[str, str], Dict[str, Set[str]], Dict[str, Set[str]], Dict[str, Set[str]]]:
        """Processa el text del diccionari permetent múltiples lemes per forma.

        Uneix lemes numerats (lema1, lema2) al lema base per poder aplicar freqüències,
        però conserva les múltiples lectures (p.ex. nom i verb) via mapping_flexions_multi.
        """
        mapping_flexions: Dict[str, str] = {}
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
            if paraula not in mapping_flexions:
                mapping_flexions[paraula] = lema_base
            formes_canoniques[lema_base].add(paraula)
        return mapping_flexions, dict(formes_canoniques), dict(mapping_flexions_multi), dict(lema_categories)

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
    def filtrar_diccionari_per_frequencia(cls, mapping_flexions, canoniques, freq_lemes, freq_min=20):
        canoniques_filtrades = {lema: flexions for lema, flexions in canoniques.items() if freq_lemes.get(lema, 0) >= freq_min}
        mapping_filtrat = {flexio: canonic for flexio, canonic in mapping_flexions.items() if canonic in canoniques_filtrades}
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
                mapping, canoniques, mapping_multi, lema_cats = list(diccionaris_data.values())[0]
                freq_lemes = cls.obtenir_freq_lemes()
                mapping, canoniques, freq_filtrat = cls.filtrar_diccionari_per_frequencia(mapping, canoniques, freq_lemes, freq_min)
                lemes_valids = set(canoniques.keys())
                mapping_multi_filtrat = {f: {l for l in lems if l in lemes_valids} for f, lems in mapping_multi.items()}
                lema_cats_filtrat = {l: lema_cats.get(l, set()) for l in lemes_valids}
                return cls(mapping, canoniques, freq_filtrat, mapping_multi_filtrat, lema_cats_filtrat)
            # Si n'hi ha més, cal adaptar-ho
            raise NotImplementedError("Només es suporta un diccionari per ara.")
        print("Generant diccionaris des de les fonts...")
        diccionaris_data = {}
        for nom, url in cls.DICCIONARI_URLS:
            print(f"Descarregant {nom}...")
            contingut = cls.descarregar_diccionari(url)
            mapping, canoniques, mapping_multi, lema_cats = cls.processar_diccionari(contingut)
            diccionaris_data[nom] = (mapping, canoniques, mapping_multi, lema_cats)
        with open(cache_file_path, 'wb') as f:
            print(f"Desant diccionaris al cache: {cache_file_path}")
            pickle.dump(diccionaris_data, f)
        # Només un diccionari
        if len(diccionaris_data) == 1:
            mapping, canoniques, mapping_multi, lema_cats = list(diccionaris_data.values())[0]
            freq_lemes = cls.obtenir_freq_lemes()
            mapping, canoniques, freq_filtrat = cls.filtrar_diccionari_per_frequencia(mapping, canoniques, freq_lemes, freq_min)
            lemes_valids = set(canoniques.keys())
            mapping_multi_filtrat = {f: {l for l in lems if l in lemes_valids} for f, lems in mapping_multi.items()}
            lema_cats_filtrat = {l: lema_cats.get(l, set()) for l in lemes_valids}
            return cls(mapping, canoniques, freq_filtrat, mapping_multi_filtrat, lema_cats_filtrat)
        raise NotImplementedError("Només es suporta un diccionari per ara.")

    def save(self, path: str):
        os.makedirs(os.path.dirname(path), exist_ok=True)
        with open(path, 'w', encoding='utf-8') as f:
            json.dump({
                'mapping_flexions': self.mapping_flexions,
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
            mapping_flexions=data['mapping_flexions'],
            canoniques={k: set(v) for k, v in data['canoniques'].items()},
            freq=data.get('freq', {}),
            mapping_flexions_multi={k: set(v) for k, v in data.get('mapping_flexions_multi', {}).items()},
            lema_categories={k: set(v) for k, v in data.get('lema_categories', {}).items()}
        )

    def lema(self, flexio: str) -> Optional[str]:
        return self.mapping_flexions.get(flexio)

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
                # Manté compatibilitat amb mapping_flexions, si existeix; si no, primer lema arbitrari
                forma_canonica = self.mapping_flexions.get(paraula_norm) or next(iter(lemes))
            es_flexio = paraula_norm != forma_canonica
            return forma_canonica, es_flexio
        # Fallback antic
        if paraula_norm not in self.mapping_flexions:
            return None, False
        forma_canonica = self.mapping_flexions[paraula_norm]
        es_flexio = paraula_norm != forma_canonica
        return forma_canonica, es_flexio
