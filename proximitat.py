import fasttext
import fasttext.util
import os
import numpy as np
from typing import List, Dict

MODEL_PATH = "cc.ca.300.bin"

def descarregar_model_fasttext():
    """Descarrega el model de fastText per al català si no existeix."""
    if not os.path.exists(MODEL_PATH):
        print(f"Descarregant el model de fastText a '{MODEL_PATH}'...")
        fasttext.util.download_model('ca', if_exists='ignore')
        # El nom per defecte és cc.ca.300.bin, que coincideix amb MODEL_PATH
        print("Descàrrega completada.")
    else:
        print("El model de fastText ja existeix localment.")

def carregar_model_fasttext():
    """Carrega el model de fastText."""
    descarregar_model_fasttext()
    print("Carregant el model de fastText a la memòria...")
    model = fasttext.load_model(MODEL_PATH)
    print("Model de fastText carregat.")
    return model

def calcular_similitud_cosinus(vec1, vec2):
    """Calcula la similitud del cosinus entre dos vectors."""
    return np.dot(vec1, vec2) / (np.linalg.norm(vec1) * np.linalg.norm(vec2))

def calcular_ranking_complet(paraula_objectiu: str, diccionari: List[str], model) -> Dict[str, int]:
    """Calcula el rànquing de totes les paraules del diccionari respecte a la paraula objectiu."""
    print(f"Calculant rànquing complet per a la paraula: '{paraula_objectiu}'...")
    
    vector_objectiu = model.get_word_vector(paraula_objectiu)
    
    similituds = []
    for paraula in diccionari:
        vector_paraula = model.get_word_vector(paraula)
        sim = calcular_similitud_cosinus(vector_objectiu, vector_paraula)
        similituds.append((paraula, sim))
        
    # Ordenar per similitud (de major a menor)
    similituds.sort(key=lambda x: x[1], reverse=True)
    
    # Crear el diccionari de rànquing (posició a la llista ordenada)
    ranking_dict = {paraula: i for i, (paraula, _) in enumerate(similituds)}

    # Escriure el rànquing a un fitxer de debug
    with open("ranking_debug.txt", "w", encoding="utf-8") as f:
        f.write(f"Rànquing per a la paraula objectiu: '{paraula_objectiu}'\n")
        f.write("="*50 + "\n")
        for i, (paraula, sim) in enumerate(similituds):
            f.write(f"{i:<5} | {paraula:<20} | Similitud: {sim:.4f}\n")
    
    print("Rànquing complet calculat i desat a 'ranking_debug.txt'.")
    return ranking_dict 