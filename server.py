
from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
from typing import List, Dict, Optional

import json
import os
from datetime import date
from dotenv import load_dotenv

load_dotenv()

from diccionari import Diccionari

app = FastAPI()

# Importa i inclou els endpoints d'admin
try:
    from main_admin_endpoints import router as admin_router
    app.include_router(admin_router)
except ImportError:
    pass

# Configurar CORS
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


# Carregar diccionari i rànquing des de fitxers JSON
DICCIONARI_PATH = os.getenv("DICCIONARI_PATH", "data/diccionari.json")
RANKING_PATH = os.getenv("RANKING_PATH", "data/ranking.json")

dicc = Diccionari.load(DICCIONARI_PATH)
with open(RANKING_PATH, "r", encoding="utf-8") as f:
    RANKING_DICCIONARI = json.load(f)

# Obtenir la paraula del dia: la que té posició 0 al rànquing
FORMES_CANONIQUES = list(RANKING_DICCIONARI.keys())
TOTAL_PARAULES_RANKING = len(RANKING_DICCIONARI)
PARAULA_DIA = min(RANKING_DICCIONARI, key=lambda k: RANKING_DICCIONARI[k])

class GuessRequest(BaseModel):
    paraula: str

class GuessResponse(BaseModel):
    paraula: str
    forma_canonica: Optional[str]
    posicio: int
    total_paraules: int
    es_correcta: bool

class PistaRequest(BaseModel):
    intents: List[Dict]

class PistaResponse(BaseModel):
    paraula: str
    forma_canonica: Optional[str]
    posicio: int
    total_paraules: int


@app.post("/guess", response_model=GuessResponse)
async def guess(request: GuessRequest):
    paraula_introduida = Diccionari.normalitzar_paraula(request.paraula)
    forma_canonica, es_flexio = dicc.obtenir_forma_canonica(paraula_introduida)
    if forma_canonica is None:
        raise HTTPException(
            status_code=400,
            detail="Paraula no vàlida. No es troba al diccionari."
        )
    rank = RANKING_DICCIONARI.get(forma_canonica)
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

@app.post("/pista", response_model=PistaResponse)
async def donar_pista(request: PistaRequest):
    intents_actuals = request.intents
    paraules_provades = {intent['paraula'] for intent in intents_actuals}
    millor_ranking = min([intent['posicio'] for intent in intents_actuals]) if intents_actuals else TOTAL_PARAULES_RANKING
    index_pista = -1
    if not intents_actuals or millor_ranking > 1000:
        index_pista = random.randint(500, min(999, TOTAL_PARAULES_RANKING-1))
    else:
        index_pista = millor_ranking // 2
    paraula_pista = None
    max_iteracions = TOTAL_PARAULES_RANKING
    iteracio = 0
    RANKING_INVERS = sorted(RANKING_DICCIONARI.keys(), key=lambda k: RANKING_DICCIONARI[k])
    while iteracio < max_iteracions:
        paraula_candidata = RANKING_INVERS[index_pista]
        if paraula_candidata not in [intent.get('forma_canonica', intent['paraula']) for intent in intents_actuals]:
            paraula_pista = paraula_candidata
            break
        index_pista = (index_pista + 1) % TOTAL_PARAULES_RANKING
        iteracio += 1
    if paraula_pista is None:
        raise HTTPException(status_code=404, detail="No s'ha pogut trobar una pista adequada.")
    return PistaResponse(
        paraula=paraula_pista,
        forma_canonica=None,
        posicio=RANKING_DICCIONARI[paraula_pista],
        total_paraules=TOTAL_PARAULES_RANKING
    )

@app.get("/")
async def root():
    return {"message": "API del joc de paraules (refactoritzat)"}

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)
