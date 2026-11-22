"""Appearance settings for the FluxFile desktop UI."""

import tkinter as tk
from tkinter import ttk

BACKGROUND = "#171b23"
FIELD = "#202736"
CONTROL = "#2a3445"
BORDER = "#45546a"
TEXT = "#edf2fa"
MUTED = "#a5b2c6"
ACCENT = "#a9cdff"
SELECTION = "#304e73"


def configure_dark_theme(style: ttk.Style) -> None:
    style.theme_create("flux-dark", parent="clam", settings={
        ".": {"configure": {
            "background": BACKGROUND, "foreground": TEXT, "bordercolor": BORDER,
            "lightcolor": CONTROL, "darkcolor": CONTROL, "troughcolor": BACKGROUND,
            "arrowcolor": TEXT, "selectbackground": SELECTION, "selectforeground": TEXT,
        }},
        "TButton": {
            "configure": {"background": CONTROL},
            "map": {
                "background": [("disabled", BACKGROUND), ("pressed", SELECTION), ("active", FIELD)],
                "foreground": [("disabled", MUTED)],
                "bordercolor": [("focus", ACCENT)],
            },
        },
        "TMenubutton": {
            "configure": {"background": CONTROL},
            "map": {"foreground": [("disabled", MUTED)], "bordercolor": [("focus", ACCENT)]},
        },
        "TCheckbutton": {"configure": {"indicatorcolor": FIELD, "indicatormargin": (0, 0, 5, 0)},
                         "map": {"indicatorcolor": [("selected", SELECTION)]}},
        "TEntry": {
            "configure": {"fieldbackground": FIELD, "insertcolor": TEXT},
            "map": {"bordercolor": [("focus", ACCENT)]},
        },
        "TCombobox": {
            "configure": {"fieldbackground": FIELD, "background": CONTROL},
            "map": {"fieldbackground": [("readonly", FIELD)], "bordercolor": [("focus", ACCENT)]},
        },
        "Treeview": {
            "configure": {"background": FIELD, "fieldbackground": FIELD, "foreground": TEXT},
            "map": {"background": [("selected", SELECTION)], "foreground": [("selected", TEXT)]},
        },
        "Treeview.Heading": {"configure": {"background": CONTROL}},
        "TScrollbar": {"configure": {"background": CONTROL}},
        "TProgressbar": {"configure": {"background": ACCENT, "troughcolor": FIELD}},
        "Flux.Primary.TButton": {
            "configure": {"background": SELECTION},
            "map": {"background": [("disabled", BACKGROUND), ("pressed", CONTROL), ("active", "#3d628f")]},
        },
    })


def color_classic_widget(widget: tk.Misc, dark: bool) -> None:
    if isinstance(widget, (tk.Tk, tk.Toplevel)):
        background = ttk.Style(widget).lookup("TFrame", "background") or "#f0f0f0"
        widget.configure(background=BACKGROUND if dark else background)
    elif isinstance(widget, (tk.Menu, tk.Text)):
        light = ttk.Style(widget).lookup("TLabel", "foreground") or "#161616"
        foreground = TEXT if dark else light
        selected = SELECTION if dark else "#d7e8fc"
        widget.configure(background=FIELD if dark else "#ffffff", foreground=foreground)
        if isinstance(widget, tk.Menu):
            widget.configure(activebackground=selected, activeforeground=foreground,
                             disabledforeground=MUTED if dark else "#666666")
        else:
            widget.configure(selectbackground=selected, selectforeground=foreground)
