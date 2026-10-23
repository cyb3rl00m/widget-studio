# Security policy

## Reporting a problem

Please **don't** open a public issue for security problems. Report them privately instead:
go to the **Security** tab of this repository and click **Report a vulnerability**. I'll
reply as soon as I can.

## What Widget Studio does on your system

- It runs entirely as your normal user and never asks for root or a password.
- It writes files only inside your home folder: `~/.config/widget-studio`,
  `~/.cache/widget-studio`, `~/.local/share/widget-studio`, `~/.local/share/fonts`
  (only when you install Doto) and `~/.config/autostart` (the login entry).
- It connects to the internet only over HTTPS, and only to:
  - `api.open-meteo.com` and `geocoding-api.open-meteo.com` for weather and city search. What
    gets sent is the city name you type in the search box and the coordinates of the city you
    pick, nothing else.
  - `api.github.com` and `github.com`, and only when you click **Install Conky** or
    **Install** for the Doto font.
- It stops only Conky processes that run one of its own widget configs, checked by config path
  and process start time, so it never touches other Conky setups or unrelated programs.
