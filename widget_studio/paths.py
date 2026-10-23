"""Where Widget Studio keeps its files."""
import os

HOME = os.path.expanduser("~")
CONFIG_DIR = os.path.join(os.environ.get("XDG_CONFIG_HOME") or os.path.join(HOME, ".config"), "widget-studio")
CACHE_DIR = os.path.join(os.environ.get("XDG_CACHE_HOME") or os.path.join(HOME, ".cache"), "widget-studio")
DATA_DIR = os.path.join(os.environ.get("XDG_DATA_HOME") or os.path.join(HOME, ".local", "share"), "widget-studio")
FONTS_DIR = os.path.join(os.environ.get("XDG_DATA_HOME") or os.path.join(HOME, ".local", "share"), "fonts")
AUTOSTART_DIR = os.path.join(os.environ.get("XDG_CONFIG_HOME") or os.path.join(HOME, ".config"), "autostart")

WIDGETS_FILE = os.path.join(CONFIG_DIR, "widgets.json")
CONKY_CONF_DIR = os.path.join(CONFIG_DIR, "conky")
CONKY_APPIMAGE = os.path.join(DATA_DIR, "conky.AppImage")
DAEMON_LOCK = os.path.join(CACHE_DIR, "daemon.lock")
AUTOSTART_FILE = os.path.join(AUTOSTART_DIR, "widget-studio.desktop")


def widget_cache_dir(widget_id: str) -> str:
    return os.path.join(CACHE_DIR, "widgets", widget_id)


def conky_conf_path(widget_id: str) -> str:
    return os.path.join(CONKY_CONF_DIR, f"{widget_id}.conf")


def ensure_dirs() -> None:
    for d in (CONFIG_DIR, CACHE_DIR, DATA_DIR, CONKY_CONF_DIR):
        os.makedirs(d, exist_ok=True)


def write_if_changed(path: str, text: str) -> bool:
    """Atomically write text to path. Returns True if the content changed."""
    try:
        with open(path, encoding="utf-8") as f:
            if f.read() == text:
                return False
    except OSError:
        pass
    os.makedirs(os.path.dirname(path), exist_ok=True)
    tmp = f"{path}.tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        f.write(text)
    os.replace(tmp, path)
    return True
