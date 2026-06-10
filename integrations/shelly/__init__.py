"""Integracja: Shelly — przekaźnik/gniazdko po LAN, auto-detekcja generacji.

Gen2/Plus: JSON-RPC (POST /rpc, Switch.Set / Switch.GetStatus).
Gen1: klasyczne GET /relay/0?turn=on i GET /status.
Generację wykrywamy raz z GET /shelly (pole "gen") i cache'ujemy do reset().
"""
from __future__ import annotations

from typing import Any, Callable

import httpx

from integrations.framework.config_store import cfg

_TIMEOUT = 6.0
_gen_cache: int | None = None


def _ip() -> str:
    ip = cfg("shelly", "SHELLY_IP", env_fallback="SHELLY_IP")
    if not ip:
        raise RuntimeError("Shelly nie skonfigurowane — ustaw adres IP (apka → Integracje → Shelly)")
    return ip


def _label() -> str:
    return cfg("shelly", "SHELLY_LABEL") or "Shelly"


def _gen() -> int:
    global _gen_cache
    if _gen_cache is None:
        r = httpx.get(f"http://{_ip()}/shelly", timeout=_TIMEOUT)
        r.raise_for_status()
        _gen_cache = int(r.json().get("gen", 1))
    return _gen_cache


def _rpc(method: str, params: dict[str, Any]) -> dict[str, Any]:
    r = httpx.post(f"http://{_ip()}/rpc", json={"id": 1, "method": method, "params": params},
                   timeout=_TIMEOUT)
    r.raise_for_status()
    data = r.json()
    if "error" in data:
        raise RuntimeError(str(data["error"]))
    return data.get("result", {})


def _set(on: bool) -> None:
    if _gen() >= 2:
        _rpc("Switch.Set", {"id": 0, "on": on})
    else:
        r = httpx.get(f"http://{_ip()}/relay/0", params={"turn": "on" if on else "off"},
                      timeout=_TIMEOUT)
        r.raise_for_status()


def turn_on() -> None:
    _set(True)


def turn_off() -> None:
    _set(False)


def get_status() -> dict[str, Any]:
    try:
        if _gen() >= 2:
            st = _rpc("Switch.GetStatus", {"id": 0})
            return {
                "reachable": True,
                "label": _label(),
                "power": "on" if st.get("output") else "off",
                "power_w": st.get("apower"),
                "temperature_c": (st.get("temperature") or {}).get("tC"),
            }
        r = httpx.get(f"http://{_ip()}/status", timeout=_TIMEOUT)
        r.raise_for_status()
        data = r.json()
        relay = (data.get("relays") or [{}])[0]
        meter = (data.get("meters") or [{}])[0]
        return {
            "reachable": True,
            "label": _label(),
            "power": "on" if relay.get("ison") else "off",
            "power_w": meter.get("power"),
        }
    except Exception as e:  # noqa: BLE001 — kontrakt: status nigdy nie rzuca
        return {"reachable": False, "label": _label(), "error": str(e)}


TOOL_SCHEMAS: list[dict[str, Any]] = [
    {
        "type": "function",
        "function": {
            "name": "turn_on_shelly",
            "description": "Turn ON the Shelly relay/plug (whatever appliance is wired to it — see its status label).",
            "parameters": {"type": "object", "properties": {}, "required": []},
        },
    },
    {
        "type": "function",
        "function": {
            "name": "turn_off_shelly",
            "description": "Turn OFF the Shelly relay/plug.",
            "parameters": {"type": "object", "properties": {}, "required": []},
        },
    },
    {
        "type": "function",
        "function": {
            "name": "get_shelly_status",
            "description": "Read Shelly relay state: on/off, current power draw (W) if metered.",
            "parameters": {"type": "object", "properties": {}, "required": []},
        },
    },
]


def _on() -> dict[str, str]:
    turn_on()
    return {"ok": "shelly on"}


def _off() -> dict[str, str]:
    turn_off()
    return {"ok": "shelly off"}


TOOLS: dict[str, Callable[..., dict[str, Any]]] = {
    "turn_on_shelly": _on,
    "turn_off_shelly": _off,
    "get_shelly_status": get_status,
}


def status_line() -> str:
    s = get_status()
    if not s.get("reachable"):
        return f"{s.get('label', 'Shelly')}: niedostępne"
    extra = f", moc={s['power_w']}W" if s.get("power_w") is not None else ""
    return f"{s.get('label', 'Shelly')} (Shelly): power={s['power']}{extra}"


def tile(status: dict[str, Any]) -> dict[str, Any]:
    if not status.get("reachable"):
        return {"value": "Offline", "meta": ""}
    on = status.get("power") == "on"
    watts = status.get("power_w")
    return {
        "value": "Wł." if on else "Wył.",
        "meta": f"{round(watts, 1)} W" if isinstance(watts, (int, float)) and on else status.get("label", ""),
        **({"tone": "accent"} if on else {}),
    }


PAIR_ACTIONS: dict[str, Callable[..., Any]] = {
    "test": get_status,
}


def reset() -> None:
    global _gen_cache
    _gen_cache = None
