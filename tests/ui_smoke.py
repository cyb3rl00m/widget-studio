"""Smoke test for the GTK code on machines WITHOUT GTK4 (like CI containers).

It swaps 'gi' for a permissive stand-in, then builds the main window, the
editor for every widget, the location dialog and runs the main window actions.
This catches typos, wrong variable names and logic errors in the UI code. It
can't check how the window looks: run the real app for that.

    python3 tests/ui_smoke.py
"""
import os
import sys
import tempfile
import time
import types

os.environ["HOME"] = tempfile.mkdtemp(prefix="ws-ui-")
os.environ["XDG_SESSION_TYPE"] = "wayland"
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

CONNECTED = []  # (signal, callback, extra args) of everything the UI connects


def _method(name):
    def call(*args, **kwargs):
        if name == "connect":
            CONNECTED.append((args[0], args[1], args[2:]))
            return 1
        if name.startswith(("get_", "is_")) or name in ("present",):
            return None
        return Stub()
    return call


class StubMeta(type):
    def __getattr__(cls, name):
        if name.startswith("__"):
            raise AttributeError(name)
        if name[:1].isupper():
            return _stub_class(name)
        return _method(name)


class Stub(metaclass=StubMeta):
    def __init__(self, *args, **kwargs):
        pass

    def __getattr__(self, name):
        if name.startswith("__"):
            raise AttributeError(name)
        return _method(name)

    def __call__(self, *args, **kwargs):
        return Stub()


_classes = {}


def _stub_class(name):
    if name not in _classes:
        _classes[name] = StubMeta(name, (Stub,), {})
    return _classes[name]


def _module(name):
    mod = types.ModuleType(name)
    mod.__getattr__ = lambda attr: _stub_class(attr) if attr[:1].isupper() else _method(attr)
    return mod


gi = types.ModuleType("gi")
gi.require_version = lambda *a: None
repo = types.ModuleType("gi.repository")
for lib in ("Gtk", "Adw", "Gio", "GLib", "Gdk", "Pango"):
    setattr(repo, lib, _module(lib))
# GLib.idle_add should actually run callbacks so the "done" paths get exercised.
repo.GLib.idle_add = lambda fn, *a: fn(*a)
repo.GLib.timeout_add = lambda ms, fn, *a: 1
repo.GLib.source_remove = lambda *a: None
gi.repository = repo
sys.modules["gi"] = gi
sys.modules["gi.repository"] = repo


class FakeRGBA:
    red = green = blue = 0.5

    def parse(self, value):
        return True


repo.Gdk.RGBA = FakeRGBA

from widget_studio import app as app_mod, dialogs, storage  # noqa: E402
from widget_studio.model import Widget  # noqa: E402


def main():
    w = Widget(name="Smoke")
    w.stats.enabled = True
    storage.save_widgets([w, Widget(name="Second")])

    window = app_mod.MainWindow(app_mod.WidgetStudioApp())
    assert len(window.widgets) == 2

    # Every handler the UI connected must run without crashing. The fake row
    # returns realistic values for each kind of control.
    class FakeDesc:
        def get_family(self):
            return "DejaVu Sans Mono"

    class FakeRow(Stub):
        def get_text(self):
            return "Europe/Sofia"

        def get_active(self):
            return True

        def get_value(self):
            return 33.0

        def get_selected(self):
            return 1

        def get_enable_expansion(self):
            return True

        def get_rgba(self):
            return FakeRGBA()

        def get_font_desc(self):
            return FakeDesc()

    ran = 0
    for signal, callback, extra in list(CONNECTED):
        target = FakeRow()
        if signal == "changed" or signal == "clicked":
            callback(target, *extra)
        elif signal.startswith("notify::"):
            callback(target, None, *extra)
        else:
            continue
        ran += 1
    print("handlers run:", ran)
    first = window.widgets[0]  # (the "+" button handler also ran and added widgets)
    assert first.clock.timezone == "Europe/Sofia", first.clock.timezone
    assert first.appearance.text_font == "DejaVu Sans Mono"
    assert first.calendar.week_start == "sunday"

    window._on_edit(window.current, "name")
    window._on_edit(window.current, "weather")
    window._apply_now(window.current)
    before = len(window.widgets)
    window.add_widget()
    window._duplicate()
    assert len(window.widgets) == before + 2
    window._delete(window.widgets[-1])
    assert len(window.widgets) == before + 1
    while window.widgets:
        window._delete(window.widgets[0])  # deleting the last one shows the empty state
    window._ensure_all()
    window._stop_all()
    window._show_conky_banner()
    window._about()
    window._confirm_delete()
    window.select(None)

    dlg = dialogs.LocationDialog(window, lambda r: None)
    dlg._show_results(dlg._search_id, [{"name": "Jasło", "admin1": "Subcarpathia",
                                         "country": "Poland", "country_code": "PL",
                                         "latitude": 49.7, "longitude": 21.4}], None)
    dlg._show_results(dlg._search_id, [], "offline")
    time.sleep(1.5)  # let background threads finish
    _stop_updater()
    print("UI smoke test passed")


def _stop_updater():
    """The window starts a background updater for this test's temporary home; stop it."""
    import signal
    from widget_studio import paths
    try:
        with open(paths.DAEMON_LOCK) as f:
            os.kill(int(f.read().strip()), signal.SIGTERM)
    except (OSError, ValueError):
        pass


if __name__ == "__main__":
    main()
