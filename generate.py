
import argparse
import json
from proximitat import carregar_model_fasttext, calcular_ranking_complet
from diccionari import Diccionari

def main():
    parser = argparse.ArgumentParser(description="Genera fitxers de rànquing de paraules en format JSON.")
    parser.add_argument("--paraula", type=str, required=False, help="Paraula objectiu per calcular el rànquing")
    parser.add_argument("--random", type=int, required=False, help="Nombre de paraules aleatòries per generar rànquings")
    parser.add_argument("--output", type=str, required=False, help="Fitxer de sortida per al rànquing (JSON). Per defecte: data/words/[PARAULA].json")
    parser.add_argument("--freq-min", type=int, default=20, help="Freqüència mínima per filtrar paraules")
    parser.add_argument("--freq-min-rand", type=int, default=-1, help="Freqüència mínima per proposar paraules aleatòries")

    args = parser.parse_args()

    if args.freq_min_rand == -1:
        args.freq_min_rand = args.freq_min

    if not args.paraula and not args.random:
        parser.error("Cal especificar --paraula o --random [NUM]")

    print("Carregant i generant diccionari...")
    dicc = Diccionari.obtenir_diccionari(freq_min=args.freq_min)
    dicc.save("data/diccionari.json")
    print(f"Diccionari filtrat guardat a data/diccionari.json amb {len(dicc.canoniques)} lemes.")

    FT_MODEL = carregar_model_fasttext()
    paraules = dicc.totes_les_lemes(freq_min=args.freq_min)

    # Si s'ha especificat --paraula
    if args.paraula:
        output_path = args.output
        if not output_path:
            import os
            os.makedirs("data/words", exist_ok=True)
            output_path = f"data/words/{args.paraula}.json"
        print(f"Calculant rànquing per a la paraula: {args.paraula}")
        ranking = calcular_ranking_complet(args.paraula, paraules, FT_MODEL)
        print(f"Guardant rànquing a {output_path}")
        with open(output_path, "w", encoding="utf-8") as f:
            json.dump(ranking, f, ensure_ascii=False, indent=2)
        print("Fet!")

    # Si s'ha especificat --random
    if args.random:
        import os
        os.makedirs("data/words", exist_ok=True)
        for i in range(args.random):
            paraula_random = dicc.obtenir_paraula_aleatoria(freq_min=args.freq_min_rand, seed=None)
            output_path = f"data/words/{paraula_random}.json"
            print(f"Calculant rànquing per a la paraula aleatòria: {paraula_random}")
            ranking = calcular_ranking_complet(paraula_random, paraules, FT_MODEL)
            print(f"Guardant rànquing a {output_path}")
            with open(output_path, "w", encoding="utf-8") as f:
                json.dump(ranking, f, ensure_ascii=False, indent=2)
        print("Fet!")

if __name__ == "__main__":
    main()
