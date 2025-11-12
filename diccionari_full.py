import os
import re
import json
import sqlite3
from collections import defaultdict
from typing import Dict, Set, Tuple, Optional, List

import requests
from rapidfuzz import fuzz


class DiccionariFull:
    """
    Diccionari complet sense filtre de freqüència, pensat per a accés ràpid i missatges d'error detallats.
    
    Emmagatzemat en SQLite amb les següents taules:
    - formes: forma, forma_simplified, primary_lemma
    - lemmes: lemma, lemma_simplified, freq
    - forma_lemma: forma, lemma (relació N:M)
    - lemma_categories: lemma, category

    Útil per:
    - comprovar si una paraula és adverbi, determinant, etc.
    - mesurar si una paraula és massa poc comuna segons un llindar.
    - cerques sense accents via forma_simplified
    """

    DATA_DIR = "data"
    DB_FILE = "diccionari_full.db"

    # Fonts
    FREQ_URL = (
        "https://raw.githubusercontent.com/Softcatala/catalan-dict-tools/refs/heads/master/frequencies/"
        "frequencies-dict-lemmas.txt"
    )
    DICCIONARI_URLS = [
        (
            "lt",
            "https://raw.githubusercontent.com/Softcatala/catalan-dict-tools/master/resultats/lt/diccionari.txt",
        ),
    ]

    # Categories permeses pel joc (igual que Diccionari.es_categoria_valida -> 'NC' i 'VM')
    ALLOWED_CAT2 = {"NC", "VM"}

    # Mapeig de codis (2 lletres) a etiqueta humana (Català)
    CAT2_LABELS = {
        "NC": "un nom comú",
        "NP": "un nom propi",
        "VM": "un verb",
        "VA": "un verb auxiliar",
        "VS": "un verb ser/estar",
        "AQ": "un adjectiu",
        "RG": "un adverbi",
        "RB": "un adverbi",
        "SP": "una preposició",
        "CC": "una conjunció coordinada",
        "CS": "una conjunció subordinada",
        "DI": "un determinant",
        "DA": "un determinant",
        "PP": "un pronom",
        "PD": "un pronom",
        "Z": "un numeral",
        "I": "una interjecció",
    }

    def __init__(self, db_path: str):
        """
        Inicialitza el diccionari amb una connexió a la base de dades SQLite.
        """
        self.db_path = db_path
        self.conn = sqlite3.connect(db_path)
        self.conn.row_factory = sqlite3.Row  # Per accedir a columnes per nom

    # ------------------------------ Construcció i càrrega ------------------------------
    @staticmethod
    def _normalitzar_paraula(paraula: str) -> str:
        return paraula.lower().strip()

    @staticmethod
    def _normalitzar_lema(lema: str) -> str:
        # Elimina sufix numèric (lema1, lema2 -> lema) per unificar variants numèriques
        return re.sub(r"\d+$", "", lema.lower().strip())
    
    @staticmethod
    def _simplificar_text(text: str) -> str:
        """
        Simplifica el text eliminant accents, dièresis i convertint l·l a ll.
        Útil per cerques sense accents.
        """
        # Mapa de caràcters amb accent/dièresis a vocals simples
        mapa = str.maketrans({
            'à': 'a', 'á': 'a', 'ä': 'a',
            'è': 'e', 'é': 'e', 'ë': 'e',
            'í': 'i', 'ï': 'i',
            'ò': 'o', 'ó': 'o', 'ö': 'o',
            'ú': 'u', 'ü': 'u',
            'ç': 'c',
            '·': ''  # Punt volat (l·l -> ll)
        })
        return text.lower().translate(mapa)

    @classmethod
    def _descarregar(cls, url: str) -> str:
        r = requests.get(url)
        r.raise_for_status()
        return r.text

    @classmethod
    def _processar_diccionari_text(
        cls, contingut: str
    ) -> Tuple[Dict[str, Set[str]], Dict[str, Set[str]], Dict[str, Set[str]]]:
        """
        Retorna:
          - forma_to_lemmas_set: flexió -> {lemes base}
          - lemma_to_forms_set: lema -> {flexions}
          - lemma_categories_set: lema -> {cats2}
        No filtra per categoria; només retalla a 2 lletres i unifica lemes numerats.
        """
        forma_to_lemmas_set: Dict[str, Set[str]] = defaultdict(set)
        lemma_to_forms_set: Dict[str, Set[str]] = defaultdict(set)
        lemma_categories_set: Dict[str, Set[str]] = defaultdict(set)

        for linia in contingut.splitlines():
            linia = linia.strip()
            if not linia:
                continue
            parts = linia.split(" ")
            if len(parts) < 3:
                continue
            forma = cls._normalitzar_paraula(parts[0])
            lema_raw = parts[1]
            categoria = parts[2]

            lema = cls._normalitzar_lema(lema_raw)
            cat2 = categoria[:2]

            forma_to_lemmas_set[forma].add(lema)
            lemma_to_forms_set[lema].add(forma)
            if cat2:
                lemma_categories_set[lema].add(cat2)

        return forma_to_lemmas_set, lemma_to_forms_set, lemma_categories_set

    @classmethod
    def _obtenir_freq_lemes(cls) -> Dict[str, int]:
        txt = cls._descarregar(cls.FREQ_URL)
        out: Dict[str, int] = {}
        for linia in txt.splitlines():
            linia = linia.strip()
            if not linia:
                continue
            parts = linia.split(",")
            if len(parts) != 2:
                continue
            lema = cls._normalitzar_lema(parts[0])
            try:
                out[lema] = int(parts[1].strip())
            except ValueError:
                continue
        return out

    @classmethod
    def obtenir_diccionari_full(cls, use_cache: bool = True) -> "DiccionariFull":
        """Construeix (o carrega) el diccionari complet i el retorna."""
        os.makedirs(cls.DATA_DIR, exist_ok=True)
        db_path = os.path.join(cls.DATA_DIR, cls.DB_FILE)

        if use_cache and os.path.exists(db_path):
            return cls(db_path)

        # 1) Descarrega i processa totes les fonts de diccionari
        forma_to_lemmas_set: Dict[str, Set[str]] = defaultdict(set)
        lemma_to_forms_set: Dict[str, Set[str]] = defaultdict(set)
        lemma_categories_set: Dict[str, Set[str]] = defaultdict(set)

        for nom, url in cls.DICCIONARI_URLS:
            txt = cls._descarregar(url)
            f2l, l2f, lcats = cls._processar_diccionari_text(txt)
            # Fusiona
            for k, v in f2l.items():
                forma_to_lemmas_set[k].update(v)
            for k, v in l2f.items():
                lemma_to_forms_set[k].update(v)
            for k, v in lcats.items():
                lemma_categories_set[k].update(v)

        # 2) Freqüències per lema
        lemma_freq = cls._obtenir_freq_lemes()

        # 3) Determina lema principal per forma (freq més alta; si empat, ordre alfabètic)
        forma_primary: Dict[str, str] = {}
        for forma, lemes in forma_to_lemmas_set.items():
            if not lemes:
                continue
            best = None
            best_freq = -1
            for l in lemes:
                f = lemma_freq.get(l, 0)
                if f > best_freq or (f == best_freq and (best is None or l < best)):
                    best = l
                    best_freq = f
            if best is None:
                best = sorted(lemes)[0]
            forma_primary[forma] = best

        # 5) Crea la base de dades SQLite
        conn = sqlite3.connect(db_path)
        cursor = conn.cursor()
        
        # Crea taules
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS formes (
                forma TEXT PRIMARY KEY,
                forma_simplified TEXT NOT NULL,
                primary_lemma TEXT NOT NULL
            )
        """)
        
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS lemmes (
                lemma TEXT PRIMARY KEY,
                lemma_simplified TEXT NOT NULL,
                freq INTEGER DEFAULT 0
            )
        """)
        
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS forma_lemma (
                forma TEXT NOT NULL,
                lemma TEXT NOT NULL,
                PRIMARY KEY (forma, lemma),
                FOREIGN KEY (forma) REFERENCES formes(forma),
                FOREIGN KEY (lemma) REFERENCES lemmes(lemma)
            )
        """)
        
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS lemma_categories (
                lemma TEXT NOT NULL,
                category TEXT NOT NULL,
                PRIMARY KEY (lemma, category),
                FOREIGN KEY (lemma) REFERENCES lemmes(lemma)
            )
        """)
        
        # Inserta lemes
        for lemma in lemma_to_forms_set.keys():
            lemma_simp = cls._simplificar_text(lemma)
            freq = lemma_freq.get(lemma, 0)
            cursor.execute(
                "INSERT OR IGNORE INTO lemmes (lemma, lemma_simplified, freq) VALUES (?, ?, ?)",
                (lemma, lemma_simp, freq)
            )
        
        # Inserta formes
        for forma, lemes in forma_to_lemmas_set.items():
            forma_simp = cls._simplificar_text(forma)
            primary = forma_primary.get(forma, "")
            cursor.execute(
                "INSERT OR IGNORE INTO formes (forma, forma_simplified, primary_lemma) VALUES (?, ?, ?)",
                (forma, forma_simp, primary)
            )
            # Inserta relacions forma-lemma
            for lemma in lemes:
                cursor.execute(
                    "INSERT OR IGNORE INTO forma_lemma (forma, lemma) VALUES (?, ?)",
                    (forma, lemma)
                )
        
        # Inserta categories
        for lemma, cats in lemma_categories_set.items():
            for cat in cats:
                cursor.execute(
                    "INSERT OR IGNORE INTO lemma_categories (lemma, category) VALUES (?, ?)",
                    (lemma, cat)
                )
        
        # Crea índexs per accelerar cerques
        cursor.execute("CREATE INDEX IF NOT EXISTS idx_forma_simplified ON formes(forma_simplified)")
        cursor.execute("CREATE INDEX IF NOT EXISTS idx_lemma_simplified ON lemmes(lemma_simplified)")
        cursor.execute("CREATE INDEX IF NOT EXISTS idx_forma_lemma_forma ON forma_lemma(forma)")
        cursor.execute("CREATE INDEX IF NOT EXISTS idx_forma_lemma_lemma ON forma_lemma(lemma)")
        cursor.execute("CREATE INDEX IF NOT EXISTS idx_lemma_categories_lemma ON lemma_categories(lemma)")
        
        conn.commit()
        conn.close()

        return cls(db_path)

    def close(self) -> None:
        """Tanca la connexió a la base de dades."""
        if hasattr(self, 'conn'):
            self.conn.close()
    
    def __del__(self):
        """Assegura que la connexió es tanqui quan l'objecte es destrueix."""
        self.close()

    # ------------------------------ Consultes i validació ------------------------------
    @staticmethod
    def _score_ortografic(query_orig: str, candidat_orig: str) -> int:
        """
        Calcula una puntuació de similitud ortogràfica usant RapidFuzz.
        Simplement utilitza fuzz.ratio sobre les versions simplificades (sense accents).
        Si les versions simplificades coincideixen però les originals no, retorna puntuació perfecta
        (només difereixen en accents, que són errors molt comuns i acceptables).
        """
        q = (query_orig or "").lower()
        c = (candidat_orig or "").lower()
        
        if q == c:
            return 100
        
        # Simplificats per perdonar accents
        q_simp = DiccionariFull._simplificar_text(q)
        c_simp = DiccionariFull._simplificar_text(c)
        
        # Si només difereixen en accents, score perfecte
        if q_simp == c_simp:
            return 100
        
        # Altrament, usa RapidFuzz sobre les versions simplificades
        score = fuzz.ratio(q_simp, c_simp)
        return int(score)

    def near(self, text: str, limit: int = 10, min_score: int = 60) -> dict:
        """
        Cerca paraules properes a 'text' amb un filtrat bàsic a SQLite i puntuació determinista
        basada en penalitzacions ortogràfiques (_score_ortografic).
        - limit: màxim de resultats retornats
        - min_score: puntuació mínima (0-100) per acceptar un candidat
        Retorna dict amb camp 'query' i llista 'candidates' (word, score, freq).
        """
        q_norm = self._normalitzar_paraula(text or "")
        if not q_norm:
            return {"query": q_norm, "simplified": "", "candidates": []}
        q_simp = self._simplificar_text(q_norm)

        cursor = self.conn.cursor()

        # Primer: match exacte (sense accents) sobre forma_simplified
        cursor.execute(
            """
            SELECT f.forma,
                   COALESCE((SELECT freq FROM lemmes l WHERE l.lemma = f.primary_lemma), 0) AS freq
            FROM formes f
            WHERE f.forma_simplified = ?
            ORDER BY freq DESC
            LIMIT ?
            """,
            (q_simp, limit)
        )
        exact_matches = cursor.fetchall()
        if exact_matches:
            candidates = [
                {"word": forma, "score": 100, "freq": int(freq)}
                for forma, freq in exact_matches
            ]
            return {"query": q_norm, "simplified": q_simp, "candidates": candidates}

        # Prefiltrat SQL per longitud i primera lletra simplificada
        L = len(q_simp)
        low = max(1, L - 2)
        high = L + 2
        first = q_simp[0]
        cursor.execute(
                """
                SELECT f.forma, f.forma_simplified,
                                COALESCE((SELECT freq FROM lemmes l WHERE l.lemma = f.primary_lemma), 0) AS freq
                FROM formes f
                WHERE LENGTH(f.forma_simplified) BETWEEN ? AND ?
                    AND substr(f.forma_simplified, 1, 1) = ?
                    AND EXISTS (
                            SELECT 1 FROM lemma_categories lc
                            WHERE lc.lemma = f.primary_lemma
                                AND lc.category IN ('NC','VM')
                    )
                    AND COALESCE((SELECT freq FROM lemmes l WHERE l.lemma = f.primary_lemma), 0) >= 20
                ORDER BY ABS(LENGTH(f.forma_simplified) - ?) ASC, freq DESC
                LIMIT 1000
                """,
                (low, high, first, L)
        )
        rows = cursor.fetchall()

        candidates = []
        for row in rows:
            forma = row[0]
            forma_simp = row[1]
            freq = row[2]
            score = self._score_ortografic(q_norm, forma)
            if score < min_score:
                continue
            candidates.append({"word": forma, "score": score, "freq": int(freq)})

        # Ordena per score desc, després lexicogràfic per estabilitat
        candidates.sort(key=lambda x: (-x["score"], x["word"]))
        candidates = candidates[: max(0, int(limit))]
        return {"query": q_norm, "simplified": q_simp, "candidates": candidates}

    def info(self, paraula: str) -> dict:
        """
        Retorna informació detallada d'una paraula/flexió:
          {
            'word': str,
            'known_form': bool,
            'lemmas': [str],
            'primary_lemma': str|None,
            'is_inflection': bool|None,
            'lemma_categories': {lema: [cat2, ...]},
            'lemma_freq': {lema: int}
          }
        """
        w = self._normalitzar_paraula(paraula)
        cursor = self.conn.cursor()
        
        # Obté lemes associats a la forma
        cursor.execute("""
            SELECT fl.lemma
            FROM forma_lemma fl
            WHERE fl.forma = ?
        """, (w,))
        raw_lemes = [row[0] for row in cursor.fetchall()]
        
        # Si la paraula és també un lema, restringeix als lemes propis (només ella mateixa)
        if w in raw_lemes:
            lemes = [w]
        else:
            lemes = raw_lemes
        
        known = len(lemes) > 0
        
        # Obté lema principal
        cursor.execute("SELECT primary_lemma FROM formes WHERE forma = ?", (w,))
        row = cursor.fetchone()
        primary = row[0] if row else None
        
        is_inflection = None
        if known and primary is not None:
            is_inflection = w != primary

        # Obté categories per lema
        lcats = {}
        for l in lemes:
            cursor.execute("SELECT category FROM lemma_categories WHERE lemma = ?", (l,))
            lcats[l] = [row[0] for row in cursor.fetchall()]
        
        # Obté freqüències per lema
        lfreq = {}
        for l in lemes:
            cursor.execute("SELECT freq FROM lemmes WHERE lemma = ?", (l,))
            row = cursor.fetchone()
            lfreq[l] = row[0] if row else 0

        return {
            "word": w,
            "known_form": known,
            "lemmas": lemes,
            "primary_lemma": primary,
            "is_inflection": is_inflection,
            "lemma_categories": lcats,
            "lemma_freq": lfreq,
        }

    def _cat2_label(self, cat2: str) -> str:
        return self.CAT2_LABELS.get(cat2, f"categoria '{cat2}'")

    def reason_invalid_category(self, paraula: str) -> Optional[str]:
        """Si la paraula existeix però cap dels seus lemes té categoria permesa, retorna missatge d'error."""
        w = self._normalitzar_paraula(paraula)
        cursor = self.conn.cursor()
        
        # Obté lemes associats
        cursor.execute("SELECT lemma FROM forma_lemma WHERE forma = ?", (w,))
        lemes = {row[0] for row in cursor.fetchall()}
        
        if w in lemes:
            # només el lema propi
            lemes = {w}
        
        if not lemes:
            return None  # Desconeguda: que ho gestioni qui crida
        
        # Comprova si algun lema és permès
        for l in lemes:
            cursor.execute("SELECT category FROM lemma_categories WHERE lemma = ?", (l,))
            cats = {row[0] for row in cursor.fetchall()}
            if any(c in self.ALLOWED_CAT2 for c in cats):
                return None
        
        # No hi ha cap lema permès; construeix etiqueta predominant per feedback
        # Tria la categoria més freqüent entre els candidats per mostrar al missatge
        counter: Dict[str, int] = defaultdict(int)
        for l in lemes:
            cursor.execute("SELECT category FROM lemma_categories WHERE lemma = ?", (l,))
            for row in cursor.fetchall():
                counter[row[0]] += 1
        
        if counter:
            # primera per major nombre i, si empat, ordre alfabètic
            cat2 = sorted(counter.items(), key=lambda kv: (-kv[1], kv[0]))[0][0]
            label = self._cat2_label(cat2)
            return f"Disculpa, la paraula és {label}. Introdueix un nom o verb comú."
        # Sense categories (cas estrany)
        return "Disculpa, la paraula no és vàlida. Només es permeten noms i verbs comuns."

    def reason_too_uncommon(self, paraula: str, freq_min: int) -> Optional[str]:
        """
        Si la paraula existeix però tots els lemes candidats tenen freq < freq_min, retorna missatge.
        """
        w = self._normalitzar_paraula(paraula)
        cursor = self.conn.cursor()
        
        # Obté lemes associats
        cursor.execute("SELECT lemma FROM forma_lemma WHERE forma = ?", (w,))
        lemes = {row[0] for row in cursor.fetchall()}
        
        if w in lemes:
            lemes = {w}
        
        if not lemes:
            return None
        
        best = 0
        for l in lemes:
            cursor.execute("SELECT freq FROM lemmes WHERE lemma = ?", (l,))
            row = cursor.fetchone()
            freq = row[0] if row else 0
            best = max(best, freq)
        
        if best < freq_min:
            return "Disculpa, la paraula no és vàlida, busca'n una de més comuna."
        return None

    def explain_invalid(self, paraula: str, freq_min: int) -> Optional[str]:
        """
        Dona una explicació curta si la paraula no és acceptable pel joc, ordenant per prioritat:
        1) Categoria no permesa
        2) Freqüència massa baixa
        Retorna None si no hi ha motiu d'invalidesa (segons aquests criteris).
        """
        # Si no existeix al diccionari complet
        w = self._normalitzar_paraula(paraula)
        cursor = self.conn.cursor()
        
        cursor.execute("SELECT 1 FROM formes WHERE forma = ?", (w,))
        if not cursor.fetchone():
            return "Disculpa, aquesta paraula no està ben escrita."
        
        msg = self.reason_invalid_category(w)
        if msg:
            return msg
        msg = self.reason_too_uncommon(w, freq_min)
        if msg:
            return msg
        return None

if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser(description="Genera/consulta el diccionari complet sense filtre")
    parser.add_argument("--rebuild", action="store_true", help="Força reconstrucció i desat a data/diccionari_full.pkl")
    parser.add_argument("--near", type=str, default=None, help="Cerca paraules properes a un text (fuzzy)")
    parser.add_argument("--near-limit", type=int, default=50, help="Nombre màxim de suggeriments per --near")
    parser.add_argument("--near-min-score", type=int, default=60, help="Puntuació mínima (0-100) per acceptar un suggeriment")
    parser.add_argument("--word", type=str, default=None, help="Consulta info d'una paraula")
    parser.add_argument("--freq-min", type=int, default=20, help="Llindar de freqüència per comprovar 'massa poc comuna'")
    args = parser.parse_args()

    if args.rebuild:
        d = DiccionariFull.obtenir_diccionari_full(use_cache=False)
        print(f"Generat i desat: {os.path.join(DiccionariFull.DATA_DIR, DiccionariFull.DB_FILE)}")
    else:
        # Carrega si existeix; si no, construeix
        db_path = os.path.join(DiccionariFull.DATA_DIR, DiccionariFull.DB_FILE)
        if os.path.exists(db_path):
            d = DiccionariFull(db_path)
        else:
            d = DiccionariFull.obtenir_diccionari_full(use_cache=False)

    if args.near:
        res = d.near(args.near, limit=args.near_limit, min_score=args.near_min_score)
        print(json.dumps(res, ensure_ascii=False, indent=2))
    elif args.word:
        info = d.info(args.word)
        print(json.dumps(info, ensure_ascii=False, indent=2))
        reason = d.explain_invalid(args.word, args.freq_min)
        if reason:
            print("reason:", reason)
    
    # Tanca la connexió
    d.close()
