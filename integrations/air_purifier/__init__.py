"""Integracja: oczyszczacz Samsung AX60R5080WD — domain wrapper nad SmartThings.

Transport (REST + CLI discovery) zostaje wspólny w integrations/smartthings.py;
ta paczka wnosi konkretne urządzenie: config (token+device id), narzędzia, stan.
"""
from __future__ import annotations

from typing import Any, Callable

from integrations import smartthings
from integrations.framework.config_store import cfg

FAN_MODES = ("auto", "low", "medium", "high", "sleep")


def _token() -> str | None:
    return cfg("air_purifier", "SMARTTHINGS_TOKEN", env_fallback="SMARTTHINGS_TOKEN") or None


def _device_id() -> str:
    dev_id = cfg("air_purifier", "SMARTTHINGS_DEVICE_ID_PURIFIER",
                 env_fallback="SMARTTHINGS_DEVICE_ID_PURIFIER")
    if not dev_id:
        raise RuntimeError("SMARTTHINGS_DEVICE_ID_PURIFIER nie ustawione (apka → Integracje, albo .env)")
    return dev_id


def turn_on() -> None:
    smartthings.execute(_device_id(), "switch", "on", token=_token())


def turn_off() -> None:
    smartthings.execute(_device_id(), "switch", "off", token=_token())


def set_fan_mode(mode: str) -> None:
    if mode not in FAN_MODES:
        raise ValueError(f"Unknown fan mode '{mode}'. Supported: {FAN_MODES}")
    smartthings.execute(_device_id(), "airConditionerFanMode", "setFanMode", [mode], token=_token())


def get_status() -> dict[str, Any]:
    """Compact state + air quality summary."""
    raw = smartthings.get_status(_device_id(), token=_token())
    main = raw["components"]["main"]

    def _v(cap: str, attr: str) -> Any:
        return main.get(cap, {}).get(attr, {}).get("value")

    return {
        "power": _v("switch", "switch"),
        "fan_mode": _v("airConditionerFanMode", "fanMode"),
        "air_quality_caqi": _v("airQualitySensor", "airQuality"),
        "air_quality_health": _v(
            "samsungce.airQualityHealthConcern", "airQualityHealthConcern"
        ),
        "pm25_ug_m3": _v("veryFineDustSensor", "veryFineDustLevel"),
        "pm10_ug_m3": _v("dustSensor", "fineDustLevel"),
        "odor_level": _v("odorSensor", "odorLevel"),
        "filter_usage_hours": _v("custom.filterUsageTime", "usageTime"),
    }


TOOL_SCHEMAS: list[dict[str, Any]] = [
    {
        "type": "function",
        "function": {
            "name": "turn_on_air_purifier",
            "description": "Turn the Samsung air purifier ON.",
            "parameters": {"type": "object", "properties": {}, "required": []},
        },
    },
    {
        "type": "function",
        "function": {
            "name": "turn_off_air_purifier",
            "description": "Turn the Samsung air purifier OFF.",
            "parameters": {"type": "object", "properties": {}, "required": []},
        },
    },
    {
        "type": "function",
        "function": {
            "name": "set_air_purifier_fan_mode",
            "description": (
                "Set fan speed/mode on the Samsung air purifier. "
                "'auto' adapts to measured air quality; 'sleep' is quietest; "
                "'low'/'medium'/'high' are fixed speeds."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "mode": {
                        "type": "string",
                        "enum": list(FAN_MODES),
                    }
                },
                "required": ["mode"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "get_air_purifier_status",
            "description": (
                "Read current power, fan mode, PM2.5/PM10 (µg/m³), odor level, "
                "CAQI air quality (1=best, 4=worst), and filter usage hours."
            ),
            "parameters": {"type": "object", "properties": {}, "required": []},
        },
    },
]


def _purifier_on() -> dict[str, str]:
    turn_on()
    return {"ok": "purifier turned on"}


def _purifier_off() -> dict[str, str]:
    turn_off()
    return {"ok": "purifier turned off"}


def _purifier_fan(mode: str) -> dict[str, str]:
    set_fan_mode(mode)
    return {"ok": f"fan mode set to {mode}"}


def _purifier_status() -> dict[str, Any]:
    return get_status()


TOOLS: dict[str, Callable[..., dict[str, Any]]] = {
    "turn_on_air_purifier": _purifier_on,
    "turn_off_air_purifier": _purifier_off,
    "set_air_purifier_fan_mode": _purifier_fan,
    "get_air_purifier_status": _purifier_status,
}


def status_line() -> str:
    try:
        s = get_status()
        return (
            f"oczyszczacz: power={s['power']}, fan_mode={s['fan_mode']}, "
            f"PM2.5={s['pm25_ug_m3']}µg/m³, PM10={s['pm10_ug_m3']}µg/m³, "
            f"CAQI={s['air_quality_caqi']}/4 ({s['air_quality_health']}), "
            f"filtr={s['filter_usage_hours']}h"
        )
    except Exception as e:
        return f"oczyszczacz: (błąd odczytu: {e})"


def tile(status: dict[str, Any]) -> dict[str, Any]:
    if status.get("error"):
        return {"value": "Offline", "meta": "brak połączenia"}
    on = status.get("power") == "on"
    pm25 = status.get("pm25_ug_m3")
    return {
        "value": "Wł." if on else "Wył.",
        "meta": f"PM2.5 {pm25}µg/m³" if pm25 is not None else "",
        **({"tone": "ok"} if on else {}),
    }


def _list_smartthings_devices() -> list[dict[str, str]]:
    """Akcja parowania: lista urządzeń konta SmartThings → użytkownik wybiera oczyszczacz."""
    out = []
    for d in smartthings.list_devices(token=_token()):
        label = d.get("label") or d.get("name") or "(bez nazwy)"
        out.append({"label": label, "value": d["deviceId"]})
    return out


PAIR_ACTIONS: dict[str, Callable[..., Any]] = {
    "list_devices": _list_smartthings_devices,
    "test": lambda: get_status(),
}
