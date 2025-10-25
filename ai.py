#!/usr/bin/env python3
"""
Script per generar llistes de paraules relacionades utilitzant l'API compatible amb OpenAI
de https://api.chatanywhere.tech.

S'utilitza el endpoint de Chat Completions i es necessita la variable d'entorn
CHATANYWHERE_API_KEY. Opcionalment, es pot definir el model amb --model o amb
la variable d'entorn CHATANYWHERE_MODEL (per defecte: gpt-3.5-turbo).

La sortida s'estandarditza igual que abans.
"""

import argparse
import json
import os
import re
import sys
from pathlib import Path
import requests
from dotenv import load_dotenv
from diccionari import Diccionari

# Carrega variables d'entorn
load_dotenv()

# Cache global per al diccionari
_diccionari_cache = None

def get_diccionari():
    """Obté el diccionari (amb cache per evitar recarregar-lo cada vegada)."""
    global _diccionari_cache
    if _diccionari_cache is None:
        print("Carregant diccionari...")
        diccionari_json = Path("data/diccionari.json")
        if diccionari_json.exists():
            try:
                _diccionari_cache = Diccionari.load(str(diccionari_json))
                print(f"✓ Diccionari carregat des de {diccionari_json}")
            except Exception as e:
                print(f"Error carregant diccionari des de {diccionari_json}: {e}")
                print("Generant nou diccionari...")
                _diccionari_cache = Diccionari.obtenir_diccionari()
                _diccionari_cache.save(str(diccionari_json))
        else:
            print("Generant diccionari...")
            _diccionari_cache = Diccionari.obtenir_diccionari()
            diccionari_json.parent.mkdir(parents=True, exist_ok=True)
            _diccionari_cache.save(str(diccionari_json))
            print(f"✓ Diccionari generat i desat a {diccionari_json}")
    return _diccionari_cache

def get_api_key():
    """Obté la clau API de ChatAnywhere (CHATANYWHERE_API_KEY)."""
    api_key = os.getenv("CHATANYWHERE_API_KEY")
    if not api_key:
        print("Error: Falta la clau de ChatAnywhere (CHATANYWHERE_API_KEY).")
        sys.exit(1)
    return api_key

def filter_and_normalize_words(words_list, diccionari):
    """Filtra les paraules per assegurar que estan al diccionari i les converteix a lemes."""
    if not words_list:
        return []
    
    filtered_words = []
    stats = {"total": len(words_list), "found": 0, "not_found": 0, "converted": 0}
    
    for word in words_list:
        if not word or not isinstance(word, str):
            continue
            
        word_clean = word.strip().lower()
        if not word_clean:
            continue
        
        # Comprova si la paraula existeix al diccionari
        forma_canonica, es_flexio = diccionari.obtenir_forma_canonica(word_clean)
        
        if forma_canonica:
            if es_flexio:
                stats["converted"] += 1
                print(f"  Convertint flexió: {word_clean} → {forma_canonica}")
            else:
                stats["found"] += 1
            
            # Evita duplicats
            if forma_canonica not in filtered_words:
                filtered_words.append(forma_canonica)
        else:
            stats["not_found"] += 1
            print(f"  ✗ Paraula no trobada al diccionari: {word_clean}")
    
    print(f"Estadístiques: {stats['total']} total, {stats['found']} trobades, "
          f"{stats['converted']} convertides, {stats['not_found']} descartades")
    print(f"Paraules finals: {len(filtered_words)}")
    
    return filtered_words

def generate_words_for_concept(concept: str, api_key: str, model: str | None = None):
    """Genera paraules relacionades amb un concepte utilitzant api.chatanywhere.tech.

    Retorna una llista de paraules o None si hi ha hagut un error.
    """
    prompt = (
        f"Genera una llista de 100 noms i verbs únics en català relacionades amb el concepte de '{concept}'. "
        "Totes les paraules han d'estar en la seva forma singular i ser una sola paraula. "
        "No s'accepten expressions ni paraules compostes, ni duplicats. "
        "El resultat ha de ser EXCLUSIVAMENT un objecte JSON amb una única clau 'paraules' i un array de les 100 paraules. "
        "Sense comentaris, sense explicacions, sense text addicional."
    )

    # ChatAnywhere (OpenAI-compatible)
    chatanywhere_model = model or os.getenv("CHATANYWHERE_MODEL") or "gpt-3.5-turbo"
    url = "https://api.chatanywhere.tech/v1/chat/completions"
    headers = {
        "Content-Type": "application/json",
        "Authorization": f"Bearer {api_key}"
    }
    payload = {
        "model": chatanywhere_model,
        "temperature": 0.7,
        "messages": [
            {"role": "system", "content": "Ets un assistent lingüístic català molt estricte amb el format."},
            {"role": "user", "content": prompt}
        ]
    }
    try:
        response = requests.post(url, json=payload, headers=headers, timeout=60)
        response.raise_for_status()
        data = response.json()
        choices = data.get("choices", [])
        if not choices:
            print(f"Error: Resposta inesperada de ChatAnywhere per '{concept}'")
            return None
        text_response = choices[0]["message"].get("content", "")
    except requests.exceptions.RequestException as e:
        print(f"Error HTTP ChatAnywhere per '{concept}': {e}")
        return None

    # Neteja i parseja JSON
    cleaned_text = re.sub(r'^```json\s*', '', text_response, flags=re.MULTILINE)
    cleaned_text = re.sub(r'^```\s*', '', cleaned_text, flags=re.MULTILINE)
    cleaned_text = re.sub(r'\s*```$', '', cleaned_text, flags=re.MULTILINE).strip()
    try:
        result = json.loads(cleaned_text)
        paraules = result.get('paraules')
        if isinstance(paraules, list):
            return paraules
        print(f"Error: JSON sense clau 'paraules' vàlida per '{concept}'")
        return None
    except json.JSONDecodeError as e:
        print(f"Error parsejant JSON per '{concept}': {e}")
        print(f"Mostra (200 caràcters): {cleaned_text[:200]}...")
        return None

def extract_word_from_filename(filename):
    """Extreu la paraula d'un nom de fitxer eliminant l'extensió .json."""
    if filename.endswith('.json'):
        return filename[:-5]  # Elimina '.json'
    return filename

def save_ai_file(word, words_list, output_dir):
    """Guarda la llista de paraules en un fitxer .ai.json."""
    output_path = output_dir / f"{word}.ai.json"
    
    try:
        with open(output_path, 'w', encoding='utf-8') as f:
            json.dump({"paraules": words_list}, f, ensure_ascii=False, indent=2)
        print(f"✓ Generat: {output_path} ({len(words_list)} paraules)")
        return True
    except IOError as e:
        print(f"Error guardant {output_path}: {e}")
        return False

def process_word(word, api_key, output_dir, model=None):
    """Processa una sola paraula."""
    print(f"\nGenerant paraules per: {word}")
    words_list = generate_words_for_concept(word, api_key, model=model)
    
    if not words_list:
        return False
    
    print(f"Rebudes {len(words_list)} paraules de ChatAnywhere")
    
    # Carrega el diccionari i filtra les paraules
    diccionari = get_diccionari()
    filtered_words = filter_and_normalize_words(words_list, diccionari)
    
    if not filtered_words:
        print(f"✗ No s'han trobat paraules vàlides per '{word}' al diccionari")
        return False
    
    return save_ai_file(word, filtered_words, output_dir)

def process_folder(folder_path, api_key, model=None):
    """Processa tots els fitxers .json d'una carpeta."""
    folder = Path(folder_path)
    
    if not folder.exists() or not folder.is_dir():
        print(f"Error: La carpeta {folder_path} no existeix o no és una carpeta")
        return False
    
    # Crea la subcarpeta /ai
    ai_folder = folder / "ai"
    ai_folder.mkdir(exist_ok=True)
    
    # Troba tots els fitxers .json
    json_files = list(folder.glob("*.json"))
    
    if not json_files:
        print(f"No s'han trobat fitxers .json a la carpeta {folder_path}")
        return False
    
    print(f"Trobats {len(json_files)} fitxers .json")
    success_count = 0
    
    for json_file in json_files:
        word = extract_word_from_filename(json_file.name)
        
        # Comprova si ja existeix el fitxer .ai.json
        ai_file_path = ai_folder / f"{word}.ai.json"
        if ai_file_path.exists():
            print(f"⚠ Fitxer ja existeix, saltant: {ai_file_path.name}")
            continue
    if process_word(word, api_key, ai_folder, model=model):
            success_count += 1
        else:
            print(f"✗ Error processant: {word}")
    
    print(f"\nProcessament completat: {success_count}/{len(json_files)} fitxers generats")
    return success_count > 0

def main():
    parser = argparse.ArgumentParser(description="Genera llistes de paraules relacionades utilitzant api.chatanywhere.tech")
    group = parser.add_mutually_exclusive_group(required=True)
    group.add_argument("--word", "-w", help="Paraula per la qual generar paraules relacionades")
    group.add_argument("--folder", "-f", help="Carpeta amb fitxers .json per processar")
    parser.add_argument("--model", help="Nom del model a utilitzar (opcional, per defecte gpt-3.5-turbo)")

    args = parser.parse_args()

    # Obté la clau API de ChatAnywhere
    api_key = get_api_key()

    if args.word:
        # Processa una sola paraula
        output_dir = Path("data/words/ai")
        output_dir.mkdir(parents=True, exist_ok=True)
        if process_word(args.word, api_key, output_dir, model=args.model):
            print("✓ Completat amb èxit")
        else:
            print("✗ Error en el processament")
            sys.exit(1)

    elif args.folder:
        # Processa una carpeta
        if process_folder(args.folder, api_key, model=args.model):
            print("✓ Processament de carpeta completat")
        else:
            print("✗ Error en el processament de la carpeta")
            sys.exit(1)

if __name__ == "__main__":
    main()
