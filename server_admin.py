import os
from fastapi import FastAPI, HTTPException, Request, Depends
from fastapi.middleware.cors import CORSMiddleware
from typing import Dict
from pydantic import BaseModel
import json
from pathlib import Path
from dotenv import load_dotenv

load_dotenv()

WORDS_DIR = Path(__file__).parent / "data" / "words"
WORDS_DIR.mkdir(parents=True, exist_ok=True)

VALIDATIONS_PATH = Path(__file__).parent / "data" / "validacions.json"

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

class RankingFile(BaseModel):
    filename: str
    data: Dict[str, int]

class MoveRequest(BaseModel):
    from_pos: int
    to_pos: int

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

class ValidationUpdate(BaseModel):
    validated: bool

@app.post("/api/validations/{filename}")
def set_validation(filename: str, upd: ValidationUpdate, _: None = Depends(require_auth)):
    # accept only existing ranking files
    file_path = WORDS_DIR / filename
    if not file_path.exists():
        raise HTTPException(status_code=404, detail="Fitxer no trobat")
    vals = _load_validations()
    if upd.validated:
        vals[filename] = True
    else:
        # remove key if false to keep file small
        if filename in vals:
            del vals[filename]
    _save_validations(vals)
    return {"ok": True, "validated": upd.validated}

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
    file_path = WORDS_DIR / filename
    body = await request.json()
    # Si rep fragment i offset, només actualitza el tram
    if "fragment" in body and "offset" in body:
        fragment: dict = body["fragment"]
        offset: int = body["offset"]
        # Carrega l'original
        if not file_path.exists():
            raise HTTPException(status_code=404, detail="Fitxer no trobat.")
        with open(file_path, encoding="utf-8") as f:
            data = json.load(f)
        # Construeix la llista ordenada
        items = sorted(data.items(), key=lambda x: x[1])
        # Actualitza el fragment
        keys = list(fragment.keys())
        for i, k in enumerate(keys):
            items[offset + i] = (k, offset + i)
        # Reconstrueix el dict
        new_data = {k: i for i, (k, _) in enumerate(items)}
        with open(file_path, "w", encoding="utf-8") as f:
            json.dump(new_data, f, ensure_ascii=False, indent=2)
        return {"ok": True}
    # Si no, comportament antic (tot el fitxer)
    else:
        data = body
        with open(file_path, "w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False, indent=2)
        return {"ok": True}

@app.post("/api/rankings")
def create_ranking(ranking: RankingFile, _: None = Depends(require_auth)):
    file_path = WORDS_DIR / ranking.filename
    if file_path.exists():
        raise HTTPException(status_code=400, detail="Ja existeix.")
    with open(file_path, "w", encoding="utf-8") as f:
        json.dump(ranking.data, f, ensure_ascii=False, indent=2)
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

@app.post("/api/rankings/generate")
def generate_ranking(req: GenerateRequest, _: None = Depends(require_auth)):
    """Genera un fitxer de rànquing per a una paraula (similar a generate.py)."""

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
    # Carrega diccionari (si ja s'ha generat prèviament, reutilitza'l)
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
    # Carrega model fastText
    from proximitat import carregar_model_fasttext, calcular_ranking_complet
    model = carregar_model_fasttext()
    paraules = dicc.totes_les_lemes()
    ranking = calcular_ranking_complet(word, paraules, model)
    with open(file_path, "w", encoding="utf-8") as f:
        json.dump(ranking, f, ensure_ascii=False, indent=2)
    return {"ok": True, "filename": filename, "total": len(ranking)}

# Endpoint alternatiu sense conflicte amb /api/rankings/{filename}
@app.post("/api/generate")
def generate_ranking_alt(req: GenerateRequest, _: None = Depends(require_auth)):
    """Mateixa funcionalitat que /api/rankings/generate però evita conflictes de routing."""
    return generate_ranking(req)

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

if __name__ == "__main__":
    import sys
    import argparse
    parser = argparse.ArgumentParser(description="Server admin ContextCat")
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
        # Executa servidor
        uvicorn.run(app, host="0.0.0.0", port=ADMIN_PORT, reload=False)
    except ImportError:
        print("Uvicorn no està instal·lat. Instal·la'l amb: pip install uvicorn[standard]")
        sys.exit(1)
