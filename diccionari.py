import requests
import re
from typing import Set, Dict, List
import os
import json

def descarregar_diccionari() -> Set[str]:
    """Descarrega i processa el diccionari de Softcatalà."""
    url = "https://raw.githubusercontent.com/Softcatala/catalan-dict-tools/master/resultats/lt/diccionari.txt"
    print(f"Descarregant diccionari de: {url}")
    response = requests.get(url)
    response.raise_for_status()
    print(f"Resposta rebuda. Mida: {len(response.text)} bytes")
    
    # Conjunt per emmagatzemar les paraules i les seves arrels
    paraules = set()
    arrels = set()
    
    # Processar cada línia del diccionari
    linies_processades = 0
    for linia in response.text.split('\n'):
        # Ignorar línies buides o comentaris
        if not linia or linia.startswith('#'):
            continue
            
        # Separar la paraula i la seva informació
        parts = linia.strip().split()
        if len(parts) >= 2:
            paraula = parts[0].strip()
            info = ' '.join(parts[1:]).strip()
            
            # Extreure l'arrel si existeix
            arrel_match = re.search(r'<l>([^<]+)</l>', info)
            if arrel_match:
                arrel = arrel_match.group(1).strip()
                # Afegir tant la paraula com l'arrel
                paraules.add(paraula)
                arrels.add(arrel)
            else:
                # Si no té arrel, la paraula és la seva pròpia arrel
                paraules.add(paraula)
                arrels.add(paraula)
            linies_processades += 1
            
            if linies_processades % 10000 == 0:
                print(f"Processades {linies_processades} línies...")
    
    print(f"Línies processades: {linies_processades}")
    print(f"Paraules úniques: {len(paraules)}")
    print(f"Arrels úniques: {len(arrels)}")
    
    # Unir les paraules i les arrels
    totes_paraules = paraules.union(arrels)
    print(f"Total de paraules després d'unir: {len(totes_paraules)}")
    
    # Filtrar paraules invàlides
    paraules_valides = {
        paraula for paraula in totes_paraules
        if paraula and not any(c in paraula for c in '0123456789')
    }
    print(f"Total de paraules vàlides: {len(paraules_valides)}")
    
    # Mostrar alguns exemples
    print("\nExemples de paraules:")
    for paraula in sorted(list(paraules_valides))[:5]:
        print(f"- {paraula}")
    
    return paraules_valides

def normalitzar_paraula(paraula: str) -> str:
    """Normalitza una paraula eliminant accents i convertint a minúscules."""
    replacements = {
        'à': 'a', 'è': 'e', 'é': 'e', 'í': 'i', 'ï': 'i',
        'ò': 'o', 'ó': 'o', 'ú': 'u', 'ü': 'u'
    }
    paraula = paraula.lower()
    for accent, no_accent in replacements.items():
        paraula = paraula.replace(accent, no_accent)
    return paraula

def obtenir_diccionari() -> Set[str]:
    """Obté el diccionari, descarregant-lo si és necessari."""
    cache_file = "diccionari_cache.txt"
    
    if os.path.exists(cache_file):
        with open(cache_file, 'r', encoding='utf-8') as f:
            return set(line.strip() for line in f)
    
    diccionari = descarregar_diccionari()
    
    with open(cache_file, 'w', encoding='utf-8') as f:
        for paraula in sorted(diccionari):
            f.write(f"{paraula}\n")
    
    return diccionari

if __name__ == "__main__":
    diccionari = obtenir_diccionari()
    print(f"Nombre de paraules al diccionari: {len(diccionari)}")
    print("\nExemples de paraules:")
    for paraula in sorted(list(diccionari))[:10]:
        print(f"- {paraula}") 