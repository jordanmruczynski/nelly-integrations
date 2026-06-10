# Philips Hue

Steruje wszystkimi światłami Hue naraz (grupa 0) przez mostek w sieci lokalnej —
bez chmury, bez konta.

## Parowanie

1. W aplikacji Nelly wpisz **adres IP mostka** (aplikacja Hue → Ustawienia →
   Moje mostki → ikona „i") i zapisz.
2. Wciśnij **okrągły przycisk na mostku**.
3. W ciągu 30 sekund dotknij **„Utwórz klucz"** — pole klucza wypełni się samo. Zapisz.
4. „Testuj połączenie" powinno pokazać zielono.

## Narzędzia głosowe

- „włącz/wyłącz światła" → `turn_on_hue_lights` / `turn_off_hue_lights`
- „przyciemnij światła do 20%" → `set_hue_brightness`
- stan (zasilanie, jasność, liczba lamp) → `get_hue_status`

## Ograniczenia

Wersja 1.0 steruje całością (grupa 0). Sterowanie pokojami/scenami — PR-y mile widziane.
