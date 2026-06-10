"""Integracja: bieżnia Kingsmith WalkingPad X21 (BLE) — kontrakt frameworku.

device.py = transport BLE (ph4-walkingpad, asyncio w wątku w tle).
Bezpieczeństwo: start/set_speed NIE są proaktywne (manifest); stop zawsze dozwolony.
"""
from __future__ import annotations

from typing import Any, Callable

from integrations.walkingpad import device
from integrations.walkingpad.device import (  # noqa: F401 — publiczne API paczki
    MAX_SPEED_KMH,
    MIN_SPEED_KMH,
    get_status,
    scan,
    set_speed,
    start,
    stop,
)

TOOL_SCHEMAS: list[dict[str, Any]] = [
    {
        "type": "function",
        "function": {
            "name": "start_walkingpad",
            "description": (
                "Start the treadmill belt at a given speed (km/h). "
                "NEVER call this on inference alone — only after the user has explicitly "
                "confirmed they want the pad started. Default speed is a gentle walk (2.0)."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "speed_kmh": {
                        "type": "number",
                        "minimum": 0.5,
                        "maximum": 6.0,
                        "default": 2.0,
                    }
                },
                "required": [],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "stop_walkingpad",
            "description": "Stop the treadmill belt immediately. Safety-critical — always allowed, no confirmation needed.",
            "parameters": {"type": "object", "properties": {}, "required": []},
        },
    },
    {
        "type": "function",
        "function": {
            "name": "set_walkingpad_speed",
            "description": "Change treadmill speed while it is running. 0.5–6.0 km/h. Only while belt is already moving.",
            "parameters": {
                "type": "object",
                "properties": {
                    "speed_kmh": {
                        "type": "number",
                        "minimum": 0.5,
                        "maximum": 6.0,
                    }
                },
                "required": ["speed_kmh"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "get_walkingpad_status",
            "description": "Read treadmill state: running, speed (km/h), distance (km), time (s), steps.",
            "parameters": {"type": "object", "properties": {}, "required": []},
        },
    },
]


def _pad_start(speed_kmh: float = 2.0) -> dict[str, str]:
    start(speed_kmh)
    return {"ok": f"walkingpad started at {speed_kmh} km/h"}


def _pad_stop() -> dict[str, str]:
    stop()
    return {"ok": "walkingpad stopped"}


def _pad_speed(speed_kmh: float) -> dict[str, str]:
    set_speed(speed_kmh)
    return {"ok": f"walkingpad speed set to {speed_kmh} km/h"}


def _pad_status() -> dict[str, Any]:
    return get_status()


TOOLS: dict[str, Callable[..., dict[str, Any]]] = {
    "start_walkingpad": _pad_start,
    "stop_walkingpad": _pad_stop,
    "set_walkingpad_speed": _pad_speed,
    "get_walkingpad_status": _pad_status,
}


def status_line() -> str:
    s = get_status()
    if not s.get("reachable"):
        return "bieżnia WalkingPad: niedostępna (wyłączona / nie podłączona)"
    if s.get("power") == "unknown":
        return "bieżnia WalkingPad: podłączona, stan nieznany"
    return (
        f"bieżnia WalkingPad: power={s['power']}, "
        f"speed={s['speed_kmh']}km/h, "
        f"dist={s['distance_km']}km, "
        f"steps={s['steps']}"
    )


def tile(status: dict[str, Any]) -> dict[str, Any]:
    if not status.get("reachable"):
        return {"value": "Offline", "meta": "wyłączona / poza zasięgiem"}
    running = status.get("power") == "on"
    return {
        "value": f"{status.get('speed_kmh', 0)} km/h" if running else "Stoi",
        "meta": f"{status.get('steps', 0)} kroków" if running else "",
        **({"tone": "accent"} if running else {}),
    }


def _scan_action(seconds: float = 6.0) -> list[dict[str, str]]:
    """Akcja parowania: skan BLE → lista {label, value} do wyboru w apce."""
    out = []
    for d in scan(seconds):
        name = d["name"]
        hint = "  ← bieżnia?" if ("walkingpad" in name.lower() or "ks-" in name.lower()) else ""
        out.append({"label": f"{name}{hint}", "value": d["address"]})
    return out


PAIR_ACTIONS: dict[str, Callable[..., Any]] = {
    "scan": _scan_action,
    "test": lambda: get_status(),
}


def reset() -> None:
    """Po zmianie adresu BLE wymuś nowe połączenie przy następnej komendzie."""
    device._ctrl = None
    device._connected = False
    device._unreachable_until = 0.0
