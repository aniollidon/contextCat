import argparse
import sys
from pathlib import Path

# Afegir el directori pare al path per importar el mòdul diccionari
sys.path.insert(0, str(Path(__file__).parent.parent))

from diccionari import Diccionari

def main():
    parser = argparse.ArgumentParser(description='Ordena lemes per freqüència')
    parser.add_argument('-n', '--num', type=int, help='Nombre de lemes a mostrar')
    parser.add_argument('--min-freq', type=int, default=0, help='Freqüència mínima per filtrar')
    args = parser.parse_args()
    
    # Carregar el diccionari
    dict_path = Path(__file__).parent.parent / 'data' / 'diccionari.json'
    print(f"Carregant diccionari des de {dict_path}...")
    dicc = Diccionari.load(str(dict_path))
    
    # Obtenir tots els lemes amb les seves freqüències
    lemes_amb_freq = []
    for lema in dicc.canoniques.keys():
        freq = dicc.freq_lema(lema)
        if freq >= args.min_freq:
            flexions = dicc.totes_les_flexions(lema)
            lemes_amb_freq.append((lema, freq, len(flexions)))
    
    # Ordenar per freqüència (de major a menor)
    lemes_ordenats = sorted(lemes_amb_freq, key=lambda x: x[1], reverse=True)
    
    # Mostrar resultats
    limit = args.num if args.num else len(lemes_ordenats)
    print(f"\nMostrant els {limit} primers lemes ordenats per freqüència:\n")
    
    for i, (lema, freq, num_flexions) in enumerate(lemes_ordenats[:limit], 1):
        print(f"{i:4d}. {lema:20s} freq={freq:8d}  flexions={num_flexions:3d}")
    
    print(f"\nTotal lemes: {len(lemes_ordenats)}")

if __name__ == '__main__':
    main()