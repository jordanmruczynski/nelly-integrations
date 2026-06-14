"""Integracja: robot sprzątający Tuya (np. COBBO PRO 28 3D Ultra) — kontrakt frameworku.

device.py = transport Tuya Cloud (tinytuya.Cloud). Tu: schematy narzędzi dla LLM,
mapowanie nazwa→handler, kafelek/status_line do apki i akcje parowania (cloud_list).

Bezpieczeństwo (wzór z walkingpad): start NIE jest proaktywny — agent uruchamia
sprzątanie tylko po wyraźnej intencji użytkownika; powrót do bazy i pauza zawsze wolno.
"""
from __future__ import annotations

from typing import Any, Callable

from integrations.tuya_vacuum import device
from integrations.tuya_vacuum.device import (  # noqa: F401 — publiczne API paczki
    SUCTION_LEVELS,
    WATER_LEVELS,
    clean_rooms,
    get_status,
    list_vacuums,
)

TOOL_SCHEMAS: list[dict[str, Any]] = [
    {
        "type": "function",
        "function": {
            "name": "start_vacuum",
            "description": (
                "Start the robot vacuum cleaning the whole home (auto/smart mode). "
                "NEVER call this on inference alone — only after the user explicitly asks "
                "the robot to start. Be considerate of quiet hours (e.g. people sleeping)."
            ),
            "parameters": {"type": "object", "properties": {}, "required": []},
        },
    },
    {
        "type": "function",
        "function": {
            "name": "clean_vacuum_rooms",
            "description": (
                "Clean only specific room(s) by name (e.g. user says 'odkurz kuchnię i salon'). "
                "Pass the room names as the user said them — they are matched against the "
                "configured room list. NEVER call on inference alone — only on explicit request. "
                "If room cleaning isn't set up, the tool returns a clear error explaining how."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "rooms": {
                        "type": "array",
                        "items": {"type": "string"},
                        "description": "Room names to clean, e.g. ['kuchnia', 'salon'].",
                    }
                },
                "required": ["rooms"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "pause_vacuum",
            "description": "Pause the robot vacuum where it is. Safe to call anytime.",
            "parameters": {"type": "object", "properties": {}, "required": []},
        },
    },
    {
        "type": "function",
        "function": {
            "name": "return_vacuum_to_dock",
            "description": "Send the robot back to its charging dock. Safe to call anytime — also the way to stop cleaning.",
            "parameters": {"type": "object", "properties": {}, "required": []},
        },
    },
    {
        "type": "function",
        "function": {
            "name": "set_vacuum_suction",
            "description": "Set vacuum suction power. quiet=lowest/quietest, max=strongest.",
            "parameters": {
                "type": "object",
                "properties": {"level": {"type": "string", "enum": list(SUCTION_LEVELS)}},
                "required": ["level"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "set_vacuum_water",
            "description": "Set mopping water flow level (only on models with a mop). low/medium/high.",
            "parameters": {
                "type": "object",
                "properties": {"level": {"type": "string", "enum": list(WATER_LEVELS)}},
                "required": ["level"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "locate_vacuum",
            "description": "Make the robot play a sound so you can find it. Safe to call anytime.",
            "parameters": {"type": "object", "properties": {}, "required": []},
        },
    },
    {
        "type": "function",
        "function": {
            "name": "get_vacuum_status",
            "description": "Read robot state: what it's doing, battery %, cleaned area and time, suction/water level.",
            "parameters": {"type": "object", "properties": {}, "required": []},
        },
    },
]


def _start() -> dict[str, str]:
    device.start_clean()
    return {"ok": "robot zaczął sprzątać"}


def _clean_rooms(rooms: list[str]) -> dict[str, Any]:
    if not rooms:
        raise ValueError("Podaj przynajmniej jeden pokój do posprzątania.")
    return clean_rooms(rooms)


def _pause() -> dict[str, str]:
    device.pause()
    return {"ok": "robot wstrzymany"}


def _dock() -> dict[str, str]:
    device.return_to_dock()
    return {"ok": "robot wraca do bazy"}


def _suction(level: str) -> dict[str, str]:
    value = device.set_suction(level)
    return {"ok": f"siła ssania ustawiona ({level} → {value})"}


def _water(level: str) -> dict[str, str]:
    value = device.set_water(level)
    return {"ok": f"przepływ wody ustawiony ({level} → {value})"}


def _locate() -> dict[str, str]:
    device.locate()
    return {"ok": "robot zasygnalizował położenie"}


TOOLS: dict[str, Callable[..., dict[str, Any]]] = {
    "start_vacuum": _start,
    "clean_vacuum_rooms": _clean_rooms,
    "pause_vacuum": _pause,
    "return_vacuum_to_dock": _dock,
    "set_vacuum_suction": _suction,
    "set_vacuum_water": _water,
    "locate_vacuum": _locate,
    "get_vacuum_status": get_status,
}


def status_line() -> str:
    s = get_status()
    if not s.get("reachable"):
        return "odkurzacz Tuya: niedostępny (offline / nieskonfigurowany)"
    bat = s.get("battery")
    bat_txt = f", bateria {bat}%" if bat is not None else ""
    return f"odkurzacz Tuya: {s.get('state', 'nieznany')}{bat_txt}"


def tile(status: dict[str, Any]) -> dict[str, Any]:
    if not status.get("reachable"):
        return {"value": "Offline", "meta": "nieosiągalny"}
    bat = status.get("battery")
    cleaning = "sprząta" in str(status.get("state", "")) or "mopuje" in str(status.get("state", ""))
    return {
        "value": status.get("state", "—"),
        "meta": f"bateria {bat}%" if bat is not None else "",
        **({"tone": "accent"} if cleaning else {}),
    }


def _list_action(**_: Any) -> list[dict[str, str]]:
    """Akcja parowania (cloud_list): roboty z konta Tuya → lista do wyboru w apce."""
    return list_vacuums()


def _test_action(**_: Any) -> dict[str, Any]:
    return get_status()


PAIR_ACTIONS: dict[str, Callable[..., Any]] = {
    "list_devices": _list_action,
    "test": _test_action,
}


def reset() -> None:
    """Po zmianie configu z apki: zrzuć klienta chmury i cache specyfikacji."""
    device._cloud_client = None
    device._functions_cache.clear()
