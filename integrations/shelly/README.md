# Shelly

Przekaźniki i inteligentne gniazdka Shelly po sieci lokalnej (bez chmury).
Obsługuje **Gen1** (Shelly 1/1PM/Plug S…) i **Gen2/Plus** (Plus 1/Plus Plug S…) —
generacja wykrywana automatycznie.

## Parowanie

1. Wpisz **adres IP** urządzenia (aplikacja Shelly → urządzenie → Ustawienia →
   Informacje, albo lista DHCP w routerze).
2. Opcjonalnie wpisz, **co jest podpięte** (np. „wentylator") — agent będzie mówił
   „włączam wentylator" zamiast „włączam Shelly".
3. „Testuj połączenie".

## Narzędzia głosowe

- `turn_on_shelly` / `turn_off_shelly`
- `get_shelly_status` — stan + pobór mocy (W) na modelach z pomiarem

## Ograniczenia

Jedno urządzenie = jedna instalacja integracji; kanał 0 (pierwszy przekaźnik).
Multi-instancje / wybór kanału — PR-y mile widziane. Testowane bez auth
(domyślnie Shelly w LAN nie wymaga hasła; jeśli włączyłeś auth, ta wersja go nie obsługuje).
