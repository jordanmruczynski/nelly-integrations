"""Twinkly LEDs — domain wrapper: polskie nazwy kolorów, stan."""
from __future__ import annotations

from typing import Any

from integrations.twinkly import device as twinkly

# HSV: hue 0-359, saturation 0-255, value 0-255
COLORS: dict[str, tuple[int, int, int]] = {
    "czerwony": (0, 255, 255),
    "pomarańczowy": (20, 255, 255),
    "żółty": (50, 255, 255),
    "zielony": (120, 255, 255),
    "cyjan": (180, 255, 255),
    "niebieski": (240, 255, 255),
    "fioletowy": (280, 255, 255),
    "różowy": (320, 200, 255),
    "biały": (0, 0, 255),
    "ciepły biały": (30, 120, 230),
    "zimny biały": (210, 50, 255),
}


def color_names() -> list[str]:
    return list(COLORS.keys())


def turn_on() -> None:
    """Włącza światła: preferuje tryb movie (zapisane animacje), inaczej ciepły biały."""
    c = twinkly.client()
    if c.list_movies():
        c.set_mode("movie")
    else:
        h, s, v = COLORS["ciepły biały"]
        c.set_color_hsv(h, s, v)
        c.set_mode("color")


def turn_off() -> None:
    twinkly.client().set_mode("off")


def set_brightness(percent: int) -> None:
    twinkly.client().set_brightness(percent)


def set_color(name: str) -> None:
    if name not in COLORS:
        raise ValueError(f"Nieznany kolor '{name}'. Dostępne: {', '.join(COLORS)}")
    h, s, v = COLORS[name]
    c = twinkly.client()
    c.set_color_hsv(h, s, v)
    c.set_mode("color")


def get_status() -> dict[str, Any]:
    c = twinkly.client()
    mode = c.get_mode()
    b = c.get_brightness()
    return {
        "power": "off" if mode == "off" else "on",
        "mode": mode,
        "brightness_percent": b.get("value"),
    }
