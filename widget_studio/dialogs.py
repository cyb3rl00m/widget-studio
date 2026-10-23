"""Weather location search dialog."""
import threading

import gi

gi.require_version("Gtk", "4.0")
gi.require_version("Adw", "1")
from gi.repository import Adw, GLib, Gtk  # noqa: E402

from . import providers  # noqa: E402


class LocationDialog(Adw.Window):
    """Search a city by name (optionally 'City, Country') and pick one."""

    def __init__(self, parent, on_chosen):
        super().__init__(transient_for=parent, modal=True, title="Weather location",
                         default_width=440, default_height=560)
        self._on_chosen = on_chosen
        self._search_id = 0

        header = Adw.HeaderBar()
        view = Adw.ToolbarView()
        view.add_top_bar(header)

        box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=12,
                      margin_top=12, margin_bottom=12, margin_start=12, margin_end=12)
        self.entry = Gtk.SearchEntry(placeholder_text="City, e.g. Berlin or Sofia, BG")
        self.entry.set_search_delay(400)
        self.entry.connect("search-changed", self._on_search)
        self.entry.connect("activate", self._on_search)
        box.append(self.entry)

        self.status = Gtk.Label(label="Type a city name. Add a country to narrow it down.",
                                wrap=True, xalign=0)
        self.status.add_css_class("dim-label")
        box.append(self.status)

        self.results = Gtk.ListBox(selection_mode=Gtk.SelectionMode.NONE)
        self.results.add_css_class("boxed-list")
        self.results.connect("row-activated", self._on_row_activated)
        scroller = Gtk.ScrolledWindow(vexpand=True, hscrollbar_policy=Gtk.PolicyType.NEVER)
        scroller.set_child(self.results)
        box.append(scroller)

        view.set_content(box)
        self.set_content(view)
        self.entry.grab_focus()

    def _clear(self):
        while (row := self.results.get_row_at_index(0)) is not None:
            self.results.remove(row)

    def _on_search(self, *_):
        query = self.entry.get_text().strip()
        self._search_id += 1
        search_id = self._search_id
        if len(query.partition(",")[0].strip()) < 2:
            self._clear()
            return
        self.status.set_label("Searching…")

        def work():
            try:
                found, error = providers.search_locations(query), None
            except Exception as exc:  # network problems etc.
                found, error = [], str(exc)
            GLib.idle_add(self._show_results, search_id, found, error)

        threading.Thread(target=work, daemon=True).start()

    def _show_results(self, search_id, found, error):
        if search_id != self._search_id:
            return False  # an older search finished late; ignore it
        self._clear()
        if error:
            self.status.set_label(f"Couldn't reach the weather service: {error}")
        elif not found:
            self.status.set_label("No matches. Try another spelling, or leave out the country.")
        else:
            self.status.set_label("Pick your city:")
        for result in found:
            subtitle = ", ".join(x for x in (result.get("admin1"), result.get("country")) if x)
            row = Adw.ActionRow(title=result.get("name", "?"), subtitle=subtitle,
                                activatable=True, use_markup=False)
            row.add_suffix(Gtk.Image.new_from_icon_name("go-next-symbolic"))
            row.result = result
            self.results.append(row)
        return False

    def _on_row_activated(self, _listbox, row):
        self._on_chosen(row.result)
        self.close()
