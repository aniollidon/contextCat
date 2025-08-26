import os
from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from typing import Dict
from pydantic import BaseModel
import json
from pathlib import Path
from dotenv import load_dotenv

load_dotenv()

WORDS_DIR = Path(__file__).parent / "data" / "words"
WORDS_DIR.mkdir(parents=True, exist_ok=True)

ADMIN_PORT = int(os.getenv("ADMIN_PORT", 5001))

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

@app.get("/api/rankings")
def list_rankings():
    files = [f.name for f in WORDS_DIR.glob("*.json")]
    return files

from fastapi import Query

@app.get("/api/rankings/{filename}")
def read_ranking(filename: str, offset: int = Query(0, ge=0), limit: int = Query(100, ge=1)):
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
def delete_ranking(filename: str):
    file_path = WORDS_DIR / filename
    if not file_path.exists():
        raise HTTPException(status_code=404, detail="No s'ha pogut esborrar.")
    file_path.unlink()
    return {"ok": True}


from fastapi import Request

@app.post("/api/rankings/{filename}")
async def save_ranking(filename: str, request: Request):
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
def create_ranking(ranking: RankingFile):
    file_path = WORDS_DIR / ranking.filename
    if file_path.exists():
        raise HTTPException(status_code=400, detail="Ja existeix.")
    with open(file_path, "w", encoding="utf-8") as f:
        json.dump(ranking.data, f, ensure_ascii=False, indent=2)
    return {"ok": True}

@app.post("/api/rankings/{filename}/move")
def move_word(filename: str, move: MoveRequest):
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
def generate_ranking(req: GenerateRequest):
    """Genera un fitxer de rànquing per a una paraula (similar a generate.py)."""
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
def generate_ranking_alt(req: GenerateRequest):
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
def generate_random(req: RandomGenerateRequest):
    """Genera diversos fitxers de rànquing per paraules aleatòries."""
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
def find_word(filename: str, word: str):
    file_path = WORDS_DIR / filename
    if not file_path.exists():
        raise HTTPException(status_code=404, detail="Fitxer no trobat.")
    with open(file_path, encoding="utf-8") as f:
        data = json.load(f)  # dict word->pos
    w = word.strip().lower()
    if w in data:
        return {"found": True, "pos": data[w]}
    return {"found": False}

if __name__ == "__main__":
    import sys
    try:
        import uvicorn
        uvicorn.run("server_admin:app", host="0.0.0.0", port=ADMIN_PORT, reload=False)
    except ImportError:
        print("Uvicorn no està instal·lat. Instal·la'l amb: pip install uvicorn[standard]")
        sys.exit(1)
