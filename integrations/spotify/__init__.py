"""Integracja: Spotify (Web API przez spotipy) — kontrakt frameworku.

service.py = cała logika (OAuth, wyszukiwanie z polską odmianą, sterowanie playbackiem).
Token OAuth żyje w data/.spotify_cache.json (auto-refresh przez spotipy).
"""
from __future__ import annotations

from typing import Any, Callable

from integrations.spotify import service
from integrations.spotify.service import (  # noqa: F401 — publiczne API paczki
    get_status,
    next_track,
    pause,
    play,
    previous_track,
    set_volume,
)

TOOL_SCHEMAS: list[dict[str, Any]] = [
    {
        "type": "function",
        "function": {
            "name": "play_spotify",
            "description": (
                "Start Spotify playback. With `query`, play what the user means:\n"
                "- ARTIST → plays that artist's TOP songs. Pass the artist's BASE name (mianownik), "
                "e.g. 'Mata' (not 'Matę'), 'Dawid Podsiadło' (not 'Podsiadłę'). Matching tolerates "
                "Polish inflection, but the base form is best.\n"
                "- SONG or ALBUM → name it ('Despacito', 'album Autentyzm').\n"
                "- PLAYLIST → 'playlista chillout'; the user's OWN playlist → 'moja playlista <nazwa>'.\n"
                "- LIKED songs → 'ulubione' / 'polubione' (plays their saved tracks, shuffled).\n"
                "Uses the user's country market so local (e.g. Polish) results rank correctly. "
                "Without `query`, resume current playback. Requires an active Spotify Connect device."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "query": {
                        "type": "string",
                        "description": "What to play, e.g. 'Beatles', 'Yesterday Beatles', 'playlist chillout'.",
                    }
                },
                "required": [],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "pause_spotify",
            "description": "Pause Spotify playback.",
            "parameters": {"type": "object", "properties": {}, "required": []},
        },
    },
    {
        "type": "function",
        "function": {
            "name": "next_spotify_track",
            "description": "Skip to the next Spotify track.",
            "parameters": {"type": "object", "properties": {}, "required": []},
        },
    },
    {
        "type": "function",
        "function": {
            "name": "previous_spotify_track",
            "description": "Go back to the previous Spotify track.",
            "parameters": {"type": "object", "properties": {}, "required": []},
        },
    },
    {
        "type": "function",
        "function": {
            "name": "set_spotify_volume",
            "description": "Set Spotify playback volume (0–100).",
            "parameters": {
                "type": "object",
                "properties": {
                    "percent": {"type": "integer", "minimum": 0, "maximum": 100},
                },
                "required": ["percent"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "get_spotify_status",
            "description": "Read current track, artist, album, volume and active device.",
            "parameters": {"type": "object", "properties": {}, "required": []},
        },
    },
]


def _spotify_play(query: str | None = None) -> dict[str, Any]:
    return play(query)


def _spotify_pause() -> dict[str, str]:
    pause()
    return {"ok": "spotify paused"}


def _spotify_next() -> dict[str, str]:
    next_track()
    return {"ok": "spotify next"}


def _spotify_prev() -> dict[str, str]:
    previous_track()
    return {"ok": "spotify prev"}


def _spotify_volume(percent: int) -> dict[str, str]:
    set_volume(percent)
    return {"ok": f"spotify volume {percent}%"}


def _spotify_status() -> dict[str, Any]:
    return get_status()


TOOLS: dict[str, Callable[..., dict[str, Any]]] = {
    "play_spotify": _spotify_play,
    "pause_spotify": _spotify_pause,
    "next_spotify_track": _spotify_next,
    "previous_spotify_track": _spotify_prev,
    "set_spotify_volume": _spotify_volume,
    "get_spotify_status": _spotify_status,
}


def status_line() -> str:
    try:
        s = get_status()
    except Exception as e:
        return f"Spotify: (błąd: {e})"
    if not s.get("reachable"):
        return f"Spotify: niedostępne ({s.get('error', '?')})"
    if not s.get("is_playing"):
        if s.get("track"):
            return f"Spotify: pauza (ostatnio: {s['track']} — {s.get('artist', '?')})"
        return "Spotify: nie gra"
    return (
        f"Spotify: gra '{s['track']}' — {s.get('artist', '?')}, "
        f"vol={s.get('volume_percent', '?')}%, "
        f"device={s.get('device', '?')}"
    )


def tile(status: dict[str, Any]) -> dict[str, Any]:
    if not status.get("reachable"):
        return {"value": "Offline", "meta": str(status.get("error", ""))[:40]}
    if status.get("is_playing"):
        return {"value": "Gra", "meta": f"{status.get('track', '?')} — {status.get('artist', '?')}",
                "tone": "accent"}
    return {"value": "Pauza" if status.get("track") else "Nie gra", "meta": status.get("track") or ""}


# OAuth dla parowania z apki (Faza 2): framework jest provider-agnostyczny —
# integracja sama buduje URL autoryzacji i wymienia code na token (spotipy cache).
def _build_authorize_url() -> str:
    return service._make_oauth().get_authorize_url()


def _exchange_code(code: str) -> None:
    service._make_oauth().get_access_token(code, as_dict=False)
    reset()  # nowy token → nowy klient


OAUTH: dict[str, Callable[..., Any]] = {
    "build_authorize_url": _build_authorize_url,
    "exchange_code": _exchange_code,
}

PAIR_ACTIONS: dict[str, Callable[..., Any]] = {
    "test": lambda: get_status(),
}


def reset() -> None:
    """Po zmianie client_id/secret lub tokena zrzuć klienta spotipy."""
    service._client = None
    service._market_cache = None
