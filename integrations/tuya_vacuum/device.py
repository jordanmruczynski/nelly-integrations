"""Robot sprzątający na platformie Tuya (np. COBBO PRO 28 3D Ultra) — sterowanie chmurą.

Transport: tinytuya.Cloud (oficjalne Tuya Cloud API) — działa zdalnie, bez zależności
od sieci lokalnej. Klient-singleton trzymany w tle (jak walkingpad), zrzucany w reset()
po zmianie configu z apki.

Roboty Tuya należą do kategorii "sd" (sweeper). Sterujemy POPRZEZ NAZWANE KODY DP,
nie numery — różne firmware'y mają różne zestawy, więc dla każdej operacji próbujemy
listy kodów-kandydatów ograniczonej do tych, które urządzenie faktycznie wspiera
(cloud.getfunctions). Dokładny zestaw potwierdzisz raz: `python -m integrations.tuya_vacuum functions <id>`.

Bezpieczeństwo (egzekwowane też w manifeście/promptcie):
- START nigdy nie dzieje się bez jednoznacznej intencji użytkownika (nie proaktywne).
- POWRÓT DO BAZY i PAUZA są zawsze dozwolone (bezpieczne, jak STOP bieżni).

Celowo BEZ load_dotenv(): paczka marketplace musi importować się bez python-dotenv;
sekrety przychodzą przez cfg(). .env to tylko fallback (ładuje go host w config.py).

CLI:
    python -m integrations.tuya_vacuum list             # roboty na koncie Tuya
    python -m integrations.tuya_vacuum status <id>      # stan + surowe kody DP
    python -m integrations.tuya_vacuum functions <id>   # wspierane kody komend (zakresy enum)
    python -m integrations.tuya_vacuum dock <id>        # wróć do bazy
    python -m integrations.tuya_vacuum locate <id>      # zlokalizuj (sygnał)
"""
from __future__ import annotations

import json
import sys
import threading
from typing import Any

import tinytuya

from integrations.framework.config_store import cfg

# Friendly poziomy → słowa kluczowe szukane w enumie konkretnego firmware'u.
# Kolejność = od najcichszego do najmocniejszego (fallback po pozycji, gdy brak trafienia).
SUCTION_LEVELS = ("quiet", "normal", "strong", "max")
WATER_LEVELS = ("low", "medium", "high")
_SUCTION_KEYWORDS = {
    "quiet": ("quiet", "gentle", "silent", "low", "eco", "soft"),
    "normal": ("normal", "standard", "auto", "middle", "mid"),
    "strong": ("strong", "high", "turbo", "power"),
    "max": ("max", "super", "boost", "ultra", "strongest"),
}
_WATER_KEYWORDS = {
    "low": ("low", "small", "less", "gentle"),
    "medium": ("middle", "medium", "mid", "normal", "standard"),
    "high": ("high", "large", "more", "max"),
}

# Kody-kandydaci per operacja (różne firmware'y Tuya "sd"). Pierwszy wspierany wygrywa.
_START_CODES = ("mode", "switch_go", "power", "switch")
_PAUSE_CODES = ("pause",)
_DOCK_CODES = ("switch_charge", "mode")  # mode -> "chargego"
_LOCATE_CODES = ("seek", "find_robot")
_SUCTION_CODES = ("suction", "fan", "mode_fan", "suction_set")
_WATER_CODES = ("cistern", "water_set", "tank", "water")

# --- Faza 2: sprzątanie pokoi ---
# Tuya ma tryb "select room" (RVC_CLEAN_MODE_SELECT_ROOM), ale format komendy wyboru
# pokoi NIE jest standaryzowany — różne marki kodują listę pokoi inaczej (JSON / lista /
# base64 / proprietarny protokół panelu). Robimy część pewną solidnie: nazwa pokoju → ID
# (config VACUUM_ROOMS) + wykrycie wspieranego kodu DP; samo ID i ewentualny kod DP
# potwierdzasz raz na swoim robocie (CLI `functions`/`status`/`rooms`).
_ROOM_MODE_VALUES = ("selectroom", "select_room", "room", "rooms", "pick_room")
_ROOM_LIST_CODES = ("room_clean", "select_room", "clean_room", "room_ids",
                    "switch_room", "room", "selectroom")


# ---------------- klient-singleton ----------------

_cloud_client: tinytuya.Cloud | None = None
_lock = threading.Lock()
_functions_cache: dict[str, dict[str, Any]] = {}  # device_id -> {code: values_dict}


def _conf() -> tuple[str, str, str]:
    region = cfg("tuya_vacuum", "TUYA_REGION", env_fallback="TUYA_REGION", default="eu")
    key = cfg("tuya_vacuum", "TUYA_ACCESS_ID", env_fallback="TUYA_ACCESS_ID")
    secret = cfg("tuya_vacuum", "TUYA_ACCESS_SECRET", env_fallback="TUYA_ACCESS_SECRET")
    if not key or not secret:
        raise RuntimeError(
            "Brak danych Tuya Cloud: ustaw TUYA_ACCESS_ID i TUYA_ACCESS_SECRET "
            "(apka → Integracje → Robot Tuya, albo .env). Weź je z projektu na iot.tuya.com."
        )
    return region, key, secret


def _device_id_default() -> str:
    return cfg("tuya_vacuum", "VACUUM_DEVICE_ID", env_fallback="VACUUM_DEVICE_ID")


def _cloud() -> tinytuya.Cloud:
    global _cloud_client
    with _lock:
        if _cloud_client is None:
            region, key, secret = _conf()
            _cloud_client = tinytuya.Cloud(
                apiRegion=region,
                apiKey=key,
                apiSecret=secret,
                apiDeviceID=_device_id_default() or None,  # pomaga getdevices() znaleźć usera
            )
        return _cloud_client


def _resolve_device(device_id: str | None) -> str:
    dev = (device_id or _device_id_default() or "").strip()
    if not dev:
        raise RuntimeError(
            "VACUUM_DEVICE_ID nie ustawione (apka → Integracje → 'Pobierz urządzenia', "
            "albo wklej Device ID z zakładki Devices w konsoli Tuya IoT)."
        )
    return dev


def _ok(resp: Any) -> Any:
    """Tuya zwraca {'success': bool, 'result': ..., 'msg': ...}. Rozpakuj albo rzuć."""
    if isinstance(resp, dict) and resp.get("success") is False:
        raise RuntimeError(f"Tuya API: {resp.get('msg') or resp}")
    if isinstance(resp, dict) and "result" in resp:
        return resp["result"]
    return resp


# ---------------- odczyt specyfikacji (kody komend) ----------------

def _functions(device_id: str) -> dict[str, Any]:
    """Mapa {code: values_dict} kodów ZAPISYWALNYCH urządzenia (z cache).

    values_dict to sparsowane "values" z Tuya (np. {'range': ['smart','chargego',...]}).
    """
    if device_id in _functions_cache:
        return _functions_cache[device_id]
    result = _ok(_cloud().getfunctions(device_id))
    out: dict[str, Any] = {}
    for fn in (result or {}).get("functions", []):
        code = fn.get("code")
        if not code:
            continue
        raw = fn.get("values")
        try:
            out[code] = json.loads(raw) if isinstance(raw, str) and raw else (raw or {})
        except (ValueError, TypeError):
            out[code] = {}
    _functions_cache[device_id] = out
    return out


def _enum_range(values: Any) -> list[str]:
    if isinstance(values, dict) and isinstance(values.get("range"), list):
        return [str(v) for v in values["range"]]
    return []


def _pick_enum(options: list[str], keywords: tuple[str, ...], fallback_index: int) -> str:
    """Z listy wartości enum wybierz tę pasującą do słów kluczowych; inaczej po pozycji."""
    for opt in options:
        low = opt.lower()
        if any(kw in low for kw in keywords):
            return opt
    if not options:
        raise RuntimeError("Urządzenie nie udostępnia tej regulacji.")
    idx = min(max(fallback_index, 0), len(options) - 1)
    return options[idx]


# ---------------- komendy ----------------

def _send(device_id: str, code: str, value: Any) -> None:
    _ok(_cloud().sendcommand(device_id, {"commands": [{"code": code, "value": value}]}))


def _first_supported(funcs: dict[str, Any], candidates: tuple[str, ...]) -> str | None:
    return next((c for c in candidates if c in funcs), None)


def start_clean(device_id: str | None = None) -> None:
    dev = _resolve_device(device_id)
    funcs = _functions(dev)
    code = _first_supported(funcs, _START_CODES)
    if code is None:
        raise RuntimeError("Robot nie udostępnia komendy startu sprzątania.")
    if code == "mode":
        opts = _enum_range(funcs["mode"])
        value = next((m for m in opts if m.lower() in ("smart", "auto", "clean", "selectroom")), None) \
            or next((m for m in opts if m.lower() not in ("chargego", "standby", "pause")), opts[0] if opts else "smart")
        _send(dev, "mode", value)
    else:  # switch_go / power / switch — boolowy start
        _send(dev, code, True)


def pause(device_id: str | None = None) -> None:
    dev = _resolve_device(device_id)
    funcs = _functions(dev)
    if "pause" in funcs:
        _send(dev, "pause", True)
        return
    if "mode" in funcs:
        opts = _enum_range(funcs["mode"])
        pv = next((m for m in opts if "pause" in m.lower() or "standby" in m.lower()), None)
        if pv:
            _send(dev, "mode", pv)
            return
    raise RuntimeError("Robot nie udostępnia pauzy.")


def return_to_dock(device_id: str | None = None) -> None:
    dev = _resolve_device(device_id)
    funcs = _functions(dev)
    if "switch_charge" in funcs:
        _send(dev, "switch_charge", True)
        return
    if "mode" in funcs:
        opts = _enum_range(funcs["mode"])
        cg = next((m for m in opts if "charge" in m.lower() or "dock" in m.lower() or "home" in m.lower()), None)
        if cg:
            _send(dev, "mode", cg)
            return
    raise RuntimeError("Robot nie udostępnia powrotu do bazy.")


def set_suction(level: str, device_id: str | None = None) -> str:
    if level not in SUCTION_LEVELS:
        raise ValueError(f"Nieznany poziom ssania '{level}'. Dozwolone: {SUCTION_LEVELS}")
    dev = _resolve_device(device_id)
    funcs = _functions(dev)
    code = _first_supported(funcs, _SUCTION_CODES)
    if code is None:
        raise RuntimeError("Robot nie udostępnia regulacji siły ssania.")
    opts = _enum_range(funcs[code])
    value = _pick_enum(opts, _SUCTION_KEYWORDS[level], SUCTION_LEVELS.index(level))
    _send(dev, code, value)
    return value


def set_water(level: str, device_id: str | None = None) -> str:
    if level not in WATER_LEVELS:
        raise ValueError(f"Nieznany poziom wody '{level}'. Dozwolone: {WATER_LEVELS}")
    dev = _resolve_device(device_id)
    funcs = _functions(dev)
    code = _first_supported(funcs, _WATER_CODES)
    if code is None:
        raise RuntimeError("Robot nie udostępnia regulacji przepływu wody (brak mopa?).")
    opts = _enum_range(funcs[code])
    value = _pick_enum(opts, _WATER_KEYWORDS[level], WATER_LEVELS.index(level))
    _send(dev, code, value)
    return value


def locate(device_id: str | None = None) -> None:
    dev = _resolve_device(device_id)
    funcs = _functions(dev)
    code = _first_supported(funcs, _LOCATE_CODES)
    if code is None:
        raise RuntimeError("Robot nie udostępnia funkcji lokalizacji.")
    _send(dev, code, True)


# ---------------- sprzątanie pokoi (Faza 2) ----------------

def rooms_map() -> dict[str, int]:
    """Mapa {nazwa_pokoju_lowercase: id} z configu VACUUM_ROOMS (JSON)."""
    raw = cfg("tuya_vacuum", "VACUUM_ROOMS", env_fallback="VACUUM_ROOMS")
    if not raw:
        return {}
    try:
        data = json.loads(raw)
    except (ValueError, TypeError) as e:
        raise RuntimeError(f"VACUUM_ROOMS to niepoprawny JSON: {e}") from None
    if not isinstance(data, dict):
        raise RuntimeError('VACUUM_ROOMS musi być obiektem JSON, np. {"kuchnia": 1, "salon": 2}.')
    return {str(name).strip().lower(): int(rid) for name, rid in data.items()}


def _resolve_room_ids(room_names: list[str]) -> list[int]:
    mapping = rooms_map()
    if not mapping:
        raise RuntimeError(
            "Brak mapy pokoi. Ustaw VACUUM_ROOMS (apka → Integracje), np. "
            '{"kuchnia": 1, "salon": 2, "sypialnia": 3}. ID pokoi znajdziesz uruchamiając '
            "sprzątanie pokoju w apce Tuya i porównując `python -m integrations.tuya_vacuum status <id>`."
        )
    ids: list[int] = []
    unknown: list[str] = []
    for name in room_names:
        key = str(name).strip().lower()
        if key in mapping:
            ids.append(mapping[key])
        else:
            unknown.append(name)
    if unknown:
        raise RuntimeError(
            f"Nieznane pokoje: {', '.join(unknown)}. Dostępne: {', '.join(sorted(mapping))}."
        )
    return ids


def _encode_room_payload(ids: list[int], spec: Any) -> Any:
    """Najczęstszy format ładunku listy pokoi to JSON-string tablicy id; dla DP typu
    'value'/pojedynczego int wysyłamy pierwsze id. Format bywa proprietarny — w razie
    czego nadpisz kodem DP w VACUUM_ROOM_DP i potwierdź `functions`."""
    if isinstance(spec, dict) and spec.get("type") in ("value", "Integer", "integer"):
        return ids[0]
    return json.dumps(ids, separators=(",", ":"))


def clean_rooms(room_names: list[str], device_id: str | None = None) -> dict[str, Any]:
    """Sprzątaj wskazane pokoje (po nazwach z VACUUM_ROOMS).

    Strategia (część proprietarna — patrz docstring modułu):
      1) jeśli `mode` ma wartość 'select room' → ustaw ją,
      2) wyślij listę ID pokoi przez kod DP z VACUUM_ROOM_DP lub wykryty kandydat.
    """
    dev = _resolve_device(device_id)
    ids = _resolve_room_ids(room_names)
    funcs = _functions(dev)

    mode_opts = _enum_range(funcs.get("mode", {}))
    sel_mode = next((m for m in mode_opts
                     if m.lower() in _ROOM_MODE_VALUES or "room" in m.lower()), None)
    if sel_mode:
        _send(dev, "mode", sel_mode)

    override = cfg("tuya_vacuum", "VACUUM_ROOM_DP", env_fallback="VACUUM_ROOM_DP")
    list_code = override or _first_supported(funcs, _ROOM_LIST_CODES)
    if list_code and list_code in funcs:
        _send(dev, list_code, _encode_room_payload(ids, funcs.get(list_code)))
        return {"ok": f"sprzątanie pokoi: {room_names}", "via": list_code, "ids": ids}
    if sel_mode:
        return {"ok": f"tryb wyboru pokoi ({sel_mode}); listę pokoi może trzeba wskazać w apce Tuya",
                "ids": ids, "warn": "nie znaleziono kodu DP na listę pokoi — ustaw VACUUM_ROOM_DP"}
    raise RuntimeError(
        "Ten robot nie udostępnia sprzątania pokoi przez chmurę Tuya (proprietarne). "
        "Sprawdź `python -m integrations.tuya_vacuum functions <id>` — jeśli jest kod na pokoje, "
        "wpisz go w VACUUM_ROOM_DP."
    )


def fetch_realtime_map(device_id: str | None = None) -> Any:
    """Link do mapy czasu rzeczywistego (udokumentowany endpoint Tuya sweeper).
    Sama mapa to binarka w proprietarnym formacie — link pomaga przy diagnostyce/dekodowaniu."""
    dev = _resolve_device(device_id)
    return _ok(_cloud().cloudrequest(f"/v1.0/users/sweepers/file/{dev}/realtime-map"))


# ---------------- status ----------------

# Czytelne etykiety PL dla typowych wartości kodu "status" Tuya "sd".
_STATE_PL = {
    "standby": "w gotowości", "sleep": "uśpiony", "paused": "wstrzymany",
    "smart": "sprząta", "smart_clean": "sprząta", "cleaning": "sprząta",
    "zone_clean": "sprząta strefę", "select_room": "sprząta pokój", "part_clean": "sprząta obszar",
    "mop_clean": "mopuje", "spot_clean": "sprząta punktowo",
    "goto_charge": "wraca do bazy", "go_charging": "wraca do bazy",
    "charging": "ładuje się", "charge_done": "naładowany", "completed": "skończył",
    "charge_maintain": "ładuje się",
}


def get_status(device_id: str | None = None) -> dict[str, Any]:
    """Zwięzły stan robota. NIGDY nie rzuca — błędy jako {"reachable": False, "error": ...}."""
    try:
        dev = _resolve_device(device_id)
        result = _ok(_cloud().getstatus(dev))
        codes = {item["code"]: item.get("value") for item in (result or []) if isinstance(item, dict) and "code" in item}

        def _first(keys: tuple[str, ...]) -> Any:
            return next((codes[k] for k in keys if k in codes), None)

        raw_state = _first(("status", "state"))
        battery = _first(("battery_percentage", "electricity_left", "battery"))
        area = _first(("clean_area", "clean_record"))
        ctime = _first(("clean_time",))
        return {
            "reachable": True,
            "state": _STATE_PL.get(str(raw_state), str(raw_state)) if raw_state is not None else "nieznany",
            "raw_state": raw_state,
            "battery": battery,
            "mode": _first(("mode",)),
            "area_m2": area,
            "time_min": ctime,
            "suction": _first(_SUCTION_CODES),
            "water": _first(_WATER_CODES),
            "codes": codes,  # surowe kody DP (diagnostyka)
        }
    except Exception as e:  # noqa: BLE001 — kontrakt: status nie rzuca
        return {"reachable": False, "error": str(e)}


def list_vacuums() -> list[dict[str, str]]:
    """Roboty (kategoria 'sd') na podpiętym koncie Tuya → [{label, value}] do wyboru w apce."""
    devices = _ok(_cloud().getdevices())
    if not isinstance(devices, list):
        raise RuntimeError(
            "Nie udało się pobrać listy urządzeń. Sprawdź ACCESS ID/SECRET, region i czy "
            "konto z apki Tuya jest podpięte (Link App Account). Możesz też wkleić Device ID ręcznie."
        )
    out: list[dict[str, str]] = []
    for d in devices:
        category = d.get("category") or d.get("productCategory") or ""
        dev_id = d.get("id") or d.get("devId") or d.get("deviceId")
        name = d.get("name") or d.get("product_name") or "(bez nazwy)"
        if not dev_id:
            continue
        is_vacuum = category == "sd" or "sweep" in str(d.get("product_name", "")).lower()
        label = f"{name}" + ("  ← robot?" if is_vacuum else f"  ({category})")
        out.append({"label": label, "value": str(dev_id)})
    # roboty na górze listy
    out.sort(key=lambda x: 0 if "robot?" in x["label"] else 1)
    return out


# ---------------- CLI ----------------

def _cli() -> None:
    if len(sys.argv) < 2:
        print("Usage: python -m integrations.tuya_vacuum "
              "{list|status <id>|functions <id>|map <id>|rooms <name...>|dock <id>|locate <id>}")
        sys.exit(1)
    cmd = sys.argv[1]
    arg = sys.argv[2] if len(sys.argv) > 2 else None
    if cmd == "list":
        for d in list_vacuums():
            print(f"  {d['value']}  {d['label']}")
    elif cmd == "status":
        print(json.dumps(get_status(arg), indent=2, ensure_ascii=False))
    elif cmd == "functions":
        print(json.dumps(_functions(_resolve_device(arg)), indent=2, ensure_ascii=False))
    elif cmd == "map":
        print(json.dumps(fetch_realtime_map(arg), indent=2, ensure_ascii=False))
    elif cmd == "rooms":
        names = sys.argv[2:]
        if not names:
            print(f"Skonfigurowane pokoje (VACUUM_ROOMS): {rooms_map() or '(brak)'}")
        else:
            print(json.dumps(clean_rooms(names), indent=2, ensure_ascii=False))
    elif cmd == "dock":
        return_to_dock(arg)
        print("Wysłano: powrót do bazy.")
    elif cmd == "locate":
        locate(arg)
        print("Wysłano: lokalizacja.")
    else:
        print(f"Unknown command: {cmd}")
        sys.exit(1)


if __name__ == "__main__":
    _cli()
