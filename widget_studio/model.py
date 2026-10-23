"""Data model for widgets. Everything is plain dataclasses saved as JSON."""
from __future__ import annotations

import dataclasses
import uuid
from dataclasses import dataclass, field

SECTIONS = ["clock", "weather", "calendar", "stats"]
SECTION_TITLES = {
    "clock": "Clock and date",
    "weather": "Weather",
    "calendar": "Calendar",
    "stats": "System stats",
}

ALIGNMENTS = [
    ("top_left", "Top left"),
    ("top_middle", "Top center"),
    ("top_right", "Top right"),
    ("middle_left", "Middle left"),
    ("middle_middle", "Center"),
    ("middle_right", "Middle right"),
    ("bottom_left", "Bottom left"),
    ("bottom_middle", "Bottom center"),
    ("bottom_right", "Bottom right"),
]


@dataclass
class Appearance:
    background: str = "#0b2116"
    opacity: int = 85            # 0-100 %
    accent: str = "#81c784"      # clock
    highlight: str = "#e6ffe9"   # today, temperature
    text: str = "#a5d6a7"        # normal text
    dim: str = "#557f5f"         # labels, past days
    lines: str = "#2e6b3a"       # dividers, bars background
    display_font: str = "Doto"   # big numbers, calendar (monospace recommended)
    display_bold: bool = True
    text_font: str = "DejaVu Sans Mono"
    text_size: int = 9


@dataclass
class ClockOptions:
    enabled: bool = True
    use_24h: bool = True
    seconds: bool = False
    show_date: bool = True
    uppercase: bool = True
    timezone: str = ""          # "" = system time zone, else e.g. "Europe/Sofia"
    size: int = 56
    date_size: int = 13


@dataclass
class WeatherOptions:
    enabled: bool = True
    location: str = ""          # label shown on the widget, e.g. "Jasło, PL"
    latitude: float | None = None
    longitude: float | None = None
    units: str = "metric"       # metric | imperial
    details: bool = True        # feels like, humidity, wind
    high_low: bool = True
    size: int = 30


@dataclass
class CalendarOptions:
    enabled: bool = True
    week_start: str = "monday"  # monday | sunday
    dim_past: bool = True
    show_title: bool = True
    size: int = 18


@dataclass
class StatsOptions:
    enabled: bool = False
    cpu: bool = True
    ram: bool = True
    disk: bool = True
    temperature: bool = True
    bars: bool = True
    disk_path: str = "/"


@dataclass
class Widget:
    id: str = field(default_factory=lambda: uuid.uuid4().hex[:10])
    name: str = "My widget"
    enabled: bool = True
    alignment: str = "top_right"
    gap_x: int = 40
    gap_y: int = 60
    width: int = 320
    padding: int = 20
    labels: bool = True         # small "WEATHER" / "SYSTEM" headings
    dividers: bool = True
    order: list = field(default_factory=lambda: list(SECTIONS))
    appearance: Appearance = field(default_factory=Appearance)
    clock: ClockOptions = field(default_factory=ClockOptions)
    weather: WeatherOptions = field(default_factory=WeatherOptions)
    calendar: CalendarOptions = field(default_factory=CalendarOptions)
    stats: StatsOptions = field(default_factory=StatsOptions)

    def section(self, name: str):
        return getattr(self, name)

    def active_sections(self) -> list[str]:
        return [s for s in self.normalized_order() if self.section(s).enabled]

    def normalized_order(self) -> list[str]:
        order = [s for s in self.order if s in SECTIONS]
        order += [s for s in SECTIONS if s not in order]
        return order

    def to_dict(self) -> dict:
        return dataclasses.asdict(self)

    @classmethod
    def from_dict(cls, data: dict) -> "Widget":
        return _build(cls, data)

    def copy(self, new_id: bool = True) -> "Widget":
        w = Widget.from_dict(self.to_dict())
        if new_id:
            w.id = uuid.uuid4().hex[:10]
        return w


def _build(cls, data):
    """Create a dataclass from a dict, ignoring unknown keys and filling defaults,
    so old or hand-edited files never crash the app."""
    if not isinstance(data, dict):
        return cls()
    kwargs = {}
    for f in dataclasses.fields(cls):
        if f.name not in data:
            continue
        value = data[f.name]
        sub = _nested_type(cls, f.name)
        if sub is not None:
            kwargs[f.name] = _build(sub, value)
        elif f.name == "order":
            kwargs[f.name] = [s for s in value if s in SECTIONS] if isinstance(value, list) else list(SECTIONS)
        else:
            kwargs[f.name] = value
    return cls(**kwargs)


_NESTED = {
    "appearance": Appearance,
    "clock": ClockOptions,
    "weather": WeatherOptions,
    "calendar": CalendarOptions,
    "stats": StatsOptions,
}


def _nested_type(cls, name):
    if cls is Widget:
        return _NESTED.get(name)
    return None
