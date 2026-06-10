"""Integracja: Govee — LED-y przez chmurowe Govee Developer API (v1).

Konfiguracja: klucz API + urządzenie w formacie "deviceId|model" (jedno pole,
wypełniane akcją parowania `list_devices` — API wymaga obu wartości w każdym wywołaniu).
Uwaga na limity API Govee (per minutę/dzień) — bez pętli odpytywania.
"""
from __future__ import annotations

from typing import Any, Callable

import httpx

from integrations.framework.config_store import cfg

_BASE = "https://developer-api.govee.com/v1"
_TIMEOUT = 8.0


def _key() -> str:
    key = cfg("govee", "GOVEE_API_KEY", env_fallback="GOVEE_API_KEY")
    if not key:
        raise RuntimeError("Govee nie skonfigurowane — wpisz klucz API (apka → Integracje → Govee)")
    return key


def _device() -> tuple[str, str]:
    raw = cfg("govee", "GOVEE_DEVICE", env_fallback="GOVEE_DEVICE")
    if not raw or "|" not in raw:
        raise RuntimeError("Wybierz urządzenie Govee (akcja 'Pobierz urządzenia' w apce)")
    device, model = raw.split("|", 1)
    return device.strip(), model.strip()


def _headers() -> dict[str, str]:
    return {"Govee-API-Key": _key()}


def _control(cmd_name: str, value: Any) -> None:
    device, model = _device()
    r = httpx.put(
        f"{_BASE}/devices/control",
        headers=_headers(),
        json={"device": device, "model": model, "cmd": {"name": cmd_name, "value": value}},
        timeout=_TIMEOUT,
    )
    r.raise_for_status()
    data = r.json()
    if data.get("code") != 200:
        raise RuntimeError(str(data.get("message", data)))


def turn_on() -> None:
    _control("turn", "on")


def turn_off() -> None:
    _control("turn", "off")


def set_brightness(percent: int) -> None:
    _control("brightness", max(0, min(100, int(percent))))


def get_status() -> dict[str, Any]:
    try:
        device, model = _device()
        r = httpx.get(f"{_BASE}/devices/state", headers=_headers(),
                      params={"device": device, "model": model}, timeout=_TIMEOUT)
        r.raise_for_status()
        props = (r.json().get("data") or {}).get("properties") or []
        flat: dict[str, Any] = {}
        for p in props:
            if isinstance(p, dict):
                flat.update(p)
        return {
            "reachable": True,
            "online": flat.get("online", True),
            "power": str(flat.get("powerState", "unknown")),
            "brightness_percent": flat.get("brightness"),
            "model": model,
        }
    except Exception as e:  # noqa: BLE001 — kontrakt: status nigdy nie rzuca
        return {"reachable": False, "error": str(e)}


TOOL_SCHEMAS: list[dict[str, Any]] = [
    {
        "type": "function",
        "function": {
            "name": "turn_on_govee",
            "description": "Turn ON the Govee LED light/strip.",
            "parameters": {"type": "object", "properties": {}, "required": []},
        },
    },
    {
        "type": "function",
        "function": {
            "name": "turn_off_govee",
            "description": "Turn OFF the Govee LED light/strip.",
            "parameters": {"type": "object", "properties": {}, "required": []},
        },
    },
    {
        "type": "function",
        "function": {
            "name": "set_govee_brightness",
            "description": "Set Govee LED brightness (0-100). Low values (10-30) suit evenings.",
            "parameters": {
                "type": "object",
                "properties": {
                    "percent": {
                        "type": "integer",
                        "minimum": 0,
                        "maximum": 100,
                        "description": "Brightness percent, 0-100.",
                    }
                },
                "required": ["percent"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "get_govee_status",
            "description": "Read Govee LED state: power, brightness, online.",
            "parameters": {"type": "object", "properties": {}, "required": []},
        },
    },
]


def _on() -> dict[str, str]:
    turn_on()
    return {"ok": "govee on"}


def _off() -> dict[str, str]:
    turn_off()
    return {"ok": "govee off"}


def _bri(percent: int) -> dict[str, str]:
    set_brightness(percent)
    return {"ok": f"govee brightness {percent}%"}


TOOLS: dict[str, Callable[..., dict[str, Any]]] = {
    "turn_on_govee": _on,
    "turn_off_govee": _off,
    "set_govee_brightness": _bri,
    "get_govee_status": get_status,
}


def status_line() -> str:
    s = get_status()
    if not s.get("reachable"):
        return "LED Govee: niedostępne"
    if not s.get("online", True):
        return "LED Govee: offline (sprawdź zasilanie/Wi-Fi taśmy)"
    return f"LED Govee: power={s['power']}, brightness={s.get('brightness_percent', '?')}%"


def tile(status: dict[str, Any]) -> dict[str, Any]:
    if not status.get("reachable") or not status.get("online", True):
        return {"value": "Offline", "meta": ""}
    on = status.get("power") == "on"
    return {
        "value": "Wł." if on else "Wył.",
        "meta": f"jasność {status.get('brightness_percent', '?')}%" if on else "",
        **({"tone": "accent"} if on else {}),
    }


def _list_devices() -> list[dict[str, str]]:
    """Akcja parowania: lista urządzeń konta → wybór wypełnia GOVEE_DEVICE ("id|model")."""
    r = httpx.get(f"{_BASE}/devices", headers=_headers(), timeout=_TIMEOUT)
    r.raise_for_status()
    devices = (r.json().get("data") or {}).get("devices") or []
    out = []
    for d in devices:
        name = d.get("deviceName") or d.get("model") or "(bez nazwy)"
        out.append({"label": f"{name} ({d.get('model', '?')})",
                    "value": f"{d.get('device')}|{d.get('model')}"})
    return out


PAIR_ACTIONS: dict[str, Callable[..., Any]] = {
    "list_devices": _list_devices,
    "test": get_status,
}


def reset() -> None:
    """Bezstanowe HTTP — konfiguracja czytana per request."""
