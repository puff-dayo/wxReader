import wx

try:
    APP_ICON = wx.Icon('icon.png', wx.BITMAP_TYPE_ANY)
except Exception:
    print(Exception)
