"""Starting and stopping widgets, finding (or installing) a Conky that works on
this session, and the login autostart entry."""
from __future__ import annotations

import fcntl
import functools
import json
import os
import threading
from contextlib import contextmanager
import platform
import shutil
import signal
import subprocess
import sys
import time
import urllib.request

from . import conkygen, daemon, fonts, paths

CONKY_RELEASES_API = "https://api.github.com/repos/brndnmtthws/conky/releases/latest"
DOTO_URL = "https://github.com/google/fonts/raw/main/ofl/doto/Doto%5BROND%2Cwght%5D.ttf"


# ---------------------------------------------------------------- conky binary

def _conky_env() -> dict:
    env = dict(os.environ)
    # Lets AppImages run without FUSE (libfuse2), which many new distros lack.
    env["APPIMAGE_EXTRACT_AND_RUN"] = "1"
    return env


def conky_version_info(path: str) -> str:
    try:
        out = subprocess.run([path, "-v"], capture_output=True, text=True,
                             timeout=20, env=_conky_env())
        return out.stdout + out.stderr
    except (OSError, subprocess.SubprocessError):
        return ""


def _candidates() -> list[str]:
    found = []
    for p in (paths.CONKY_APPIMAGE, os.path.join(paths.HOME, ".local", "bin", "conky"),
              shutil.which("conky")):
        if p and os.path.isfile(p) and os.access(p, os.X_OK) and p not in found:
            found.append(p)
    return found


_cached_conky: tuple | None = None


def find_conky(refresh: bool = False) -> str | None:
    """Path to a Conky that can draw on this session (Wayland needs Wayland support)."""
    global _cached_conky
    session = conkygen.session_type()
    if _cached_conky and not refresh and _cached_conky[0] == session:
        return _cached_conky[1]
    result = None
    for path in _candidates():
        info = conky_version_info(path).lower()
        if not info:
            continue
        if session == "wayland" and "wayland" not in info:
            continue
        result = path
        break
    _cached_conky = (session, result)
    return result


def install_conky(progress=None) -> str:
    """Download the latest official Conky AppImage (built with Wayland support)."""
    if platform.machine() not in ("x86_64", "AMD64"):
        raise RuntimeError("The official Conky AppImage is only built for x86_64. "
                           "Install Conky from your distro instead.")
    req = urllib.request.Request(CONKY_RELEASES_API, headers={"User-Agent": "WidgetStudio"})
    with urllib.request.urlopen(req, timeout=20) as resp:
        release = json.load(resp)
    assets = [a["browser_download_url"] for a in release.get("assets", [])]
    images = [u for u in assets if u.lower().endswith(".appimage")
              and "x86_64" in u.lower() and "debug" not in u.lower()]
    if not images:
        raise RuntimeError("Couldn't find a Conky AppImage in the latest release.")
    images.sort(key=lambda u: "24.04" not in u)  # prefer the Ubuntu 24.04 build
    url = images[0]

    paths.ensure_dirs()
    tmp = paths.CONKY_APPIMAGE + ".part"
    req = urllib.request.Request(url, headers={"User-Agent": "WidgetStudio"})
    with urllib.request.urlopen(req, timeout=60) as resp, open(tmp, "wb") as out:
        total = int(resp.headers.get("Content-Length") or 0)
        done = 0
        while chunk := resp.read(256 * 1024):
            out.write(chunk)
            done += len(chunk)
            if progress and total:
                progress(done / total)
    os.chmod(tmp, 0o755)
    os.replace(tmp, paths.CONKY_APPIMAGE)
    find_conky(refresh=True)
    return paths.CONKY_APPIMAGE


# ---------------------------------------------------------------- fonts

def font_installed(family: str) -> bool:
    return fonts.is_installed(family)


def install_doto_font() -> None:
    os.makedirs(paths.FONTS_DIR, exist_ok=True)
    dest = os.path.join(paths.FONTS_DIR, "Doto.ttf")
    req = urllib.request.Request(DOTO_URL, headers={"User-Agent": "WidgetStudio"})
    with urllib.request.urlopen(req, timeout=60) as resp, open(dest + ".part", "wb") as out:
        shutil.copyfileobj(resp, out)
    os.replace(dest + ".part", dest)
    subprocess.run(["fc-cache", "-f"], capture_output=True, timeout=120)
    fonts.forget()
    if not fonts.is_installed("Doto"):
        raise RuntimeError("the font file was saved but fontconfig doesn't list it")


# ---------------------------------------------------------------- processes

_lock_state = threading.local()


@contextmanager
def _widget_lock():
    """Only one start/stop at a time, across the app's threads AND the background
    updater, so two restarts can never race into a doubled widget. Re-entrant
    within one thread (apply -> start -> stop)."""
    depth = getattr(_lock_state, "depth", 0)
    if depth:
        _lock_state.depth = depth + 1
        try:
            yield
        finally:
            _lock_state.depth -= 1
        return
    paths.ensure_dirs()
    with open(os.path.join(paths.CACHE_DIR, "process.lock"), "a+") as f:
        fcntl.flock(f, fcntl.LOCK_EX)
        _lock_state.depth = 1
        try:
            yield
        finally:
            _lock_state.depth = 0
            fcntl.flock(f, fcntl.LOCK_UN)


def _locked(func):
    @functools.wraps(func)
    def wrapper(*args, **kwargs):
        with _widget_lock():
            return func(*args, **kwargs)
    return wrapper


def _processes_using(conf_path: str) -> list[int]:
    """PIDs whose command line contains exactly this config file. Works for both
    the AppImage launcher and the real Conky process it starts."""
    pids = []
    me = os.getpid()
    for entry in os.listdir("/proc"):
        if not entry.isdigit() or int(entry) == me:
            continue
        try:
            with open(f"/proc/{entry}/cmdline", "rb") as f:
                args = f.read().split(b"\0")
        except OSError:
            continue
        if conf_path.encode() in args:
            pids.append(int(entry))
    return pids


def is_widget_running(widget_id: str) -> bool:
    return bool(_processes_using(paths.conky_conf_path(widget_id))) or bool(_recorded_group(widget_id))


def _start_time(pid: int) -> str | None:
    try:
        with open(f"/proc/{pid}/stat") as f:
            # field 22 = start time; split after the ")" so spaces in the name don't matter
            return f.read().rsplit(")", 1)[1].split()[19]
    except (OSError, IndexError):
        return None


def _pidfile(widget_id: str) -> str:
    return os.path.join(paths.widget_cache_dir(widget_id), "conky.pid")


def _record_group(widget_id: str, pid: int) -> None:
    started = _start_time(pid)
    if started:
        paths.write_if_changed(_pidfile(widget_id), f"{pid} {started}\n")


def _recorded_group(widget_id: str) -> int | None:
    """Process group of the Conky we started last, if that exact process still runs.
    The start time check stops a reused PID (e.g. after a reboot) from matching."""
    try:
        with open(_pidfile(widget_id)) as f:
            pid_text, started = f.read().split()
        pid = int(pid_text)
    except (OSError, ValueError):
        return None
    try:
        with open(f"/proc/{pid}/stat") as f:
            fields = f.read().rsplit(")", 1)[1].split()
    except (OSError, IndexError):
        return None
    if fields[0] == "Z" or fields[19] != started:  # exited (zombie) or a different process
        return None
    return pid


@_locked
def stop_widget(widget_id: str) -> None:
    conf = paths.conky_conf_path(widget_id)
    group = _recorded_group(widget_id)

    def signal_all(sig):
        if group:
            try:
                os.killpg(group, sig)  # the whole group: AppImage launcher + real Conky
            except OSError:
                pass
        for pid in _processes_using(conf):
            try:
                os.kill(pid, sig)
            except OSError:
                pass

    signal_all(signal.SIGTERM)
    deadline = time.time() + 3
    while time.time() < deadline and (_processes_using(conf) or _recorded_group(widget_id)):
        time.sleep(0.05)
    if _processes_using(conf) or _recorded_group(widget_id):
        signal_all(signal.SIGKILL)
    try:
        os.remove(_pidfile(widget_id))
    except OSError:
        pass


def write_config(widget) -> bool:
    """Write the widget's Conky config. Returns True if it changed."""
    paths.ensure_dirs()
    return paths.write_if_changed(paths.conky_conf_path(widget.id), conkygen.generate(widget))


@_locked
def start_widget(widget, conky: str | None = None) -> bool:
    """(Re)start exactly one Conky for this widget. Returns False if no usable Conky."""
    conky = conky or find_conky()
    if not conky:
        return False
    write_config(widget)
    daemon.refresh_widget(widget, weather=False)
    stop_widget(widget.id)
    conf = paths.conky_conf_path(widget.id)
    proc = subprocess.Popen([conky, "-c", conf],
                            env=_conky_env(), stdin=subprocess.DEVNULL,
                            stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
                            start_new_session=True)
    _record_group(widget.id, proc.pid)
    # Don't let the next start/stop run until this process is visible by its
    # config path; otherwise a quick second restart could miss it and leave
    # two copies running.
    deadline = time.time() + 3
    while time.time() < deadline and proc.poll() is None:
        if proc.pid in _processes_using(conf):
            break
        time.sleep(0.02)
    return True


@_locked
def apply_widget(widget) -> None:
    """Bring the running state in line with the widget settings. Only restarts
    Conky when its config actually changed (Conky would flicker otherwise)."""
    changed = write_config(widget)
    if not widget.enabled:
        stop_widget(widget.id)
        return
    daemon.refresh_widget(widget, weather=False)
    if changed or not is_widget_running(widget.id):
        start_widget(widget)


@_locked
def remove_widget_files(widget_id: str) -> None:
    stop_widget(widget_id)
    try:
        os.remove(paths.conky_conf_path(widget_id))
    except OSError:
        pass
    shutil.rmtree(paths.widget_cache_dir(widget_id), ignore_errors=True)


@_locked
def stop_all(widgets) -> None:
    for w in widgets:
        stop_widget(w.id)


@_locked
def start_all(widgets) -> bool:
    ensure_daemon()
    conky = find_conky()
    if not conky:
        return False
    for w in widgets:
        if w.enabled:
            start_widget(w, conky)
        else:
            stop_widget(w.id)
    return True


# ---------------------------------------------------------------- updater + autostart

def _package_parent() -> str:
    return os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def launch_command(*args: str) -> list[str]:
    """Command that runs Widget Studio, installed or straight from a source checkout."""
    installed = shutil.which("widget-studio")
    if installed and os.path.realpath(_package_parent()).startswith("/usr/"):
        return [installed, *args]
    return ["env", f"PYTHONPATH={_package_parent()}", sys.executable, "-m", "widget_studio", *args]


def ensure_daemon() -> None:
    if daemon.is_running():
        return
    subprocess.Popen(launch_command("--daemon"), stdin=subprocess.DEVNULL,
                     stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
                     start_new_session=True)


def autostart_enabled() -> bool:
    return os.path.isfile(paths.AUTOSTART_FILE)


def set_autostart(enabled: bool) -> None:
    if not enabled:
        try:
            os.remove(paths.AUTOSTART_FILE)
        except OSError:
            pass
        return
    os.makedirs(paths.AUTOSTART_DIR, exist_ok=True)
    cmd = " ".join(_desktop_quote(a) for a in launch_command("--start"))
    paths.write_if_changed(paths.AUTOSTART_FILE, (
        "[Desktop Entry]\n"
        "Type=Application\n"
        "Name=Widget Studio widgets\n"
        "Comment=Show your desktop widgets\n"
        f"Exec={cmd}\n"
        "Icon=io.github.cyb3rl00m.WidgetStudio\n"
        "X-GNOME-Autostart-enabled=true\n"
        "NoDisplay=true\n"
    ))


def _desktop_quote(arg: str) -> str:
    if all(c.isalnum() or c in "/._-=:+" for c in arg):
        return arg
    escaped = arg.replace("\\", "\\\\\\\\").replace('"', '\\\\"').replace("$", "\\\\$").replace("`", "\\\\`")
    return f'"{escaped}"'
