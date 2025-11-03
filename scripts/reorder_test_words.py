import json
from pathlib import Path

FILE = Path(__file__).resolve().parents[1] / 'data' / 'test.json'
PREFIX = [
    'casa','aigua','cotxe','llum','gos','porta','taula','ordinador','llibre','mà','ull','terra','cel','foc','vent','pluja','sol','lluna','estrella','menjar','pa','vi','peix','arbre','flor','herba','pedra','muntanya','mar','riu','barca','amic','família','escola','treball','diners','ciutat','poble','camí','pont','carretera','avió','tren','vaixell','rellotge','joc','música','cant','somni','idea','temps','vida','mort'
]


def main():
    words = json.loads(FILE.read_text(encoding='utf-8'))
    seen = set()
    # Build starting ordered list, adding missing words from prefix
    ordered = []
    for w in PREFIX:
        if w not in seen:
            ordered.append(w)
            seen.add(w)
    # Append remaining existing words preserving order, skipping those already in prefix
    for w in words:
        if w not in seen:
            ordered.append(w)
            seen.add(w)
    # Write back
    FILE.write_text(json.dumps(ordered, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')
    print(f'Wrote {len(ordered)} unique words (was {len(words)})')

if __name__ == '__main__':
    main()
