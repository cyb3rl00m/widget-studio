"""Main window: list of widgets on the left, settings for the selected one on the right."""
import os
import threading

import gi

gi.require_version("Gtk", "4.0")
gi.require_version("Adw", "1")
from gi.repository import Adw, Gio, GLib, Gtk, Pango  # noqa: E402

from . import APP_ID, APP_NAME, VERSION, WEBSITE, daemon, paths, process, storage  # noqa: E402
from .editor import WidgetEditor  # noqa: E402
from .model import Widget  # noqa: E402

APPLY_DELAY_MS = 450
NEW_WIDGET_SPOTS = ["top_right", "top_left", "bottom_right", "bottom_left", "middle_right"]

# Only one apply runs at a time, so starts and stops never overlap.
_apply_lock = threading.Lock()


def _in_thread(work, done=None):
    """Run work() off the UI thread, then done(result) back on it."""
    def runner():
        try:
            result, error = work(), None
        except Exception as exc:
            result, error = None, exc
        if done:
            GLib.idle_add(lambda: (done(result, error), False)[1])
    threading.Thread(target=runner, daemon=True).start()


class WidgetRow(Gtk.ListBoxRow):
    def __init__(self, widget):
        super().__init__()
        self.widget = widget
        box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=2,
                      margin_top=8, margin_bottom=8, margin_start=6, margin_end=6)
        self.title = Gtk.Label(xalign=0, ellipsize=Pango.EllipsizeMode.END)
        self.subtitle = Gtk.Label(xalign=0, ellipsize=Pango.EllipsizeMode.END)
        self.subtitle.add_css_class("dim-label")
        self.subtitle.add_css_class("caption")
        box.append(self.title)
        box.append(self.subtitle)
        self.set_child(box)
        self.refresh()

    def refresh(self, status=None):
        self.title.set_label(self.widget.name)
        if status is None:
            status = "Shown" if self.widget.enabled else "Hidden"
        self.subtitle.set_label(status)


class MainWindow(Adw.ApplicationWindow):
    def __init__(self, app):
        super().__init__(application=app, title=APP_NAME, default_width=980, default_height=760)
        self.widgets = storage.load_widgets()
        self.first_run = not os.path.exists(paths.WIDGETS_FILE)
        self.conky = None
        self.doto_missing = False
        self._apply_source = None
        self._pending_kinds = set()
        self.current = None

        if not self.widgets:
            self.widgets = [Widget(name="My widget")]
            storage.save_widgets(self.widgets)

        self._build_ui()
        self._install_actions()
        self._fill_sidebar()
        self.select(self.widgets[0])
        self._startup_checks()

    # ------------------------------------------------------------ layout

    def _build_ui(self):
        self.toasts = Adw.ToastOverlay()
        self.split = Adw.NavigationSplitView(min_sidebar_width=220, max_sidebar_width=300)

        # Sidebar
        side_header = Adw.HeaderBar()
        add = Gtk.Button(icon_name="list-add-symbolic", tooltip_text="Add a widget")
        add.connect("clicked", lambda *_: self.add_widget())
        side_header.pack_start(add)
        menu = Gio.Menu()
        menu.append("Show all widgets", "win.start-all")
        menu.append("Hide all widgets", "win.stop-all")
        menu.append(f"About {APP_NAME}", "win.about")
        side_header.pack_end(Gtk.MenuButton(icon_name="open-menu-symbolic", menu_model=menu,
                                            tooltip_text="Main menu"))
        self.listbox = Gtk.ListBox()
        self.listbox.add_css_class("navigation-sidebar")
        self.listbox.connect("row-selected", self._on_row_selected)
        side_scroll = Gtk.ScrolledWindow(vexpand=True, hscrollbar_policy=Gtk.PolicyType.NEVER)
        side_scroll.set_child(self.listbox)
        side_view = Adw.ToolbarView()
        side_view.add_top_bar(side_header)
        side_view.set_content(side_scroll)
        self.split.set_sidebar(Adw.NavigationPage(child=side_view, title="Widgets"))

        # Content
        self.content_title = Adw.WindowTitle(title="", subtitle="")
        content_header = Adw.HeaderBar(title_widget=self.content_title)
        widget_menu = Gio.Menu()
        widget_menu.append("Duplicate widget", "win.duplicate")
        widget_menu.append("Delete widget", "win.delete")
        content_header.pack_end(Gtk.MenuButton(icon_name="view-more-symbolic",
                                               menu_model=widget_menu,
                                               tooltip_text="Widget menu"))
        self.banner = Adw.Banner(revealed=False)
        self.banner.connect("button-clicked", self._on_banner_clicked)
        self.content_box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, vexpand=True)
        content_view = Adw.ToolbarView()
        content_view.add_top_bar(content_header)
        content_view.add_top_bar(self.banner)
        content_view.set_content(self.content_box)
        self.content_page = Adw.NavigationPage(child=content_view, title="Widget")
        self.split.set_content(self.content_page)

        self.toasts.set_child(self.split)
        self.set_content(self.toasts)

        breakpoint = Adw.Breakpoint.new(Adw.BreakpointCondition.parse("max-width: 640sp"))
        breakpoint.add_setter(self.split, "collapsed", True)
        self.add_breakpoint(breakpoint)

    def _install_actions(self):
        for name, callback in (("start-all", self._start_all), ("stop-all", self._stop_all),
                               ("about", self._about), ("duplicate", self._duplicate),
                               ("delete", self._confirm_delete)):
            action = Gio.SimpleAction.new(name, None)
            action.connect("activate", lambda *_a, cb=callback: cb())
            self.add_action(action)

    def toast(self, text):
        self.toasts.add_toast(Adw.Toast.new(text))

    # ------------------------------------------------------------ sidebar

    def _fill_sidebar(self):
        while (row := self.listbox.get_row_at_index(0)) is not None:
            self.listbox.remove(row)
        for w in self.widgets:
            self.listbox.append(WidgetRow(w))

    def _row_for(self, widget):
        i = 0
        while (row := self.listbox.get_row_at_index(i)) is not None:
            if row.widget is widget:
                return row
            i += 1
        return None

    def _on_row_selected(self, _listbox, row):
        if row is not None and row.widget is not self.current:
            self.select(row.widget)
        if row is not None:
            self.split.set_show_content(True)

    def select(self, widget):
        self.current = widget
        row = self._row_for(widget)
        if row is not None and self.listbox.get_selected_row() is not row:
            self.listbox.select_row(row)
        while (child := self.content_box.get_first_child()) is not None:
            self.content_box.remove(child)
        if widget is None:
            self.content_title.set_title("")
            self.content_box.append(self._empty_state())
            return
        self.content_title.set_title(widget.name)
        self.content_page.set_title(widget.name)
        editor = WidgetEditor(self, widget, lambda kind: self._on_edit(widget, kind),
                              self.doto_missing)
        editor.set_vexpand(True)
        self.content_box.append(editor)

    def _empty_state(self):
        button = Gtk.Button(label="Add a widget", halign=Gtk.Align.CENTER)
        button.add_css_class("pill")
        button.add_css_class("suggested-action")
        button.connect("clicked", lambda *_: self.add_widget())
        return Adw.StatusPage(icon_name=APP_ID, title="No widgets yet",
                              description="Make a clock, weather, calendar or system "
                                          "widget for your desktop.",
                              child=button, vexpand=True)

    # ------------------------------------------------------------ editing

    def _on_edit(self, widget, kind):
        if kind == "name":
            row = self._row_for(widget)
            if row:
                row.refresh()
            self.content_title.set_title(widget.name)
        self._pending_kinds.add(kind)
        if self._apply_source:
            GLib.source_remove(self._apply_source)
        self._apply_source = GLib.timeout_add(APPLY_DELAY_MS, self._apply_now, widget)

    def _apply_now(self, widget):
        self._apply_source = None
        kinds, self._pending_kinds = self._pending_kinds, set()
        storage.save_widgets(self.widgets)
        snapshot = widget.copy(new_id=False)
        fetch_weather = "weather" in kinds and snapshot.weather.enabled
        has_conky = self.conky is not None

        def work():
            with _apply_lock:
                if fetch_weather:
                    daemon.refresh_widget(snapshot, weather=True, force_weather=True)
                if has_conky:
                    process.apply_widget(snapshot)
                else:
                    process.write_config(snapshot)
                    daemon.refresh_widget(snapshot, weather=False)

        def done(_result, error):
            row = self._row_for(widget)
            if row:
                row.refresh(None if has_conky else "Needs Conky")
            if error:
                self.toast(f"Couldn't update the widget: {error}")

        _in_thread(work, done)
        return False

    def add_widget(self):
        spot = NEW_WIDGET_SPOTS[len(self.widgets) % len(NEW_WIDGET_SPOTS)]
        w = Widget(name=f"Widget {len(self.widgets) + 1}", alignment=spot)
        if self.current is not None:
            w.appearance = Widget.from_dict(self.current.to_dict()).appearance
            if self.current.weather.latitude is not None:
                w.weather = Widget.from_dict(self.current.to_dict()).weather
        self.widgets.append(w)
        self.listbox.append(WidgetRow(w))
        self.select(w)
        self._on_edit(w, "weather")

    def _duplicate(self):
        if self.current is None:
            return
        w = self.current.copy()
        w.name = f"{self.current.name} copy"
        w.gap_y += 40
        self.widgets.append(w)
        self.listbox.append(WidgetRow(w))
        self.select(w)
        self._on_edit(w, "weather")

    def _confirm_delete(self):
        widget = self.current
        if widget is None:
            return
        heading = f"Delete “{widget.name}”?"
        body = "The widget disappears from your desktop and its settings are removed."
        if hasattr(Adw, "AlertDialog"):
            dialog = Adw.AlertDialog(heading=heading, body=body)
        else:
            dialog = Adw.MessageDialog(transient_for=self, heading=heading, body=body)
        dialog.add_response("cancel", "Cancel")
        dialog.add_response("delete", "Delete")
        dialog.set_response_appearance("delete", Adw.ResponseAppearance.DESTRUCTIVE)
        dialog.set_default_response("cancel")
        dialog.set_close_response("cancel")
        dialog.connect("response", lambda _d, r: r == "delete" and self._delete(widget))
        if hasattr(Adw, "AlertDialog"):
            dialog.present(self)
        else:
            dialog.present()

    def _delete(self, widget):
        index = self.widgets.index(widget)
        self.widgets.remove(widget)
        row = self._row_for(widget)
        if row:
            self.listbox.remove(row)
        storage.save_widgets(self.widgets)
        _in_thread(lambda: process.remove_widget_files(widget.id))
        self.select(self.widgets[min(index, len(self.widgets) - 1)] if self.widgets else None)
        self.toast(f"Deleted “{widget.name}”")

    # ------------------------------------------------------------ start / stop all

    def _start_all(self):
        if not self.conky:
            self.toast("Install Conky first (see the bar at the top)")
            return
        snapshot = [w.copy(new_id=False) for w in self.widgets]

        def work():
            with _apply_lock:
                process.start_all(snapshot)

        _in_thread(work, lambda *_: self._refresh_rows())

    def _ensure_all(self):
        """Make sure every enabled widget is showing, without restarting ones that
        are already up to date (no flicker when you open the app)."""
        snapshot = [w.copy(new_id=False) for w in self.widgets]

        def work():
            with _apply_lock:
                process.ensure_daemon()
                for w in snapshot:
                    process.apply_widget(w)

        _in_thread(work, lambda *_: self._refresh_rows())

    def _stop_all(self):
        snapshot = [w.copy(new_id=False) for w in self.widgets]

        def work():
            with _apply_lock:
                process.stop_all(snapshot)

        _in_thread(work, lambda *_: self._refresh_rows("Hidden"))

    def _refresh_rows(self, status=None):
        i = 0
        while (row := self.listbox.get_row_at_index(i)) is not None:
            row.refresh(status)
            i += 1

    # ------------------------------------------------------------ startup checks

    def _startup_checks(self):
        if self.first_run:
            process.set_autostart(True)  # widgets should come back after a reboot

        def work():
            conky = process.find_conky()
            doto_missing = not process.font_installed("Doto")
            return conky, doto_missing

        def done(result, error):
            if error or result is None:
                return
            self.conky, doto_missing = result
            if doto_missing != self.doto_missing:
                self.doto_missing = doto_missing
                self.select(self.current)
            if self.conky is None:
                self._show_conky_banner()
            else:
                self._ensure_all()

        process.ensure_daemon()
        _in_thread(work, done)

    def _show_conky_banner(self):
        from .conkygen import session_type
        if session_type() == "wayland":
            self.banner.set_title("Widgets need Conky with Wayland support to appear on your desktop.")
        else:
            self.banner.set_title("Widgets need Conky to appear on your desktop.")
        self.banner.set_button_label("Install Conky")
        self.banner.set_revealed(True)
        self._refresh_rows("Needs Conky")

    def _on_banner_clicked(self, banner):
        banner.set_button_label(None)
        banner.set_title("Downloading Conky…")

        def progress(fraction):
            GLib.idle_add(lambda: (banner.set_title(f"Downloading Conky… {int(fraction * 100)}%"),
                                   False)[1])

        def work():
            process.install_conky(progress)
            return process.find_conky(refresh=True)

        def done(conky, error):
            if error or not conky:
                banner.set_title(f"Couldn't install Conky: {error or 'it did not start'}")
                banner.set_button_label("Try again")
                return
            self.conky = conky
            banner.set_revealed(False)
            self.toast("Conky installed. Your widgets are on the desktop now.")
            self._ensure_all()

        _in_thread(work, done)

    def install_doto(self, button, row, group):
        button.set_sensitive(False)
        button.set_label("Installing…")

        def done(_result, error):
            if error:
                button.set_sensitive(True)
                button.set_label("Try again")
                self.toast(f"Couldn't install the font: {error}")
                return
            self.doto_missing = False
            group.remove(row)
            # Running widgets loaded the font list when they started: restart them all.
            self._ensure_all()
            self.toast("Doto installed. Reopen Widget Studio to see it in the font picker.")

        _in_thread(process.install_doto_font, done)

    # ------------------------------------------------------------ about

    def _about(self):
        about = Adw.AboutWindow(
            transient_for=self, application_name=APP_NAME, application_icon=APP_ID,
            version=VERSION, developer_name="cyb3rl00m", website=WEBSITE,
            issue_url=f"{WEBSITE}/issues", license_type=Gtk.License.MIT_X11,
            comments="Design desktop widgets and pin them to your screen. "
                     "Drawn by Conky, weather by Open-Meteo.")
        about.present()


class WidgetStudioApp(Adw.Application):
    def __init__(self):
        super().__init__(application_id=APP_ID, flags=Gio.ApplicationFlags.DEFAULT_FLAGS)

    def do_activate(self):
        window = self.get_active_window() or MainWindow(self)
        window.present()


def run_app(argv) -> int:
    return WidgetStudioApp().run(argv)
