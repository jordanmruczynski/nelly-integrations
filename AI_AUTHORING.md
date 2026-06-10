# Wygeneruj integrację AI-em (dla nietechnicznych i leniwych)

Nie musisz umieć programować, żeby dodać urządzenie do Nelly. Potrzebujesz:
1. dokumentacji API swojego urządzenia (link albo skopiowany tekst — często wystarczy
   wygooglować „<urządzenie> local API" / „<usługa> REST API docs"),
2. dostępu do dobrego modelu AI (Claude, ChatGPT…) albo Claude Code
   (wtedy użyj skilla `/new-integration` z tego repo — zrobi wszystko sam).

## Szablon prompta (skopiuj całość, uzupełnij dwa miejsca)

```text
Napisz integrację urządzenia dla asystentki głosowej Nelly. Integracja to katalog
integrations/<id>/ z plikami manifest.json i __init__.py (opcjonalnie device.py).

KONTRAKT __init__.py (wszystkie eksporty na poziomie modułu):
- TOOL_SCHEMAS: list[dict] — schematy narzędzi w formacie OpenAI function-calling
  ({"type":"function","function":{"name","description","parameters":{...}}}).
  Opisy po ANGIELSKU, pisz kiedy agent ma użyć narzędzia. Każdy parametr ma "type"
  i "description".
- TOOLS: dict[str, Callable] — nazwa → handler; handler zwraca dict
  (np. {"ok": "..."} albo wynik stanu); argumenty handlera == properties schematu.
- get_status() -> dict — NIGDY nie rzuca; błąd = {"reachable": False, "error": str};
  sukces zawiera "reachable": True i pola stanu.
- status_line() -> str — krótka POLSKA linijka stanu dla LLM.
- tile(status: dict) -> dict — {"value": str, "meta": str, opcjonalnie "tone":
  "ok"|"accent"|"warn"} — kafelek w aplikacji.
- PAIR_ACTIONS: dict[str, Callable] — minimum {"test": get_status}; akcje typu
  skan/lista zwracają [{"label": str, "value": str}].
- reset() -> None — wyzeruj singleton klienta/tokenu.

ZASADY TWARDE:
- import modułu MUSI działać bez konfiguracji, sieci i urządzenia (zero side effects)
- konfigurację czytaj WYŁĄCZNIE przez:
  from integrations.framework.config_store import cfg
  wartość = cfg("<id>", "KLUCZ")    # zwraca str, "" gdy brak
- ZERO load_dotenv, ZERO os.getenv, ZERO hardcodowanych IP/tokenów
- jedyne importy: stdlib, httpx, własne pliki paczki, integrations.framework.config_store
  (+ biblioteki, które zadeklarujesz w manifest.json "requirements")
- każde wywołanie sieciowe z timeoutem ≤ 8 s; narzędzie musi skończyć < 15 s
- mutacje stanu rzucają wyjątek z POLSKIM komunikatem przy braku configu;
  get_status zamiast rzucać zwraca {"reachable": False, ...}
- narzędzia fizycznie niebezpieczne (silniki, zamki, grzanie): w manifeście
  "proactive": false i ostrzeżenie w description

MANIFEST.JSON (metadane bez kodu):
{"manifest_version":1,"id":"<id>","name":"...","description":{"pl":"...","en":"..."},
 "version":"1.0.0","author":"<twoj-nick>","category":"lighting|climate|media|fitness|info|security|other",
 "icon":"<jedna z: orbit grid routines gear mic moon sunrise home film play shield bolt
 climate air camera chip cloud database snapshot history clock arrow signal>",
 "requirements":["httpx>=0.27"],
 "config":[{"key":"...","label":{"pl":"..."},"type":"string|password|integer|boolean|enum",
   "required":true,"secret":false,"placeholder":"...","help":{"pl":"skąd wziąć wartość"}}],
 "pairing":{"method":"form|oauth|ble_scan|cloud_list","actions":[
   {"id":"test","label":{"pl":"Testuj połączenie"},"kind":"test"}]},
 "tools":[{"name":"...","proactive":true}],
 "dashboard_tile":{"icon":"...","label":{"pl":"..."}},
 "status_line":true}
Nazwy w manifest.tools MUSZĄ być identyczne z TOOL_SCHEMAS i kluczami TOOLS.

WZORZEC (przykład minimalnej integracji — pogoda):
<<tu wklej zawartość integrations/weather/__init__.py i manifest.json z tego repo>>

MOJE URZĄDZENIE: <<opisz: nazwa, jak się z nim gadasz (LAN/chmura/BLE), co ma robić>>

DOKUMENTACJA API URZĄDZENIA:
<<wklej dokumentację / linki / przykłady requestów>>

Wygeneruj: manifest.json, __init__.py (i device.py jeśli transport jest złożony),
README.md (po polsku: co robi, skąd wziąć klucze/IP). Potem podam Ci wynik
walidatora — poprawiaj, aż przejdzie.
```

## Pętla z walidatorem

Po wygenerowaniu plików zapisz je w swojej Nelly jako `integrations/<id>/…` i odpal:

```bash
python -m integrations.validate integrations/<id>
```

Każdy `FAIL` wklej z powrotem do AI z prośbą „popraw". Powtarzaj, aż zobaczysz `OK`.
Potem przetestuj na żywym urządzeniu (`python run_nelly.py` + aplikacja), a na koniec
otwórz PR do tego repo — instrukcja w `INTEGRATIONS.md`.

## Masz Claude Code?

Sklonuj to repo i odpal w nim skill: `/new-integration`. Poprowadzi Cię przez
pytania o urządzenie, sam wygeneruje paczkę, sam uruchomi walidator i sam poprawi
błędy. Definicja: `.claude/skills/new-integration/SKILL.md`.
