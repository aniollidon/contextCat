import os
from fastapi import FastAPI, HTTPException, Request, Depends
from fastapi.middleware.cors import CORSMiddleware
from typing import Dict
from pydantic import BaseModel
import json
from pathlib import Path
from dotenv import load_dotenv
import requests
import re
import json
import re
import importlib.util
from datetime import datetime

load_dotenv()

WORDS_DIR = Path(__file__).parent / "data" / "words"
WORDS_DIR.mkdir(parents=True, exist_ok=True)

COMMENTS_DIR = Path(__file__).parent / "data" / "words" / "comments"
COMMENTS_DIR.mkdir(parents=True, exist_ok=True)

VALIDATIONS_PATH = Path(__file__).parent / "data" / "validacions.json"
FAVORITES_PATH = Path(__file__).parent / "data" / "preferits.json"
DIFFICULTIES_PATH = Path(__file__).parent / "data" / "dificultats.json"
SYNONYMS_PATH = Path(__file__).parent / "data" / "sinonims.txt"
NEW_WORDS_PATH = Path(__file__).parent / "data" / "noves_paraules.json"

SYNONYMS_URL = "https://raw.githubusercontent.com/Softcatala/sinonims-cat/refs/heads/master/dict/sinonims.txt"

def _load_validations() -> dict:
    if VALIDATIONS_PATH.exists():
        try:
            with open(VALIDATIONS_PATH, encoding="utf-8") as f:
                data = json.load(f)
                if isinstance(data, dict):
                    return data
        except Exception:
            pass
    return {}

def _save_validations(data: dict):
    try:
        with open(VALIDATIONS_PATH, "w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False, indent=2)
    except Exception:
        raise HTTPException(status_code=500, detail="No s'ha pogut desar validacions")

def _load_favorites() -> dict:
    if FAVORITES_PATH.exists():
        try:
            with open(FAVORITES_PATH, encoding="utf-8") as f:
                data = json.load(f)
                if isinstance(data, dict):
                    return data
        except Exception:
            pass
    return {}

def _save_favorites(data: dict):
    try:
        with open(FAVORITES_PATH, "w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False, indent=2)
    except Exception:
        raise HTTPException(status_code=500, detail="No s'ha pogut desar preferits")

def _load_difficulties() -> dict:
    if DIFFICULTIES_PATH.exists():
        try:
            with open(DIFFICULTIES_PATH, encoding="utf-8") as f:
                data = json.load(f)
                if isinstance(data, dict):
                    return data
        except Exception:
            pass
    return {}

def _save_difficulties(data: dict):
    try:
        with open(DIFFICULTIES_PATH, "w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False, indent=2)
    except Exception:
        raise HTTPException(status_code=500, detail="No s'ha pogut desar dificultats")

def _get_comment_path(filename: str) -> Path:
    """Obté el path del fitxer de comentaris per una paraula rebuscada."""
    base_name = filename.replace('.json', '')
    return COMMENTS_DIR / f"{base_name}.comm.json"

def _load_comments(filename: str) -> dict:
    """Carrega els comentaris d'un fitxer de rànquing."""
    comment_path = _get_comment_path(filename)
    if comment_path.exists():
        try:
            with open(comment_path, encoding="utf-8") as f:
                data = json.load(f)
                if isinstance(data, dict):
                    return data
        except Exception:
            pass
    return {"global": "", "words": {}}

def _save_comments(filename: str, data: dict):
    """Desa els comentaris d'un fitxer de rànquing."""
    comment_path = _get_comment_path(filename)
    try:
        with open(comment_path, "w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False, indent=2)
    except Exception:
        raise HTTPException(status_code=500, detail="No s'ha pogut desar els comentaris")

def _delete_comments_file(filename: str):
    """Esborra el fitxer de comentaris si existeix."""
    comment_path = _get_comment_path(filename)
    if comment_path.exists():
        try:
            comment_path.unlink()
        except Exception:
            raise HTTPException(status_code=500, detail="No s'ha pogut esborrar el fitxer de comentaris")

def _download_synonyms():
    """Descarrega el fitxer de sinònims si no existeix."""
    if SYNONYMS_PATH.exists():
        return True
    
    try:
        print("Descarregant fitxer de sinònims...")
        response = requests.get(SYNONYMS_URL)
        response.raise_for_status()
        
        # Assegura que el directori existeix
        SYNONYMS_PATH.parent.mkdir(parents=True, exist_ok=True)
        
        with open(SYNONYMS_PATH, 'w', encoding='utf-8') as f:
            f.write(response.text)
        
        print(f"✓ Fitxer de sinònims descarregat a {SYNONYMS_PATH}")
        return True
    except Exception as e:
        print(f"Error descarregant sinònims: {e}")
        return False

def _get_synonyms_for_word(word: str) -> list:
    """Obté els sinònims d'una paraula del fitxer de sinònims agrupats per línia."""
    if not SYNONYMS_PATH.exists():
        return []
    
    word_lower = word.lower().strip()
    synonym_groups = []
    
    try:
        with open(SYNONYMS_PATH, 'r', encoding='utf-8') as f:
            for line_num, line in enumerate(f, 1):
                line = line.strip()
                if not line or line.startswith('#'):
                    continue
                
                # Elimina comentaris al final de la línia (tot després de #)
                if '#' in line:
                    line = line.split('#')[0].strip()
                    if not line:  # Si després d'eliminar el comentari no queda res
                        continue
                
                original_line = line
                
                # Elimina la categoria gramatical (tot fins als :)
                if ':' in line:
                    line = line.split(':', 1)[1].strip()
                
                # Divideix per comes per obtenir les paraules
                words_in_line = [w.strip() for w in line.split(',')]
                
                # Si la paraula base està en aquesta línia, afegeix el grup sencer
                words_clean = []
                for w in words_in_line:
                    # Elimina acotacions entre parèntesi
                    w_clean = re.sub(r'\([^)]*\)', '', w).strip()
                    if w_clean:
                        words_clean.append(w_clean.lower())
                
                if word_lower in words_clean:
                    # Afegeix tots els sinònims d'aquesta línia (excepte la paraula base)
                    group_synonyms = []
                    for syn in words_clean:
                        if syn != word_lower and syn:
                            group_synonyms.append(syn)
                    
                    if group_synonyms:
                        synonym_groups.append({
                            'line_num': line_num,
                            'original_line': original_line,
                            'synonyms': group_synonyms
                        })
        
        return synonym_groups
    except Exception as e:
        print(f"Error llegint fitxer de sinònims: {e}")
        return []

ADMIN_PORT = int(os.getenv("ADMIN_PORT", 5001))

ADMIN_PASSWORD = os.getenv("ADMIN_PASSWORD", "")

app = FastAPI()

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)



class AiGenerateRequest(BaseModel):
    prompt: str
class MoveRequest(BaseModel):
    from_pos: int
    to_pos: int

class InsertOrMoveRequest(BaseModel):
    word: str  # paraula a inserir o moure
    to_pos: int  # posició destí (0 <= to_pos <= len)

class AddNewWordRequest(BaseModel):
    word: str
    to_pos: int | None = None  # si None -> al final

class GenerateRequest(BaseModel):
    word: str

class RandomGenerateRequest(BaseModel):
    count: int = 10

class AuthRequest(BaseModel):
    password: str

class AddTestWordsRequest(BaseModel):
    # Accept either a single word or a list of words. Both optional but at least one must appear.
    word: str | None = None
    words: list[str] | None = None

class DeleteTestWordsRequest(BaseModel):
    words: list[str]

class CommentUpdate(BaseModel):
    comment: str  # El text del comentari

class WordCommentUpdate(BaseModel):
    word: str
    comment: str  # El text del comentari (buida per esborrar)

def require_auth(request: Request):
    if not ADMIN_PASSWORD:
        return  # no password set -> open
    header = request.headers.get("x-admin-token")
    if not header or header != ADMIN_PASSWORD:
        raise HTTPException(status_code=401, detail="Unauthorized")

@app.post("/api/auth")
def auth(req: AuthRequest):
    if not ADMIN_PASSWORD:
        return {"ok": True, "note": "No password configured"}
    if req.password == ADMIN_PASSWORD:
        return {"ok": True}
    raise HTTPException(status_code=401, detail="Contrasenya incorrecta")

@app.get("/api/rankings")
def list_rankings(_: None = Depends(require_auth)):
    files = [f.name for f in WORDS_DIR.glob("*.json")]
    return files

@app.get("/api/validations")
def get_validations(_: None = Depends(require_auth)):
    return _load_validations()

@app.get("/api/favorites")
def get_favorites(_: None = Depends(require_auth)):
    return _load_favorites()

@app.get("/api/difficulties")
def get_difficulties(_: None = Depends(require_auth)):
    return _load_difficulties()

class ValidationUpdate(BaseModel):
    validated: str  # 'validated', 'approved', or empty string to remove

class FavoriteUpdate(BaseModel):
    favorite: bool

class DifficultyUpdate(BaseModel):
    difficulty: str  # 'facil', 'mitja', 'dificil', or empty string to remove

@app.post("/api/validations/{filename}")
def set_validation(filename: str, upd: ValidationUpdate, _: None = Depends(require_auth)):
    # accept only existing ranking files
    file_path = WORDS_DIR / filename
    if not file_path.exists():
        raise HTTPException(status_code=404, detail="Fitxer no trobat")
    
    # Valida que la validació sigui vàlida
    valid_statuses = ['validated', 'approved']
    if upd.validated and upd.validated not in valid_statuses:
        raise HTTPException(status_code=400, detail="Estat de validació no vàlid")
    
    vals = _load_validations()
    if upd.validated:
        vals[filename] = upd.validated
    else:
        # remove key if empty to keep file small
        if filename in vals:
            del vals[filename]
    _save_validations(vals)
    return {"ok": True, "validated": upd.validated}

@app.post("/api/favorites/{filename}")
def set_favorite(filename: str, upd: FavoriteUpdate, _: None = Depends(require_auth)):
    # accept only existing ranking files
    file_path = WORDS_DIR / filename
    if not file_path.exists():
        raise HTTPException(status_code=404, detail="Fitxer no trobat")
    favs = _load_favorites()
    if upd.favorite:
        favs[filename] = True
    else:
        # remove key if false to keep file small
        if filename in favs:
            del favs[filename]
    _save_favorites(favs)
    return {"ok": True, "favorite": upd.favorite}

@app.post("/api/difficulties/{filename}")
def set_difficulty(filename: str, upd: DifficultyUpdate, _: None = Depends(require_auth)):
    # accept only existing ranking files
    file_path = WORDS_DIR / filename
    if not file_path.exists():
        raise HTTPException(status_code=404, detail="Fitxer no trobat")
    
    # Valida que la dificultat sigui vàlida
    valid_difficulties = ['facil', 'mitja', 'dificil']
    if upd.difficulty and upd.difficulty not in valid_difficulties:
        raise HTTPException(status_code=400, detail="Dificultat no vàlida")
    
    diffs = _load_difficulties()
    if upd.difficulty:
        diffs[filename] = upd.difficulty
    else:
        # remove key if empty to keep file small
        if filename in diffs:
            del diffs[filename]
    _save_difficulties(diffs)
    return {"ok": True, "difficulty": upd.difficulty}

from fastapi import Query

@app.get("/api/rankings/{filename}")
def read_ranking(filename: str, offset: int = Query(0, ge=0), limit: int = Query(100, ge=1), _: None = Depends(require_auth)):
    file_path = WORDS_DIR / filename
    if not file_path.exists():
        raise HTTPException(status_code=404, detail="Fitxer no trobat.")
    with open(file_path, encoding="utf-8") as f:
        data = json.load(f)
    # data is a dict {word: pos}
    # sort by pos, then slice
    items = sorted(data.items(), key=lambda x: x[1])
    paged = items[offset:offset+limit]
    return {"total": len(items), "words": [{"word": w, "pos": p} for w, p in paged]}

@app.delete("/api/rankings/{filename}")
def delete_ranking(filename: str, _: None = Depends(require_auth)):
    file_path = WORDS_DIR / filename
    if not file_path.exists():
        raise HTTPException(status_code=404, detail="No s'ha pogut esborrar.")
    file_path.unlink()
    return {"ok": True}


from fastapi import Request

@app.post("/api/rankings/{filename}")
async def save_ranking(filename: str, request: Request, _: None = Depends(require_auth)):
    """Actualitza només un fragment (offset + claus ordenades) preservant la resta del rànquing."""
    file_path = WORDS_DIR / filename
    if not file_path.exists():
        raise HTTPException(status_code=404, detail="Fitxer no trobat.")
    body = await request.json()
    if "fragment" not in body or "offset" not in body:
        raise HTTPException(status_code=400, detail="Cal fragment i offset")
    fragment: dict = body["fragment"]
    offset: int = body["offset"]
    with open(file_path, encoding="utf-8") as f:
        data = json.load(f)
    items = sorted(data.items(), key=lambda x: x[1])
    keys = list(fragment.keys())
    # Assegura longitud suficient
    if offset + len(keys) > len(items):
        raise HTTPException(status_code=400, detail="Fragment excedeix longitud")
    for i, k in enumerate(keys):
        items[offset + i] = (k, offset + i)
    new_data = {k: i for i, (k, _) in enumerate(items)}
    with open(file_path, "w", encoding="utf-8") as f:
        json.dump(new_data, f, ensure_ascii=False, indent=2)
    return {"ok": True}


@app.post("/api/rankings/{filename}/move")
def move_word(filename: str, move: MoveRequest, _: None = Depends(require_auth)):
    """Move a word from one absolute position to another without loading all slices on frontend."""
    file_path = WORDS_DIR / filename
    if not file_path.exists():
        raise HTTPException(status_code=404, detail="Fitxer no trobat.")
    with open(file_path, encoding="utf-8") as f:
        data = json.load(f)
    items = sorted(data.items(), key=lambda x: x[1])  # list of (word, pos)
    total = len(items)
    if move.from_pos < 0 or move.from_pos >= total or move.to_pos < 0 or move.to_pos >= total:
        raise HTTPException(status_code=400, detail="Posicions fora de rang.")
    if move.from_pos == move.to_pos:
        return {"ok": True, "unchanged": True}
    # Extract
    word, _ = items.pop(move.from_pos)
    items.insert(move.to_pos, (word, move.to_pos))
    # Reassign positions
    new_data = {w: i for i, (w, _) in enumerate(items)}
    with open(file_path, "w", encoding="utf-8") as f:
        json.dump(new_data, f, ensure_ascii=False, indent=2)
    return {"ok": True, "word": word, "from": move.from_pos, "to": move.to_pos, "total": total}

@app.post("/api/rankings/{filename}/insert-or-move")
def insert_or_move_word(filename: str, req: InsertOrMoveRequest, _: None = Depends(require_auth)):
    """Insereix una paraula nova a la posició indicada o mou una existent a la nova posició.
    Manté la integritat de tot el rànquing i reindexa.
    - Si la paraula existeix: es mou (length invariant)
    - Si no existeix: s'insereix (length +1)
    """
    file_path = WORDS_DIR / filename
    if not file_path.exists():
        raise HTTPException(status_code=404, detail="Fitxer no trobat.")
    word = req.word.strip().lower()
    if not word:
        raise HTTPException(status_code=400, detail="Paraula buida")
    if req.to_pos < 0:
        raise HTTPException(status_code=400, detail="Posició negativa")
    with open(file_path, encoding="utf-8") as f:
        data = json.load(f)
    items = sorted(data.items(), key=lambda x: x[1])  # [(word,pos),...]
    original_len = len(items)
    # Localitza si existeix
    existing_index = next((i for i, (w, _) in enumerate(items) if w == word), None)
    inserting = existing_index is None
    # Normalitza to_pos dins límits
    to_pos = min(max(0, req.to_pos), original_len if inserting else original_len - 1)
    from_pos = None
    if inserting:
        # Inserció nova
        items.insert(to_pos, (word, to_pos))
    else:
        from_pos = existing_index
        if from_pos == to_pos:
            return {"ok": True, "action": "noop", "word": word, "from": from_pos, "to": to_pos, "total": original_len}
        # Extreu i re-insereix
        wtuple = items.pop(from_pos)
        # Ajust si l'element es mou cap avall (remoció abans redueix índexs)
        if from_pos < to_pos:
            to_pos -= 1
        items.insert(to_pos, wtuple)
    # Reindexa
    new_data = {w: i for i, (w, _) in enumerate(items)}
    expected_len = original_len + (1 if inserting else 0)
    if len(new_data) != expected_len:
        raise HTTPException(status_code=500, detail="Inconsistència de longitud")
    # Desa
    with open(file_path, "w", encoding="utf-8") as f:
        json.dump(new_data, f, ensure_ascii=False, indent=2)
    return {
        "ok": True,
        "action": "inserted" if inserting else "moved",
        "word": word,
        "from": from_pos,
        "to": to_pos,
        "total": expected_len,
    }

@app.get("/api/lemma-info/{word}")
def lemma_info(word: str, _: None = Depends(require_auth)):
    """Retorna informació de lema / flexió per informar abans d'afegir.
    is_inflection: True si la paraula és una flexió d'un lema diferent.
    """
    dicc = _get_diccionari()
    w = word.strip().lower()
    if not w:
        raise HTTPException(status_code=400, detail="Paraula buida")
    lema, es_flexio = dicc.obtenir_forma_canonica(w)
    return {
        "word": w,
        "lemma": lema,
        "is_inflection": bool(lema and es_flexio),
        "is_known": bool(lema),
    }

def _append_new_word_log(entry: dict):
    """Afegeix un registre a noves_paraules.json mantenint una llista."""
    try:
        if NEW_WORDS_PATH.exists():
            with open(NEW_WORDS_PATH, encoding="utf-8") as f:
                data = json.load(f)
            if not isinstance(data, list):
                data = []
        else:
            data = []
        data.append(entry)
        with open(NEW_WORDS_PATH, "w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False, indent=2)
    except Exception as e:
        print(f"[WARN] No s'ha pogut registrar nova paraula: {e}")

@app.post("/api/rankings/{filename}/add-new")
def add_new_word(filename: str, req: AddNewWordRequest, _: None = Depends(require_auth)):
    """Afegeix una paraula nova (nom/verb en forma canònica) al rànquing si no existeix.
    Valida i informa si sembla una flexió. Desa també registre a noves_paraules.json.
    """
    file_path = WORDS_DIR / filename
    if not file_path.exists():
        raise HTTPException(status_code=404, detail="Fitxer no trobat.")
    word = req.word.strip().lower()
    if not word:
        raise HTTPException(status_code=400, detail="Paraula buida")
    # Carrega ranking
    with open(file_path, encoding="utf-8") as f:
        data = json.load(f)
    if word in data:
        raise HTTPException(status_code=400, detail="La paraula ja existeix al rànquing")
    # Lema
    dicc = _get_diccionari()
    lema, es_flexio = dicc.obtenir_forma_canonica(word)
    is_inflection = bool(lema and es_flexio)
    # Inserció: decideix posició
    items = sorted(data.items(), key=lambda x: x[1])
    total = len(items)
    to_pos = req.to_pos
    if to_pos is None:
        to_pos = total  # al final
    to_pos = max(0, min(to_pos, total))
    items.insert(to_pos, (word, to_pos))
    # Reindexa
    new_data = {w: i for i, (w, _) in enumerate(items)}
    with open(file_path, "w", encoding="utf-8") as f:
        json.dump(new_data, f, ensure_ascii=False, indent=2)
    # Log
    _append_new_word_log({
        "word": word,
        "ranking_file": filename,
        "inserted_pos": to_pos,
        "total_after": len(new_data),
        "lemma": lema,
        "is_inflection": is_inflection,
        "timestamp": datetime.utcnow().isoformat() + "Z",
    })
    return {
        "ok": True,
        "action": "inserted",
        "word": word,
        "to": to_pos,
        "total": len(new_data),
        "lemma": lema,
        "is_inflection": is_inflection,
    }

@app.post("/api/generate")
def generate_ranking(req: GenerateRequest, _: None = Depends(require_auth)):
    """Genera un fitxer de rànquing per a una paraula (únic endpoint)."""
    # Si és linux retorna un error
    if sys.platform.startswith("linux"):
        raise HTTPException(status_code=400, detail="No es pot generar rànquing en sistemes Linux.")
    word = req.word.strip().lower()
    if not word:
        raise HTTPException(status_code=400, detail="Paraula buida")
    filename = f"{word}.json"
    file_path = WORDS_DIR / filename
    if file_path.exists():
        raise HTTPException(status_code=400, detail="Ja existeix")
    diccionari_json = Path("data/diccionari.json")
    from diccionari import Diccionari
    if diccionari_json.exists():
        try:
            dicc = Diccionari.load(str(diccionari_json))
        except Exception:
            dicc = Diccionari.obtenir_diccionari()
            dicc.save(str(diccionari_json))
    else:
        dicc = Diccionari.obtenir_diccionari()
        dicc.save(str(diccionari_json))
    from proximitat import carregar_model_fasttext, calcular_ranking_complet
    model = carregar_model_fasttext()
    paraules = dicc.totes_les_lemes()
    ranking = calcular_ranking_complet(word, paraules, model)
    with open(file_path, "w", encoding="utf-8") as f:
        json.dump(ranking, f, ensure_ascii=False, indent=2)
    return {"ok": True, "filename": filename, "total": len(ranking)}

# Cache globals per evitar recàrregues costoses
_DICC = None
_MODEL = None

def _get_diccionari():
    global _DICC
    from diccionari import Diccionari
    diccionari_json = Path("data/diccionari.json")
    if _DICC is None:
        if diccionari_json.exists():
            try:
                _DICC = Diccionari.load(str(diccionari_json))
            except Exception:
                _DICC = Diccionari.obtenir_diccionari()
                _DICC.save(str(diccionari_json))
        else:
            _DICC = Diccionari.obtenir_diccionari()
            _DICC.save(str(diccionari_json))
    return _DICC

def _get_model():
    global _MODEL
    if _MODEL is None:
        from proximitat import carregar_model_fasttext
        _MODEL = carregar_model_fasttext()
    return _MODEL

@app.post("/api/generate-random")
def generate_random(req: RandomGenerateRequest, _: None = Depends(require_auth)):
    """Genera diversos fitxers de rànquing per paraules aleatòries."""
    
    # Si és linux retorna un error
    if sys.platform.startswith("linux"):
        raise HTTPException(status_code=400, detail="No es pot generar rànquing en sistemes Linux.")

    count = max(1, min(req.count, 50))  # límit de seguretat
    dicc = _get_diccionari()
    from proximitat import calcular_ranking_complet
    model = _get_model()
    paraules = dicc.totes_les_lemes()
    generats = []
    vistes = set()
    import random
    intents = 0
    while len(generats) < count and intents < count * 10:
        intents += 1
        try:
            w = dicc.obtenir_paraula_aleatoria(freq_min=2000)
        except Exception:
            break
        if w in vistes:
            continue
        vistes.add(w)
        filename = f"{w}.json"
        file_path = WORDS_DIR / filename
        if file_path.exists():
            continue
        ranking = calcular_ranking_complet(w, paraules, model)
        with open(file_path, "w", encoding="utf-8") as f:
            json.dump(ranking, f, ensure_ascii=False, indent=2)
        generats.append({"word": w, "filename": filename, "total": len(ranking)})
    return {"ok": True, "generated": generats, "count": len(generats)}

@app.get("/api/rankings/{filename}/find")
def find_word(filename: str, word: str, _: None = Depends(require_auth)):
    file_path = WORDS_DIR / filename
    if not file_path.exists():
        raise HTTPException(status_code=404, detail="Fitxer no trobat.")
    with open(file_path, encoding="utf-8") as f:
        data = json.load(f)  # dict word->pos
    w = word.strip().lower()
    if w in data:
        return {"found": True, "pos": data[w]}
    return {"found": False}

@app.get("/api/rankings/{filename}/test-words")
def ranking_test_words(filename: str, _: None = Depends(require_auth)):
    """Retorna les paraules de data/test.json amb la seva posició (o no trobada)."""
    file_path = WORDS_DIR / filename
    if not file_path.exists():
        raise HTTPException(status_code=404, detail="Fitxer no trobat.")
    test_path = Path(__file__).parent / "data" / "test.json"
    if not test_path.exists():
        raise HTTPException(status_code=404, detail="test.json no trobat")
    try:
        with open(test_path, encoding="utf-8") as f:
            test_words = json.load(f)
    except Exception:
        raise HTTPException(status_code=500, detail="No s'ha pogut llegir test.json")
    with open(file_path, encoding="utf-8") as f:
        ranking = json.load(f)  # dict word->pos
    out = []
    for w in test_words:
        wl = str(w).strip().lower()
        if not wl:
            continue
        if wl in ranking:
            out.append({"word": w, "found": True, "pos": ranking[wl]})
        else:
            out.append({"word": w, "found": False})
    return {"count": len(out), "words": out}

@app.get("/api/rankings/{filename}/test-words-ai")
def ranking_test_words_ai(filename: str, _: None = Depends(require_auth)):
    """Retorna les paraules del fitxer .ai.json corresponent amb la seva posició al ranking."""
    file_path = WORDS_DIR / filename
    if not file_path.exists():
        raise HTTPException(status_code=404, detail="Fitxer no trobat.")
    
    # Busca el fitxer .ai.json corresponent
    base_name = filename.replace('.json', '')
    ai_file_path = WORDS_DIR / "ai" / f"{base_name}.ai.json"
    
    if not ai_file_path.exists():
        raise HTTPException(status_code=404, detail="Fitxer .ai.json no trobat")
    
    try:
        with open(ai_file_path, encoding="utf-8") as f:
            ai_data = json.load(f)
        if "paraules" not in ai_data:
            raise Exception("Format .ai.json invàlid")
        ai_words = ai_data["paraules"]
    except Exception:
        raise HTTPException(status_code=500, detail="No s'ha pogut llegir el fitxer .ai.json")
    
    with open(file_path, encoding="utf-8") as f:
        ranking = json.load(f)  # dict word->pos
    
    out = []
    for w in ai_words:
        wl = str(w).strip().lower()
        if not wl:
            continue
        if wl in ranking:
            out.append({"word": w, "found": True, "pos": ranking[wl]})
        else:
            out.append({"word": w, "found": False})
    
    return {"count": len(out), "words": out}

@app.get("/api/rankings/{filename}/test-words-synonyms")
def ranking_test_words_synonyms(filename: str, _: None = Depends(require_auth)):
    """Retorna els sinònims de la paraula base agrupats per línia amb la seva posició al ranking."""
    file_path = WORDS_DIR / filename
    if not file_path.exists():
        raise HTTPException(status_code=404, detail="Fitxer no trobat.")
    
    # Extreu la paraula base del nom del fitxer
    base_word = filename.replace('.json', '').lower().strip()
    
    # Obté els grups de sinònims
    synonym_groups = _get_synonyms_for_word(base_word)
    if not synonym_groups:
        return {"count": 0, "groups": []}
    
    with open(file_path, encoding="utf-8") as f:
        ranking = json.load(f)  # dict word->pos
    
    out_groups = []
    total_count = 0
    
    for group in synonym_groups:
        group_words = []
        for w in group['synonyms']:
            wl = str(w).strip().lower()
            if not wl:
                continue
            if wl in ranking:
                group_words.append({"word": w, "found": True, "pos": ranking[wl]})
            else:
                group_words.append({"word": w, "found": False})
            total_count += 1
        
        if group_words:
            out_groups.append({
                "line_num": group['line_num'],
                "original_line": group['original_line'],
                "words": group_words
            })
    
    return {"count": total_count, "groups": out_groups}

@app.get("/api/rankings/{filename}/test-words-synonyms-custom/{word}")
def ranking_test_words_synonyms_custom(filename: str, word: str, _: None = Depends(require_auth)):
    """Retorna els sinònims d'una paraula personalitzada amb la seva posició al ranking."""
    file_path = WORDS_DIR / filename
    if not file_path.exists():
        raise HTTPException(status_code=404, detail="Fitxer no trobat.")
    
    # Normalitza la paraula
    base_word = word.lower().strip()
    if not base_word:
        raise HTTPException(status_code=400, detail="Paraula buida")
    
    # Obté els grups de sinònims
    synonym_groups = _get_synonyms_for_word(base_word)
    if not synonym_groups:
        return {"count": 0, "groups": [], "base_word": base_word}
    
    with open(file_path, encoding="utf-8") as f:
        ranking = json.load(f)  # dict word->pos
    
    out_groups = []
    total_count = 0
    
    for group in synonym_groups:
        group_words = []
        for w in group['synonyms']:
            wl = str(w).strip().lower()
            if not wl:
                continue
            if wl in ranking:
                group_words.append({"word": w, "found": True, "pos": ranking[wl]})
            else:
                group_words.append({"word": w, "found": False})
            total_count += 1
        
        if group_words:
            out_groups.append({
                "line_num": group['line_num'],
                "original_line": group['original_line'],
                "words": group_words
            })
    
    return {"count": total_count, "groups": out_groups, "base_word": base_word}

@app.post("/api/test-words")
def add_test_words(req: AddTestWordsRequest, _: None = Depends(require_auth)):
    """Afegeix paraules al fitxer data/test.json (evitant duplicats). Accepta 'word' o 'words'."""
    test_path = Path(__file__).parent / "data" / "test.json"
    if test_path.exists():
        try:
            with open(test_path, encoding="utf-8") as f:
                current = json.load(f)
            if not isinstance(current, list):
                current = []
        except Exception:
            current = []
    else:
        current = []
    new_words = []
    if req.word:
        new_words.append(req.word)
    if req.words:
        new_words.extend(req.words)
    # Normalize, filter empties
    cleaned = []
    for w in new_words:
        if not isinstance(w, str):
            continue
        wl = w.strip().lower()
        if wl:
            cleaned.append(wl)
    if not cleaned:
        raise HTTPException(status_code=400, detail="Cap paraula vàlida")
    existing_set = {str(w).strip().lower() for w in current if isinstance(w, str)}
    added = []
    for w in cleaned:
        if w not in existing_set:
            current.append(w)
            existing_set.add(w)
            added.append(w)
    try:
        with open(test_path, 'w', encoding='utf-8') as f:
            json.dump(current, f, ensure_ascii=False, indent=2)
    except Exception:
        raise HTTPException(status_code=500, detail="No s'ha pogut desar test.json")
    return {"ok": True, "added": added, "total": len(current)}

@app.post("/api/test-words/delete")
def delete_test_words(req: DeleteTestWordsRequest, _: None = Depends(require_auth)):
    """Elimina paraules de data/test.json (ignora les que no existeixin)."""
    test_path = Path(__file__).parent / "data" / "test.json"
    if not test_path.exists():
        raise HTTPException(status_code=404, detail="test.json no trobat")
    try:
        with open(test_path, encoding="utf-8") as f:
            current = json.load(f)
        if not isinstance(current, list):
            raise Exception()
    except Exception:
        raise HTTPException(status_code=500, detail="Format test.json invàlid")
    target = {w.strip().lower() for w in req.words if isinstance(w, str)}
    if not target:
        raise HTTPException(status_code=400, detail="Cap paraula a eliminar")
    new_list = []
    removed = []
    for w in current:
        wl = str(w).strip().lower()
        if wl in target:
            removed.append(wl)
        else:
            new_list.append(w)
    try:
        with open(test_path, 'w', encoding='utf-8') as f:
            json.dump(new_list, f, ensure_ascii=False, indent=2)
    except Exception:
        raise HTTPException(status_code=500, detail="No s'ha pogut desar test.json")
    return {"ok": True, "removed": removed, "total": len(new_list)}

@app.delete("/api/rankings/{filename}/word/{pos}")
def delete_word(filename: str, pos: int, _: None = Depends(require_auth)):
    """Elimina una paraula de la llista pel seu rang (posició absoluta) i reindexa."""
    file_path = WORDS_DIR / filename
    if not file_path.exists():
        raise HTTPException(status_code=404, detail="Fitxer no trobat.")
    with open(file_path, encoding="utf-8") as f:
        data = json.load(f)  # dict word->pos
    items = sorted(data.items(), key=lambda x: x[1])  # [(word, pos), ...]
    total = len(items)
    if pos < 0 or pos >= total:
        raise HTTPException(status_code=400, detail="Posició fora de rang")
    deleted_word, _ = items.pop(pos)
    # Reindexa
    new_data = {w: i for i, (w, _) in enumerate(items)}
    with open(file_path, "w", encoding="utf-8") as f:
        json.dump(new_data, f, ensure_ascii=False, indent=2)
    return {"ok": True, "deleted": deleted_word, "pos": pos, "total": len(items)}

# ==================== ENDPOINTS DE COMENTARIS ====================

@app.get("/api/rankings/{filename}/comments")
def get_comments(filename: str, _: None = Depends(require_auth)):
    """Obté tots els comentaris d'un fitxer de rànquing (global i per paraula)."""
    file_path = WORDS_DIR / filename
    if not file_path.exists():
        raise HTTPException(status_code=404, detail="Fitxer no trobat")
    return _load_comments(filename)

@app.post("/api/rankings/{filename}/comments/global")
def set_global_comment(filename: str, upd: CommentUpdate, _: None = Depends(require_auth)):
    """Actualitza el comentari global del fitxer."""
    file_path = WORDS_DIR / filename
    if not file_path.exists():
        raise HTTPException(status_code=404, detail="Fitxer no trobat")
    
    comments = _load_comments(filename)
    comments["global"] = upd.comment.strip()
    
    # Si no hi ha comentaris (global buit i cap paraula), esborra el fitxer
    if not comments["global"] and not comments.get("words", {}):
        _delete_comments_file(filename)
    else:
        _save_comments(filename, comments)
    
    return {"ok": True, "comment": comments["global"]}

@app.delete("/api/rankings/{filename}/comments/global")
def delete_global_comment(filename: str, _: None = Depends(require_auth)):
    """Esborra el comentari global del fitxer."""
    file_path = WORDS_DIR / filename
    if not file_path.exists():
        raise HTTPException(status_code=404, detail="Fitxer no trobat")
    
    comments = _load_comments(filename)
    comments["global"] = ""
    
    # Si no hi ha comentaris (global buit i cap paraula), esborra el fitxer
    if not comments.get("words", {}):
        _delete_comments_file(filename)
    else:
        _save_comments(filename, comments)
    
    return {"ok": True}

@app.post("/api/rankings/{filename}/comments/word")
def set_word_comment(filename: str, upd: WordCommentUpdate, _: None = Depends(require_auth)):
    """Actualitza el comentari d'una paraula específica."""
    file_path = WORDS_DIR / filename
    if not file_path.exists():
        raise HTTPException(status_code=404, detail="Fitxer no trobat")
    
    word = upd.word.strip().lower()
    if not word:
        raise HTTPException(status_code=400, detail="Paraula buida")
    
    comments = _load_comments(filename)
    if "words" not in comments:
        comments["words"] = {}
    
    comment_text = upd.comment.strip()
    if comment_text:
        comments["words"][word] = comment_text
    else:
        # Si el comentari és buit, l'esborrem
        if word in comments["words"]:
            del comments["words"][word]
    
    # Si no hi ha comentaris (global buit i cap paraula), esborra el fitxer
    if not comments.get("global", "") and not comments["words"]:
        _delete_comments_file(filename)
    else:
        _save_comments(filename, comments)
    
    return {"ok": True, "word": word, "comment": comment_text}

@app.delete("/api/rankings/{filename}/comments/word/{word}")
def delete_word_comment(filename: str, word: str, _: None = Depends(require_auth)):
    """Esborra el comentari d'una paraula específica."""
    file_path = WORDS_DIR / filename
    if not file_path.exists():
        raise HTTPException(status_code=404, detail="Fitxer no trobat")
    
    word = word.strip().lower()
    comments = _load_comments(filename)
    
    if "words" in comments and word in comments["words"]:
        del comments["words"][word]
    
    # Si no hi ha comentaris (global buit i cap paraula), esborra el fitxer
    if not comments.get("global", "") and not comments["words"]:
        _delete_comments_file(filename)
    else:
        _save_comments(filename, comments)
    
    return {"ok": True}

# ==================== FI ENDPOINTS DE COMENTARIS ====================

if __name__ == "__main__":
    import sys
    import argparse
    parser = argparse.ArgumentParser(description="Server admin Rebuscada")
    parser.add_argument("--frontend", action="store_true", help="Serveix també el frontend d'administració (carpeta /admin) a /admin")
    args = parser.parse_args()
    try:
        import uvicorn
        if args.frontend:
            from fastapi.staticfiles import StaticFiles
            from fastapi.responses import RedirectResponse
            admin_dir = Path(__file__).parent / "admin"
            if admin_dir.exists():
                # Munta els fitxers estàtics a /admin
                app.mount("/admin", StaticFiles(directory=str(admin_dir), html=True), name="admin")
                # Redirecció arrel -> /admin/
                @app.get("/")
                def _root_redirect():
                    return RedirectResponse(url="/admin/", status_code=307)
                # Redirecció /admin -> /admin/ (sense barra final) perquè StaticFiles normalment espera la barra
                @app.middleware("http")
                async def _redirect_admin_root(request, call_next):
                    if request.url.path == "/admin":
                        return RedirectResponse(url="/admin/", status_code=307)
                    return await call_next(request)
            else:
                print("[WARN] Carpeta 'admin' no trobada; no es servirà el frontend.")
        
        # Descarrega sinònims si no existeix
        _download_synonyms()
        
        # Executa servidor
        uvicorn.run(app, host="0.0.0.0", port=ADMIN_PORT, reload=False)
    except ImportError:
        print("Uvicorn no està instal·lat. Instal·la'l amb: pip install uvicorn[standard]")
        sys.exit(1)
