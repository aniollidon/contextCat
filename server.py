
from fastapi import FastAPI, HTTPException, Request, Query
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
from typing import List, Dict, Optional
from functools import lru_cache
import json
import os
import logging
from dotenv import load_dotenv
from pathlib import Path
from diccionari import Diccionari
from diccionari_full import DiccionariFull

class GuessRequest(BaseModel):
    paraula: str
    rebuscada: Optional[str] = None  # Paraula del dia opcional

class GuessResponse(BaseModel):
    paraula: str
    forma_canonica: Optional[str]
    posicio: int
    total_paraules: int
    es_correcta: bool

class ExplicacioNoValida(BaseModel):
    raó: str
    suggeriments: Optional[List[str]] = None

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
app = FastAPI()

# Configurar CORS
app.add_middleware(
    CORSMiddleware,
    allow_origins=["https://rebuscada.cat"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Carregar diccionari
DICCIONARI_PATH = os.getenv("DICCIONARI_PATH", "data/diccionari.json")
DEFAULT_REBUSCADA = os.getenv("DEFAULT_REBUSCADA", "paraula")
DICCIONARI_FULL_DB = os.path.join("data", DiccionariFull.DB_FILE)

dicc = Diccionari.load(DICCIONARI_PATH)
dicc_full = DiccionariFull(DICCIONARI_FULL_DB) if os.path.exists(DICCIONARI_FULL_DB) else None

# Carregar llista d'exclusions
EXCLUSIONS_PATH = os.path.join("data", "exclusions.json")
exclusions_set = set()
if os.path.exists(EXCLUSIONS_PATH):
    with open(EXCLUSIONS_PATH, "r", encoding="utf-8") as f:
        exclusions_data = json.load(f)
        exclusions_set = set(Diccionari.normalitzar_paraula(l) for l in exclusions_data.get("lemmas", []))

# Cache per emmagatzemar fins a 10 rànquings carregats (evita recarregar constantment)
CACHE_MAX_SIZE = int(os.getenv("RANKING_CACHE_SIZE", "10"))

def is_catalan(word: str) -> bool:
    """Retorna false si hi ha un caràcter no alfabètic (català, accepta accents, ç, dièresis, punt volat i guionet)
    """
    if not word or len(word) > 100:  # Evita strings buides o massa llargues
        return False
    if not any(c.isalpha() for c in word):  # Almenys una lletra
        return False
    return all(c.isalpha() or c in "àèéíïòóúüç·-" for c in word)

@lru_cache(maxsize=CACHE_MAX_SIZE)
def carregar_ranking(rebuscada: str):
    """Carrega el rànquing per una paraula específica"""

    # Comprova caràcters vàlids
    if not is_catalan(rebuscada):
        raise Exception(f"La paraula '{rebuscada}' conté caràcters no vàlids.")

    words_dir = Path("data/words")
    fitxer_paraula = words_dir / f"{rebuscada}.json"
    
    if not fitxer_paraula.exists():
        raise Exception(f"No s'ha trobat el fitxer de rànquing per la paraula '{rebuscada}'")
    
    try:
        with open(fitxer_paraula, "r", encoding="utf-8") as f:
            ranking_diccionari = json.load(f)
        
        # Si el rànquing està buit
        if not ranking_diccionari:
            raise Exception(f"El fitxer de rànquing per la paraula '{rebuscada}' està buit.")
        
        total_paraules_ranking = len(ranking_diccionari)
        paraula_objectiu = min(ranking_diccionari, key=lambda k: ranking_diccionari[k])
        
        return ranking_diccionari, total_paraules_ranking, paraula_objectiu
        
    except Exception as e:
        raise Exception(f"Error carregant el fitxer de rànquing: {str(e)}")

def obtenir_ranking_actiu(rebuscada_request: Optional[str] = None):
    """Obté el rànquing actiu, sigui el global o el especificat"""
    rebuscada = rebuscada_request.lower() if rebuscada_request else DEFAULT_REBUSCADA
    try:
        return carregar_ranking(rebuscada)
    except Exception as e:
        logger.error(f"Error carregant el rànquing per la paraula '{rebuscada}': {str(e)}")
        raise HTTPException(status_code=500, detail=str(e))

@app.post("/guess", response_model=GuessResponse)
async def guess(request: GuessRequest):
    # Obtenir rànquing actiu (global o especificat)
    ranking_diccionari, total_paraules, paraula_objectiu = obtenir_ranking_actiu(request.rebuscada)
    
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
        # Si no, rebutja la paraula
        msg = "Disculpa, aquesta paraula no és vàlida."
        logger.info(f"GUESS: '{paraula_introduida}' -> INVÀLIDA (objectiu: {paraula_objectiu}) | reason={msg}")
        raise HTTPException(status_code=400, detail=msg)
    rank = ranking_diccionari.get(forma_canonica)
    if rank is None:
        logger.info(f"GUESS: '{paraula_introduida}' ({forma_canonica}) -> NO TROBADA (objectiu: {paraula_objectiu})")
        raise HTTPException(
            status_code=400,
            detail="Disculpa, aquesta paraula no es troba al nostre llistat."
        )
    es_correcta = forma_canonica == paraula_objectiu
    
    # Log de l'intent
    status = "CORRECTA!" if es_correcta else f"#{rank}"
    logger.info(f"GUESS: '{paraula_introduida}'{' ('+ forma_canonica + ')' if es_flexio else ''} -> {status} (objectiu: {paraula_objectiu})")
    
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
    ranking_diccionari, total_paraules, paraula_objectiu = obtenir_ranking_actiu(request.rebuscada)
    intents_actuals = request.intents
    
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
    
    # Buscar una paraula adequada (prioritza freqüència de lema dins del rang)
    paraula_pista = None
    try:
        subllista = ranking_invers[inici_rang:fi_rang + 1] if fi_rang >= inici_rang else []
        candidats = [w for w in subllista if w not in formes_canoniques_provades and w != paraula_objectiu]
        if candidats:
            # Tria el candidat amb més freqüència al diccionari; si empata, el de millor rànquing (valor més petit), i després ordre alfabètic
            paraula_pista = max(
                candidats,
                key=lambda w: (dicc.freq_lema(w), -ranking_diccionari.get(w, total_paraules), w)
            )
    except Exception:
        paraula_pista = None
    
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

@app.post("/whynot", response_model=ExplicacioNoValida)
async def whynot(request: GuessRequest):
    """Endpoint per explicar per què una paraula no és vàlida"""
    ranking_diccionari, total_paraules, paraula_objectiu = obtenir_ranking_actiu(request.rebuscada)
    paraula_introduida = Diccionari.normalitzar_paraula(request.paraula)
    forma_canonica, es_flexio = dicc.obtenir_forma_canonica(paraula_introduida)
    rank_directe = ranking_diccionari.get(paraula_introduida)

    
    # Si la paraula és vàlida respondre HTTP Error ja que la paraula és correcta
    if forma_canonica is not None or rank_directe is not None:
        raise HTTPException(
            status_code=400,
            detail="La paraula introduïda és vàlida; aquest endpoint només és per paraules no vàlides."
        )

    # Si no tenim diccionari complet, no podem donar explicacions detallades
    if dicc_full is None:
        raise HTTPException(
            status_code=500,
            detail="El diccionari complet no està disponible."
        )

    # Obtenir informació de la paraula del diccionari complet
    info = dicc_full.info(paraula_introduida)

    explicacio = "Aquesta paraula simplement no és vàlida."
    suggeriments = None
    
    # 1. Si la paraula no existeix al diccionari complet -> error tipogràfic
    if not info['known_form']:
        explicacio = "Aquesta paraula probablement no està ben escrita."
        # Recomanar paraules similars amb la funció near
        near_result = dicc_full.near(paraula_introduida, limit=6, min_score=60)
        if near_result['candidates']:
            suggeriments = [c['word'] for c in near_result['candidates']]
    
    # 2. Si existeix, comprovar la categoria
    else:
        lemes = info['lemmas']
        primary_lemma = info['primary_lemma'] or (lemes[0] if lemes else None)
        
        if not primary_lemma:
            explicacio = "Aquesta paraula no és vàlida per una inconsistència al diccionari (#NOLEMA-ERROR). Si creus que hi hauria d'estar, si us plau, informa'ns."
        else:
            # Obtenir categories del lema principal
            categories = info['lemma_categories'].get(primary_lemma, [])
            cat_debug = ','.join(categories)
            
            # Comprovar si és una categoria no permesa (no NC ni VM)
            te_nc_o_vm = any(cat in ['NC', 'VM'] for cat in categories)
            
            if not te_nc_o_vm and categories:
                # Té categories però no són NC o VM
                # Trobar la categoria més comuna per fer el missatge
                from collections import Counter
                counter = Counter(categories)
                cat_principal = counter.most_common(1)[0][0] if counter else categories[0]
                
                # Etiqueta humana de la categoria
                cat_label = dicc_full._cat2_label(cat_principal)
                explicacio = f"Aquesta paraula és {cat_label}. Només es permeten noms i verbs comuns."
            
            # 3. Si està a la llista d'exclusions
            elif primary_lemma in exclusions_set:              
                if te_nc_o_vm:
                    # Intentem justificar si té alguna altre categoria diferent a NC o VM
                    altre_categories = [cat for cat in categories if cat not in ['NC', 'VM']]
                    if altre_categories:
                        from collections import Counter
                        counter = Counter(altre_categories)
                        cat_principal = counter.most_common(1)[0][0] if counter else altre_categories[0]
                        cat_label = dicc_full._cat2_label(cat_principal)
                        explicacio = f"Aquesta paraula és principalment {cat_label} i s'ha exclòs del joc."
                    else:
                        explicacio = "Aquesta paraula s'ha exclòs del joc (pot ser un arcaisme, castellanisme o per canvis ortogràfics recents)."
            
            # 4. Si existeix al diccionari però no al ranking -> poca freqüència
            elif forma_canonica is None and rank_directe is None:
                explicacio = "Aquesta paraula és massa poc comuna i s'ha exclòs del joc, per facilitar la jugabilitat."

    logger.info(f"WHYNOT: '{paraula_introduida}' -> {explicacio[:50]}...")
    
    return ExplicacioNoValida(
        raó=explicacio,
        suggeriments=suggeriments
    )


@app.get("/")
async def root():
    return {"message": "API del joc de paraules (refactoritzat)"}

@app.get("/paraula-dia")
async def get_rebuscada():
    """Retorna la paraula del dia actual"""
    return {"paraula": DEFAULT_REBUSCADA}

@app.post("/rendirse", response_model=RendirseResponse)
async def rendirse(request: RendirseRequest):
    """Endpoint per rendir-se i obtenir la resposta correcta"""
    try:
        # Obtenir rànquing actiu (global o especificat)
        ranking_diccionari, total_paraules, paraula_objectiu = obtenir_ranking_actiu(request.rebuscada)
        
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
        ranking_diccionari, total_paraules, paraula_objectiu = obtenir_ranking_actiu(rebuscada)
        # Ordenar per posició (valor més petit = més proper)
        ordenat = sorted(ranking_diccionari.items(), key=lambda kv: kv[1])[:limit]
        return RankingListResponse(
            rebuscada=rebuscada.lower() if rebuscada else DEFAULT_REBUSCADA,
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
