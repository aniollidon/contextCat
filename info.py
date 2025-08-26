import argparse
import json
from pathlib import Path
from diccionari import Diccionari

# Ruta del diccionari serialitzat (compatible amb generate.py)
DICC_PATH = Path("data/diccionari.json")

def carregar_diccionari_complet():
    """Carrega el diccionari si existeix; si no, el genera sense filtre de freqüència.
    Si el fitxer existent no conté 'freq', es regenera per obtenir les freqüències."""
    if DICC_PATH.exists():
        try:
            dicc = Diccionari.load(str(DICC_PATH))
            if dicc.freq:  # ja tenim freq
                return dicc
            print("[info] El fitxer existent no té freqüències; es regenera...")
        except Exception as e:
            print(f"[warn] Error carregant diccionari existent: {e}; es regenera...")
    dicc = Diccionari.obtenir_diccionari(freq_min=0)
    dicc.save(str(DICC_PATH))
    return dicc

def llistar_ordenat(max_len: int = 0):
    """Retorna tots els lemes ordenats per freq desc, aplicant filtre de longitud màxima si cal."""
    dicc = carregar_diccionari_complet()
    result = []
    for lema in dicc.canoniques.keys():
        if max_len and len(lema) > max_len:
            continue
        result.append((lema, dicc.freq_lema(lema)))
    result.sort(key=lambda x: x[1], reverse=True)
    return result

def main():
    parser = argparse.ArgumentParser(description="Llista lemes ordenats per freqüència (tots o filtrats). Tots els filtres són opcionals.")
    parser.add_argument("--top", type=int, default=0, help="Limita a N lemes més freqüents (0 = sense límit)")
    parser.add_argument(
        "--json",
        nargs="?",
        const="-",
        metavar="FITXER",
        help="Exporta JSON (llista de paraules). Sense valor = stdout. Indica un nom per desar a fitxer."
    )
    parser.add_argument("--max-len", type=int, default=0, help="Inclou només lemes amb longitud <= aquest valor")
    args = parser.parse_args()

    if args.top < 0:
        parser.error("--top ha de ser >= 0")

    result_all = llistar_ordenat(max_len=args.max_len)
    if args.top > 0:
        result = result_all[:args.top]
    else:
        result = result_all

    if args.json is not None:
        json_data = json.dumps([w for w, _ in result], ensure_ascii=False, indent=2)
        if args.json == '-' or args.json == '':
            print(json_data)
        else:
            from pathlib import Path
            out_path = Path(args.json)
            out_path.parent.mkdir(parents=True, exist_ok=True)
            out_path.write_text(json_data, encoding='utf-8')
            print(f"JSON desat a {out_path}")
        return

    extra = []
    if args.max_len:
        extra.append(f"len<={args.max_len}")
    header_filters = (" (" + ", ".join(extra) + ")") if extra else ""
    if args.top:
        print(f"Lemes per freqüència (desc) - mostrant TOP {args.top}{header_filters}. Total filtrats: {len(result_all)}")
    else:
        print(f"Lemes per freqüència (desc){header_filters}. Total: {len(result)}")
    width = max(8, len(str(result[0][1])) if result else 8)
    for w, f in result:
        print(f"{f:>{width}}  {w}")

if __name__ == "__main__":
    main()
