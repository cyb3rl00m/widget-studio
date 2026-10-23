"""Ready-made color themes. Applying one only changes colors and fonts."""

PRESETS = {
    "Forest": dict(background="#0b2116", opacity=85, accent="#81c784", highlight="#e6ffe9",
                   text="#a5d6a7", dim="#557f5f", lines="#2e6b3a",
                   display_font="Doto", display_bold=True, text_font="DejaVu Sans Mono"),
    "Nothing": dict(background="#000000", opacity=88, accent="#ffffff", highlight="#d71921",
                    text="#e6e6e6", dim="#7a7a7a", lines="#333333",
                    display_font="Doto", display_bold=True, text_font="DejaVu Sans Mono"),
    "Midnight": dict(background="#0d1326", opacity=85, accent="#8ab4f8", highlight="#ffffff",
                     text="#c6d2ec", dim="#5d6b8c", lines="#24304f",
                     display_font="Doto", display_bold=True, text_font="DejaVu Sans Mono"),
    "Amber terminal": dict(background="#140c00", opacity=90, accent="#ffb000", highlight="#ffe08a",
                           text="#e0a030", dim="#7a5a1e", lines="#3d2a08",
                           display_font="Doto", display_bold=True, text_font="DejaVu Sans Mono"),
    "Paper": dict(background="#f4f1e8", opacity=92, accent="#2b2b2b", highlight="#c0392b",
                  text="#3a3a3a", dim="#9a958a", lines="#d6d0c2",
                  display_font="DejaVu Sans Mono", display_bold=True, text_font="DejaVu Sans"),
    "Glass": dict(background="#000000", opacity=0, accent="#ffffff", highlight="#ffffff",
                  text="#f0f0f0", dim="#bdbdbd", lines="#9e9e9e",
                  display_font="Doto", display_bold=True, text_font="DejaVu Sans"),
}


def apply_preset(appearance, name: str) -> None:
    for key, value in PRESETS[name].items():
        setattr(appearance, key, value)
