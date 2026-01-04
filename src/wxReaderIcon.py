import os
import platform
from functools import lru_cache

import pywinstyles
import wx


@lru_cache(maxsize=1)
def get_app_icon():
    icon_path = 'icon.png'

    if not os.path.exists(icon_path):
        print(f"Error: {icon_path} not found.")
        return wx.NullIcon

    try:
        icon = wx.Icon(icon_path, wx.BITMAP_TYPE_ANY)
        if icon.IsOk():
            return icon
    except Exception as e:
        print(f"Failed to create icon: {e}")

    return wx.NullIcon


@lru_cache(maxsize=6)
def get_app_font(add_size=0):
    face_name = 'Segoe UI'
    try:
        sys_font = wx.SystemSettings.GetFont(wx.SYS_DEFAULT_GUI_FONT)
        font = wx.Font(sys_font.GetPointSize() + add_size, wx.FONTFAMILY_SWISS,
                       wx.FONTSTYLE_NORMAL, wx.FONTWEIGHT_NORMAL,
                       faceName=face_name)
        print(f"[DEBUG] App font set to {face_name}.")
        return font
    except Exception as e:
        print(f"[ERROR ]Failed to font set: {e}")

    return wx.SYS_DEFAULT_GUI_FONT


@lru_cache(maxsize=None)
def is_windows_11():
    if platform.system() == "Windows":
        build_number = int(platform.version().split('.')[-1])
        return build_number >= 22000
    return False


def msw_set_theme(frame):
    if is_windows_11():
        try:
            pywinstyles.change_header_color(frame, "#568466")
            pywinstyles.change_title_color(frame, color="white")
        except Exception as e1:
            try:
                pywinstyles.apply_style(frame, "mica")
            except Exception as e2:
                print(f"[ERROR] Failed to apply sytle: {e1}. {e2}")
