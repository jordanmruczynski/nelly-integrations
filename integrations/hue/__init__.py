"""Integracja: Philips Hue — światła przez lokalny Hue Bridge (API v1, grupa 0 = wszystkie).

Parowanie: użytkownik wciska przycisk na mostku, akcja `create_user` woła
POST /api i dostaje klucz aplikacji (username) — apka wpisuje go do configu.
"""
from __future__ import annotations

from typing import Any, Callable

import httpx

from integrations.framework.config_store import cfg

_TIMEOUT = 6.0


def _base() -> str:
    ip = cfg("hue", "HUE_BRIDGE_IP", env_fallback="HUE_BRIDGE_IP")
    user = cfg("hue", "HUE_USERNAME", env_fallback="HUE_USERNAME")
    if not ip or not user:
        raise RuntimeError("Hue nie skonfigurowane — ustaw adres mostka i utwórz klucz (apka → Integracje → Hue)")
    return f"http://{ip}/api/{user}"


def _check(resp: httpx.Response) -> Any:
    resp.raise_for_status()
    data = resp.json()
    # Hue zwraca 200 nawet przy błędzie — błędy siedzą w liście [{"error": {...}}].
    if isinstance(data, list):
        for item in data:
            if isinstance(item, dict) and "error" in item:
                raise RuntimeError(str(item["error"].get("description", item["error"])))
    return data


def _group_action(payload: dict[str, Any]) -> None:
    _check(httpx.put(f"{_base()}/groups/0/action", json=payload, timeout=_TIMEOUT))


def turn_on() -> None:
    _group_action({"on": True})


def turn_off() -> None:
    _group_action({"on": False})


def set_brightness(percent: int) -> None:
    p = max(0, min(100, int(percent)))
    # Hue: bri 1–254; 0% traktujemy jako wyłączenie.
    if p == 0:
        turn_off()
        return
    _group_action({"on": True, "bri": max(1, round(p * 254 / 100))})


def get_status() -> dict[str, Any]:
    try:
        g = _check(httpx.get(f"{_base()}/groups/0", timeout=_TIMEOUT))
        state = g.get("state", {})
        action = g.get("action", {})
        bri = action.get("bri")
        return {
            "reachable": True,
            "power": "on" if state.get("any_on") else "off",
            "all_on": bool(state.get("all_on")),
            "brightness_percent": round(bri * 100 / 254) if isinstance(bri, (int, float)) else None,
            "lights": len(g.get("lights", []) or []),
        }
    except Exception as e:  # noqa: BLE001 — kontrakt: status nigdy nie rzuca
        return {"reachable": False, "error": str(e)}


TOOL_SCHEMAS: list[dict[str, Any]] = [
    {
        "type": "function",
        "function": {
            "name": "turn_on_hue_lights",
            "description": "Turn ON all Philips Hue lights (whole home group).",
            "parameters": {"type": "object", "properties": {}, "required": []},
        },
    },
    {
        "type": "function",
        "function": {
            "name": "turn_off_hue_lights",
            "description": "Turn OFF all Philips Hue lights (whole home group).",
            "parameters": {"type": "object", "properties": {}, "required": []},
        },
    },
    {
        "type": "function",
        "function": {
            "name": "set_hue_brightness",
            "description": "Set brightness of all Philips Hue lights (0-100). Low values (10-30) suit evenings; 0 turns lights off.",
            "parameters": {
                "type": "object",
                "properties": {
                    "percent": {
                        "type": "integer",
                        "minimum": 0,
                        "maximum": 100,
                        "description": "Brightness percent, 0-100 (0 = off).",
                    }
                },
                "required": ["percent"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "get_hue_status",
            "description": "Read Philips Hue lights state: power, brightness, number of lights.",
            "parameters": {"type": "object", "properties": {}, "required": []},
        },
    },
]


def _on() -> dict[str, str]:
    turn_on()
    return {"ok": "hue lights on"}


def _off() -> dict[str, str]:
    turn_off()
    return {"ok": "hue lights off"}


def _bri(percent: int) -> dict[str, str]:
    set_brightness(percent)
    return {"ok": f"hue brightness set to {percent}%"}


TOOLS: dict[str, Callable[..., dict[str, Any]]] = {
    "turn_on_hue_lights": _on,
    "turn_off_hue_lights": _off,
    "set_hue_brightness": _bri,
    "get_hue_status": get_status,
}


def status_line() -> str:
    s = get_status()
    if not s.get("reachable"):
        return "światła Hue: niedostępne"
    return (f"światła Hue: power={s['power']}, brightness={s.get('brightness_percent', '?')}%, "
            f"lamp={s.get('lights', '?')}")


def tile(status: dict[str, Any]) -> dict[str, Any]:
    if not status.get("reachable"):
        return {"value": "Offline", "meta": str(status.get("error", ""))[:40]}
    on = status.get("power") == "on"
    return {
        "value": "Wł." if on else "Wył.",
        "meta": f"jasność {status.get('brightness_percent', '?')}%" if on else "",
        **({"tone": "accent"} if on else {}),
    }


def _create_user() -> list[dict[str, str]]:
    """Akcja parowania: POST /api po wciśnięciu przycisku mostka → klucz aplikacji."""
    ip = cfg("hue", "HUE_BRIDGE_IP", env_fallback="HUE_BRIDGE_IP")
    if not ip:
        raise RuntimeError("Najpierw wpisz i zapisz adres IP mostka")
    data = _check(httpx.post(f"http://{ip}/api", json={"devicetype": "nelly#hub"}, timeout=_TIMEOUT))
    username = data[0]["success"]["username"]
    return [{"label": "Klucz utworzony — wybierz, by wypełnić pole", "value": username}]


PAIR_ACTIONS: dict[str, Callable[..., Any]] = {
    "create_user": _create_user,
    "test": get_status,
}


def reset() -> None:
    """Bezstanowe HTTP — nic do zrzucenia (konfiguracja czytana per request)."""
