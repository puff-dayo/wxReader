import wx

from wxReaderIcon import get_app_font


def show_toast(self, message, is_error=False):
    wx.CallAfter(ToastPopup, self, message, is_error=is_error)


class ToastPopup(wx.Frame):
    def __init__(self, parent, message, duration=3000, is_error=False):
        style = wx.FRAME_TOOL_WINDOW | wx.STAY_ON_TOP | wx.NO_BORDER | wx.FRAME_FLOAT_ON_PARENT
        super().__init__(parent, style=style)

        bg_color = wx.Colour(220, 53, 69) if is_error else wx.Colour(75, 149, 81)
        text_color = wx.WHITE

        self.SetBackgroundColour(bg_color)
        self.duration = duration
        self.alpha = 0
        self.SetTransparent(0)

        panel = wx.Panel(self)
        panel.SetBackgroundColour(bg_color)

        sizer = wx.BoxSizer(wx.VERTICAL)
        lbl = wx.StaticText(panel, label=message)
        lbl.SetForegroundColour(text_color)

        lbl.SetFont(get_app_font(8))

        sizer.Add(lbl, 1, wx.ALL | wx.ALIGN_CENTER, 15)
        panel.SetSizer(sizer)

        main_sizer = wx.BoxSizer(wx.VERTICAL)
        main_sizer.Add(panel, 1, wx.EXPAND)
        self.SetSizerAndFit(main_sizer)

        # at bottom-right of parent
        if parent:
            p_rect = parent.GetScreenRect()
            sz = self.GetSize()
            x = p_rect.x + p_rect.width - sz.width - 30
            y = p_rect.y + p_rect.height - sz.height - 50
            self.SetPosition((x, y))

        self.timer = wx.Timer(self)
        self.Bind(wx.EVT_TIMER, self.OnTimer)
        self.step = 0  # 0: FadeIn, 1: Wait, 2: FadeOut
        self.timer.Start(20)
        self.Show()

    def OnTimer(self, evt):
        if self.step == 0:  # Fade In
            self.alpha += 25
            if self.alpha >= 240:
                self.alpha = 240
                self.step = 1
                self.timer.Start(self.duration, wx.TIMER_ONE_SHOT)
            self.SetTransparent(self.alpha)

        elif self.step == 1:  # Wait done
            self.step = 2
            self.timer.Start(20)

        elif self.step == 2:  # Fade Out
            self.alpha -= 20
            if self.alpha <= 0:
                self.timer.Stop()
                self.Close()
            else:
                self.SetTransparent(self.alpha)
