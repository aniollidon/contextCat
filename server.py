
from fastapi import FastAPI, HTTPException, Request, Query, WebSocket, WebSocketDisconnect
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
import uuid
import asyncio
from datetime import datetime

class GuessRequest(BaseModel):
    paraula: str
    rebuscada: Optional[str] = None  # Paraula del dia opcional
    comp_id: Optional[str] = None  # ID de competició opcional
    nom_jugador: Optional[str] = None  # Nom del jugador en competició

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
    comp_id: Optional[str] = None  # ID de competició opcional
    nom_jugador: Optional[str] = None  # Nom del jugador en competició

class PistaResponse(BaseModel):
    paraula: str
    forma_canonica: Optional[str]
    posicio: int
    total_paraules: int

class RendirseRequest(BaseModel):
    rebuscada: Optional[str] = None  # Paraula del dia opcional
    comp_id: Optional[str] = None  # ID de competició opcional
    nom_jugador: Optional[str] = None  # Nom del jugador en competició

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

# Models per competicions
class PlayerState(BaseModel):
    nom: str
    intents: int = 0
    pistes: int = 0
    estat_joc: str = "jugant"  # "jugant", "guanyat" o "rendit"
    millor_posicio: Optional[int] = None  # Millor posició aconseguida
    ultima_actualitzacio: str

class CompetitionState(BaseModel):
    comp_id: str
    rebuscada: str
    creador: str
    jugadors: Dict[str, PlayerState]
    data_creacio: str
    ultima_activitat: str

class CreateCompetitionRequest(BaseModel):
    nom_creador: str
    rebuscada: Optional[str] = None
    intents_existents: Optional[List[Dict]] = None

class CreateCompetitionResponse(BaseModel):
    comp_id: str
    rebuscada: str

class JoinCompetitionRequest(BaseModel):
    nom_jugador: str
    intents_existents: Optional[List[Dict]] = None

class JoinCompetitionResponse(BaseModel):
    comp_id: str
    rebuscada: str
    nom_jugador: str

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

@app.on_event("startup")
async def startup_event():
    """Inicia la tasca de neteja de competicions caducades"""
    asyncio.create_task(cleanup_expired_competitions())
    logger.info(f"Competition cleanup task started (expiry: {COMPETITION_EXPIRY_DAYS} days)")

# Configurar CORS
# En producció només permetre rebuscada.cat, en desenvolupament també localhost
ALLOWED_ORIGINS = os.getenv("ALLOWED_ORIGINS", "https://rebuscada.cat,http://localhost:3000").split(",")
app.add_middleware(
    CORSMiddleware,
    allow_origins=ALLOWED_ORIGINS,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Carregar diccionari
DICCIONARI_PATH = os.getenv("DICCIONARI_PATH", "data/diccionari.json")
DEFAULT_REBUSCADA = os.getenv("DEFAULT_REBUSCADA", "paraula")
DICCIONARI_FULL_DB = os.path.join("data", DiccionariFull.DB_FILE)
COMPETITION_EXPIRY_DAYS = int(os.getenv("COMPETITION_EXPIRY_DAYS", "2"))

dicc = Diccionari.load(DICCIONARI_PATH)
dicc_full = DiccionariFull(DICCIONARI_FULL_DB) if os.path.exists(DICCIONARI_FULL_DB) else None

# Emmagatzematge en memòria per competicions
competitions: Dict[str, CompetitionState] = {}
competition_connections: Dict[str, List[WebSocket]] = {}

# Funció de neteja de competicions caducades
async def cleanup_expired_competitions():
    """Esborra competicions que no han tingut activitat en els últims N dies"""
    while True:
        try:
            await asyncio.sleep(3600)  # Comprova cada hora
            
            now = datetime.now()
            expired_ids = []
            
            for comp_id, competition in competitions.items():
                ultima_activitat = datetime.fromisoformat(competition.ultima_activitat)
                days_inactive = (now - ultima_activitat).days
                
                if days_inactive >= COMPETITION_EXPIRY_DAYS:
                    expired_ids.append(comp_id)
                    logger.info(f"COMPETITION: Expiring {comp_id} (inactive for {days_inactive} days)")
            
            # Esborrar competicions caducades
            for comp_id in expired_ids:
                del competitions[comp_id]
                if comp_id in competition_connections:
                    del competition_connections[comp_id]
        except Exception as e:
            logger.error(f"Error in cleanup_expired_competitions: {e}")

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
    
    # Si és una competició, actualitzar estat
    if request.comp_id and request.nom_jugador:
        await actualitzar_progres_competicio(
            request.comp_id, 
            request.nom_jugador, 
            posicio=rank,
            estat_joc="guanyat" if es_correcta else None
        )
    
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
    
    # Si és una competició, actualitzar pistes
    if request.comp_id and request.nom_jugador:
        await actualitzar_progres_competicio(
            request.comp_id, 
            request.nom_jugador, 
            incrementar_pistes=True,
            posicio=ranking_diccionari[paraula_pista]
        )
    
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
    # Cas específic: espais no permesos (només una paraula simple)
    if any(ch.isspace() for ch in request.paraula):
        suggeriments = None
        try:
            if dicc_full is not None:
                # Prova sense espais per suggerir alternatives
                sense_espais = "".join(paraula_introduida.split())
                if sense_espais:
                    near_result = dicc_full.near(sense_espais, limit=6, min_score=60)
                    if near_result and near_result.get('candidates'):
                        suggeriments = [c['word'] for c in near_result['candidates']]
        except Exception:
            suggeriments = None

        logger.info(f"WHYNOT: '{request.paraula}' -> conté espais")
        return ExplicacioNoValida(
            raó=(
                "Sembla que has introduït un espai. Només s'accepten paraules simples (sense espais)."
            ),
            suggeriments=suggeriments
        )

    # Validació de caràcters catalans permesos
    if not is_catalan(paraula_introduida):
        logger.info(f"WHYNOT: '{paraula_introduida}' -> caràcters no permesos")
        return ExplicacioNoValida(
            raó=(
                "Aquesta paraula conté caràcters no permesos. Només s'accepten lletres catalanes amb accents, "
                "dièresi, la ce trencada (ç), el punt volat (l·l) i el guionet (-)."
            ),
            suggeriments=None
        )
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


async def actualitzar_progres_competicio(
    comp_id: str, 
    nom_jugador: str, 
    incrementar_pistes: bool = False,
    posicio: Optional[int] = None,
    estat_joc: Optional[str] = None
):
    """Actualitza el progrés d'un jugador en una competició
    
    Args:
        estat_joc: "guanyat", "rendit" o None (per mantenir estat actual)
    """
    if comp_id not in competitions:
        return
    
    competition = competitions[comp_id]
    if nom_jugador not in competition.jugadors:
        return
    
    player = competition.jugadors[nom_jugador]
    
    if not incrementar_pistes:
        player.intents += 1
    
    if incrementar_pistes:
        player.pistes += 1
    
    if estat_joc is not None:
        player.estat_joc = estat_joc
    
    # Actualitzar millor posició
    if posicio is not None:
        if player.millor_posicio is None or posicio < player.millor_posicio:
            player.millor_posicio = posicio
    
    now = datetime.now().isoformat()
    player.ultima_actualitzacio = now
    competition.ultima_activitat = now
    
    # Notificar altres jugadors
    await broadcast_competition_update(comp_id)

async def broadcast_competition_update(comp_id: str):
    """Envia actualitzacions a tots els clients connectats a una competició"""
    if comp_id not in competition_connections:
        return
    
    if comp_id not in competitions:
        return
    
    competition = competitions[comp_id]
    message = {
        "type": "update",
        "jugadors": [
            {
                "nom": player.nom,
                "intents": player.intents,
                "pistes": player.pistes,
                "estat_joc": player.estat_joc,
                "millor_posicio": player.millor_posicio
            }
            for player in competition.jugadors.values()
        ]
    }
    
    # Enviar a tots els websockets connectats
    disconnected = []
    for websocket in competition_connections[comp_id]:
        try:
            await websocket.send_json(message)
        except:
            disconnected.append(websocket)
    
    # Netejar connexions desconnectades
    for ws in disconnected:
        competition_connections[comp_id].remove(ws)

@app.post("/competition/create", response_model=CreateCompetitionResponse)
async def create_competition(request: CreateCompetitionRequest):
    """Crea una nova competició"""
    try:
        comp_id = str(uuid.uuid4())[:8]  # ID curt
        rebuscada = request.rebuscada or DEFAULT_REBUSCADA
        
        # Validar que la rebuscada existeix
        try:
            carregar_ranking(rebuscada)
        except Exception as e:
            raise HTTPException(status_code=400, detail=f"Paraula no vàlida: {str(e)}")
        
        now = datetime.now().isoformat()
        
        # Calcular intents i millor posició dels intents existents
        intents_count = len(request.intents_existents) if request.intents_existents else 0
        millor_pos = None
        if request.intents_existents:
            posicions = [intent.get('posicio') for intent in request.intents_existents if 'posicio' in intent]
            if posicions:
                millor_pos = min(posicions)
        
        player_state = PlayerState(
            nom=request.nom_creador,
            intents=intents_count,
            pistes=0,
            estat_joc="jugant",
            millor_posicio=millor_pos,
            ultima_actualitzacio=now
        )
        
        competition = CompetitionState(
            comp_id=comp_id,
            rebuscada=rebuscada,
            creador=request.nom_creador,
            jugadors={request.nom_creador: player_state},
            data_creacio=now,
            ultima_activitat=now
        )
        
        competitions[comp_id] = competition
        competition_connections[comp_id] = []
        
        logger.info(f"COMPETITION: Created {comp_id} by {request.nom_creador} for word '{rebuscada}' with {intents_count} existing attempts (millor pos: {millor_pos})")
        
        return CreateCompetitionResponse(
            comp_id=comp_id,
            rebuscada=rebuscada
        )
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error creating competition: {str(e)}")
        raise HTTPException(status_code=500, detail=str(e))

@app.post("/competition/{comp_id}/join", response_model=JoinCompetitionResponse)
async def join_competition(comp_id: str, request: JoinCompetitionRequest):
    """Uneix un jugador a una competició existent"""
    if comp_id not in competitions:
        raise HTTPException(status_code=404, detail="Competició no trobada")
    
    competition = competitions[comp_id]
    
    # Comprovar si el nom ja està ocupat
    now = datetime.now().isoformat()
    if request.nom_jugador in competition.jugadors:
        # Nom ja ocupat per un altre jugador
        logger.warning(f"COMPETITION: Player name '{request.nom_jugador}' already exists in {comp_id}")
        raise HTTPException(
            status_code=409, 
            detail=f"El nom '{request.nom_jugador}' ja està ocupat en aquesta competició. Tria un altre nom."
        )
    else:
        # Nou jugador
        intents_count = len(request.intents_existents) if request.intents_existents else 0
        
        # Calcular la millor posició dels intents existents
        millor_pos = None
        if request.intents_existents:
            posicions = [intent.get('posicio') for intent in request.intents_existents if 'posicio' in intent]
            if posicions:
                millor_pos = min(posicions)
        
        player_state = PlayerState(
            nom=request.nom_jugador,
            intents=intents_count,
            pistes=0,
            estat_joc="jugant",
            millor_posicio=millor_pos,
            ultima_actualitzacio=now
        )
        
        competition.jugadors[request.nom_jugador] = player_state
        logger.info(f"COMPETITION: Player {request.nom_jugador} joined {comp_id} with {intents_count} existing attempts (millor pos: {millor_pos})")
        
        # Notificar altres jugadors
        await broadcast_competition_update(comp_id)
    
    return JoinCompetitionResponse(
        comp_id=comp_id,
        rebuscada=competition.rebuscada,
        nom_jugador=request.nom_jugador
    )

@app.get("/competition/{comp_id}", response_model=CompetitionState)
async def get_competition(comp_id: str):
    """Obté l'estat actual d'una competició"""
    if comp_id not in competitions:
        raise HTTPException(status_code=404, detail="Competició no trobada")
    
    return competitions[comp_id]

@app.post("/competition/{comp_id}/leave")
async def leave_competition(comp_id: str, nom_jugador: str = Query(...)):
    """Surt d'una competició (elimina el jugador)"""
    if comp_id not in competitions:
        raise HTTPException(status_code=404, detail="Competició no trobada")
    
    competition = competitions[comp_id]
    
    if nom_jugador not in competition.jugadors:
        raise HTTPException(status_code=404, detail="Jugador no trobat en aquesta competició")
    
    # Eliminar jugador
    del competition.jugadors[nom_jugador]
    logger.info(f"COMPETITION: Player {nom_jugador} left {comp_id}")
    
    # Si no queden jugadors, eliminar la competició
    if len(competition.jugadors) == 0:
        del competitions[comp_id]
        if comp_id in competition_connections:
            del competition_connections[comp_id]
        logger.info(f"COMPETITION: Deleted {comp_id} (no players left)")
    else:
        # Notificar altres jugadors
        await broadcast_competition_update(comp_id)
    
    return {"message": "Has sortit de la competició"}

@app.websocket("/ws/competition/{comp_id}")
async def competition_websocket(websocket: WebSocket, comp_id: str):
    """WebSocket per rebre actualitzacions en temps real d'una competició"""
    if comp_id not in competitions:
        await websocket.close(code=1008, reason="Competició no trobada")
        return
    
    await websocket.accept()
    
    if comp_id not in competition_connections:
        competition_connections[comp_id] = []
    
    competition_connections[comp_id].append(websocket)
    logger.info(f"COMPETITION WS: Client connected to {comp_id}")
    
    try:
        # Enviar estat inicial
        competition = competitions[comp_id]
        await websocket.send_json({
            "type": "init",
            "jugadors": [
                {
                    "nom": player.nom,
                    "intents": player.intents,
                    "pistes": player.pistes,
                    "estat_joc": player.estat_joc,
                    "millor_posicio": player.millor_posicio
                }
                for player in competition.jugadors.values()
            ]
        })
        
        # Mantenir connexió oberta
        while True:
            # Esperar missatges (per detectar desconnexions)
            await websocket.receive_text()
    except WebSocketDisconnect:
        logger.info(f"COMPETITION WS: Client disconnected from {comp_id}")
    except Exception as e:
        logger.error(f"COMPETITION WS: Error - {str(e)}")
    finally:
        if websocket in competition_connections.get(comp_id, []):
            competition_connections[comp_id].remove(websocket)

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
        
        # Si és una competició, marcar com a rendit
        if request.comp_id and request.nom_jugador:
            await actualitzar_progres_competicio(
                request.comp_id, 
                request.nom_jugador, 
                estat_joc="rendit"
            )
        
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
