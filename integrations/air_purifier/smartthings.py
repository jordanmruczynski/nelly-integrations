"""SmartThings REST API client + discovery CLI.

Usage:
    python -m integrations.smartthings list              # list all devices + capabilities
    python -m integrations.smartthings status <dev_id>   # full status JSON for one device
"""
from __future__ import annotations

import json
import os
import sys
from typing import Any

import httpx

# Celowo BEZ load_dotenv(): .env ładuje host (config.py) — paczki marketplace muszą
# importować się bez zależności od python-dotenv (token i tak przychodzi przez cfg()).
BASE_URL = "https://api.smartthings.com/v1"


def _token(override: str | None = None) -> str:
    tok = (override or os.getenv("SMARTTHINGS_TOKEN", "")).strip()
    if not tok or tok.startswith("paste-"):
        raise RuntimeError("SMARTTHINGS_TOKEN is not set in .env")
    return tok


def _client(token: str | None = None) -> httpx.Client:
    return httpx.Client(
        base_url=BASE_URL,
        headers={"Authorization": f"Bearer {_token(token)}"},
        timeout=15.0,
    )


def list_devices(token: str | None = None) -> list[dict[str, Any]]:
    with _client(token) as c:
        r = c.get("/devices")
        r.raise_for_status()
        return r.json().get("items", [])


def get_status(device_id: str, token: str | None = None) -> dict[str, Any]:
    with _client(token) as c:
        r = c.get(f"/devices/{device_id}/status")
        r.raise_for_status()
        return r.json()


def execute(
    device_id: str,
    capability: str,
    command: str,
    arguments: list[Any] | None = None,
    component: str = "main",
    token: str | None = None,
) -> dict[str, Any]:
    payload = {
        "commands": [
            {
                "component": component,
                "capability": capability,
                "command": command,
                "arguments": arguments or [],
            }
        ]
    }
    with _client(token) as c:
        r = c.post(f"/devices/{device_id}/commands", json=payload)
        r.raise_for_status()
        return r.json()


def _fmt_device(d: dict[str, Any]) -> str:
    caps = sorted(
        {
            cap["id"]
            for comp in d.get("components", [])
            for cap in comp.get("capabilities", [])
        }
    )
    label = d.get("label") or d.get("name") or "(no label)"
    return f"{d['deviceId']}  {label}\n  capabilities: {', '.join(caps) or '(none)'}"


def _cli() -> None:
    if len(sys.argv) < 2:
        print("Usage: python -m integrations.smartthings {list|status <device_id>}")
        sys.exit(1)

    cmd = sys.argv[1]
    if cmd == "list":
        devices = list_devices()
        if not devices:
            print("No devices found on this SmartThings account.")
            return
        for d in devices:
            print(_fmt_device(d))
            print()
    elif cmd == "status":
        if len(sys.argv) < 3:
            print("Usage: python -m integrations.smartthings status <device_id>")
            sys.exit(1)
        print(json.dumps(get_status(sys.argv[2]), indent=2))
    else:
        print(f"Unknown command: {cmd}")
        sys.exit(1)


if __name__ == "__main__":
    _cli()
