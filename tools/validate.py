#!/usr/bin/env python3
"""Walidator paczki integracji — wersja STANDALONE dla CI repo nelly-integrations.

    python tools/validate.py integrations/<id>

Logika weryfikacji zsynchronizowana z NEL/integrations/validate.py (tam jest wersja
działająca w pełnym środowisku Nelly) — zmieniaj OBA pliki. Tu dodatkowo budujemy
shim środowiska (stub `config` i `integrations.framework.config_store`), żeby paczki
importowały się bez kodu Nelly: import w paczce ma działać bez configu, a wartości
czyta wyłącznie przez cfg() — stub zwraca puste/zerowe wartości.
"""
from __future__ import annotations

import importlib
import inspect
import os
import re
import shutil
import sys
import tempfile
from pathlib import Path

HERE = Path(__file__).resolve().parent
ROOT = HERE.parent

_CONFIG_STUB = '''\
"""Stub config.py dla CI — paczki mogą importować stałe; wartości nie mają znaczenia
przy walidacji (import-only + get_status, które ma zwracać reachable=False)."""
import pathlib
DATA_DIR = pathlib.Path("./_ci_data")
def __getattr__(name):
    return 0
'''

_CONFIG_STORE_STUB = '''\
"""Stub config_store dla CI — cfg() czyta tylko env (w CI puste)."""
import os
import pathlib
CONFIG_DIR = pathlib.Path("./_ci_data/integrations")
def get_config(integration_id):
    return {}
def set_config(integration_id, values):
    return dict(values or {})
def cfg(integration_id, key, env_fallback=None, default=""):
    v = os.getenv(env_fallback or key)
    return v.strip() if v and v.strip() else default
'''


def _bootstrap(pkg_dir: Path) -> Path:
    """Buduje tymczasowe drzewo importowe: config-stub + framework-stub + paczka."""
    tmp = Path(tempfile.mkdtemp(prefix="nelly-ci-validate-"))
    (tmp / "config.py").write_text(_CONFIG_STUB, encoding="utf-8")
    fw = tmp / "integrations" / "framework"
    fw.mkdir(parents=True)
    (tmp / "integrations" / "__init__.py").write_text("", encoding="utf-8")
    (fw / "__init__.py").write_text("", encoding="utf-8")
    (fw / "config_store.py").write_text(_CONFIG_STORE_STUB, encoding="utf-8")
    shutil.copy(HERE / "vendor_manifest.py", fw / "manifest.py")
    shutil.copytree(pkg_dir, tmp / "integrations" / pkg_dir.name)
    sys.path.insert(0, str(tmp))
    return tmp


_SECRET_PATTERNS = (
    (re.compile(r"['\"](sk-[A-Za-z0-9]{20,})"), "wygląda na klucz API (sk-...)"),
    (re.compile(r"['\"]([A-Fa-f0-9]{32,})['\"]"), "długi hex — możliwy token"),
    (re.compile(r"Bearer\s+[A-Za-z0-9_\-\.]{16,}"), "hardcodowany nagłówek Bearer"),
    (re.compile(r"['\"](\d{1,3}\.\d{1,3}\.\d{1,3}\.\d{1,3})['\"]"), "hardcodowany adres IP (powinien być w config)"),
)
_SECRET_ALLOW = ("0.0.0.0", "127.0.0.1", "255.255.255.255")


def validate(pkg_dir: Path) -> tuple[list[str], list[str]]:
    """Identyczne checki jak NEL/integrations/validate.py (sync ręczny)."""
    errors: list[str] = []
    warnings: list[str] = []

    from integrations.framework import manifest as manifest_mod  # po _bootstrap

    man_path = pkg_dir / "manifest.json"
    if not man_path.is_file():
        return [f"brak {man_path}"], warnings
    try:
        man = manifest_mod.load_manifest(man_path)
    except Exception as e:
        return [f"manifest.json nie parsuje się: {e}"], warnings
    errors += [f"manifest: {e}" for e in manifest_mod.validate_manifest(man)]
    if errors:
        return errors, warnings
    iid = man["id"]
    if pkg_dir.name != iid:
        errors.append(f"katalog '{pkg_dir.name}' ≠ manifest.id '{iid}'")

    os.environ["NELLY_VALIDATE"] = "1"
    try:
        module = importlib.import_module(f"integrations.{iid}")
    except Exception as e:
        errors.append(f"import integrations.{iid} padł (musi działać BEZ configu): {type(e).__name__}: {e}")
        return errors, warnings

    schemas = getattr(module, "TOOL_SCHEMAS", None)
    tools = getattr(module, "TOOLS", None)
    if not isinstance(schemas, list) or not schemas:
        errors.append("brak TOOL_SCHEMAS (niepusta lista, format OpenAI)")
    if not isinstance(tools, dict) or not tools:
        errors.append("brak TOOLS (dict nazwa → handler)")
    if errors:
        return errors, warnings

    schema_names = [s.get("function", {}).get("name") for s in schemas]
    manifest_names = [t["name"] for t in man.get("tools", [])]
    if set(schema_names) != set(tools.keys()):
        errors.append(f"nazwy TOOL_SCHEMAS {sorted(set(schema_names))} ≠ klucze TOOLS {sorted(tools.keys())}")
    if set(schema_names) != set(manifest_names):
        errors.append(f"nazwy w kodzie {sorted(set(schema_names))} ≠ manifest.tools {sorted(manifest_names)}")

    for s in schemas:
        fn_schema = s.get("function", {})
        name = fn_schema.get("name", "?")
        params = (fn_schema.get("parameters") or {}).get("properties") or {}
        required = set((fn_schema.get("parameters") or {}).get("required") or [])
        for pname, pschema in params.items():
            if "type" not in pschema:
                errors.append(f"{name}.{pname}: brak 'type'")
            if "description" not in pschema and "enum" not in pschema:
                warnings.append(f"{name}.{pname}: brak 'description' (ElevenLabs dostanie fallback)")
        handler = (tools or {}).get(name)
        if handler is None:
            continue
        try:
            sig = inspect.signature(handler)
        except (TypeError, ValueError):
            continue
        accepts_kwargs = any(p.kind == inspect.Parameter.VAR_KEYWORD for p in sig.parameters.values())
        if not accepts_kwargs:
            handler_params = {n for n, p in sig.parameters.items()
                              if p.kind in (inspect.Parameter.POSITIONAL_OR_KEYWORD, inspect.Parameter.KEYWORD_ONLY)}
            unknown = set(params) - handler_params
            if unknown:
                errors.append(f"{name}: handler nie przyjmuje parametrów {sorted(unknown)} ze schematu")
            no_default = {n for n, p in sig.parameters.items() if p.default is inspect.Parameter.empty
                          and p.kind in (inspect.Parameter.POSITIONAL_OR_KEYWORD, inspect.Parameter.KEYWORD_ONLY)}
            missing = no_default - set(params)
            if missing:
                errors.append(f"{name}: handler wymaga {sorted(missing)}, których nie ma w schemacie")
            opt_in_schema = set(params) - required
            req_in_handler = opt_in_schema & no_default
            if req_in_handler:
                errors.append(f"{name}: parametry {sorted(req_in_handler)} są opcjonalne w schemacie, "
                              f"ale handler nie ma dla nich defaultów")

    get_status = getattr(module, "get_status", None)
    if not callable(get_status):
        errors.append("brak get_status() — wymagany przez dashboard/kontrakt")
    else:
        try:
            st = get_status()
            if not isinstance(st, dict):
                errors.append(f"get_status() zwrócił {type(st).__name__}, oczekiwany dict")
            elif "reachable" not in st and not man.get("config"):
                warnings.append("get_status(): brak klucza 'reachable' (zalecany)")
        except Exception as e:
            warnings.append(f"get_status() rzucił bez configu ({type(e).__name__}: {e}) — "
                            "kontrakt zaleca {'reachable': False, ...} zamiast wyjątku")

    for py in pkg_dir.glob("*.py"):
        text = py.read_text(encoding="utf-8", errors="replace")
        for rx, why in _SECRET_PATTERNS:
            for m in rx.finditer(text):
                frag = m.group(0)
                if any(a in frag for a in _SECRET_ALLOW):
                    continue
                warnings.append(f"{py.name}: {why}: {frag[:40]}…")

    for req in man.get("requirements", []):
        if not re.search(r"[><=~]", req):
            warnings.append(f"requirements: '{req}' bez wersji (zalecane np. '{req}>=1.0')")

    return errors, warnings


def main(argv: list[str]) -> int:
    if len(argv) != 1:
        print(__doc__)
        return 2
    pkg_dir = Path(argv[0]).resolve()
    if not pkg_dir.is_dir():
        print(f"BŁĄD: {pkg_dir} nie jest katalogiem")
        return 2
    tmp = _bootstrap(pkg_dir)
    try:
        errors, warnings = validate(tmp / "integrations" / pkg_dir.name)
    finally:
        shutil.rmtree(tmp, ignore_errors=True)
    for w in warnings:
        print(f"  WARN  {w}")
    for e in errors:
        print(f"  FAIL  {e}")
    if errors:
        print(f"\n{pkg_dir.name}: {len(errors)} błędów, {len(warnings)} ostrzeżeń — POPRAW PRZED PR-em")
        return 1
    print(f"\n{pkg_dir.name}: OK ({len(warnings)} ostrzeżeń)")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
