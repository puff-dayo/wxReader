import platform

import pywinstyles
import wx

try:
    APP_ICON = wx.Icon('icon.png', wx.BITMAP_TYPE_ANY)
except Exception:
    print(Exception)


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
        except Exception:
            print(f"[ERROR] Failed to apply sytle: {Exception}")