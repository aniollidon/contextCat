
from fastapi import FastAPI, HTTPException, Request, Query
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
from typing import List, Dict, Optional

import json
import os
import random
import logging
from datetime import date
from dotenv import load_dotenv
from pathlib import Path

# Configurar logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s',
    handlers=[
        logging.FileHandler('game.log'),
        logging.StreamHandler()
    ]
)
logger = logging.getLogger(__name__)

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


# Carregar diccionari 
DICCIONARI_PATH = os.getenv("DICCIONARI_PATH", "data/diccionari.json")
DEFAULT_REBUSCADA = os.getenv("DEFAULT_REBUSCADA", "paraula")

dicc = Diccionari.load(DICCIONARI_PATH)

# Variables globals que es carregaran dinàmicament
RANKING_DICCIONARI = {}
FORMES_CANONIQUES = []
TOTAL_PARAULES_RANKING = 0
REBUSCADA = ""

def carregar_ranking(rebuscada: str):
    """Carrega el rànquing per una paraula específica"""
    words_dir = Path("data/words")
    fitxer_paraula = words_dir / f"{rebuscada}.json"
    
    if not fitxer_paraula.exists():
        raise HTTPException(
            status_code=404,
            detail=f"No s'ha trobat el fitxer de rànquing per la paraula '{rebuscada}'"
        )
    
    try:
        with open(fitxer_paraula, "r", encoding="utf-8") as f:
            ranking_diccionari = json.load(f)
        
        formes_canoniques = list(ranking_diccionari.keys())
        total_paraules_ranking = len(ranking_diccionari)
        paraula_objectiu = min(ranking_diccionari, key=lambda k: ranking_diccionari[k])
        
        return ranking_diccionari, formes_canoniques, total_paraules_ranking, paraula_objectiu
        
    except Exception as e:
        raise HTTPException(
            status_code=500,
            detail=f"Error carregant el fitxer de rànquing: {str(e)}"
        )

def obtenir_ranking_actiu(rebuscada_request: Optional[str] = None):
    """Obté el rànquing actiu, sigui el global o el especificat"""
    if rebuscada_request:
        return carregar_ranking(rebuscada_request.lower())
    else:
        return RANKING_DICCIONARI, FORMES_CANONIQUES, TOTAL_PARAULES_RANKING, REBUSCADA

# Carregar rànquing per defecte
RANKING_DICCIONARI, FORMES_CANONIQUES, TOTAL_PARAULES_RANKING, REBUSCADA = carregar_ranking(DEFAULT_REBUSCADA)
logger.info(f"SERVIDOR INICIAT: Paraula objectiu '{REBUSCADA}' ({TOTAL_PARAULES_RANKING} paraules)")

class GuessRequest(BaseModel):
    paraula: str
    rebuscada: Optional[str] = None  # Paraula del dia opcional

class GuessResponse(BaseModel):
    paraula: str
    forma_canonica: Optional[str]
    posicio: int
    total_paraules: int
    es_correcta: bool

class PistaRequest(BaseModel):
    intents: List[Dict]
    rebuscada: Optional[str] = None  # Paraula del dia opcional

class PistaResponse(BaseModel):
    paraula: str
    forma_canonica: Optional[str]
    posicio: int
    total_paraules: int

class RendirseRequest(BaseModel):
    rebuscada: Optional[str] = None  # Paraula del dia opcional

class RendirseResponse(BaseModel):
    paraula_correcta: str

class RankingItem(BaseModel):
    paraula: str
    posicio: int

class RankingListResponse(BaseModel):
    rebuscada: str
    total_paraules: int
    objectiu: str
    ranking: List[RankingItem]


@app.post("/guess", response_model=GuessResponse)
async def guess(request: GuessRequest):
    # Obtenir rànquing actiu (global o especificat)
    ranking_diccionari, formes_canoniques, total_paraules, paraula_objectiu = obtenir_ranking_actiu(request.rebuscada)
    
    paraula_introduida = Diccionari.normalitzar_paraula(request.paraula)
    forma_canonica, es_flexio = dicc.obtenir_forma_canonica(paraula_introduida)
    if forma_canonica is None:
        # Millora: si la paraula no és al diccionari però sí apareix literalment al rànquing, accepta-la.
        rank_directe = ranking_diccionari.get(paraula_introduida)
        if rank_directe is not None:
            es_correcta_directe = paraula_introduida == paraula_objectiu
            logger.info(
                f"GUESS: '{paraula_introduida}' (fora diccionari però trobat al rànquing) -> "
                f"{'CORRECTA!' if es_correcta_directe else f'#'+str(rank_directe)} (objectiu: {paraula_objectiu})"
            )
            return GuessResponse(
                paraula=paraula_introduida,
                forma_canonica=None,
                posicio=rank_directe,
                total_paraules=total_paraules,
                es_correcta=es_correcta_directe
            )
        logger.info(f"GUESS: '{paraula_introduida}' -> INVÀLIDA (objectiu: {paraula_objectiu})")
        raise HTTPException(
            status_code=400,
            detail="Disculpa, aquesta paraula no és vàlida."
        )
    rank = ranking_diccionari.get(forma_canonica)
    if rank is None:
        logger.info(f"GUESS: '{paraula_introduida}' ({forma_canonica}) -> NO TROBADA (objectiu: {paraula_objectiu})")
        raise HTTPException(
            status_code=500,
            detail="Disculpa, aquesta paraula no es troba al nostre llistat."
        )
    es_correcta = forma_canonica == paraula_objectiu
    
    # Log de l'intent
    status = "CORRECTA!" if es_correcta else f"#{rank}"
    logger.info(f"GUESS: '{paraula_introduida}' ({forma_canonica if es_flexio else forma_canonica}) -> {status} (objectiu: {paraula_objectiu})")
    
    return GuessResponse(
        paraula=paraula_introduida,
        forma_canonica=forma_canonica if es_flexio else None,
        posicio=rank,
        total_paraules=total_paraules,
        es_correcta=es_correcta
    )

@app.post("/pista", response_model=PistaResponse)
async def donar_pista(request: PistaRequest):
    # Obtenir rànquing actiu (global o especificat)
    ranking_diccionari, formes_canoniques, total_paraules, paraula_objectiu = obtenir_ranking_actiu(request.rebuscada)
    
    intents_actuals = request.intents
    paraules_provades = {intent['paraula'] for intent in intents_actuals}
    
    # Obtenir les formes canòniques de les paraules provades
    formes_canoniques_provades = set()
    for intent in intents_actuals:
        forma_canonica = intent.get('forma_canonica')
        if forma_canonica:
            formes_canoniques_provades.add(forma_canonica)
        else:
            formes_canoniques_provades.add(intent['paraula'])
    
    # Obtenir la millor posició actual
    millor_ranking = min([intent['posicio'] for intent in intents_actuals]) if intents_actuals else total_paraules
    
    # Crear llista ordenada per posició (rànquing invers)
    ranking_invers = sorted(ranking_diccionari.keys(), key=lambda k: ranking_diccionari[k])
    
    # Determinar el rang de posicions per la pista
    if not intents_actuals or millor_ranking >= 1000:
        # Primera pista o molt lluny: començar a prop de la posició 500
        target_pos = 500
        variacio = 50
        inici_rang = max(0, target_pos - variacio)
        fi_rang = min(target_pos + variacio, total_paraules - 1)
    elif millor_ranking == 1:
        # Si ja tenen la posició 1, donar una paraula molt propera (posicions 2-5)
        inici_rang = 1  # posició 2 (index 1)
        fi_rang = min(4, total_paraules - 1)  # posició 5 màxim
    elif millor_ranking <= 10:
        # Si estan molt a prop, donar alguna cosa una mica millor
        target_pos = millor_ranking // 2
        inici_rang = max(0, target_pos - 2)
        fi_rang = max(target_pos + 2, millor_ranking - 1)
    elif millor_ranking <= 50:
        # Rang mitjà-petit: més a prop de la meitat
        target_pos = millor_ranking // 2
        inici_rang = max(0, target_pos - 5)
        fi_rang = max(target_pos + 5, millor_ranking - 1)
    elif millor_ranking <= 200:
        # Rang mitjà: centrat a la meitat amb una mica de variació
        target_pos = millor_ranking // 2
        inici_rang = max(0, target_pos - 10)
        fi_rang = max(target_pos + 10, millor_ranking - 1)
    elif millor_ranking <= 500:
        # Rang llunyà però no extremadament: a prop de la meitat
        target_pos = millor_ranking // 2
        variacio = min(15, millor_ranking // 15)
        inici_rang = max(0, target_pos - variacio)
        fi_rang = max(target_pos + variacio, millor_ranking - 1)
    else:
        # Rang molt llunyà: centrat a la meitat
        target_pos = millor_ranking // 2
        variacio = min(25, millor_ranking // 12)
        inici_rang = max(0, target_pos - variacio)
        fi_rang = max(target_pos + variacio, millor_ranking - 1)
    
    # Buscar una paraula adequada
    paraula_pista = None
    max_iteracions = 1000
    iteracio = 0
    
    while iteracio < max_iteracions and paraula_pista is None:
        # Escollir una posició aleatòria dins el rang
        index_pista = random.randint(inici_rang, fi_rang)
        
        if index_pista < len(ranking_invers):
            paraula_candidata = ranking_invers[index_pista]
            
            # Comprovar que no s'hagi provat ja i que no sigui la solució
            if (paraula_candidata not in formes_canoniques_provades and 
                paraula_candidata != paraula_objectiu):
                paraula_pista = paraula_candidata
                break
        
        iteracio += 1
    
    # Si no trobem cap paraula adequada, buscar qualsevol paraula no provada
    if paraula_pista is None:
        for paraula_candidata in ranking_invers:
            if (paraula_candidata not in formes_canoniques_provades and 
                paraula_candidata != paraula_objectiu):
                paraula_pista = paraula_candidata
                break
    
    if paraula_pista is None:
        logger.warning(f"PISTA: No s'ha trobat cap pista adequada (objectiu: {paraula_objectiu}, millor: #{millor_ranking})")
        raise HTTPException(status_code=404, detail="No s'ha pogut trobar una pista adequada.")
    
    # Log de la pista donada
    logger.info(f"PISTA: '{paraula_pista}' -> #{ranking_diccionari[paraula_pista]} (objectiu: {paraula_objectiu}, millor: #{millor_ranking})")
    
    return PistaResponse(
        paraula=paraula_pista,
        forma_canonica=None,
        posicio=ranking_diccionari[paraula_pista],
        total_paraules=total_paraules
    )

@app.get("/")
async def root():
    return {"message": "API del joc de paraules (refactoritzat)"}

@app.get("/paraula/{rebuscada}")
async def canviar_rebuscada(rebuscada: str):
    """Canvia la paraula del dia i carrega el seu rànquing corresponent"""
    global RANKING_DICCIONARI, FORMES_CANONIQUES, TOTAL_PARAULES_RANKING, REBUSCADA
    try:
        RANKING_DICCIONARI, FORMES_CANONIQUES, TOTAL_PARAULES_RANKING, REBUSCADA = carregar_ranking(rebuscada.lower())
        logger.info(f"PARAULA DIA CANVIADA: '{REBUSCADA}' ({TOTAL_PARAULES_RANKING} paraules)")
        return {
            "message": f"Paraula del dia canviada a '{rebuscada}'",
            "rebuscada": REBUSCADA,
            "total_paraules": TOTAL_PARAULES_RANKING
        }
    except HTTPException as e:
        logger.error(f"PARAULA DIA ERROR: No s'ha trobat '{rebuscada}'")
        raise e
    except Exception as e:
        logger.error(f"PARAULA DIA ERROR: {str(e)}")
        raise HTTPException(
            status_code=500,
            detail=f"Error canviant la paraula del dia: {str(e)}"
        )

@app.get("/info")
async def info():
    """Retorna informació sobre la paraula del dia actual"""
    return {
        "rebuscada": REBUSCADA,
        "total_paraules": TOTAL_PARAULES_RANKING,
        "rànquing_carregat": len(RANKING_DICCIONARI) > 0
    }

@app.get("/paraula-dia")
async def get_rebuscada():
    """Retorna la paraula del dia actual"""
    return {"paraula": REBUSCADA}

@app.post("/rendirse", response_model=RendirseResponse)
async def rendirse(request: RendirseRequest):
    """Endpoint per rendir-se i obtenir la resposta correcta"""
    global REBUSCADA
    
    try:
        # Obtenir rànquing actiu (global o especificat)
        ranking_diccionari, formes_canoniques, total_paraules, paraula_objectiu = obtenir_ranking_actiu(request.rebuscada)
        
        # Log de rendició
        logger.info(f"RENDICIÓ: Revelada paraula '{paraula_objectiu}'")
        
        return RendirseResponse(paraula_correcta=paraula_objectiu)
    
    except Exception as e:
        logger.error(f"RENDICIÓ: Error - {str(e)}")
        raise HTTPException(
            status_code=500,
            detail=f"Error en rendir-se: {str(e)}"
        )

@app.get("/ranking", response_model=RankingListResponse)
async def obtenir_ranking(limit: int = Query(300, ge=1, le=2000), rebuscada: Optional[str] = None):
    """Retorna les primeres 'limit' paraules del rànquing per la paraula del dia actual o l'especificada.

    Parameters
    ----------
    limit: int
        Nombre màxim de paraules a retornar (per defecte 300, màxim 2000)
    rebuscada: Optional[str]
        Paraula del dia per la qual es vol obtenir el rànquing (opcional)
    """
    try:
        ranking_diccionari, _formes, total_paraules, paraula_objectiu = obtenir_ranking_actiu(rebuscada)
        # Ordenar per posició (valor més petit = més proper)
        ordenat = sorted(ranking_diccionari.items(), key=lambda kv: kv[1])[:limit]
        return RankingListResponse(
            rebuscada=rebuscada.lower() if rebuscada else REBUSCADA,
            total_paraules=total_paraules,
            objectiu=paraula_objectiu,
            ranking=[RankingItem(paraula=p, posicio=pos) for p, pos in ordenat]
        )
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error obtenint el rànquing: {str(e)}")

if __name__ == "__main__":
    import uvicorn
    port = int(os.getenv("PORT", 8000))
    uvicorn.run(app, host="0.0.0.0", port=port)
