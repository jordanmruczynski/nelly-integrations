# Jak napisać integrację dla Nelly

Integracja = jeden katalog `integrations/<id>/` z dwoma obowiązkowymi plikami:

```
integrations/twinkly/
  manifest.json    ← metadane: co to jest, jak konfigurować, jak parować (BEZ kodu)
  __init__.py      ← kontrakt w Pythonie: narzędzia agenta, status, kafelek
  device.py        ← (opcjonalnie) transport — HTTP/BLE/chmura
  domain.py        ← (opcjonalnie) logika domenowa
```

Najlepszy sposób nauki: przeczytaj `integrations/weather/` (najprostsza — zero auth)
i `integrations/twinkly/` (LAN + auth + kolory). Generator szkieletu masz w swojej
Nelly: `python -m integrations.scaffold <id> --name "..." --pairing form`.

## Kontrakt kodu (`__init__.py`)

| Eksport | Wymagany | Opis |
|---|---|---|
| `TOOL_SCHEMAS: list[dict]` | TAK | schematy narzędzi w formacie OpenAI function-calling |
| `TOOLS: dict[str, Callable]` | TAK | nazwa narzędzia → handler zwracający `dict` |
| `get_status() -> dict` | TAK | stan urządzenia; **NIGDY nie rzuca** |
| `status_line() -> str` | nie | polska linijka stanu wstrzykiwana do kontekstu LLM |
| `tile(status) -> dict` | nie | kafelek dashboardu apki: `{"value","meta","tone"}` |
| `PAIR_ACTIONS: dict[str, Callable]` | nie | akcje parowania (skan, lista urządzeń, test) |
| `OAUTH: dict` | nie | `{"build_authorize_url": fn, "exchange_code": fn}` |
| `reset() -> None` | nie | zrzuć klienta-singleton po zmianie konfiguracji |

## Twarde zasady (walidator + review je egzekwują)

1. **Import bez konfiguracji.** `import integrations.<id>` MUSI się udać na maszynie,
   która nie ma żadnego configu, sieci ani urządzenia. Żadnych połączeń, skanów,
   wątków przy imporcie — wszystko leniwie, przy pierwszym wywołaniu narzędzia.
2. **Konfiguracja tylko przez `cfg()`.**
   ```python
   from integrations.framework.config_store import cfg
   ip = cfg("twinkly", "TWINKLY_IP", env_fallback="TWINKLY_IP")
   ```
   Zero `os.getenv` rozsianych po kodzie, zero hardcodowanych IP/tokenów (CI skanuje).
   Każdy klucz musi być zadeklarowany w `manifest.json → config[]` — apka generuje
   z tego formularz.
3. **Bez `load_dotenv()`.** `.env` ładuje host (Nelly). W CI nie ma python-dotenv.
4. **`get_status()` nigdy nie rzuca.** Błąd = `{"reachable": false, "error": "..."}`.
   LLM wtedy powie „urządzenie niedostępne" zamiast się wywalić.
5. **Paczka samowystarczalna.** Importuj tylko: stdlib, swoje pliki w katalogu,
   `integrations.framework.config_store` oraz biblioteki z `requirements`.
   Nie sięgaj do innych integracji ani do modułów rdzenia Nelly.
6. **Narzędzia < 15 s.** ElevenLabs ubija client-tool po 15 s (`response_timeout_secs`).
   Daj timeouty na HTTP (5–10 s) i krótkie retry albo wcale.
7. **Opisy narzędzi po angielsku, teksty dla użytkownika po polsku.** LLM czyta
   `description` — pisz, KIEDY agent ma użyć narzędzia, nie tylko co robi. Każdy
   parametr musi mieć `type` (i najlepiej `description` — bez niego ElevenLabs
   dostaje sztuczny fallback). Etykiety/manifest: `{"pl": "...", "en": "..."}`.
8. **Bezpieczeństwo fizyczne.** Narzędzie, które rusza czymś w świecie (bieżnia,
   zamek, piekarnik), ma `"proactive": false` w manifeście i ostrzeżenie w
   description („NEVER call on inference alone…"). STOP zawsze dozwolony.
9. **Singleton + `reset()`.** Jeśli trzymasz połączenie/token, trzymaj w zmiennej
   modułowej i wyzeruj w `reset()` — apka woła go po zmianie konfiguracji.
10. **Wersjonuj.** Podbij `version` w manifeście przy każdej zmianie — od tego
    działa „Aktualizuj" w sklepie.

## manifest.json — ściąga pól

```jsonc
{
  "manifest_version": 1,
  "id": "shelly",                          // == nazwa katalogu, [a-z][a-z0-9_]*
  "name": "Shelly",
  "description": {"pl": "...", "en": "..."},
  "version": "1.0.0",
  "author": "twoj-github",
  "category": "lighting|climate|media|fitness|info|security|other",
  "icon": "bolt",                          // jedna z ikon apki (patrz niżej)
  "requirements": ["httpx>=0.27"],         // pip; instalowane przy instalacji ze sklepu
  "config": [{
    "key": "SHELLY_IP", "label": {"pl": "Adres IP"}, "type": "string",
    "required": true, "secret": false, "placeholder": "192.168.1.50",
    "env_fallback": "SHELLY_IP",           // opcjonalnie: stary klucz .env
    "help": {"pl": "Skąd wziąć tę wartość."}
  }],
  "pairing": {
    "method": "form|oauth|ble_scan|cloud_list",
    "actions": [
      {"id": "test", "label": {"pl": "Testuj połączenie"}, "kind": "test"},
      {"id": "scan", "label": {"pl": "Skanuj"}, "kind": "list_pick", "fills": "SHELLY_IP"}
    ]
  },
  "tools": [{"name": "turn_on_shelly", "proactive": true}],
  "dashboard_tile": {"icon": "bolt", "label": {"pl": "Gniazdko"}},
  "status_line": true
}
```

Typy pól config: `string | password | integer | boolean | enum` (+`choices`).
`secret: true` → wartość nigdy nie wraca przez API, w apce kropki.
Ikony: `orbit grid routines gear mic moon sunrise home film play shield bolt climate
air camera chip back close send ellipsis chevron trash cloud database snapshot
history clock arrow signal`.

## Cztery przepisy na parowanie

| Metoda | Kiedy | Przykład w repo |
|---|---|---|
| `form` | użytkownik wpisuje IP/klucz ręcznie | `twinkly` |
| `cloud_list` | token chmury → akcja `list_pick` pobiera urządzenia | `air_purifier` |
| `ble_scan` | akcja `list_pick` skanuje BLE i wypełnia adres | `walkingpad` |
| `oauth` | konto usługi; eksportuj `OAUTH`, apka prowadzi flow „wklej URL" | `spotify` |

Akcja `kind: "list_pick"` zwraca `[{"label": "...", "value": "..."}]` — apka pokazuje
listę, wybór wypełnia pole `fills`. Akcja `kind: "test"` powinna zwrócić wynik
`get_status()` (apka patrzy na `reachable`).

BLE/async? Trzymaj pętlę asyncio w wątku w tle i wystaw sync API — gotowy przepis:
`integrations/walkingpad/device.py`.

## Pętla pracy

```bash
# w Twojej kopii Nelly
python -m integrations.scaffold mojeurzadzenie --name "Moje Urządzenie" --pairing form
# ...wypełnij TODO...
python -m integrations.validate integrations/mojeurzadzenie   # aż przejdzie
python run_nelly.py                                           # test głosem + w apce
python -m enrollment.provision_agent --apply                  # agent widzi narzędzia
```

Działa? → fork tego repo → skopiuj katalog do `integrations/` → PR.
CI uruchomi `tools/validate.py` (ta sama logika). Po merge'u CI przebuduje
`index.json` i integracja pojawi się w sklepie wszystkich Nelly.

## Checklist do PR-a

- [ ] `python tools/validate.py integrations/<id>` przechodzi bez FAIL
- [ ] import bez configu, bez efektów ubocznych, bez `load_dotenv`
- [ ] zero sekretów/IP/PII w kodzie i README
- [ ] `requirements` przypięte (`pakiet>=x.y`)
- [ ] opisy narzędzi mówią LLM-owi KIEDY ich użyć; parametry mają `description`
- [ ] narzędzia fizycznie ruszające światem: `proactive: false`
- [ ] przetestowane na żywym urządzeniu (napisz w PR, na jakim)
- [ ] `version` ustawione; README.md paczki opisuje, skąd wziąć klucze/IP

Nie masz ochoty pisać ręcznie? Zobacz `AI_AUTHORING.md` — szablon, którym
wygenerujesz paczkę dowolnym dobrym modelem AI (albo skillem Claude Code z tego repo).
