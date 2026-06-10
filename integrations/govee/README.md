# Govee

Taśmy i lampy LED Govee przez oficjalne **Govee Developer API** (chmura).

## Parowanie

1. Zdobądź klucz API: aplikacja **Govee Home** → profil → ⚙ → **Apply for API Key**
   (przychodzi mailem, zwykle w kilka minut).
2. W aplikacji Nelly wklej klucz i **zapisz**.
3. Dotknij **„Pobierz urządzenia"** i wybierz swoją taśmę/lampę — pole urządzenia
   wypełni się samo (format `id|model`, bo API Govee wymaga obu). Zapisz.
4. „Testuj połączenie".

## Narzędzia głosowe

- `turn_on_govee` / `turn_off_govee`
- `set_govee_brightness` (0–100)
- `get_govee_status`

## Ograniczenia

Jedno urządzenie na instalację. API Govee ma limity zapytań (na minutę/dzień) —
integracja nie odpytuje w pętli, ale przy bardzo częstym sterowaniu możesz dostać 429.
Kolory — PR-y mile widziane (`cmd: color` w tym samym API).
