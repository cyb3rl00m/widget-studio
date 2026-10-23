"""Tests for everything except the GTK window. Run:  python3 -m unittest discover tests

Uses a temporary HOME, a fake 'conky' that just sleeps, and sample weather data,
so it needs no network and touches nothing on your real desktop."""
import datetime
import os
import re
import shutil
import sys
import tempfile
import time
import unittest

TMP_HOME = tempfile.mkdtemp(prefix="ws-test-")
os.environ["HOME"] = TMP_HOME
for var in ("XDG_CONFIG_HOME", "XDG_CACHE_HOME", "XDG_DATA_HOME"):
    os.environ.pop(var, None)
os.environ["XDG_SESSION_TYPE"] = "wayland"
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from widget_studio import conkygen, daemon, fonts, paths, presets, process, providers, storage  # noqa: E402
from widget_studio.model import Widget  # noqa: E402

SAMPLE_WEATHER = {
    "current": {"temperature_2m": 7.6, "apparent_temperature": 4.8, "relative_humidity_2m": 91,
                "weather_code": 2, "wind_speed_10m": 12.3, "wind_direction_10m": 268},
    "daily": {"temperature_2m_max": [13.8], "temperature_2m_min": [3.9]},
}

FAKE_CONKY = """#!/bin/sh
if [ "$1" = "-v" ]; then echo "conky 1.24.2 compiled for Linux x86_64"; echo " Wayland"; exit 0; fi
exec python3 -c "import time; time.sleep(300)" "$@"
"""


def visible(markup: str) -> str:
    return re.sub(r"\$\{[^}]*\}", "", markup)


class ModelTests(unittest.TestCase):
    def test_round_trip_and_tolerance(self):
        w = Widget(name="Test")
        w.weather.location = "Jasło, PL"
        w.order = ["calendar", "clock"]
        again = Widget.from_dict(w.to_dict())
        self.assertEqual(again.to_dict(), w.to_dict())
        self.assertEqual(again.normalized_order(), ["calendar", "clock", "weather", "stats"])
        odd = Widget.from_dict({"name": "Old", "unknown": 1, "clock": {"size": 40, "bogus": True},
                                "order": ["stats", "nope"]})
        self.assertEqual(odd.clock.size, 40)
        self.assertEqual(odd.order, ["stats"])

    def test_storage(self):
        storage.save_widgets([Widget(name="A"), Widget(name="B")])
        self.assertEqual([w.name for w in storage.load_widgets()], ["A", "B"])

    def test_presets_apply(self):
        w = Widget()
        presets.apply_preset(w.appearance, "Nothing")
        self.assertEqual(w.appearance.highlight, "#d71921")


class ProviderTests(unittest.TestCase):
    def test_calendar_grid_is_aligned_and_marks_today(self):
        w = Widget()
        out = providers.render_calendar(w, today=datetime.date(2026, 10, 23))
        lines = out.splitlines()
        self.assertIn("OCTOBER 2026", lines[0])
        grid = lines[1:]
        self.assertEqual(len(grid), 1 + 5)  # header + 5 weeks
        self.assertTrue(all(len(visible(l)) == 20 for l in grid), [visible(l) for l in grid])
        self.assertIn("${color1}23${color}", out)
        self.assertIn("${color4}22${color}", out)       # past day dimmed
        self.assertIn(" 24", visible(grid[-2]))
        self.assertLess(len(out), 8192)                   # fits text_buffer_size

    def test_calendar_sunday_start(self):
        w = Widget()
        w.calendar.week_start = "sunday"
        out = providers.render_calendar(w, today=datetime.date(2026, 10, 23))
        self.assertIn("SU MO TU WE TH FR SA", visible(out))

    def test_calendar_centering(self):
        w = Widget()  # width 320, size 18 -> grid 288px -> offset 16 (measured on the real widget)
        self.assertEqual(providers.calendar_offset_px(w), 16)

    def test_weather_render(self):
        w = Widget()
        w.weather.latitude, w.weather.longitude, w.weather.location = 49.75, 21.47, "Jasło, PL"
        out = providers.render_weather(w, SAMPLE_WEATHER)
        self.assertIn("8°", out)
        self.assertIn("PARTLY CLOUDY", out)
        self.assertIn("JASŁO, PL", out)
        self.assertIn("H 14°  L 4°", out)
        self.assertIn("WIND 12 KM/H W", out)
        self.assertEqual(providers.render_weather(Widget(), None), "PICK A CITY IN WIDGET STUDIO")

    def test_escape_dollar(self):
        w = Widget()
        w.weather.latitude = w.weather.longitude = 0.0
        w.weather.location = "Ca$h City"
        self.assertIn("CA$$H CITY", providers.render_weather(w, SAMPLE_WEATHER))

    def test_date_and_timezone(self):
        w = Widget()
        self.assertTrue(providers.render_date(w).isupper())
        self.assertTrue(providers.valid_timezone("Europe/Sofia"))
        self.assertFalse(providers.valid_timezone("Mars/Base"))


class FontTests(unittest.TestCase):
    """The bug from the 1.0.0 screenshot: Doto wasn't available to Conky, a serif
    fallback was used, and the calendar fell apart."""

    def setUp(self):
        self._saved = fonts._table

    def tearDown(self):
        fonts._table = self._saved
        fonts.forget()

    def fake(self, table):
        fonts._table = lambda: table

    def test_calendar_falls_back_to_monospace_when_doto_missing(self):
        self.fake({"dejavu sans mono": 100, "dejavu sans": 0})
        w = Widget()  # display font Doto (missing)
        self.assertEqual(fonts.calendar_font(w.appearance)[0], "DejaVu Sans Mono")
        cal = providers.render_calendar(w, today=datetime.date(2026, 10, 23))
        self.assertIn("${font DejaVu Sans Mono:bold:size=18}", cal)
        self.assertNotIn("Doto", cal.split("\n", 2)[1])

    def test_calendar_uses_doto_when_installed(self):
        self.fake({"doto": 100, "dejavu sans mono": 100})
        self.assertEqual(fonts.calendar_font(Widget().appearance)[0], "Doto")

    def test_proportional_display_font_is_not_used_for_calendar(self):
        self.fake({"ubuntu": 0, "dejavu sans mono": 100})
        w = Widget()
        w.appearance.display_font = "Ubuntu"
        self.assertEqual(fonts.calendar_font(w.appearance)[0], "DejaVu Sans Mono")

    def test_installing_a_font_changes_the_config(self):
        w = Widget()
        self.fake({"dejavu sans mono": 100})
        before = conkygen.generate(w, "wayland")
        self.fake({"doto": 100, "dejavu sans mono": 100})
        after = conkygen.generate(w, "wayland")
        self.assertNotEqual(before, after)   # -> apply_widget restarts the widget
        self.assertIn("Doto=yes", after)

    def test_real_fontconfig(self):
        fonts.forget()
        if fonts._table() is None:
            self.skipTest("no fontconfig")
        self.assertTrue(fonts.is_monospace("DejaVu Sans Mono"))
        self.assertFalse(fonts.is_installed("Definitely Not A Font 123"))


class ConkyConfigTests(unittest.TestCase):
    def test_wayland_config(self):
        w = Widget()
        w.stats.enabled = True
        conf = conkygen.generate(w, "wayland")
        self.assertIn("out_to_wayland = true", conf)
        self.assertIn("own_window_type = 'desktop'", conf)
        self.assertIn("text_buffer_size = 8192", conf)
        self.assertNotIn("execpi", conf)
        self.assertIn(f"${{catp {paths.widget_cache_dir(w.id)}/calendar.txt}}", conf)
        self.assertIn("${cpubar cpu0 4}", conf)
        self.assertIn("own_window_argb_value = 217", conf)  # 85 %

    def test_x11_config(self):
        conf = conkygen.generate(Widget(), "x11")
        self.assertIn("out_to_x = true", conf)
        self.assertIn("below,sticky", conf)

    def test_order_and_options(self):
        w = Widget()
        w.order = ["calendar", "weather", "clock", "stats"]
        w.clock.use_24h, w.clock.timezone = False, "Europe/Sofia"
        conf = conkygen.generate(w, "wayland")
        self.assertLess(conf.index("calendar.txt"), conf.index("weather.txt"))
        self.assertIn("${tztime Europe/Sofia %I:%M}", conf)
        self.assertIn("${tztime Europe/Sofia %p}", conf)

    def test_lua_is_valid(self):
        lua = shutil.which("luac") or shutil.which("luac5.4") or shutil.which("luac5.3")
        if not lua:
            self.skipTest("no luac available")
        w = Widget(name="It's \"quoted\"")
        path = os.path.join(TMP_HOME, "check.lua")
        with open(path, "w") as f:
            f.write("conky = {}\n" + conkygen.generate(w, "wayland"))
        self.assertEqual(os.system(f"{lua} -p {path}"), 0)


class DaemonTests(unittest.TestCase):
    def test_refresh_writes_files(self):
        w = Widget()
        w.stats.enabled = True
        daemon.refresh_widget(w, weather=True)
        cache = paths.widget_cache_dir(w.id)
        for name in ("date.txt", "calendar.txt", "weather.txt", "temp.txt"):
            self.assertTrue(os.path.isfile(os.path.join(cache, name)), name)
        with open(os.path.join(cache, "weather.txt")) as f:
            self.assertEqual(f.read(), "PICK A CITY IN WIDGET STUDIO")

    def test_updater_restarts_itself_after_an_update(self):
        calls = []
        saved_exec, saved_disk = os.execv, daemon._version_on_disk
        try:
            os.execv = lambda *a: calls.append(a)
            daemon._version_on_disk = lambda: daemon.VERSION      # same version: stay
            daemon._restart_if_updated()
            self.assertEqual(calls, [])
            daemon._version_on_disk = lambda: "99.0.0"            # newer .deb installed
            daemon._restart_if_updated()
            self.assertEqual(len(calls), 1)
            self.assertEqual(calls[0][1][1:], ["-m", "widget_studio", "--daemon"])
        finally:
            os.execv, daemon._version_on_disk = saved_exec, saved_disk
        self.assertEqual(daemon._version_on_disk(), daemon.VERSION)  # reads the real file

    def test_single_updater_lock(self):
        lock = daemon.acquire_lock()
        self.assertIsNotNone(lock)
        self.assertTrue(daemon.is_running())
        with open(paths.DAEMON_LOCK) as f:          # checking must not erase the owner's PID
            self.assertEqual(f.read(), str(os.getpid()))
        lock.close()
        self.assertFalse(daemon.is_running())


class ProcessTests(unittest.TestCase):
    def setUp(self):
        paths.ensure_dirs()
        with open(paths.CONKY_APPIMAGE, "w") as f:
            f.write(FAKE_CONKY)
        os.chmod(paths.CONKY_APPIMAGE, 0o755)
        process._cached_conky = None

    def tearDown(self):
        for w in storage.load_widgets():
            process.stop_widget(w.id)

    def test_find_conky(self):
        self.assertEqual(process.find_conky(refresh=True), paths.CONKY_APPIMAGE)

    def test_exactly_one_copy_after_restarts(self):
        w = Widget(name="Run")
        storage.save_widgets([w])
        for _ in range(3):
            self.assertTrue(process.start_widget(w))
        time.sleep(0.5)
        self.assertEqual(len(process._processes_using(paths.conky_conf_path(w.id))), 1)
        process.stop_widget(w.id)
        self.assertFalse(process.is_widget_running(w.id))

    def test_apply_only_restarts_on_change(self):
        w = Widget(name="Apply")
        storage.save_widgets([w])
        process.apply_widget(w)
        time.sleep(0.3)
        first = process._processes_using(paths.conky_conf_path(w.id))
        process.apply_widget(w)               # nothing changed -> same process
        time.sleep(0.3)
        self.assertEqual(process._processes_using(paths.conky_conf_path(w.id)), first)
        w.gap_x = 99                          # config changed -> restarted
        process.apply_widget(w)
        time.sleep(0.3)
        now = process._processes_using(paths.conky_conf_path(w.id))
        self.assertEqual(len(now), 1)
        self.assertNotEqual(now, first)
        w.enabled = False
        process.apply_widget(w)
        self.assertFalse(process.is_widget_running(w.id))

    def test_parallel_restarts_never_double_a_widget(self):
        """App threads and the updater may restart the same widget at once."""
        import threading
        w = Widget(name="Race")
        storage.save_widgets([w])
        threads = [threading.Thread(target=process.start_widget, args=(w,)) for _ in range(6)]
        for t in threads:
            t.start()
        for t in threads:
            t.join()
        time.sleep(0.5)
        self.assertEqual(len(process._processes_using(paths.conky_conf_path(w.id))), 1)

    def test_stale_pid_file_never_kills_another_program(self):
        """After a reboot the saved PID may belong to something else entirely."""
        import subprocess
        bystander = subprocess.Popen(["sleep", "30"], start_new_session=True)
        try:
            w = Widget(name="Stale")
            os.makedirs(paths.widget_cache_dir(w.id), exist_ok=True)
            with open(process._pidfile(w.id), "w") as f:
                f.write(f"{bystander.pid} 12345\n")   # right PID, wrong start time
            self.assertIsNone(process._recorded_group(w.id))
            process.stop_widget(w.id)
            time.sleep(0.2)
            self.assertIsNone(bystander.poll(), "an unrelated process was killed")
        finally:
            bystander.kill()
            bystander.wait()

    def test_font_change_restarts_running_widget(self):
        w = Widget(name="Fonty")
        storage.save_widgets([w])
        saved = fonts._table
        try:
            fonts._table = lambda: {"dejavu sans mono": 100}
            process.apply_widget(w)
            time.sleep(0.3)
            first = process._processes_using(paths.conky_conf_path(w.id))
            daemon._restart_if_fonts_changed([w])      # nothing changed
            self.assertEqual(process._processes_using(paths.conky_conf_path(w.id)), first)
            fonts._table = lambda: {"doto": 100, "dejavu sans mono": 100}   # Doto installed
            daemon._restart_if_fonts_changed([w])
            time.sleep(0.3)
            now = process._processes_using(paths.conky_conf_path(w.id))
            self.assertEqual(len(now), 1)
            self.assertNotEqual(now, first)
        finally:
            fonts._table = saved
            fonts.forget()

    def test_autostart(self):
        process.set_autostart(True)
        with open(paths.AUTOSTART_FILE) as f:
            text = f.read()
        self.assertIn("--start", text)
        self.assertIn("widget_studio", text)
        process.set_autostart(False)
        self.assertFalse(process.autostart_enabled())


if __name__ == "__main__":
    unittest.main()
