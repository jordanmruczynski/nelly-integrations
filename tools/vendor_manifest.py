"""Manifest integracji — wczytanie i walidacja (ręczna, bez zależności jsonschema).

Manifest to manifest.json w katalogu paczki: metadane czytelne bez wykonywania kodu.
Walidacja zwraca listę błędów (pusta = OK), żeby walidator/CLI mogły wypisać wszystkie
problemy naraz zamiast wywalać się na pierwszym.
"""
from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any

MANIFEST_VERSION = 1
_ID_RE = re.compile(r"^[a-z][a-z0-9_]{1,40}$")

CONFIG_TYPES = ("string", "password", "integer", "boolean", "enum")
PAIRING_METHODS = ("form", "oauth", "ble_scan", "cloud_list")
ACTION_KINDS = ("test", "list_pick", "info")


def load_manifest(path: Path | str) -> dict[str, Any]:
    """Wczytuje manifest.json. Rzuca przy niepoprawnym JSON — wołający decyduje co dalej."""
    with open(path, encoding="utf-8") as f:
        data = json.load(f)
    if not isinstance(data, dict):
        raise ValueError(f"{path}: manifest musi być obiektem JSON")
    return data


def _pl_text(value: Any) -> bool:
    """Tekst wielojęzyczny: {'pl': '...'} (en opcjonalne) albo zwykły string."""
    if isinstance(value, str):
        return bool(value.strip())
    return isinstance(value, dict) and bool(str(value.get("pl", "")).strip())


def validate_manifest(m: dict[str, Any]) -> list[str]:
    """Sprawdza strukturę manifestu. Zwraca listę błędów (po polsku, z kluczem pola)."""
    errs: list[str] = []

    if m.get("manifest_version") != MANIFEST_VERSION:
        errs.append(f"manifest_version: wymagane {MANIFEST_VERSION}, jest {m.get('manifest_version')!r}")
    if not isinstance(m.get("id"), str) or not _ID_RE.match(m.get("id", "")):
        errs.append("id: wymagany slug [a-z][a-z0-9_]* (np. 'twinkly')")
    if not _pl_text(m.get("name")):
        errs.append("name: wymagana nazwa")
    if not _pl_text(m.get("description")):
        errs.append("description: wymagany opis z kluczem 'pl'")
    if not isinstance(m.get("version"), str) or not m.get("version"):
        errs.append("version: wymagany string (np. '1.0.0')")

    reqs = m.get("requirements", [])
    if not isinstance(reqs, list) or any(not isinstance(r, str) for r in reqs):
        errs.append("requirements: lista stringów pip (może być pusta)")

    config = m.get("config", [])
    if not isinstance(config, list):
        errs.append("config: musi być listą pól")
        config = []
    seen_keys: set[str] = set()
    for i, f in enumerate(config):
        where = f"config[{i}]"
        if not isinstance(f, dict):
            errs.append(f"{where}: musi być obiektem")
            continue
        key = f.get("key")
        if not isinstance(key, str) or not key:
            errs.append(f"{where}.key: wymagany")
        elif key in seen_keys:
            errs.append(f"{where}.key: duplikat '{key}'")
        else:
            seen_keys.add(key)
        if not _pl_text(f.get("label")):
            errs.append(f"{where}.label: wymagana etykieta (pl)")
        if f.get("type", "string") not in CONFIG_TYPES:
            errs.append(f"{where}.type: dozwolone {CONFIG_TYPES}")
        if f.get("type") == "enum" and not isinstance(f.get("choices"), list):
            errs.append(f"{where}.choices: wymagane dla type='enum'")

    pairing = m.get("pairing", {})
    if pairing:
        if not isinstance(pairing, dict):
            errs.append("pairing: musi być obiektem")
        else:
            if pairing.get("method") not in PAIRING_METHODS:
                errs.append(f"pairing.method: dozwolone {PAIRING_METHODS}")
            for i, a in enumerate(pairing.get("actions", []) or []):
                where = f"pairing.actions[{i}]"
                if not isinstance(a, dict) or not a.get("id"):
                    errs.append(f"{where}: wymagany obiekt z 'id'")
                    continue
                if a.get("kind") not in ACTION_KINDS:
                    errs.append(f"{where}.kind: dozwolone {ACTION_KINDS}")
                if a.get("kind") == "list_pick" and a.get("fills") not in seen_keys:
                    errs.append(f"{where}.fills: musi wskazywać istniejący klucz config")

    tools = m.get("tools", [])
    if not isinstance(tools, list) or not tools:
        errs.append("tools: wymagana niepusta lista narzędzi")
    else:
        seen_tools: set[str] = set()
        for i, t in enumerate(tools):
            if not isinstance(t, dict) or not isinstance(t.get("name"), str) or not t.get("name"):
                errs.append(f"tools[{i}]: wymagany obiekt z 'name'")
                continue
            if t["name"] in seen_tools:
                errs.append(f"tools[{i}].name: duplikat '{t['name']}'")
            seen_tools.add(t["name"])

    tile = m.get("dashboard_tile")
    if tile is not None and (not isinstance(tile, dict) or not _pl_text(tile.get("label"))):
        errs.append("dashboard_tile: obiekt z 'label' (pl), opcjonalnie 'icon'")

    return errs


def text_pl(value: Any) -> str:
    """Wyciąga polski wariant tekstu z pola wielojęzycznego (lub zwykłego stringa)."""
    if isinstance(value, dict):
        return str(value.get("pl") or value.get("en") or "")
    return str(value or "")
