"""Spotify Web API wrapper (przez spotipy).

Sterowanie odtwarzaniem na aktywnym urządzeniu Spotify Connect (telefon, desktop,
głośnik). Wyszukiwanie po nazwie — "włącz Beatles" → szuka i gra.

Wymaga w .env:
    SPOTIFY_CLIENT_ID=...
    SPOTIFY_CLIENT_SECRET=...
    SPOTIFY_REDIRECT_URI=http://127.0.0.1:8888/callback   # opcjonalne (default)

Pierwszy run autoryzacji:
    python -m enrollment.auth_spotify
(otworzy przeglądarkę → log in → token zapisany w data/.spotify_cache.json)

CLI:
    python -m integrations.spotify status
    python -m integrations.spotify play "Beatles"
    python -m integrations.spotify pause
"""
from __future__ import annotations

import random
import sys
import unicodedata
from typing import Any, Optional

from config import DATA_DIR
from integrations.framework.config_store import cfg

# UWAGA: po rozszerzeniu scope trzeba RAZ przelogować: python -m enrollment.auth_spotify
# (refresh token trzyma stare uprawnienia; nowe — czytanie polubionych i playlist — wymagają
# ponownej zgody). Bez tego czytanie biblioteki zwróci 403 / wymusi ponowną autoryzację.
_SCOPE = (
    "user-modify-playback-state "
    "user-read-playback-state "
    "user-read-currently-playing "
    "user-library-read "
    "playlist-read-private "
    "playlist-read-collaborative"
)
_CACHE_PATH = DATA_DIR / ".spotify_cache.json"
_DEFAULT_REDIRECT = "http://127.0.0.1:8888/callback"

_client = None  # spotipy.Spotify


def _make_oauth():
    from spotipy.oauth2 import SpotifyOAuth

    client_id = cfg("spotify", "SPOTIFY_CLIENT_ID", env_fallback="SPOTIFY_CLIENT_ID")
    client_secret = cfg("spotify", "SPOTIFY_CLIENT_SECRET", env_fallback="SPOTIFY_CLIENT_SECRET")
    redirect_uri = cfg("spotify", "SPOTIFY_REDIRECT_URI",
                       env_fallback="SPOTIFY_REDIRECT_URI", default=_DEFAULT_REDIRECT)
    if not client_id or not client_secret:
        raise RuntimeError("Brak SPOTIFY_CLIENT_ID / SPOTIFY_CLIENT_SECRET (apka → Integracje, albo .env)")
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    return SpotifyOAuth(
        client_id=client_id,
        client_secret=client_secret,
        redirect_uri=redirect_uri,
        scope=_SCOPE,
        cache_path=str(_CACHE_PATH),
        open_browser=True,
    )


def _get_client(allow_interactive: bool = False):
    """Zwraca uwierzytelnionego klienta spotipy. Bez `allow_interactive` nie odpali OAuth flow —
    wymaga aktualnego tokena w cache (czyli wcześniejszego uruchomienia auth_spotify)."""
    global _client
    if _client is not None:
        return _client
    import spotipy

    auth = _make_oauth()
    if not allow_interactive and auth.get_cached_token() is None:
        raise RuntimeError(
            "Spotify nie autoryzowane. Uruchom raz: python -m enrollment.auth_spotify"
        )
    _client = spotipy.Spotify(auth_manager=auth)
    return _client


def _active_device_id() -> Optional[str]:
    sp = _get_client()
    devs = (sp.devices() or {}).get("devices", []) or []
    if not devs:
        return None
    for d in devs:
        if d.get("is_active"):
            return d["id"]
    return devs[0]["id"]


_market_cache: Optional[str] = None


def _market() -> str:
    """Kraj konta dla wyszukiwania (żeby polscy artyści / lokalne wyniki rankowały sensownie)."""
    global _market_cache
    if _market_cache is None:
        try:
            _market_cache = (_get_client().me() or {}).get("country") or "PL"
        except Exception:
            _market_cache = "PL"
    return _market_cache


def _fold(s: str) -> str:
    """Lowercase + bez diakrytyków (do dopasowań odpornych na polską odmianę/ogonki).
    'ł' nie rozkłada się przez NFKD (to osobna litera) — mapujemy ręcznie ł→l."""
    s = unicodedata.normalize("NFKD", s or "")
    s = "".join(c for c in s if not unicodedata.combining(c))
    return s.lower().replace("ł", "l").strip()


def _artist_matches(name: str, query: str) -> bool:
    """Czy `name` (artysta) to sensownie to, o co chodziło w `query` — odporne na odmianę
    ('Matę' → 'Mata', 'Podsiadłę' → 'Podsiadło')."""
    n, q = _fold(name), _fold(query)
    if not n or not q:
        return False
    if n == q or n in q or q in n:
        return True
    pref = max(3, min(len(n), len(q)) - 2)   # wspólny rdzeń (ucięta końcówka fleksyjna)
    return n[:pref] == q[:pref]


_LIKED_HINTS = ("ulubion", "polubion", "zapisane", "liked", "moich utwor", "moje utwor")
_OWN_PLAYLIST_HINTS = ("moja playlist", "moją playlist", "mojej playlist", "moich playlist",
                       "moje playlist", "mojej li", "moja li")
_PLAYLIST_STOPWORDS = (
    "z ", "graj ", "puść ", "pusc ", "włącz ", "wlacz ", "odtwórz ", "odtworz ", "nastaw ",
    "playlistę", "playliste", "playlista", "playlist", "moją", "moja", "moich", "mojej", "moje",
    "ulubione", "ulubionych", "ulubiona", "polubione", "polubionych", "lista", "listę", "liste",
)


def _playlist_name_hint(ql: str) -> str:
    out = ql
    for w in _PLAYLIST_STOPWORDS:
        out = out.replace(w, " ")
    return " ".join(out.split()).strip()


def _liked_track_uris(limit: int = 50, shuffle: bool = True) -> list[str]:
    sp = _get_client()
    items = (sp.current_user_saved_tracks(limit=min(50, limit)) or {}).get("items") or []
    uris = [it["track"]["uri"] for it in items if it.get("track") and it["track"].get("uri")]
    if shuffle:
        random.shuffle(uris)
    return uris


def _user_playlists() -> list[dict[str, Any]]:
    sp = _get_client()
    return [p for p in ((sp.current_user_playlists(limit=50) or {}).get("items") or []) if p]


def _match_user_playlist(name_hint: str) -> Optional[dict[str, Any]]:
    h = _fold(name_hint)
    if not h:
        return None
    pls = _user_playlists()
    for p in pls:                                  # dokładne
        if _fold(p["name"]) == h:
            return p
    for p in pls:                                  # zawieranie
        pn = _fold(p["name"])
        if h in pn or pn in h:
            return p
    return None


def _best_track(tracks: list[dict[str, Any]], query: str) -> Optional[dict[str, Any]]:
    """Wybierz utwór, preferując ten, gdzie GŁÓWNY artysta pasuje do frazy (nie kawałek gościnny)."""
    if not tracks:
        return None
    for t in tracks:
        if t.get("artists") and _artist_matches(t["artists"][0]["name"], query):
            return t
    return tracks[0]


def _resolve_query(query: str) -> Optional[dict[str, Any]]:
    """Zamienia frazę na coś grywalnego. Kolejność: Twoje playlisty / polubione → artysta
    (top utwory) → utwór (główny artysta) → album → fallback. Wszystko z `market` użytkownika."""
    sp = _get_client()
    q = query.strip()
    ql = _fold(q)
    market = _market()

    own = any(h in ql for h in _OWN_PLAYLIST_HINTS) or any(w in ql for w in ("moich", "moja ", "moje ", "mojej"))

    # 1) Playlisty (Twoje wg nazwy / losowa Twoja / publiczna z wyszukiwania)
    if "playlist" in ql or any(h in ql for h in _OWN_PLAYLIST_HINTS):
        name = _playlist_name_hint(ql)
        if name:
            pl = _match_user_playlist(name)
            if pl:
                return {"context_uri": pl["uri"], "kind": "playlist", "name": f"playlista {pl['name']}"}
        if own:
            pls = _user_playlists()
            if pls:
                pl = _match_user_playlist(name) or random.choice(pls)
                return {"context_uri": pl["uri"], "kind": "playlist", "name": f"playlista {pl['name']}"}
        res = sp.search(q=name or q, type="playlist", limit=5, market=market)
        items = (res.get("playlists") or {}).get("items") or []
        if items:
            p = items[0]
            return {"context_uri": p["uri"], "kind": "playlist", "name": f"playlista {p['name']}"}

    # 2) Polubione utwory ("ulubione/polubione", bez słowa 'playlist')
    if any(h in ql for h in _LIKED_HINTS):
        uris = _liked_track_uris()
        if uris:
            return {"uris": uris, "kind": "liked", "name": "polubione utwory (losowo)"}

    # 3) Wyszukiwanie publiczne z market użytkownika
    res = sp.search(q=q, type="artist,track,album", limit=10, market=market)
    artists = (res.get("artists") or {}).get("items") or []
    tracks = (res.get("tracks") or {}).get("items") or []
    albums = (res.get("albums") or {}).get("items") or []

    # 3a) Artysta (odporny na odmianę) → graj KONTEKST artysty (Spotify odtwarza jego popularne
    # kawałki). NIE używamy artist_top_tracks — ten endpoint zwraca 403 dla części aplikacji
    # (tryb deweloperski / ograniczenia quota Spotify). Kontekst artysty działa bez dodatkowego GET.
    art = next((a for a in artists if _artist_matches(a["name"], q)), None)
    if art:
        return {"context_uri": art["uri"], "kind": "artist", "name": art["name"]}

    # 3b) Utwór (preferuj główny artysta == fraza)
    t = _best_track(tracks, q)
    if t:
        who = t["artists"][0]["name"] if t.get("artists") else "?"
        return {"uris": [t["uri"]], "kind": "track", "name": f"{t['name']} — {who}"}

    # 3c) Album
    if albums:
        a = albums[0]
        return {"context_uri": a["uri"], "kind": "album", "name": a["name"]}

    # 3d) Fallback: pierwszy artysta jako kontekst
    if artists:
        a = artists[0]
        return {"context_uri": a["uri"], "kind": "artist", "name": a["name"]}

    return None


def play(query: Optional[str] = None) -> dict[str, Any]:
    sp = _get_client()
    device_id = _active_device_id()
    if device_id is None:
        raise RuntimeError(
            "Brak aktywnego urządzenia Spotify. Otwórz aplikację Spotify gdziekolwiek."
        )

    if query:
        match = _resolve_query(query)
        if match is None:
            raise RuntimeError(f"Nic nie znalazłam dla: {query}")
        kwargs = {"device_id": device_id}
        if "uris" in match:
            kwargs["uris"] = match["uris"]
        else:
            kwargs["context_uri"] = match["context_uri"]
        sp.start_playback(**kwargs)
        return {"playing": match["name"], "kind": match["kind"]}

    sp.start_playback(device_id=device_id)
    return {"playing": "resumed"}


def pause() -> None:
    _get_client().pause_playback()


def next_track() -> None:
    _get_client().next_track()


def previous_track() -> None:
    _get_client().previous_track()


def set_volume(percent: int) -> None:
    p = max(0, min(100, int(percent)))
    _get_client().volume(p)


def get_status() -> dict[str, Any]:
    try:
        sp = _get_client()
    except Exception as e:
        return {"reachable": False, "error": str(e)}
    try:
        cur = sp.current_playback()
    except Exception as e:
        return {"reachable": False, "error": str(e)}
    if not cur:
        return {"reachable": True, "is_playing": False}
    item = cur.get("item") or {}
    artists = item.get("artists") or []
    device = cur.get("device") or {}
    return {
        "reachable": True,
        "is_playing": cur.get("is_playing", False),
        "track": item.get("name"),
        "artist": ", ".join(a["name"] for a in artists) if artists else None,
        "album": (item.get("album") or {}).get("name"),
        "volume_percent": device.get("volume_percent"),
        "device": device.get("name"),
    }


def _cli() -> int:
    if len(sys.argv) < 2:
        print(__doc__)
        return 2
    cmd = sys.argv[1]
    if cmd == "status":
        import json
        print(json.dumps(get_status(), ensure_ascii=False, indent=2))
        return 0
    if cmd == "play":
        q = sys.argv[2] if len(sys.argv) > 2 else None
        print(play(q))
        return 0
    if cmd == "pause":
        pause(); print("paused"); return 0
    if cmd == "next":
        next_track(); print("next"); return 0
    if cmd == "prev":
        previous_track(); print("prev"); return 0
    if cmd == "vol" and len(sys.argv) > 2:
        set_volume(int(sys.argv[2])); print(f"vol {sys.argv[2]}%"); return 0
    print(f"unknown command: {cmd}", file=sys.stderr)
    return 2


if __name__ == "__main__":
    sys.exit(_cli())
