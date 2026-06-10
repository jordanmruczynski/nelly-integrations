"""Integracja Twinkly — światełka LED po LAN (kontrakt frameworku integracji).

device.py = transport (HTTP challenge-response), domain.py = polskie kolory/stan.
Nazwy narzędzi historycznie `*_leds` (tak zna je agent) — NIE zmieniać.
"""
from __future__ import annotations

from typing import Any, Callable

from integrations.twinkly import device
from integrations.twinkly.domain import (  # noqa: F401 — publiczne API paczki
    COLORS,
    color_names,
    get_status,
    set_brightness,
    set_color,
    turn_off,
    turn_on,
)

TOOL_SCHEMAS: list[dict[str, Any]] = [
    {
        "type": "function",
        "function": {
            "name": "turn_on_leds",
            "description": (
                "Turn the Twinkly LED lights ON. Restores the last saved movie/animation "
                "if available; otherwise shows warm white."
            ),
            "parameters": {"type": "object", "properties": {}, "required": []},
        },
    },
    {
        "type": "function",
        "function": {
            "name": "turn_off_leds",
            "description": "Turn the Twinkly LED lights OFF.",
            "parameters": {"type": "object", "properties": {}, "required": []},
        },
    },
    {
        "type": "function",
        "function": {
            "name": "set_leds_color",
            "description": (
                "Set a solid color on the Twinkly LEDs. Switches to 'color' mode. "
                "Use Polish color names."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "color": {
                        "type": "string",
                        "enum": color_names(),
                    }
                },
                "required": ["color"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "set_leds_brightness",
            "description": "Set LED brightness (0–100). Use lower values (10–30) for evening/sleep contexts.",
            "parameters": {
                "type": "object",
                "properties": {
                    "percent": {
                        "type": "integer",
                        "minimum": 0,
                        "maximum": 100,
                    }
                },
                "required": ["percent"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "get_leds_status",
            "description": "Read power, mode, and brightness of the Twinkly LEDs.",
            "parameters": {"type": "object", "properties": {}, "required": []},
        },
    },
]


def _leds_on() -> dict[str, str]:
    turn_on()
    return {"ok": "leds on"}


def _leds_off() -> dict[str, str]:
    turn_off()
    return {"ok": "leds off"}


def _leds_color(color: str) -> dict[str, str]:
    set_color(color)
    return {"ok": f"leds color set to {color}"}


def _leds_brightness(percent: int) -> dict[str, str]:
    set_brightness(percent)
    return {"ok": f"leds brightness set to {percent}"}


def _leds_status() -> dict[str, Any]:
    return get_status()


TOOLS: dict[str, Callable[..., dict[str, Any]]] = {
    "turn_on_leds": _leds_on,
    "turn_off_leds": _leds_off,
    "set_leds_color": _leds_color,
    "set_leds_brightness": _leds_brightness,
    "get_leds_status": _leds_status,
}


def status_line() -> str:
    try:
        s = get_status()
        return f"światełka Twinkly: power={s['power']}, mode={s['mode']}, brightness={s['brightness_percent']}%"
    except Exception as e:
        return f"światełka Twinkly: (błąd odczytu: {e})"


def tile(status: dict[str, Any]) -> dict[str, Any]:
    if status.get("error"):
        return {"value": "Offline", "meta": "brak połączenia"}
    on = status.get("power") == "on"
    return {
        "value": "Wł." if on else "Wył.",
        "meta": f"jasność {status.get('brightness_percent', '?')}%" if on else "",
        **({"tone": "accent"} if on else {}),
    }


PAIR_ACTIONS: dict[str, Callable[..., Any]] = {
    "test": lambda: get_status(),
}


def reset() -> None:
    """Po zmianie IP zrzuć klienta — następne wywołanie zbuduje go z nowym configiem."""
    device._singleton = None
