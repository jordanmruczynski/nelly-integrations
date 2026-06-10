"""Pogoda przez Open-Meteo — darmowe API, bez klucza.

Domenowy wrapper jak `air_purifier.py`: zwraca zwięzły dict stanu, błędy łapie
i raportuje jako `{"reachable": False, ...}` zamiast rzucać do LLM-a.
"""
from __future__ import annotations

import time
from typing import Any

import httpx

from config import (
    WEATHER_CACHE_TTL_S,
    WEATHER_LATITUDE,
    WEATHER_LOCATION_NAME,
    WEATHER_LONGITUDE,
)

_API_URL = "https://api.open-meteo.com/v1/forecast"

# WMO weather codes → krótki polski opis (do czytania na głos).
_WMO_PL: dict[int, str] = {
    0: "bezchmurnie",
    1: "przeważnie słonecznie",
    2: "częściowe zachmurzenie",
    3: "pochmurno",
    45: "mgła",
    48: "marznąca mgła",
    51: "mżawka",
    53: "mżawka",
    55: "gęsta mżawka",
    56: "marznąca mżawka",
    57: "marznąca mżawka",
    61: "lekki deszcz",
    63: "deszcz",
    65: "ulewny deszcz",
    66: "marznący deszcz",
    67: "marznący deszcz",
    71: "lekki śnieg",
    73: "śnieg",
    75: "intensywny śnieg",
    77: "śnieg ziarnisty",
    80: "przelotny deszcz",
    81: "przelotny deszcz",
    82: "gwałtowne ulewy",
    85: "przelotny śnieg",
    86: "intensywny przelotny śnieg",
    95: "burza",
    96: "burza z gradem",
    99: "silna burza z gradem",
}

# Cache na (when) — krótkoterminowy, żeby seryjne pytania nie biły po API.
_cache: dict[str, tuple[float, dict[str, Any]]] = {}


def _describe(code: Any) -> str:
    try:
        return _WMO_PL.get(int(code), "nieokreślona pogoda")
    except (TypeError, ValueError):
        return "nieokreślona pogoda"


def _fetch() -> dict[str, Any]:
    params = {
        "latitude": WEATHER_LATITUDE,
        "longitude": WEATHER_LONGITUDE,
        "current": "temperature_2m,weather_code,wind_speed_10m",
        "daily": "weather_code,temperature_2m_max,temperature_2m_min",
        "timezone": "auto",
    }
    resp = httpx.get(_API_URL, params=params, timeout=8.0)
    resp.raise_for_status()
    return resp.json()


def get_weather(when: str = "now") -> dict[str, Any]:
    """Pogoda dla skonfigurowanej lokalizacji. `when` ∈ {'now', 'today', 'tomorrow'}."""
    when = (when or "now").lower()
    if when not in ("now", "today", "tomorrow"):
        when = "now"

    cached = _cache.get(when)
    if cached and time.time() - cached[0] < WEATHER_CACHE_TTL_S:
        return cached[1]

    try:
        data = _fetch()
    except Exception as e:
        return {"reachable": False, "location": WEATHER_LOCATION_NAME, "error": str(e)}

    out: dict[str, Any] = {"reachable": True, "location": WEATHER_LOCATION_NAME, "when": when}

    if when == "now":
        cur = data.get("current", {})
        out["description"] = _describe(cur.get("weather_code"))
        out["temp_c"] = cur.get("temperature_2m")
        out["wind_kmh"] = cur.get("wind_speed_10m")
    else:
        daily = data.get("daily", {})
        idx = 0 if when == "today" else 1
        try:
            out["description"] = _describe(daily["weather_code"][idx])
            out["temp_max_c"] = daily["temperature_2m_max"][idx]
            out["temp_min_c"] = daily["temperature_2m_min"][idx]
        except (KeyError, IndexError, TypeError) as e:
            return {"reachable": False, "location": WEATHER_LOCATION_NAME, "error": f"brak danych dla '{when}': {e}"}

    _cache[when] = (time.time(), out)
    return out


# ── Kontrakt frameworku integracji ──
# Najprostsza paczka w repo — wzorzec dla twórców nowych integracji (zero auth, zero parowania).

TOOL_SCHEMAS: list[dict[str, Any]] = [
    {
        "type": "function",
        "function": {
            "name": "get_weather",
            "description": (
                "Read current weather or the forecast for today/tomorrow at the "
                "user's configured location. Returns a short Polish description, "
                "temperature (°C) and wind."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "when": {
                        "type": "string",
                        "enum": ["now", "today", "tomorrow"],
                        "default": "now",
                    }
                },
                "required": [],
            },
        },
    },
]


def _weather(when: str = "now") -> dict[str, Any]:
    return get_weather(when)


TOOLS = {"get_weather": _weather}


def get_status() -> dict[str, Any]:
    return get_weather("now")


def tile(status: dict[str, Any]) -> dict[str, Any]:
    if not status.get("reachable"):
        return {"value": "—", "meta": "brak danych"}
    return {
        "value": f"{status.get('temp_c', '?')}°",
        "meta": str(status.get("description", "")),
    }


PAIR_ACTIONS = {"test": get_status}
