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

if __name__ == "__main__":
    import sys
    try:
        import uvicorn
        uvicorn.run("server_admin:app", host="0.0.0.0", port=ADMIN_PORT, reload=False)
    except ImportError:
        print("Uvicorn no està instal·lat. Instal·la'l amb: pip install uvicorn[standard]")
        sys.exit(1)
