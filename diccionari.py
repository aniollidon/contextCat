
import os
import json
import pickle
import random
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

    def __init__(self, mapping_flexions: Dict[str, str], canoniques: Dict[str, Set[str]], freq: Optional[Dict[str, int]] = None):
        self.mapping_flexions = mapping_flexions  # flexió -> lema
        self.canoniques = canoniques  # lema -> conjunt de flexions
        self.freq = freq or {}  # lema -> freq

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
    def processar_diccionari(cls, contingut: str) -> Tuple[Dict[str, str], Dict[str, Set[str]]]:
        mapping_flexions = {}
        formes_canoniques = defaultdict(set)
        for linia in contingut.split('\n'):
            if not linia.strip():
                continue
            parts = linia.split(' ')
            if len(parts) < 3:
                continue
            paraula = parts[0].lower()
            lema = parts[1].lower()
            categoria = parts[2]
            if not cls.es_categoria_valida(categoria):
                continue
            if paraula in formes_canoniques:
                mapping_flexions[paraula] = paraula
            else:
                mapping_flexions[paraula] = lema
            if paraula == lema and paraula in mapping_flexions:
                mapping_flexions[paraula] = lema
            formes_canoniques[lema].add(paraula)
        return mapping_flexions, dict(formes_canoniques)

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
                mapping, canoniques = list(diccionaris_data.values())[0]
                freq_lemes = cls.obtenir_freq_lemes()
                mapping, canoniques, freq_filtrat = cls.filtrar_diccionari_per_frequencia(mapping, canoniques, freq_lemes, freq_min)
                return cls(mapping, canoniques, freq_filtrat)
            # Si n'hi ha més, cal adaptar-ho
            raise NotImplementedError("Només es suporta un diccionari per ara.")
        print("Generant diccionaris des de les fonts...")
        diccionaris_data = {}
        for nom, url in cls.DICCIONARI_URLS:
            print(f"Descarregant {nom}...")
            contingut = cls.descarregar_diccionari(url)
            mapping, canoniques = cls.processar_diccionari(contingut)
            diccionaris_data[nom] = (mapping, canoniques)
        with open(cache_file_path, 'wb') as f:
            print(f"Desant diccionaris al cache: {cache_file_path}")
            pickle.dump(diccionaris_data, f)
        # Només un diccionari
        if len(diccionaris_data) == 1:
            mapping, canoniques = list(diccionaris_data.values())[0]
            freq_lemes = cls.obtenir_freq_lemes()
            mapping, canoniques, freq_filtrat = cls.filtrar_diccionari_per_frequencia(mapping, canoniques, freq_lemes, freq_min)
            return cls(mapping, canoniques, freq_filtrat)
        raise NotImplementedError("Només es suporta un diccionari per ara.")

    def save(self, path: str):
        os.makedirs(os.path.dirname(path), exist_ok=True)
        with open(path, 'w', encoding='utf-8') as f:
            json.dump({
                'mapping_flexions': self.mapping_flexions,
                'canoniques': {k: list(v) for k, v in self.canoniques.items()},
                'freq': self.freq
            }, f, ensure_ascii=False, indent=2)

    @classmethod
    def load(cls, path: str):
        with open(path, 'r', encoding='utf-8') as f:
            data = json.load(f)
        return cls(
            mapping_flexions=data['mapping_flexions'],
            canoniques={k: set(v) for k, v in data['canoniques'].items()},
            freq=data.get('freq', {})
        )

    def lema(self, flexio: str) -> Optional[str]:
        return self.mapping_flexions.get(flexio)

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
        if paraula_norm not in self.mapping_flexions:
            return None, False
        forma_canonica = self.mapping_flexions[paraula_norm]
        es_flexio = paraula_norm != forma_canonica
        return forma_canonica, es_flexio
