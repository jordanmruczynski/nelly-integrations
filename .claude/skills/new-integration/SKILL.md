---
name: new-integration
description: >
  Tworzy nową integrację urządzenia dla asystentki Nelly w tym repo (nelly-integrations):
  zbiera od użytkownika opis urządzenia i dokumentację API, generuje katalog
  integrations/<id>/ (manifest.json + __init__.py [+ device.py] + README.md) zgodny
  z kontraktem frameworku, iteruje z walidatorem tools/validate.py aż przejdzie,
  i przygotowuje gałąź pod PR. Użyj, gdy użytkownik chce dodać nowe urządzenie/usługę
  ("dodaj integrację", "nowa integracja", "wsparcie dla <urządzenie>").
---

# Nowa integracja Nelly

Pracujesz w repo `nelly-integrations`. Wynik = katalog `integrations/<id>/` przechodzący
`python tools/validate.py integrations/<id>` bez FAIL.

## Krok 1 — zbierz wymagania (pytaj TYLKO o to, czego nie podano)

1. Co to za urządzenie/usługa i jak się z nim komunikuje (LAN HTTP / chmura REST / BLE / OAuth)?
2. Dokumentacja API: poproś o link lub wklejkę. Jeśli user nie ma — poszukaj w sieci
   oficjalnej dokumentacji („<device> local API", „<service> REST API").
3. Jakie operacje głosowe mają działać (włącz/wyłącz/ustaw X/odczyt stanu)?
4. Czego potrzeba do konfiguracji (IP? klucz API? token? id urządzenia?) i skąd user to bierze.

## Krok 2 — przeczytaj kontrakt i wzorce (obowiązkowo, PRZED pisaniem)

- `INTEGRATIONS.md` — kontrakt i twarde zasady (import bez configu, cfg()-only,
  get_status nie rzuca, bez load_dotenv, self-contained, <15 s, proactive-safety).
- Najbliższy wzorzec: `integrations/weather/` (zero auth), `integrations/twinkly/`
  (LAN+auth), `integrations/air_purifier/` (chmura+token+list_pick),
  `integrations/walkingpad/` (BLE/async), `integrations/spotify/` (OAuth).

## Krok 3 — wygeneruj paczkę

- `id`: krótki slug [a-z][a-z0-9_]*; katalog `integrations/<id>/`.
- `manifest.json`: pełny (config z `help` PO POLSKU — skąd wziąć wartość; pairing
  z akcją `test`; flagi `proactive` przemyślane — fizycznie niebezpieczne → false).
- `__init__.py`: TOOL_SCHEMAS (opisy EN mówiące KIEDY użyć), TOOLS, get_status,
  status_line (PL), tile, PAIR_ACTIONS (min. test), reset. Transport złożony → device.py.
- `README.md` paczki: po polsku — co robi, jak zdobyć klucze/IP, ograniczenia.
- Nazwy narzędzi: `czasownik_obiekt` np. `turn_on_<id>`, `get_<id>_status`.

## Krok 4 — pętla walidacji (nie kończ przed zielonym)

```bash
python tools/validate.py integrations/<id>
```

Każdy FAIL napraw i uruchom ponownie. WARN-y oceń: brakujące description parametrów
dopisz; wersje requirements przypnij.

## Krok 5 — wykończenie

1. Pokaż userowi krótkie podsumowanie: pliki, narzędzia, pola konfiguracji,
   jak sparuje w aplikacji.
2. Przypomnij o teście na żywym urządzeniu we własnej Nelly (skopiować katalog do
   `NEL/integrations/`, `python -m integrations.validate ...`, restart run_nelly,
   `python -m enrollment.provision_agent --apply`).
3. Zaproponuj gałąź + commit pod PR (`git checkout -b add-<id>`); NIE pushuj bez zgody.

## Zasady bezpieczeństwa skilla

- Nie wstawiaj sekretów użytkownika do plików — wszystko przez manifest config.
- Nie wykonuj kodu integracji przeciw urządzeniom użytkownika bez jego prośby;
  walidator wystarcza (działa offline).
