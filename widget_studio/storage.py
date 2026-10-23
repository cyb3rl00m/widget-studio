"""Load and save the list of widgets (~/.config/widget-studio/widgets.json)."""
from __future__ import annotations

import json
import os

from . import paths
from .model import Widget


def load_widgets() -> list[Widget]:
    try:
        with open(paths.WIDGETS_FILE, encoding="utf-8") as f:
            data = json.load(f)
    except (OSError, ValueError):
        return []
    items = data.get("widgets", []) if isinstance(data, dict) else []
    return [Widget.from_dict(item) for item in items if isinstance(item, dict)]


def save_widgets(widgets: list[Widget]) -> None:
    paths.ensure_dirs()
    text = json.dumps({"version": 1, "widgets": [w.to_dict() for w in widgets]},
                      indent=2, ensure_ascii=False)
    paths.write_if_changed(paths.WIDGETS_FILE, text + "\n")


def widgets_mtime() -> float:
    try:
        return os.path.getmtime(paths.WIDGETS_FILE)
    except OSError:
        return 0.0
