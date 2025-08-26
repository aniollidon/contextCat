import fasttext
import fasttext.util
import os
import shutil
import numpy as np
from typing import List, Dict
from pathlib import Path

# Carpeta de dades relativa al fitxer actual (no al cwd) per evitar problemes en entorns diferents
BASE_DATA_DIR = Path(__file__).parent / "data"
MODEL_PATH = BASE_DATA_DIR / "cc.ca.300.bin"

def descarregar_model_fasttext():
    """Descarrega el model de fastText per al català dins de la carpeta data si no existeix.

    Soluciona els casos en què al servidor Linux el working directory no és el mateix i
    'data/cc.ca.300.bin' no es troba. Fem servir rutes absolutes i forcem la descarrega
    dins de BASE_DATA_DIR.
    """
    if MODEL_PATH.exists():
        return
    BASE_DATA_DIR.mkdir(parents=True, exist_ok=True)
    print(f"[fasttext] Descarregant model a '{MODEL_PATH}' ...")
    cwd = os.getcwd()
    try:
        # Canvia temporalment a la carpeta data perquè fasttext.util.download_model
        # desa els fitxers al cwd.
        os.chdir(BASE_DATA_DIR)
        fasttext.util.download_model('ca', if_exists='ignore')  # genera cc.ca.300.bin (.gz primer)
    finally:
        os.chdir(cwd)
    # Comprova i, si cal, mou el fitxer resultant
    downloaded = BASE_DATA_DIR / "cc.ca.300.bin"
    if not downloaded.exists():
        # Intent de fallback si només hi ha la versió .bin.gz sense descomprimir (versions antigues)
        gz = BASE_DATA_DIR / "cc.ca.300.bin.gz"
        if gz.exists():
            print("[fasttext] Descompressió manual del .gz...")
            import gzip
            with gzip.open(gz, 'rb') as f_in, open(downloaded, 'wb') as f_out:
                shutil.copyfileobj(f_in, f_out)
        else:
            raise RuntimeError("No s'ha pogut obtenir cc.ca.300.bin després de la descàrrega")
    size_mb = downloaded.stat().st_size / (1024 * 1024)
    if size_mb < 50:  # el model normalment és força més gran (> 1GB). Llindar baix per detectar descàrrega corrupta.
        print(f"[WARN] Mida inesperadament petita ({size_mb:.1f} MB). Pot estar corrupta la descàrrega.")
    print("[fasttext] Model descarregat/corresponent disponible.")

def carregar_model_fasttext():
    """Carrega el model de fastText amb rutes robustes (independentment del cwd)."""
    descarregar_model_fasttext()
    print(f"[fasttext] Carregant model des de '{MODEL_PATH}' ...")
    model = fasttext.load_model(str(MODEL_PATH))
    print("[fasttext] Model carregat.")
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
    debug_path = os.path.join("data", "ranking_debug.txt")
    with open(debug_path, "w", encoding="utf-8") as f:
        f.write(f"Rànquing per a la paraula objectiu: '{paraula_objectiu}'\n")
        f.write("="*50 + "\n")
        for i, (paraula, sim) in enumerate(similituds):
            f.write(f"{i:<5} | {paraula:<20} | Similitud: {sim:.4f}\n")
    print(f"Rànquing complet calculat i desat a '{debug_path}'.")
    return ranking_dict 