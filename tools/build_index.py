#!/usr/bin/env python3
"""Generuje index.json marketplace z katalogu integrations/.

    python tools/build_index.py [--commit <sha>]

Każdy wpis: metadane z manifestu + sha256 KAŻDEGO pliku paczki + pin do commita.
Klient Nelly pobiera pliki spod tego commita i odmawia instalacji przy niezgodnym
hashu (tamper-evidence). Uruchamiane przez CI po merge'u do main — NIE edytuj
index.json ręcznie.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import subprocess
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
INTEGRATIONS = ROOT / "integrations"
INDEX = ROOT / "index.json"


def _commit(arg: str | None) -> str | None:
    if arg:
        return arg
    try:
        return subprocess.run(["git", "rev-parse", "HEAD"], cwd=ROOT,
                              capture_output=True, text=True, check=True).stdout.strip()
    except Exception:
        return None


def _pl(value) -> str:
    if isinstance(value, dict):
        return str(value.get("pl") or value.get("en") or "")
    return str(value or "")


def build(commit: str | None) -> dict:
    entries = []
    for d in sorted(INTEGRATIONS.iterdir()):
        man_path = d / "manifest.json"
        if not d.is_dir() or not man_path.is_file():
            continue
        man = json.loads(man_path.read_text(encoding="utf-8"))
        files = {}
        for f in sorted(d.iterdir()):
            if f.is_file() and not f.name.startswith(".") and f.suffix in (".py", ".json", ".md"):
                files[f.name] = "sha256:" + hashlib.sha256(f.read_bytes()).hexdigest()
        entries.append({
            "id": man["id"],
            "name": _pl(man.get("name")),
            "description_pl": _pl(man.get("description")),
            "version": man.get("version", "0.0.0"),
            "category": man.get("category", "other"),
            "icon": man.get("icon", "bolt"),
            "author": man.get("author", "?"),
            "requirements": man.get("requirements", []),
            "files": files,
            "commit": commit,
            "min_framework": man.get("manifest_version", 1),
        })
    return {
        "schema": 1,
        "generated_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        "integrations": entries,
    }


def main() -> int:
    p = argparse.ArgumentParser()
    p.add_argument("--commit", default=None, help="sha commita do przypięcia (default: git HEAD)")
    args = p.parse_args()
    index = build(_commit(args.commit))
    INDEX.write_text(json.dumps(index, ensure_ascii=False, indent=1) + "\n", encoding="utf-8")
    print(f"index.json: {len(index['integrations'])} integracji (commit={index['integrations'][0]['commit'] if index['integrations'] else None})")
    return 0


if __name__ == "__main__":
    sys.exit(main())
