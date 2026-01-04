DEFAULT_KEYBINDS = {
    "open": "Ctrl+O",
    "close": "Ctrl+W",

    "toggle_sidebar": "F9",
    "switch_tab": "F8",
    "single_page": "Ctrl+1",
    "two_page": "Ctrl+2",
    "zoom_in": "Ctrl++",
    "zoom_out": "Ctrl+-",
    "fit_width": "Ctrl+3",
    "fit_page": "Ctrl+4",
    "fullscreen": "F11",

    "prev_page": "Left",
    "next_page": "Right",
    "goto_page": "Ctrl+G",
    "find": "Ctrl+F",
    "show_toc": "Ctrl+T",
    "extract_text": "Ctrl+E",
    "extract_images": "Ctrl+I",
    "help": "F1",
}


def get_menu_label(label, action_name, binds=DEFAULT_KEYBINDS):
    shortcut = binds.get(action_name)
    if shortcut:
        return f"{label}\t{shortcut}"
    return label

