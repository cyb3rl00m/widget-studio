"""The settings page for one widget."""
import gi

gi.require_version("Gtk", "4.0")
gi.require_version("Adw", "1")
from gi.repository import Adw, Gdk, Gtk, Pango  # noqa: E402

from . import process, providers  # noqa: E402
from .model import ALIGNMENTS, SECTION_TITLES  # noqa: E402
from .presets import PRESETS, apply_preset  # noqa: E402


def _rgba(hex_color: str) -> Gdk.RGBA:
    rgba = Gdk.RGBA()
    if not rgba.parse(hex_color or "#000000"):
        rgba.parse("#000000")
    return rgba


def _hex(rgba: Gdk.RGBA) -> str:
    return "#{:02x}{:02x}{:02x}".format(round(rgba.red * 255), round(rgba.green * 255),
                                        round(rgba.blue * 255))


class WidgetEditor(Adw.PreferencesPage):
    """on_change(kind) is called after every edit. kind is 'config', 'name' or 'weather'."""

    def __init__(self, window, widget, on_change, doto_missing: bool):
        super().__init__()
        self.window = window
        self.widget = widget
        self.on_change = on_change
        self._refreshers = []  # callables that reload rows from the model (after a theme)

        self._build_general()
        self._build_sections()
        self._build_layout()
        self._build_position()
        self._build_appearance()
        self._build_fonts(doto_missing)
        self._build_startup()

    # ------------------------------------------------------------ row helpers

    def _changed(self, kind="config"):
        self.on_change(kind)

    def switch(self, obj, attr, title, subtitle=None, kind="config"):
        row = Adw.SwitchRow(title=title, active=bool(getattr(obj, attr)))
        if subtitle:
            row.set_subtitle(subtitle)

        def on_toggle(r, _p):
            if getattr(obj, attr) != r.get_active():
                setattr(obj, attr, r.get_active())
                self._changed(kind)

        row.connect("notify::active", on_toggle)
        self._refreshers.append(lambda: row.set_active(bool(getattr(obj, attr))))
        return row

    def spin(self, obj, attr, title, low, high, step=1, subtitle=None):
        row = Adw.SpinRow.new_with_range(low, high, step)
        row.set_title(title)
        if subtitle:
            row.set_subtitle(subtitle)
        row.set_value(getattr(obj, attr))

        def on_value(r, _p):
            value = int(r.get_value())
            if getattr(obj, attr) != value:
                setattr(obj, attr, value)
                self._changed()

        row.connect("notify::value", on_value)
        self._refreshers.append(lambda: row.set_value(getattr(obj, attr)))
        return row

    def combo(self, obj, attr, title, options, kind="config", subtitle=None):
        values = [v for v, _ in options]
        row = Adw.ComboRow(title=title, model=Gtk.StringList.new([label for _, label in options]))
        if subtitle:
            row.set_subtitle(subtitle)
        current = getattr(obj, attr)
        row.set_selected(values.index(current) if current in values else 0)

        def on_selected(r, _p):
            value = values[r.get_selected()]
            if getattr(obj, attr) != value:
                setattr(obj, attr, value)
                self._changed(kind)

        row.connect("notify::selected", on_selected)
        return row

    def color(self, obj, attr, title, subtitle=None):
        row = Adw.ActionRow(title=title)
        if subtitle:
            row.set_subtitle(subtitle)
        button = Gtk.ColorDialogButton.new(Gtk.ColorDialog(with_alpha=False))
        button.set_valign(Gtk.Align.CENTER)
        button.set_rgba(_rgba(getattr(obj, attr)))

        def on_color(b, _p):
            value = _hex(b.get_rgba())
            if getattr(obj, attr) != value:
                setattr(obj, attr, value)
                self._changed()

        button.connect("notify::rgba", on_color)
        row.add_suffix(button)
        row.set_activatable_widget(button)
        self._refreshers.append(lambda: button.set_rgba(_rgba(getattr(obj, attr))))
        return row

    def font(self, obj, attr, title, subtitle=None):
        row = Adw.ActionRow(title=title)
        if subtitle:
            row.set_subtitle(subtitle)
        button = Gtk.FontDialogButton.new(Gtk.FontDialog())
        button.set_level(Gtk.FontLevel.FAMILY)
        button.set_valign(Gtk.Align.CENTER)
        button.set_font_desc(Pango.FontDescription.from_string(getattr(obj, attr)))

        def on_font(b, _p):
            desc = b.get_font_desc()
            family = desc.get_family() if desc else None
            if family and getattr(obj, attr) != family:
                setattr(obj, attr, family)
                self._changed()

        button.connect("notify::font-desc", on_font)
        row.add_suffix(button)
        row.set_activatable_widget(button)
        self._refreshers.append(
            lambda: button.set_font_desc(Pango.FontDescription.from_string(getattr(obj, attr))))
        return row

    def entry(self, obj, attr, title, validate=None, kind="config"):
        row = Adw.EntryRow(title=title, text=getattr(obj, attr) or "")

        def on_text(r):
            value = r.get_text().strip()
            if validate and not validate(value):
                r.add_css_class("error")
                return
            r.remove_css_class("error")
            if getattr(obj, attr) != value:
                setattr(obj, attr, value)
                self._changed(kind)

        row.connect("changed", on_text)
        return row

    # ------------------------------------------------------------ groups

    def _build_general(self):
        w = self.widget
        group = Adw.PreferencesGroup()
        group.add(self.entry(w, "name", "Name", validate=lambda v: bool(v), kind="name"))
        group.add(self.switch(w, "enabled", "Show on desktop"))
        self.add(group)

    def _build_sections(self):
        w = self.widget
        group = Adw.PreferencesGroup(title="Sections",
                                     description="Turn each part of the widget on or off.")

        # Clock and date
        clock = self._section_expander("clock", "Time, date and time zone")
        c = w.clock
        clock.add_row(self.switch(c, "use_24h", "24-hour clock"))
        clock.add_row(self.switch(c, "seconds", "Show seconds"))
        clock.add_row(self.switch(c, "show_date", "Show date"))
        clock.add_row(self.switch(c, "uppercase", "Date in capitals"))
        clock.add_row(self.entry(c, "timezone", "Time zone (empty = this computer's)",
                                 validate=providers.valid_timezone))
        clock.add_row(self.spin(c, "size", "Clock size", 12, 160))
        clock.add_row(self.spin(c, "date_size", "Date size", 6, 60))
        group.add(clock)

        # Weather
        weather = self._section_expander("weather", "Current weather from Open-Meteo")
        wo = w.weather
        self.location_row = Adw.ActionRow(title="Location", use_markup=False)
        self._update_location_subtitle()
        change = Gtk.Button(label="Change…", valign=Gtk.Align.CENTER)
        change.connect("clicked", self._on_change_location)
        self.location_row.add_suffix(change)
        self.location_row.set_activatable_widget(change)
        weather.add_row(self.location_row)
        weather.add_row(self.combo(wo, "units", "Units",
                                   [("metric", "Metric (°C, km/h)"), ("imperial", "Imperial (°F, mph)")],
                                   kind="weather"))
        weather.add_row(self.switch(wo, "high_low", "Show today's high and low"))
        weather.add_row(self.switch(wo, "details", "Show feels like, humidity and wind"))
        weather.add_row(self.spin(wo, "size", "Temperature size", 10, 100))
        group.add(weather)

        # Calendar
        cal = self._section_expander("calendar", "This month, today highlighted")
        co = w.calendar
        cal.add_row(self.combo(co, "week_start", "Week starts on",
                               [("monday", "Monday"), ("sunday", "Sunday")]))
        cal.add_row(self.switch(co, "dim_past", "Dim days that have passed"))
        cal.add_row(self.switch(co, "show_title", "Show month name"))
        cal.add_row(self.spin(co, "size", "Calendar size", 8, 48,
                              subtitle="The grid is centered automatically"))
        group.add(cal)

        # System stats
        stats = self._section_expander("stats", "CPU, memory, disk and temperature")
        so = w.stats
        stats.add_row(self.switch(so, "cpu", "CPU usage"))
        stats.add_row(self.switch(so, "ram", "Memory usage"))
        stats.add_row(self.switch(so, "disk", "Disk usage"))
        stats.add_row(self.entry(so, "disk_path", "Disk to show (folder)",
                                 validate=lambda v: v.startswith("/") and " " not in v))
        stats.add_row(self.switch(so, "temperature", "CPU temperature"))
        stats.add_row(self.switch(so, "bars", "Show usage bars"))
        group.add(stats)

        self.add(group)

    def _section_expander(self, name, subtitle):
        section = self.widget.section(name)
        row = Adw.ExpanderRow(title=SECTION_TITLES[name], subtitle=subtitle,
                              show_enable_switch=True, enable_expansion=section.enabled)
        row.set_expanded(False)

        def on_enable(r, _p):
            if section.enabled != r.get_enable_expansion():
                section.enabled = r.get_enable_expansion()
                self._changed("weather" if name == "weather" else "config")

        row.connect("notify::enable-expansion", on_enable)
        return row

    def _build_layout(self):
        w = self.widget
        group = Adw.PreferencesGroup(title="Layout")
        group.add(self.switch(w, "labels", "Section labels", "Small headings like WEATHER"))
        group.add(self.switch(w, "dividers", "Divider lines between sections"))
        self.add(group)

        self.order_group = Adw.PreferencesGroup(title="Order",
                                                description="Top to bottom on the widget.")
        self._order_rows = []
        self._fill_order()
        self.add(self.order_group)

    def _fill_order(self):
        for row in self._order_rows:
            self.order_group.remove(row)
        self._order_rows = []
        order = self.widget.normalized_order()
        for i, name in enumerate(order):
            row = Adw.ActionRow(title=SECTION_TITLES[name])
            up = Gtk.Button(icon_name="go-up-symbolic", valign=Gtk.Align.CENTER,
                            sensitive=i > 0, tooltip_text="Move up")
            down = Gtk.Button(icon_name="go-down-symbolic", valign=Gtk.Align.CENTER,
                              sensitive=i < len(order) - 1, tooltip_text="Move down")
            for b in (up, down):
                b.add_css_class("flat")
            up.connect("clicked", self._move, i, -1)
            down.connect("clicked", self._move, i, 1)
            row.add_suffix(up)
            row.add_suffix(down)
            self.order_group.add(row)
            self._order_rows.append(row)

    def _move(self, _button, index, delta):
        order = self.widget.normalized_order()
        j = index + delta
        if not (0 <= index < len(order) and 0 <= j < len(order)):
            return
        order[index], order[j] = order[j], order[index]
        self.widget.order = order
        self._fill_order()
        self._changed()

    def _build_position(self):
        w = self.widget
        group = Adw.PreferencesGroup(title="Position and size")
        group.add(self.combo(w, "alignment", "Screen position", ALIGNMENTS))
        group.add(self.spin(w, "gap_x", "Distance from the side", 0, 4000, 5,
                            subtitle="In pixels"))
        group.add(self.spin(w, "gap_y", "Distance from the top or bottom", 0, 4000, 5,
                            subtitle="In pixels"))
        group.add(self.spin(w, "width", "Width", 120, 1200, 10))
        group.add(self.spin(w, "padding", "Inner padding", 0, 80))
        self.add(group)

    def _build_appearance(self):
        ap = self.widget.appearance
        group = Adw.PreferencesGroup(title="Colors")

        names = list(PRESETS)
        theme = Adw.ComboRow(title="Theme", subtitle="Sets all colors and fonts at once",
                             model=Gtk.StringList.new(["Pick a theme…", *names]))

        def on_theme(r, _p):
            index = r.get_selected()
            if index == 0:
                return
            apply_preset(ap, names[index - 1])
            for refresh in self._refreshers:
                refresh()
            r.set_selected(0)
            self._changed()
            self.window.toast(f"Applied the {names[index - 1]} theme")

        theme.connect("notify::selected", on_theme)
        group.add(theme)
        group.add(self.color(ap, "background", "Background"))
        group.add(self.spin(ap, "opacity", "Background opacity", 0, 100, 5, subtitle="Percent"))
        group.add(self.color(ap, "accent", "Clock"))
        group.add(self.color(ap, "highlight", "Highlights", "Today and the temperature"))
        group.add(self.color(ap, "text", "Text"))
        group.add(self.color(ap, "dim", "Dimmed text", "Labels and past days"))
        group.add(self.color(ap, "lines", "Divider lines"))
        self.add(group)

    def _build_fonts(self, doto_missing):
        ap = self.widget.appearance
        group = Adw.PreferencesGroup(title="Fonts")
        group.add(self.font(ap, "display_font", "Display font",
                            "Clock, temperature and calendar. For the Nothing look, "
                            "pick Doto. Non-monospace fonts are swapped for a "
                            "monospace one in the calendar so it lines up."))
        group.add(self.switch(ap, "display_bold", "Bold display font"))
        group.add(self.font(ap, "text_font", "Text font", "Small labels and details"))
        group.add(self.spin(ap, "text_size", "Text size", 6, 30))
        if doto_missing:
            row = Adw.ActionRow(title="Get the Doto dot-matrix font",
                                subtitle="The Nothing-style font the themes use")
            button = Gtk.Button(label="Install", valign=Gtk.Align.CENTER)
            button.add_css_class("suggested-action")
            button.connect("clicked", lambda b: self.window.install_doto(b, row, group))
            row.add_suffix(button)
            group.add(row)
        self.add(group)

    def _build_startup(self):
        group = Adw.PreferencesGroup(title="Startup")
        row = Adw.SwitchRow(title="Show widgets when I log in", active=process.autostart_enabled(),
                            subtitle="Applies to all widgets")
        row.connect("notify::active", lambda r, _p: process.set_autostart(r.get_active()))
        group.add(row)
        self.add(group)

    # ------------------------------------------------------------ weather location

    def _update_location_subtitle(self):
        w = self.widget.weather
        self.location_row.set_subtitle(w.location if w.location else "Not set yet")

    def _on_change_location(self, _button):
        from .dialogs import LocationDialog

        def chosen(result):
            w = self.widget.weather
            w.latitude = float(result["latitude"])
            w.longitude = float(result["longitude"])
            w.location = providers.location_label(result)
            self._update_location_subtitle()
            self._changed("weather")

        LocationDialog(self.window, chosen).present()
