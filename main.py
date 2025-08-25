from fastapi import FastAPI, HTTPException, Body
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
import random
from typing import List, Dict, Tuple, Optional
from datetime import date
import json # Importem json per a la depuració
from diccionari_millorat import obtenir_diccionari_millorat, obtenir_forma_canonica, normalitzar_paraula, obtenir_paraula_aleatoria
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
    # Generar una paraula del dia consistent basada en la data, però només freq > 2000
    avui = date.today()
    seed_diaria = avui.year * 10000 + avui.month * 100 + avui.day +1
    random.seed(seed_diaria)

    PARAULA_DIA = obtenir_paraula_aleatoria(MAPPING_FLEXIONS, FORMES_CANONIQUES, freq_min=2000)
    print(f"\nParaula del dia seleccionada (freq > 2000, seed: {seed_diaria}): {PARAULA_DIA}")

    # Calcular rànquing inicial
    RANKING_DICCIONARI = calcular_ranking_complet(
        PARAULA_DIA, 
        list(FORMES_CANONIQUES.keys()), 
        FT_MODEL
    )
    # Crear una llista de paraules ordenades per rànquing per a les pistes
    RANKING_INVERS = sorted(RANKING_DICCIONARI.keys(), key=lambda k: RANKING_DICCIONARI[k])
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

class PistaRequest(BaseModel):
    intents: List[Dict]

class PistaResponse(BaseModel):
    paraula: str
    forma_canonica: Optional[str]
    posicio: int
    total_paraules: int

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

@app.post("/pista", response_model=PistaResponse)
async def donar_pista(request: PistaRequest):
    intents_actuals = request.intents
    paraules_provades = {intent['paraula'] for intent in intents_actuals}
    
    # Trobar el millor rànquing actual
    millor_ranking = min([intent['posicio'] for intent in intents_actuals]) if intents_actuals else TOTAL_PARAULES_RANKING

    index_pista = -1
    if not intents_actuals or millor_ranking > 1000:
        # Si no hi ha intents o el millor és molt llunyà, donar una pista entre 500 i 1000
        index_pista = random.randint(500, 999)
    else:
        # Donar una pista a mig camí del millor intent
        index_pista = millor_ranking // 2
    
    # Buscar una paraula per a la pista que no hagi estat provada
    paraula_pista = None
    max_iteracions = TOTAL_PARAULES_RANKING # Evitar bucles infinits
    iteracio = 0
    while iteracio < max_iteracions:
        paraula_candidata = RANKING_INVERS[index_pista]
        
        # Comprovem si la forma canònica ja s'ha utilitzat
        if paraula_candidata not in [intent.get('forma_canonica', intent['paraula']) for intent in intents_actuals]:
             paraula_pista = paraula_candidata
             break

        # Si ja s'ha dit, provem amb la següent/anterior per no encallar-nos
        index_pista = (index_pista + 1) % TOTAL_PARAULES_RANKING
        iteracio += 1
    
    if paraula_pista is None:
        raise HTTPException(status_code=404, detail="No s'ha pogut trobar una pista adequada.")

    # La paraula pista sempre és una forma canònica, per tant no té una forma canònica diferent
    return PistaResponse(
        paraula=paraula_pista,
        forma_canonica=None,
        posicio=RANKING_DICCIONARI[paraula_pista],
        total_paraules=TOTAL_PARAULES_RANKING
    )

@app.get("/")
async def root():
    return {"message": "API del joc de paraules"}

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)
