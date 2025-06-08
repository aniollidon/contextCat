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
    # AQ: adjectiu qualificatiu
    return categoria.startswith(('NC', 'VM', 'AQ'))

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
            
        # Si la paraula ja existeix al mapping, preferim la forma més simple
        if paraula in mapping_flexions:
            # Si el lema actual és més curt, l'utilitzem
            if len(lema) < len(mapping_flexions[paraula]):
                mapping_flexions[paraula] = lema
        else:
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
    if os.path.exists(CACHE_FILE):
        print(f"Carregant diccionari des del cache: {CACHE_FILE}")
        with open(CACHE_FILE, 'rb') as f:
            mapping_final, canoniques_final = pickle.load(f)
        return mapping_final, canoniques_final

    print("Generant diccionari des de les fonts...")
    # URLs dels diccionaris
    url_lt = "https://raw.githubusercontent.com/Softcatala/catalan-dict-tools/master/resultats/lt/diccionari.txt"
    url_dnv = "https://raw.githubusercontent.com/Softcatala/catalan-dict-tools/refs/heads/master/resultats/lt/diccionari-dnv.txt"
    
    # Descarregar i processar els diccionaris
    contingut_lt = descarregar_diccionari(url_lt)
    contingut_dnv = descarregar_diccionari(url_dnv)
    
    # Processar cada diccionari
    mapping_lt, canoniques_lt = processar_diccionari(contingut_lt)
    mapping_dnv, canoniques_dnv = processar_diccionari(contingut_dnv)
    
    # Combinar els resultats
    mapping_final = {**mapping_lt, **mapping_dnv}
    canoniques_final = canoniques_lt.copy()
    for lema, flexions in canoniques_dnv.items():
        if lema in canoniques_final:
            canoniques_final[lema].update(flexions)
        else:
            canoniques_final[lema] = flexions
    
    # Desar al cache per a futures execucions
    with open(CACHE_FILE, 'wb') as f:
        print(f"Desant diccionari al cache: {CACHE_FILE}")
        pickle.dump((mapping_final, canoniques_final), f)
    
    return mapping_final, canoniques_final

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