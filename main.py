from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
import random
from typing import List, Dict
import torch
from transformers import AutoTokenizer, AutoModel
import numpy as np
from diccionari import obtenir_diccionari, normalitzar_paraula
import os

app = FastAPI()

# Configurar CORS
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Carregar el model d'IA
print("Carregant el model d'IA...")
tokenizer = AutoTokenizer.from_pretrained("BSC-TeMU/roberta-base-ca")
model = AutoModel.from_pretrained("BSC-TeMU/roberta-base-ca")
print("Model carregat correctament!")

# Carregar el diccionari
DICCIONARI = obtenir_diccionari()
print(f"Nombre de paraules al diccionari: {len(DICCIONARI)}")
if len(DICCIONARI) == 0:
    print("ERROR: El diccionari està buit!")
    print("Verificant si existeix el fitxer de cache...")
    if os.path.exists("diccionari_cache.txt"):
        print("El fitxer de cache existeix")
        with open("diccionari_cache.txt", 'r', encoding='utf-8') as f:
            content = f.read()
            print(f"Mida del fitxer: {len(content)} bytes")
    else:
        print("El fitxer de cache NO existeix")
else:
    print("Exemples de paraules al diccionari:")
    for paraula in list(DICCIONARI)[:5]:
        print(f"- {paraula}")

# Paraula del dia (normalitzada)
if len(DICCIONARI) > 0:
    PARAULA_DIA = 'gat'# random.choice(list(DICCIONARI))
    PARAULA_DIA_NORMALITZADA = normalitzar_paraula(PARAULA_DIA)
    print(f"\nParaula del dia seleccionada: {PARAULA_DIA}")
else:
    print("No es pot seleccionar una paraula del dia perquè el diccionari està buit")
    exit(1)

class GuessRequest(BaseModel):
    word: str

class GuessResponse(BaseModel):
    proximitat: float
    es_correcta: bool
    arrel: str

def calcular_proximitat(paraula1: str, paraula2: str) -> float:
    """Calcula la proximitat semàntica entre dues paraules utilitzant el model d'IA."""
    try:
        # Normalitzar les paraules
        paraula1_norm = normalitzar_paraula(paraula1)
        paraula2_norm = normalitzar_paraula(paraula2)
        
        # Si són exactament iguals, retornar 1.0
        if paraula1_norm == paraula2_norm:
            return 1.0
            
        # Obtenir els embeddings de les paraules
        tokens1 = tokenizer(paraula1_norm, return_tensors="pt", padding=True, truncation=True)
        tokens2 = tokenizer(paraula2_norm, return_tensors="pt", padding=True, truncation=True)
        
        with torch.no_grad():
            embeddings1 = model(**tokens1).last_hidden_state.mean(dim=1)
            embeddings2 = model(**tokens2).last_hidden_state.mean(dim=1)
        
        # Calcular la similitud del cosinus
        similarity = torch.nn.functional.cosine_similarity(embeddings1, embeddings2)
        return float(similarity[0])
    except Exception as e:
        print(f"Error calculant proximitat: {e}")
        return 0.0

@app.post("/guess", response_model=GuessResponse)
async def guess_word(guess: GuessRequest):
    # Normalitzar la paraula introduïda
    paraula_introduida = guess.word.lower()
    paraula_introduida_norm = normalitzar_paraula(paraula_introduida)
    
    # Verificar si la paraula és vàlida
    if paraula_introduida not in DICCIONARI:
        raise HTTPException(status_code=400, detail="Paraula no vàlida")
    
    # Calcular la proximitat
    proximitat = calcular_proximitat(paraula_introduida, PARAULA_DIA)
    
    # Determinar si és correcta
    es_correcta = paraula_introduida_norm == PARAULA_DIA_NORMALITZADA
    
    return GuessResponse(
        proximitat=proximitat,
        es_correcta=es_correcta,
        arrel=paraula_introduida  # En aquest cas, la paraula és la seva pròpia arrel
    )

@app.get("/")
async def root():
    return {"message": "API del joc de paraules"}

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)
