"""Entry point.

  widget-studio            open the app
  widget-studio --start    show all enabled widgets (used at login)
  widget-studio --stop     hide all widgets
  widget-studio --daemon   run the background updater (started automatically)
"""
import argparse
import sys
import time

from . import APP_NAME, VERSION


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(prog="widget-studio", description=f"{APP_NAME} {VERSION}")
    group = parser.add_mutually_exclusive_group()
    group.add_argument("--start", action="store_true", help="show all enabled widgets and exit")
    group.add_argument("--stop", action="store_true", help="hide all widgets and exit")
    group.add_argument("--daemon", action="store_true", help="run the background updater")
    parser.add_argument("--delay", type=float, default=None,
                        help="seconds to wait before --start (default 5)")
    parser.add_argument("--version", action="version", version=f"{APP_NAME} {VERSION}")
    args, gtk_args = parser.parse_known_args(argv)

    if args.daemon:
        from . import daemon
        return daemon.run()

    if args.start or args.stop:
        from . import process, storage
        widgets = storage.load_widgets()
        if args.stop:
            process.stop_all(widgets)
            return 0
        time.sleep(5 if args.delay is None else max(0.0, args.delay))
        if not process.start_all(widgets):
            print("No Conky with support for this session was found. "
                  "Open Widget Studio to install it.", file=sys.stderr)
            return 1
        return 0

    from .app import run_app
    return run_app([sys.argv[0], *gtk_args])


if __name__ == "__main__":
    sys.exit(main())
