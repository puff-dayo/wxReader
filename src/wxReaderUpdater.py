import wx
import json
import urllib.request
import webbrowser
import threading

from wxReaderString import APP_VERSION, GITHUB_REPO_OWNER, GITHUB_REPO_NAME
from wxReaderIcon import get_app_font, msw_set_theme, get_app_icon


class UpdateChecker:
    def __init__(self, parent_frame, silent_on_no_update=False):
        self.parent = parent_frame
        self.silent = silent_on_no_update
        self.current_ver = APP_VERSION.lstrip('v')

    def check(self):
        threading.Thread(target=self._do_check, daemon=True).start()

    def _do_check(self):
        url = f"https://api.github.com/repos/{GITHUB_REPO_OWNER}/{GITHUB_REPO_NAME}/releases/latest"

        try:
            req = urllib.request.Request(url, headers={'User-Agent': 'wxReader-App'})
            with urllib.request.urlopen(req, timeout=6) as response:
                data = json.loads(response.read().decode())

            tag_name = data.get("tag_name", "").lstrip("v")
            html_url = data.get("html_url", "")
            body = data.get("body", "")

            remote_ver_tuple = self._parse_version(tag_name)
            local_ver_tuple = self._parse_version(self.current_ver)

            if remote_ver_tuple > local_ver_tuple:
                wx.CallAfter(self._show_update_dialog, tag_name, html_url, body)
            else:
                if not self.silent:
                    wx.CallAfter(self._show_no_update_dialog)

        except Exception as e:
            print(f"[Update Check Error] {e}")
            if not self.silent:
                wx.CallAfter(wx.MessageBox, f"Failed to check for updates.\n{e}", "Error", wx.ICON_ERROR)

    def _parse_version(self, version_str):
        try:
            clean_ver = version_str.split('-')[0]
            return tuple(map(int, clean_ver.split('.')))
        except ValueError:
            return (0, 0, 0)

    def _show_update_dialog(self, new_version, url, notes):
        dlg = NewVersionDialog(self.parent, self.current_ver, new_version, url, notes)
        dlg.ShowModal()
        dlg.Destroy()

    def _show_no_update_dialog(self):
        wx.MessageBox(f"You are using the latest version (v{APP_VERSION}).", "Up to date", wx.ICON_INFORMATION)


class NewVersionDialog(wx.Dialog):
    def __init__(self, parent, current_ver, new_version, url, notes):
        super().__init__(parent, title="Update Available", size=(500, 400))
        self.url = url

        panel = wx.Panel(self)
        v_sizer = wx.BoxSizer(wx.VERTICAL)

        icon = get_app_icon()
        if icon.IsOk():
            self.SetIcon(icon)

        msw_set_theme(self)

        self.SetFont(get_app_font())

        lbl_header = wx.StaticText(panel, label=f"A new version is available!")
        lbl_header.SetFont(get_app_font(2))
        lbl_header.SetForegroundColour(wx.Colour("#2e7d32"))

        lbl_info = wx.StaticText(panel, label=f"Current: v{current_ver}  ➜  New: v{new_version}")

        v_sizer.Add(lbl_header, 0, wx.ALL | wx.CENTER, 15)
        v_sizer.Add(lbl_info, 0, wx.BOTTOM | wx.CENTER, 10)

        lbl_notes = wx.StaticText(panel, label="Release Notes:")
        v_sizer.Add(lbl_notes, 0, wx.LEFT, 20)

        self.txt_notes = wx.TextCtrl(panel, value=notes, style=wx.TE_MULTILINE | wx.TE_READONLY | wx.TE_BESTWRAP)
        self.txt_notes.SetBackgroundColour(wx.Colour(250, 250, 250))
        self.txt_notes.SetFont(get_app_font())
        v_sizer.Add(self.txt_notes, 1, wx.EXPAND | wx.LEFT | wx.RIGHT | wx.BOTTOM, 20)

        btn_sizer = wx.BoxSizer(wx.HORIZONTAL)

        self.btn_ignore = wx.Button(panel, wx.ID_CANCEL, "Ignore")
        self.btn_download = wx.Button(panel, label="View Release Page")
        self.btn_download.SetBitmap(wx.ArtProvider.GetBitmap(wx.ART_GO_FORWARD, wx.ART_BUTTON, (16, 16)))

        btn_sizer.Add(self.btn_ignore, 0, wx.RIGHT, 10)
        btn_sizer.Add(self.btn_download, 0)

        v_sizer.Add(btn_sizer, 0, wx.ALIGN_RIGHT | wx.ALL, 15)

        self.btn_download.Bind(wx.EVT_BUTTON, self.on_download)

        panel.SetSizer(v_sizer)
        self.Layout()
        self.CenterOnParent()

    def on_download(self, evt):
        webbrowser.open(self.url)
        self.EndModal(wx.ID_OK)
