# nelly-integrations

Oficjalny katalog integracji urządzeń dla **Nelly** — prywatnej, domowej asystentki
głosowej (Raspberry Pi + ElevenLabs Agents). Każdy katalog w `integrations/` to jedna
samoopisująca się paczka: `manifest.json` (metadane, konfiguracja, sposób parowania)
+ kod Pythona z kontraktem frameworku (narzędzia agenta, status, kafelek dashboardu).

*Official integration catalog for the Nelly voice assistant. Polish-first; PRs welcome.*

## Instalacja u siebie (użytkownik Nelly)

1. W `.env` swojej Nelly ustaw:
   ```
   MARKET_INDEX_URL=https://raw.githubusercontent.com/<OWNER>/nelly-integrations/main/index.json
   ```
2. W aplikacji mobilnej: **Ustawienia → Integracje → Sklep integracji** → *Zainstaluj*.
   Bez nowych zależności pip integracja działa od razu; z zależnościami apka poprosi
   o restart huba (przycisk — wymaga systemd, patrz `docs/nelly.service` w repo Nelly).

Instalator weryfikuje **sha256 każdego pliku** wobec `index.json` przypiętego do
konkretnego commita — podmieniona treść = odmowa instalacji.

## Dodanie własnej integracji (twórca)

W swojej kopii Nelly:

```bash
python -m integrations.scaffold moje_urzadzenie --name "Moje Urządzenie" --pairing form
# ...wypełnij TODO w integrations/moje_urzadzenie/...
python -m integrations.validate integrations/moje_urzadzenie
```

Gdy walidator przechodzi i urządzenie działa u Ciebie głosem + w apce:

1. Zrób fork tego repo, skopiuj katalog do `integrations/moje_urzadzenie/`.
2. Otwórz PR. CI uruchomi ten sam walidator (`tools/validate.py`).
3. Po review właściciela i merge'u CI przebuduje `index.json` — integracja
   pojawi się w sklepie wszystkich Nelly.

Twarde zasady (szczegóły w `INTEGRATIONS.md` — w przygotowaniu):
- import paczki MUSI działać bez konfiguracji; wartości tylko przez `cfg()`,
- `get_status()` nigdy nie rzuca — zwraca `{"reachable": false, "error": ...}`,
- zero sekretów/IP w kodzie (CI skanuje), wszystko przez `manifest.json → config`,
- opisy narzędzi zrozumiałe dla LLM; teksty dla użytkownika po polsku (`{"pl": …}`),
- narzędzia kończą się < 15 s (timeout client-tools ElevenLabs).

## Bezpieczeństwo

Integracje wykonują się z pełnymi uprawnieniami procesu Nelly na Twoim Pi.
Model zaufania v1 = review każdego PR-a przez właściciela repo + walidacja CI
+ hashe w indeksie. Czytaj kod tego, co instalujesz.
