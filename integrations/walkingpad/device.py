"""Kingsmith WalkingPad (X21) — BLE control via ph4-walkingpad.

Sync API poprzez trzymany w tle async event-loop w osobnym wątku,
żeby oszczędzać rekonektów przy sekwencyjnych komendach głosowych.

Bezpieczeństwo:
- START nigdy nie dzieje się bez jednoznacznej intencji (egzekwowane w promptzie).
- Prędkość ograniczona do 0.5 – 6.0 km/h dla sterowania głosem.
- STOP jest zawsze bezwarunkowy — to funkcja bezpieczeństwa.

CLI:
    python -m integrations.walkingpad scan      # wykryj urządzenia w pobliżu
    python -m integrations.walkingpad status    # pokaż stan podłączonej bieżni
    python -m integrations.walkingpad stop      # awaryjne zatrzymanie
"""
from __future__ import annotations

import asyncio
import sys
import threading
import time
from typing import Any

from bleak import BleakScanner
from ph4_walkingpad.pad import Controller

from integrations.framework.config_store import cfg

MIN_SPEED_KMH = 0.5
MAX_SPEED_KMH = 6.0
_CONNECT_TIMEOUT_S = 12.0
_UNREACHABLE_COOLDOWN_S = 30.0  # jak raz padło, nie próbuj przez 30s
_unreachable_until: float = 0.0


# ---------------- background event loop ----------------

_loop: asyncio.AbstractEventLoop | None = None
_loop_thread: threading.Thread | None = None
_loop_lock = threading.Lock()


def _get_loop() -> asyncio.AbstractEventLoop:
    global _loop, _loop_thread
    with _loop_lock:
        if _loop is None or _loop.is_closed():
            _loop = asyncio.new_event_loop()

            def runner() -> None:
                assert _loop is not None
                asyncio.set_event_loop(_loop)
                _loop.run_forever()

            _loop_thread = threading.Thread(target=runner, daemon=True, name="walkingpad-loop")
            _loop_thread.start()
        return _loop


def _run(coro: Any, timeout: float = _CONNECT_TIMEOUT_S) -> Any:
    fut = asyncio.run_coroutine_threadsafe(coro, _get_loop())
    return fut.result(timeout=timeout)


# ---------------- controller singleton ----------------

_ctrl: Controller | None = None
_connected: bool = False


def _address() -> str:
    addr = cfg("walkingpad", "WALKINGPAD_ADDRESS", env_fallback="WALKINGPAD_ADDRESS")
    if not addr:
        raise RuntimeError("WALKINGPAD_ADDRESS nie ustawione (apka → Integracje → skan BLE, "
                           "albo `python -m integrations.walkingpad scan` + .env).")
    return addr


async def _ensure_connected() -> Controller:
    global _ctrl, _connected
    if _ctrl is None:
        _ctrl = Controller()
    if not _connected:
        await _ctrl.run(_address())
        _connected = True
    return _ctrl


async def _disconnect() -> None:
    global _ctrl, _connected
    if _ctrl is not None and _connected:
        try:
            await _ctrl.disconnect()
        except Exception:
            pass
    _connected = False


# ---------------- public sync API ----------------

def scan(seconds: float = 6.0) -> list[dict[str, str]]:
    async def _scan() -> list[dict[str, str]]:
        devs = await BleakScanner.discover(timeout=seconds)
        return [
            {"name": d.name or "(unnamed)", "address": d.address}
            for d in devs
        ]

    return _run(_scan(), timeout=seconds + 4)


def start(speed_kmh: float = 2.0) -> None:
    global _unreachable_until
    _unreachable_until = 0.0  # eksplicitna akcja usera — zignoruj cooldown
    speed_kmh = max(MIN_SPEED_KMH, min(MAX_SPEED_KMH, float(speed_kmh)))

    async def _start() -> None:
        c = await _ensure_connected()
        await c.switch_mode(1)  # manual mode
        await asyncio.sleep(0.3)
        await c.start_belt()
        await asyncio.sleep(0.3)
        await c.change_speed(int(round(speed_kmh * 10)))

    _run(_start())


def stop() -> None:
    global _unreachable_until
    _unreachable_until = 0.0

    async def _stop() -> None:
        c = await _ensure_connected()
        await c.stop_belt()

    _run(_stop())


def set_speed(speed_kmh: float) -> None:
    global _unreachable_until
    _unreachable_until = 0.0
    speed_kmh = max(MIN_SPEED_KMH, min(MAX_SPEED_KMH, float(speed_kmh)))

    async def _set() -> None:
        c = await _ensure_connected()
        await c.change_speed(int(round(speed_kmh * 10)))

    _run(_set())


def get_status() -> dict[str, Any]:
    async def _status() -> dict[str, Any]:
        c = await _ensure_connected()
        await c.ask_stats()
        await asyncio.sleep(0.4)
        s = c.last_status
        if s is None:
            return {"reachable": True, "power": "unknown"}
        belt_state = getattr(s, "belt_state", None)
        running = belt_state == 1
        return {
            "reachable": True,
            "power": "on" if running else "off",
            "speed_kmh": round((s.speed or 0) / 10, 1),
            "distance_km": round((s.dist or 0) / 100, 2),
            "time_s": s.time or 0,
            "steps": s.steps or 0,
            "belt_state": belt_state,
        }

    global _unreachable_until
    if time.time() < _unreachable_until:
        return {"reachable": False, "power": "off", "reason": "cooldown"}
    try:
        return _run(_status(), timeout=4.0)
    except Exception as e:
        _unreachable_until = time.time() + _UNREACHABLE_COOLDOWN_S
        return {"reachable": False, "error": str(e)}


# ---------------- CLI ----------------

def _cli() -> None:
    if len(sys.argv) < 2:
        print("Usage: python -m integrations.walkingpad {scan|status|stop}")
        sys.exit(1)

    cmd = sys.argv[1]
    if cmd == "scan":
        print("Skanuję ~6s... (upewnij się, że bieżnia jest włączona)")
        for d in scan():
            marker = "  <-- walkingpad?" if "walkingpad" in d["name"].lower() or "ks-" in d["name"].lower() else ""
            print(f"  {d['address']}  {d['name']}{marker}")
    elif cmd == "status":
        import json
        print(json.dumps(get_status(), indent=2, ensure_ascii=False))
    elif cmd == "stop":
        stop()
        print("Stopped.")
    else:
        print(f"Unknown command: {cmd}")
        sys.exit(1)


if __name__ == "__main__":
    _cli()
