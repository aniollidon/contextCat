from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
import random
from typing import List, Dict, Tuple, Optional
from datetime import date
import json # Importem json per a la depuració
from diccionari_millorat import obtenir_diccionari_millorat, obtenir_forma_canonica, normalitzar_paraula
from proximitat import carregar_model_fasttext, calcular_ranking_complet

app = FastAPI()

# Configurar CORS
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # Permet tots els orígens, per a desenvolupament
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Carregar diccionari
print("Carregant diccionari...")
MAPPING_FLEXIONS, FORMES_CANONIQUES = obtenir_diccionari_millorat()
print(f"Nombre de formes canòniques: {len(FORMES_CANONIQUES)}")

# Carregar model fastText
FT_MODEL = carregar_model_fasttext()

# Paraula del dia i càlcul de rànquing
if len(FORMES_CANONIQUES) > 0:
    # Generar una paraula del dia consistent basada en la data
    avui = date.today()
    seed_diaria = avui.year * 10000 + avui.month * 100 + avui.day
    random.seed(seed_diaria)
    
    PARAULA_DIA = "perímetre" #random.choice(list(FORMES_CANONIQUES.keys()))
    print(f"\nParaula del dia seleccionada (seed: {seed_diaria}): {PARAULA_DIA}")
    
    # Calcular rànquing inicial
    RANKING_DICCIONARI = calcular_ranking_complet(
        PARAULA_DIA, 
        list(FORMES_CANONIQUES.keys()), 
        FT_MODEL
    )
    TOTAL_PARAULES_RANKING = len(RANKING_DICCIONARI)
else:
    print("No es pot seleccionar una paraula del dia perquè el diccionari està buit")
    exit(1)

class GuessRequest(BaseModel):
    paraula: str

class GuessResponse(BaseModel):
    paraula: str
    forma_canonica: Optional[str]
    posicio: int
    total_paraules: int
    es_correcta: bool

@app.post("/guess", response_model=GuessResponse)
async def guess(request: GuessRequest):
    paraula_introduida = normalitzar_paraula(request.paraula)
    
    forma_canonica, es_flexio = obtenir_forma_canonica(paraula_introduida, MAPPING_FLEXIONS)
    
    if forma_canonica is None:
        raise HTTPException(
            status_code=400, 
            detail="Paraula no vàlida. No es troba al diccionari."
        )
    
    # Obtenir el rànquing de la paraula
    rank = RANKING_DICCIONARI.get(forma_canonica)
    
    # Si la paraula canònica no està al rànquing (no hauria de passar si està al diccionari)
    if rank is None:
        raise HTTPException(
            status_code=500, 
            detail="Error intern: La paraula no s'ha trobat al rànquing."
        )

    es_correcta = forma_canonica == PARAULA_DIA
    
    return GuessResponse(
        paraula=paraula_introduida,
        forma_canonica=forma_canonica if es_flexio else None,
        posicio=rank,
        total_paraules=TOTAL_PARAULES_RANKING,
        es_correcta=es_correcta
    )

@app.get("/")
async def root():
    return {"message": "API del joc de paraules"}

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)
