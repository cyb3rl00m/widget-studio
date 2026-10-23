"""Background updater. Writes date, calendar, weather and temperature text into
~/.cache/widget-studio/widgets/<id>/*.txt every few seconds. Conky only reads
those files, so nothing heavy ever runs inside Conky itself.

Only one updater runs at a time (file lock)."""
from __future__ import annotations

import fcntl
import os
import re
import sys
import time

from . import VERSION, paths, providers, storage

TICK = 5  # seconds
FONT_CHECK_TICKS = 12  # once a minute


def _restart_if_fonts_changed(widgets) -> None:
    """A font installed while widgets are running (by the app or by hand) only
    shows up after Conky restarts. Regenerating the config notices the change
    (see conkygen's font fingerprint) and restarts just those widgets."""
    from . import process  # imported here: process imports this module
    for widget in widgets:
        try:
            if widget.enabled and process.is_widget_running(widget.id):
                process.apply_widget(widget)
        except Exception:
            pass


def refresh_widget(widget, weather: bool = True, force_weather: bool = False, sensor=None) -> None:
    """Write all cache files for one widget."""
    cache = paths.widget_cache_dir(widget.id)
    os.makedirs(cache, exist_ok=True)

    paths.write_if_changed(os.path.join(cache, "date.txt"), providers.render_date(widget))
    paths.write_if_changed(os.path.join(cache, "calendar.txt"), providers.render_calendar(widget))

    if widget.stats.enabled and widget.stats.temperature:
        if sensor is None:
            sensor = providers.find_cpu_sensor()
        paths.write_if_changed(os.path.join(cache, "temp.txt"),
                               providers.render_temperature(widget, sensor))

    if weather and widget.weather.enabled:
        w = widget.weather
        data = None
        if w.latitude is not None and w.longitude is not None:
            data, _ = providers.get_weather(w.latitude, w.longitude, w.units, force=force_weather)
        paths.write_if_changed(os.path.join(cache, "weather.txt"),
                               providers.render_weather(widget, data))


def acquire_lock():
    """Returns an open lock file if we are the only updater, else None."""
    paths.ensure_dirs()
    f = open(paths.DAEMON_LOCK, "a+")  # "a+" so a failed attempt never erases the owner's PID
    try:
        fcntl.flock(f, fcntl.LOCK_EX | fcntl.LOCK_NB)
    except OSError:
        f.close()
        return None
    f.seek(0)
    f.truncate()
    f.write(str(os.getpid()))
    f.flush()
    return f


def is_running() -> bool:
    lock = acquire_lock()
    if lock is None:
        return True
    lock.close()
    return False


def _version_on_disk() -> str | None:
    """VERSION as written in the installed __init__.py right now (it changes when a
    newer .deb is installed while this updater keeps running the old code)."""
    try:
        with open(os.path.join(os.path.dirname(os.path.abspath(__file__)), "__init__.py"),
                  encoding="utf-8") as f:
            match = re.search(r'^VERSION\s*=\s*"([^"]+)"', f.read(), re.M)
        return match.group(1) if match else None
    except OSError:
        return None


def _restart_if_updated() -> None:
    """After an update, replace this process with the new code (same PID, same
    session). The lock file is closed on exec, so the new updater takes it over."""
    on_disk = _version_on_disk()
    if on_disk and on_disk != VERSION:
        os.execv(sys.executable, [sys.executable, "-m", "widget_studio", "--daemon"])


def run() -> int:
    lock = acquire_lock()
    if lock is None:
        return 0  # another updater is already running
    sensor = providers.find_cpu_sensor()
    widgets, mtime = [], -1.0
    failed_at: dict[str, float] = {}
    tick = 0

    while True:
        tick += 1
        if tick % FONT_CHECK_TICKS == 0:
            _restart_if_updated()
            _restart_if_fonts_changed(widgets)

        new_mtime = storage.widgets_mtime()
        if new_mtime != mtime:
            widgets, mtime = storage.load_widgets(), new_mtime

        for widget in widgets:
            if not widget.enabled:
                continue
            # After a failed download, wait 2 minutes before trying again.
            key = f"{widget.weather.latitude},{widget.weather.longitude},{widget.weather.units}"
            retry_ok = time.time() - failed_at.get(key, 0) > 120
            try:
                refresh_widget(widget, weather=retry_ok, sensor=sensor)
                with open(os.path.join(paths.widget_cache_dir(widget.id), "weather.txt"),
                          encoding="utf-8") as f:
                    if "UNAVAILABLE" in f.read():
                        failed_at[key] = time.time()
            except Exception:
                pass  # never let one broken widget stop the others
        time.sleep(TICK)
