import random
def obtenir_paraula_aleatoria(mapping_flexions, canoniques, freq_url="https://raw.githubusercontent.com/Softcatala/catalan-dict-tools/refs/heads/master/frequencies/frequencies-dict-lemmas.txt", freq_min=2000, rnd=None, seed=None):
    """
    Retorna una paraula aleatòria (lema) amb freqüència >= freq_min.
    mapping_flexions: dict flexió -> canònica
    canoniques: dict canònica -> conjunt de flexions
    freq_url: URL del fitxer de freqüències de lemes
    freq_min: freqüència mínima per considerar
    rnd: objecte random.Random opcional per controlar la repetició
    seed: si es passa, es crea un random.Random amb aquesta seed
    """
    print(f"Descarregant freqüències de lemes des de {freq_url}...")
    contingut = descarregar_diccionari(freq_url)
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

    candidats = [lema for lema in canoniques if freq_lemes.get(lema, 0) >= freq_min]
    if not candidats:
        raise ValueError(f"No s'ha trobat cap paraula amb freqüència >= {freq_min}")
    if seed is not None:
        rnd = random.Random(seed)
    if rnd is None:
        rnd = random
    lema_aleatori = rnd.choice(candidats)

    return lema_aleatori
def filtrar_diccionari_per_frequencia(mapping_flexions, canoniques, freq_url="https://raw.githubusercontent.com/Softcatala/catalan-dict-tools/refs/heads/master/frequencies/frequencies-dict-lemmas.txt", freq_min=20):
    """
    Filtra el diccionari segons la freqüència de lema. Només es conserven les paraules amb freqüència >= freq_min.
    mapping_flexions: dict flexió -> canònica
    canoniques: dict canònica -> conjunt de flexions
    freq_url: URL del fitxer de freqüències de lemes
    freq_min: freqüència mínima per conservar
    Retorna: (nou_mapping_flexions, noves_canoniques)
    """
    print(f"Descarregant freqüències de lemes des de {freq_url}...")
    contingut = descarregar_diccionari(freq_url)
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

    # Filtrar les canòniques segons la freqüència
    canoniques_filtrades = {lema: flexions for lema, flexions in canoniques.items() if freq_lemes.get(lema, 0) >= freq_min}
    # Filtrar mapping_flexions per només incloure flexions que tinguin canònica vàlida
    mapping_filtrat = {flexio: canonic for flexio, canonic in mapping_flexions.items() if canonic in canoniques_filtrades}
    print(f"Paraules filtrades per freqüència >= {freq_min}: {len(mapping_filtrat)} flexions, {len(canoniques_filtrades)} lemes.")
    return mapping_filtrat, canoniques_filtrades
import re
from typing import Dict, Set, Tuple
import requests
from collections import defaultdict
import pickle
import os

CACHE_FILE = "diccionari_cache.pkl"

def descarregar_diccionari(url: str) -> str:
    """Descarrega el contingut d'un diccionari des d'una URL."""
    response = requests.get(url)
    return response.text

def es_categoria_valida(categoria: str) -> bool:
    """Determina si una categoria gramatical és vàlida pel nostre diccionari."""
    # NC: nom comú
    # VM: verb principal
    return categoria.startswith(('NC', 'VM'))

def processar_diccionari(contingut: str) -> Tuple[Dict[str, str], Dict[str, Set[str]]]:
    """
    Processa el contingut del diccionari i retorna:
    - Un diccionari de formes flexionades -> forma canònica
    - Un diccionari de formes canòniques -> conjunt de flexions
    """
    mapping_flexions = {}  # paraula flexionada -> forma canònica
    formes_canoniques = defaultdict(set)  # forma canònica -> conjunt de flexions
    
    for linia in contingut.split('\n'):
        if not linia.strip():
            continue
            
        parts = linia.split(' ')
        if len(parts) < 3:
            continue
            
        paraula = parts[0].lower()
        lema = parts[1].lower()
        categoria = parts[2]
        
        # Filtrar categories no desitjades
        if not es_categoria_valida(categoria):
            continue
            
        # si la paraula ja existeix com a canònica, l'afegim a les flexions
        if paraula in formes_canoniques:
            mapping_flexions[paraula] = paraula
        else:
            mapping_flexions[paraula] = lema

        # Si la paraula és canonica i ja existex com a flexió, la substituim per la canònica
        if paraula == lema and paraula in mapping_flexions:
            mapping_flexions[paraula] = lema
            
        # Afegir a les formes canòniques
        formes_canoniques[lema].add(paraula)
    
    return mapping_flexions, dict(formes_canoniques)

def obtenir_diccionari_millorat() -> Tuple[Dict[str, str], Dict[str, Set[str]]]:
    """
    Obté el diccionari millorat amb:
    - Mapping de flexions a formes canòniques
    - Mapping de formes canòniques a les seves flexions
    Primer intenta carregar des del cache, si no existeix, el genera i el desa.
    """
    # Llista de diccionaris a utilitzar (comenta/descomenta els que vulguis)
    diccionaris = [
        #("dnv", "https://raw.githubusercontent.com/Softcatala/catalan-dict-tools/refs/heads/master/resultats/lt/diccionari-dnv.txt"),
        ("lt", "https://raw.githubusercontent.com/Softcatala/catalan-dict-tools/master/resultats/lt/diccionari.txt"),
        # ("ALTRE", "URL_ALTRE_DICCIONARI"),
    ]

    freq_url = "https://raw.githubusercontent.com/Softcatala/catalan-dict-tools/refs/heads/master/frequencies/frequencies-dict-lemmas.txt"
    freq_min = 20

    if os.path.exists(CACHE_FILE):
        print(f"Carregant diccionari des del cache: {CACHE_FILE}")
        with open(CACHE_FILE, 'rb') as f:
            diccionaris_data = pickle.load(f)
        # Escriure fitxers de debug per cada diccionari carregat
        for nom, (mapping, canoniques) in diccionaris_data.items():
            debug_file = f"diccionari_debug_{nom}.txt"
            with open(debug_file, 'w', encoding='utf-8') as f_debug:
                for flexio, canonic in mapping.items():
                    f_debug.write(f"{flexio} -> {canonic}\n")
            debug_file_canoniques = f"diccionari_debug_canoniques_{nom}.txt"
            with open(debug_file_canoniques, 'w', encoding='utf-8') as f_debug_can:
                for canonic, flexions in canoniques.items():
                    flexions_str = ', '.join(sorted(flexions))
                    f_debug_can.write(f"{canonic}: {flexions_str}\n")
        # Compatibilitat: si només hi ha un diccionari, retorna directament el mapping/canoniques
        if len(diccionaris_data) == 1:
            return list(diccionaris_data.values())[0]
        return diccionaris_data

    print("Generant diccionaris des de les fonts...")
    diccionaris_data = {}
    for nom, url in diccionaris:
        print(f"Descarregant {nom}...")
        contingut = descarregar_diccionari(url)
        mapping, canoniques = processar_diccionari(contingut)
        mapping, canoniques = filtrar_diccionari_per_frequencia(mapping, canoniques, freq_url=freq_url, freq_min=freq_min)
        diccionaris_data[nom] = (mapping, canoniques)
        # Fitxers de debug per cada diccionari
        debug_file = f"diccionari_debug_{nom}.txt"
        with open(debug_file, 'w', encoding='utf-8') as f_debug:
            for flexio, canonic in mapping.items():
                f_debug.write(f"{flexio} -> {canonic}\n")
        debug_file_canoniques = f"diccionari_debug_canoniques_{nom}.txt"
        with open(debug_file_canoniques, 'w', encoding='utf-8') as f_debug_can:
            for canonic, flexions in canoniques.items():
                flexions_str = ', '.join(sorted(flexions))
                f_debug_can.write(f"{canonic}: {flexions_str}\n")

    # Desar al cache per a futures execucions
    with open(CACHE_FILE, 'wb') as f:
        print(f"Desant diccionaris al cache: {CACHE_FILE}")
        pickle.dump(diccionaris_data, f)

    # Compatibilitat: si només hi ha un diccionari, retorna directament el mapping/canoniques
    if len(diccionaris_data) == 1:
        return list(diccionaris_data.values())[0]
    return diccionaris_data

def normalitzar_paraula(paraula: str) -> str:
    """Normalitza una paraula mantenint accents i caràcters especials."""
    return paraula.lower().strip()

def obtenir_forma_canonica(paraula: str, mapping_flexions: Dict[str, str]) -> Tuple[str, bool]:
    """
    Retorna la forma canònica d'una paraula i si és una flexió.
    Si la paraula no existeix al diccionari, retorna None.
    """
    paraula_norm = normalitzar_paraula(paraula)
    if paraula_norm not in mapping_flexions:
        return None, False
    
    forma_canonica = mapping_flexions[paraula_norm]
    es_flexio = paraula_norm != forma_canonica
    return forma_canonica, es_flexio 