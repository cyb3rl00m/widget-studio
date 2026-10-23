"""Data for the widgets: date, calendar, weather (Open-Meteo, no API key) and CPU
temperature. Each render_* function returns Conky markup that the background
updater writes into a small text file; Conky shows it with ${catp}.

Colors in the markup refer to the per-widget Conky config:
  ${color}  = text   ${color1} = highlight   ${color3} = accent   ${color4} = dim
"""
from __future__ import annotations

import calendar as _calendar
import datetime as _dt
import glob
import hashlib
import json
import os
import time
import urllib.parse
import urllib.request

from . import fonts, paths

USER_AGENT = "WidgetStudio/1.0 (+https://github.com/cyb3rl00m/widget-studio)"

# Doto and most monospace fonts are 0.6 em wide per character; Conky sizes are
# points at 96 dpi. Used to center the calendar grid in the widget.
MONO_CHAR_EM = 0.6


def conky_escape(text: str) -> str:
    """Make user text safe to show literally in Conky markup."""
    return str(text).replace("$", "$$")


def font(family: str, size: int, bold: bool = False) -> str:
    style = ":bold" if bold else ""
    return f"${{font {family}{style}:size={int(size)}}}"


# ---------------------------------------------------------------- date

def now_in(tz_name: str) -> _dt.datetime:
    if tz_name:
        try:
            from zoneinfo import ZoneInfo
            return _dt.datetime.now(ZoneInfo(tz_name))
        except Exception:
            pass
    return _dt.datetime.now()


def valid_timezone(tz_name: str) -> bool:
    if not tz_name:
        return True
    try:
        from zoneinfo import ZoneInfo
        ZoneInfo(tz_name)
        return True
    except Exception:
        return False


def render_date(widget) -> str:
    text = now_in(widget.clock.timezone).strftime("%a %d %b %Y")
    if widget.clock.uppercase:
        text = text.upper()
    return conky_escape(text)


# ---------------------------------------------------------------- calendar

def calendar_offset_px(widget) -> int:
    size_px = widget.calendar.size * 96 / 72
    grid_width = 20 * size_px * MONO_CHAR_EM
    return max(0, int((widget.width - grid_width) / 2))


def render_calendar(widget, today: _dt.date | None = None) -> str:
    opts, ap = widget.calendar, widget.appearance
    today = today or now_in(widget.clock.timezone).date()
    first = 0 if opts.week_start == "monday" else 6
    names = ["MO", "TU", "WE", "TH", "FR", "SA", "SU"]
    names = names[first:] + names[:first]
    pad = f"${{offset {calendar_offset_px(widget)}}}"
    # The grid is always drawn in a monospace font, or the columns can't line up.
    family, bold = fonts.calendar_font(ap)
    grid_font = font(family, opts.size, bold)

    lines = []
    if opts.show_title:
        title = today.strftime("%B %Y").upper()
        lines.append(f"{font(ap.text_font, ap.text_size)}${{color4}}{title}${{color}}")
    lines.append(f"{grid_font}{pad}${{color4}}{' '.join(names)}${{color}}")
    for week in _calendar.Calendar(firstweekday=first).monthdayscalendar(today.year, today.month):
        cells = []
        for d in week:
            if d == 0:
                cells.append("  ")
            elif d == today.day:
                cells.append(f"${{color1}}{d:2}${{color}}")
            elif d < today.day and opts.dim_past:
                cells.append(f"${{color4}}{d:2}${{color}}")
            else:
                cells.append(f"{d:2}")
        lines.append(pad + " ".join(cells))
    return "\n".join(lines)


# ---------------------------------------------------------------- weather

WMO = {0: "Clear", 1: "Mostly clear", 2: "Partly cloudy", 3: "Overcast", 45: "Fog",
       48: "Freezing fog", 51: "Light drizzle", 53: "Drizzle", 55: "Heavy drizzle",
       56: "Freezing drizzle", 57: "Freezing drizzle", 61: "Light rain", 63: "Rain",
       65: "Heavy rain", 66: "Freezing rain", 67: "Freezing rain", 71: "Light snow",
       73: "Snow", 75: "Heavy snow", 77: "Snow grains", 80: "Showers", 81: "Showers",
       82: "Heavy showers", 85: "Snow showers", 86: "Snow showers", 95: "Thunderstorm",
       96: "Storm, hail", 99: "Storm, hail"}
COMPASS = ["N", "NE", "E", "SE", "S", "SW", "W", "NW"]
WEATHER_MAX_AGE = 15 * 60       # refresh every 15 minutes
WEATHER_STALE_OK = 6 * 3600     # show old data for up to 6 hours if offline


def _http_json(url: str, timeout: int = 15):
    req = urllib.request.Request(url, headers={"User-Agent": USER_AGENT})
    with urllib.request.urlopen(req, timeout=timeout) as resp:
        return json.load(resp)


def search_locations(query: str) -> list[dict]:
    """Search cities. 'Berlin, DE' or 'Berlin, Germany' filters by country."""
    city, _, country = query.partition(",")
    city, country = city.strip(), country.strip().lower()
    if not city:
        return []
    url = "https://geocoding-api.open-meteo.com/v1/search?" + urllib.parse.urlencode(
        {"name": city, "count": 30, "language": "en", "format": "json"})
    results = _http_json(url).get("results", []) or []
    if country:
        results = [r for r in results
                   if country in (r.get("country", "").lower(), r.get("country_code", "").lower())]
    return results[:15]


def location_label(result: dict) -> str:
    code = result.get("country_code", "")
    return f"{result.get('name', '?')}, {code}" if code else result.get("name", "?")


def _weather_cache_file(lat: float, lon: float, units: str) -> str:
    key = hashlib.sha1(f"{lat:.3f},{lon:.3f},{units}".encode()).hexdigest()[:12]
    return os.path.join(paths.CACHE_DIR, f"weather-{key}.json")


def get_weather(lat: float, lon: float, units: str, force: bool = False):
    """Returns (data, fetched_at) or (None, 0). Uses a shared on-disk cache so
    several widgets with the same city only download once."""
    cache = _weather_cache_file(lat, lon, units)
    cached, fetched = None, 0.0
    try:
        with open(cache, encoding="utf-8") as f:
            blob = json.load(f)
        cached, fetched = blob["data"], float(blob["time"])
    except (OSError, ValueError, KeyError):
        pass
    if cached is not None and not force and time.time() - fetched < WEATHER_MAX_AGE:
        return cached, fetched

    params = {
        "latitude": lat, "longitude": lon, "timezone": "auto", "forecast_days": 1,
        "current": "temperature_2m,apparent_temperature,relative_humidity_2m,"
                   "weather_code,wind_speed_10m,wind_direction_10m",
        "daily": "temperature_2m_max,temperature_2m_min",
    }
    if units == "imperial":
        params.update(temperature_unit="fahrenheit", wind_speed_unit="mph")
    try:
        data = _http_json("https://api.open-meteo.com/v1/forecast?" + urllib.parse.urlencode(params))
        paths.write_if_changed(cache, json.dumps({"time": time.time(), "data": data}))
        return data, time.time()
    except Exception:
        if cached is not None and time.time() - fetched < WEATHER_STALE_OK:
            return cached, fetched
        return None, 0


def render_weather(widget, data) -> str:
    opts, ap = widget.weather, widget.appearance
    if opts.latitude is None or opts.longitude is None:
        return "PICK A CITY IN WIDGET STUDIO"
    if not data:
        return "WEATHER UNAVAILABLE, RETRYING SOON"
    try:
        cur, day = data["current"], data["daily"]
        temp = round(cur["temperature_2m"])
        feels = round(cur["apparent_temperature"])
        hi = round(day["temperature_2m_max"][0])
        lo = round(day["temperature_2m_min"][0])
        cond = WMO.get(cur["weather_code"], "Unknown").upper()
        wind = round(cur["wind_speed_10m"])
        wdir = COMPASS[int((cur["wind_direction_10m"] + 22.5) // 45) % 8]
        hum = cur["relative_humidity_2m"]
    except (KeyError, TypeError, IndexError, ValueError):
        return "WEATHER DATA ERROR"
    speed = "MPH" if opts.units == "imperial" else "KM/H"
    lines = [
        f"{font(ap.display_font, opts.size, ap.display_bold)}${{color1}}{temp}°${{font}}${{color}}  "
        f"{font(ap.display_font, max(8, opts.size // 2.5), ap.display_bold)}{cond}${{font}}"
    ]
    label = conky_escape(opts.location.upper())
    if opts.high_low:
        lines.append(f"${{color4}}{label}${{alignr}}H {hi}°  L {lo}°${{color}}")
    else:
        lines.append(f"${{color4}}{label}${{color}}")
    if opts.details:
        lines.append(f"FEELS {feels}°  HUM {hum}%  WIND {wind} {speed} {wdir}")
    return "\n".join(lines)


# ---------------------------------------------------------------- temperature

_SENSOR_PREFERENCE = [
    ("k10temp", ("tctl", "tdie")),       # AMD Ryzen
    ("zenpower", ("tdie", "tctl")),
    ("coretemp", ("package",)),          # Intel
    ("cpu_thermal", ()),                 # ARM boards
    ("acpitz", ()),
]


def find_cpu_sensor() -> str | None:
    """Path of the temp*_input file that best represents the CPU."""
    devices = {}
    for d in glob.glob("/sys/class/hwmon/hwmon*"):
        try:
            with open(os.path.join(d, "name")) as f:
                devices.setdefault(f.read().strip(), d)
        except OSError:
            continue
    for name, label_hints in _SENSOR_PREFERENCE:
        d = devices.get(name)
        if not d:
            continue
        inputs = sorted(glob.glob(os.path.join(d, "temp*_input")))
        for inp in inputs:
            try:
                with open(inp.replace("_input", "_label")) as f:
                    label = f.read().strip().lower()
            except OSError:
                label = ""
            if any(h in label for h in label_hints):
                return inp
        if inputs:
            return inputs[0]
    return None


def render_temperature(widget, sensor: str | None) -> str:
    if not sensor:
        return "N/A"
    try:
        with open(sensor) as f:
            celsius = int(f.read().strip()) / 1000
    except (OSError, ValueError):
        return "N/A"
    if widget.weather.units == "imperial":
        return f"{round(celsius * 9 / 5 + 32)}°F"
    return f"{round(celsius)}°C"
