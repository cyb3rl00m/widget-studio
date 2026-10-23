"""Which fonts are installed, and which are monospace (asked from fontconfig).

Conky silently swaps a missing font for a default one, and a calendar drawn in
a non-monospace font can't line up, so we check before using a font."""
from __future__ import annotations

import subprocess
import time

FALLBACK_MONO = "DejaVu Sans Mono"   # installed on every Ubuntu-based system
_TTL = 20  # seconds; short, so a font installed a moment ago is noticed quickly
_cache: tuple[float, dict | None] = (0.0, None)


def _table() -> dict | None:
    """{family name (lowercase): spacing}. spacing 100 = mono, 90 = dual, 110 = charcell,
    0 = proportional. None if fontconfig isn't available."""
    global _cache
    stamp, table = _cache
    if table is not None and time.time() - stamp < _TTL:
        return table
    try:
        out = subprocess.run(["fc-list", "-f", "%{family}\t%{spacing}\n"],
                             capture_output=True, text=True, timeout=20).stdout
    except (OSError, subprocess.SubprocessError):
        _cache = (time.time(), None)
        return None
    table = {}
    for line in out.splitlines():
        families, _, spacing = line.partition("\t")
        try:
            value = int(spacing.strip() or 0)
        except ValueError:
            value = 0
        for name in families.split(","):
            name = name.strip().lower()
            if name:
                table[name] = max(table.get(name, 0), value)
    _cache = (time.time(), table)
    return table


def forget() -> None:
    """Call after installing a font."""
    global _cache
    _cache = (0.0, None)


def is_installed(family: str) -> bool:
    table = _table()
    return True if table is None else (family or "").strip().lower() in table


def is_monospace(family: str) -> bool:
    table = _table()
    if table is None:
        return True  # can't tell; trust the user's choice
    return table.get((family or "").strip().lower(), 0) >= 90


def calendar_font(appearance) -> tuple[str, bool]:
    """(family, bold) for the calendar grid. Always monospace so the columns line up."""
    if is_installed(appearance.display_font) and is_monospace(appearance.display_font):
        return appearance.display_font, appearance.display_bold
    if is_installed(appearance.text_font) and is_monospace(appearance.text_font):
        return appearance.text_font, appearance.display_bold
    return FALLBACK_MONO, appearance.display_bold


def fingerprint(appearance) -> str:
    """Changes whenever the widget's fonts become (un)available, so the Conky config
    changes too and the widget restarts with the new font list."""
    parts = []
    for family in (appearance.display_font, appearance.text_font):
        parts.append(f"{family}={'yes' if is_installed(family) else 'missing'}")
    parts.append(f"calendar={calendar_font(appearance)[0]}")
    return ", ".join(parts)
