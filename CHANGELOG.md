# Changelog

## 1.0.2 (2026-10-23)

- Updating is now just installing the new `.deb`. The background updater notices the new
  version within a minute and restarts itself with the new code, and widgets pick up any
  changes automatically. Before, you had to stop the old updater by hand.

## 1.0.1 (2026-10-23)

- The calendar always lines up. If the chosen font isn't monospace (or isn't installed), the
  calendar grid uses a monospace font instead of falling apart.
- Widgets restart by themselves when a font they use gets installed, whether the app installed
  it or you did. Conky only reads the font list when it starts, so before this a new font
  needed a manual restart.
- Starting and stopping widgets can no longer race into two copies of the same widget, even
  when the app and the background updater restart it at the same moment.
- The font settings explain that Doto is the font for the Nothing look.

## 1.0.0 (2026-10-23)

First release.

- Clock and date, weather (Open-Meteo), month calendar and system stats sections
- Colors, fonts, size, position, section order, labels and divider lines
- Six themes: Forest, Nothing, Midnight, Amber terminal, Paper and Glass
- One-click install of Conky (Wayland build) and the Doto dot-matrix font
- Several widgets at once, live updates while editing, start at login
- Works on COSMIC, KDE Plasma and X11 desktops
