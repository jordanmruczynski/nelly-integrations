"""Twinkly local HTTP API — challenge-response auth + token lifecycle.

Unikamy zewnętrznych bibliotek (xled, ttls) żeby mieć pełną kontrolę.
Dokumentacja API: https://xled-docs.readthedocs.io/
"""
from __future__ import annotations

import base64
import secrets
import time
from typing import Any

import httpx

from integrations.framework.config_store import cfg


def _ip() -> str:
    ip = cfg("twinkly", "TWINKLY_IP", env_fallback="TWINKLY_IP")
    if not ip:
        raise RuntimeError("TWINKLY_IP nie ustawione (apka → Integracje → Twinkly, albo .env)")
    return ip


class TwinklyClient:
    def __init__(self, ip: str | None = None) -> None:
        self._base = f"http://{ip or _ip()}/xled/v1"
        self._token: str | None = None
        self._token_exp: float = 0.0
        self._http = httpx.Client(timeout=5.0)

    def _ensure_auth(self) -> None:
        if self._token and time.time() < self._token_exp - 60:
            return
        challenge = base64.b64encode(secrets.token_bytes(32)).decode()
        login = self._http.post(f"{self._base}/login", json={"challenge": challenge})
        login.raise_for_status()
        j = login.json()
        token = j["authentication_token"]
        verify = self._http.post(
            f"{self._base}/verify",
            headers={"X-Auth-Token": token},
            json={"challenge-response": j["challenge-response"]},
        )
        verify.raise_for_status()
        if verify.json().get("code") != 1000:
            raise RuntimeError(f"Twinkly verify failed: {verify.json()}")
        self._token = token
        self._token_exp = time.time() + j.get("authentication_token_expires_in", 14400)

    def _req(self, method: str, path: str, **kw: Any) -> httpx.Response:
        self._ensure_auth()
        headers = kw.pop("headers", {})
        headers["X-Auth-Token"] = self._token
        r = self._http.request(method, f"{self._base}{path}", headers=headers, **kw)
        if r.status_code == 401:
            self._token = None
            self._ensure_auth()
            headers["X-Auth-Token"] = self._token
            r = self._http.request(method, f"{self._base}{path}", headers=headers, **kw)
        r.raise_for_status()
        return r

    def get_mode(self) -> str:
        return self._req("GET", "/led/mode").json().get("mode", "unknown")

    def set_mode(self, mode: str) -> None:
        """mode: off | color | movie | demo | effect | rt | playlist"""
        self._req("POST", "/led/mode", json={"mode": mode})

    def get_brightness(self) -> dict[str, Any]:
        return self._req("GET", "/led/out/brightness").json()

    def set_brightness(self, percent: int) -> None:
        v = max(0, min(100, int(percent)))
        self._req(
            "POST",
            "/led/out/brightness",
            json={"mode": "enabled", "type": "A", "value": v},
        )

    def set_color_hsv(self, h: int, s: int, v: int) -> None:
        self._req("POST", "/led/color", json={"hue": h, "saturation": s, "value": v})

    def list_movies(self) -> list[dict[str, Any]]:
        try:
            return self._req("GET", "/movies").json().get("movies", [])
        except httpx.HTTPError:
            return []


_singleton: TwinklyClient | None = None


def client() -> TwinklyClient:
    global _singleton
    if _singleton is None:
        _singleton = TwinklyClient()
    return _singleton
