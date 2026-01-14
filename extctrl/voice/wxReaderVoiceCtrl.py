import os
import sys
import platform
from functools import lru_cache

import pywinstyles
import wx
import pyaudio
import json
import threading
import socket
from vosk import Model, KaldiRecognizer

DEFAULT_MODEL_PATH = "./model/vosk-model-small-en-us-0.15"
DEFAULT_IP = "127.0.0.1"


def _base_dir():
    if getattr(sys, "frozen", False):
        return os.path.dirname(os.path.abspath(sys.executable))
    return os.path.dirname(os.path.abspath(__file__))


def _resource_path(*parts):
    return os.path.join(_base_dir(), *parts)


@lru_cache(maxsize=1)
def get_app_icon():
    icon_path = _resource_path("icon.png")

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


class VoiceControllerFrame(wx.Frame):
    def __init__(self):
        super().__init__(None, title="wxReader Voice Commander", size=(480, 560))

        self.is_running = False
        self.thread = None
        self.pa = pyaudio.PyAudio()

        self.init_ui()
        self.SetFont(get_app_font(0))
        self.SetMinSize((480, 560))
        self.Center()
        msw_set_theme(self)

    def init_ui(self):
        panel = wx.Panel(self)
        outer = wx.BoxSizer(wx.VERTICAL)
        outer.SetMinSize((480, 560))

        header = wx.BoxSizer(wx.HORIZONTAL)
        title = wx.StaticText(panel, label="Voice Commander")
        title.SetFont(get_app_font(3))
        self.lbl_status = wx.StaticText(panel, label="Idle")
        header.Add(title, 1, wx.ALIGN_CENTER_VERTICAL | wx.LEFT, 10)
        header.Add(self.lbl_status, 0, wx.ALIGN_CENTER_VERTICAL | wx.RIGHT, 10)
        outer.Add(header, 0, wx.EXPAND | wx.TOP | wx.BOTTOM, 8)

        top_row = wx.BoxSizer(wx.HORIZONTAL)

        sb_conn = wx.StaticBox(panel, label="Connection")
        sbs_conn = wx.StaticBoxSizer(sb_conn, wx.VERTICAL)

        grid_conn = wx.FlexGridSizer(2, 2, 6, 8)
        grid_conn.AddGrowableCol(1, 1)

        lbl_port = wx.StaticText(panel, label="Port")
        self.txt_port = wx.TextCtrl(panel, value="", size=(110, -1))

        lbl_token = wx.StaticText(panel, label="Token")
        self.txt_token = wx.TextCtrl(panel, value="")

        grid_conn.Add(lbl_port, 0, wx.ALIGN_CENTER_VERTICAL)
        grid_conn.Add(self.txt_port, 1, wx.EXPAND)
        grid_conn.Add(lbl_token, 0, wx.ALIGN_CENTER_VERTICAL)
        grid_conn.Add(self.txt_token, 1, wx.EXPAND)

        sbs_conn.Add(grid_conn, 0, wx.EXPAND | wx.ALL, 8)
        top_row.Add(sbs_conn, 1, wx.EXPAND | wx.RIGHT, 10)

        sb_audio = wx.StaticBox(panel, label="Microphone")
        sbs_audio = wx.StaticBoxSizer(sb_audio, wx.VERTICAL)

        hbox_mic = wx.BoxSizer(wx.HORIZONTAL)
        self.combo_mics = wx.ComboBox(panel, style=wx.CB_READONLY)
        self.refresh_mics()

        btn_refresh = wx.Button(panel, label="Refresh", size=(80, -1))
        btn_refresh.Bind(wx.EVT_BUTTON, lambda e: self.refresh_mics())

        hbox_mic.Add(self.combo_mics, 1, wx.EXPAND | wx.RIGHT, 8)
        hbox_mic.Add(btn_refresh, 0, wx.ALIGN_CENTER_VERTICAL)
        sbs_audio.Add(hbox_mic, 0, wx.EXPAND | wx.ALL, 8)
        top_row.Add(sbs_audio, 1, wx.EXPAND)

        outer.Add(top_row, 0, wx.EXPAND | wx.LEFT | wx.RIGHT, 10)

        sb_cmd = wx.StaticBox(panel, label="Keywords")
        sbs_cmd = wx.StaticBoxSizer(sb_cmd, wx.VERTICAL)

        grid_cmd = wx.FlexGridSizer(2, 2, 6, 8)
        grid_cmd.AddGrowableCol(1, 1)

        lbl_next = wx.StaticText(panel, label="Next page")
        self.txt_cmd_next = wx.TextCtrl(panel, value="next page, go down")
        self.txt_cmd_next.SetHint("Comma-separated words/phrases")
        self.txt_cmd_next.SetToolTip("Comma-separated keywords that trigger NEXT")

        lbl_prev = wx.StaticText(panel, label="Previous page")
        self.txt_cmd_prev = wx.TextCtrl(panel, value="previous, go up")
        self.txt_cmd_prev.SetHint("Comma-separated words/phrases")
        self.txt_cmd_prev.SetToolTip("Comma-separated keywords that trigger PREV")

        grid_cmd.Add(lbl_next, 0, wx.ALIGN_CENTER_VERTICAL)
        grid_cmd.Add(self.txt_cmd_next, 1, wx.EXPAND)
        grid_cmd.Add(lbl_prev, 0, wx.ALIGN_CENTER_VERTICAL)
        grid_cmd.Add(self.txt_cmd_prev, 1, wx.EXPAND)

        note = wx.StaticText(panel, label="Vosk model: small-en-us-0.15 (Apache 2.0)")
        sbs_cmd.Add(grid_cmd, 0, wx.EXPAND | wx.ALL, 8)
        sbs_cmd.Add(note, 0, wx.LEFT | wx.RIGHT | wx.BOTTOM, 8)
        outer.Add(sbs_cmd, 0, wx.EXPAND | wx.LEFT | wx.RIGHT | wx.TOP, 10)

        log_header = wx.BoxSizer(wx.HORIZONTAL)
        log_label = wx.StaticText(panel, label="Activity")
        log_label.SetFont(get_app_font(1))
        self.btn_clear_log = wx.Button(panel, label="Clear", size=(80, -1))
        self.btn_clear_log.Bind(wx.EVT_BUTTON, lambda e: self.txt_log.SetValue(""))
        log_header.Add(log_label, 1, wx.ALIGN_CENTER_VERTICAL)
        log_header.Add(self.btn_clear_log, 0, wx.ALIGN_CENTER_VERTICAL)

        self.txt_log = wx.TextCtrl(panel, style=wx.TE_MULTILINE | wx.TE_READONLY)
        outer.Add(log_header, 0, wx.EXPAND | wx.LEFT | wx.RIGHT | wx.TOP, 10)
        outer.Add(self.txt_log, 1, wx.EXPAND | wx.LEFT | wx.RIGHT | wx.TOP, 8)

        footer = wx.BoxSizer(wx.HORIZONTAL)
        self.btn_toggle = wx.Button(panel, label="Start Listening", size=(-1, 36))
        self.btn_toggle.Bind(wx.EVT_BUTTON, self.on_toggle)
        footer.Add(self.btn_toggle, 1, wx.EXPAND)
        outer.Add(footer, 0, wx.EXPAND | wx.ALL, 10)

        panel.SetSizer(outer)

    def refresh_mics(self):
        self.combo_mics.Clear()
        self.device_map = {}

        try:
            info = self.pa.get_host_api_info_by_index(0)
            numdevices = info.get('deviceCount')
        except Exception:
            numdevices = 0

        idx = 0
        for i in range(0, numdevices):
            try:
                di = self.pa.get_device_info_by_host_api_device_index(0, i)
                if (di.get('maxInputChannels', 0)) > 0:
                    name = di.get('name', 'Unknown')
                    label = f"{name}"
                    self.combo_mics.Append(label)
                    self.device_map[idx] = i
                    idx += 1
            except Exception:
                continue

        if self.combo_mics.GetCount() > 0:
            self.combo_mics.SetSelection(0)

    def log(self, msg):
        wx.CallAfter(self.txt_log.AppendText, f"{msg}\n")

    def on_toggle(self, event):
        if not self.is_running:
            self.start_listening()
        else:
            self.stop_listening()

    def start_listening(self):
        port_str = self.txt_port.GetValue().strip()
        token = self.txt_token.GetValue().strip()
        if not port_str.isdigit() or not token:
            wx.MessageBox("Please enter a valid Port and Token.", "Error")
            return

        next_words = [w.strip().lower() for w in self.txt_cmd_next.GetValue().split(",") if w.strip()]
        prev_words = [w.strip().lower() for w in self.txt_cmd_prev.GetValue().split(",") if w.strip()]

        if not next_words or not prev_words:
            wx.MessageBox("Please provide keywords for both Next and Previous.", "Error")
            return

        selection = self.combo_mics.GetSelection()
        if selection == wx.NOT_FOUND:
            wx.MessageBox("Please select a microphone device.", "Error")
            return
        device_index = self.device_map[selection]

        model_path = DEFAULT_MODEL_PATH
        if not os.path.isabs(model_path):
            model_path = _resource_path(*model_path.replace("\\", "/").split("/"))
        if not os.path.exists(model_path):
            wx.MessageBox(f"Vosk model not found:\n{model_path}", "Error")
            return

        self.is_running = True
        self.btn_toggle.SetLabel("Stop")
        self.lbl_status.SetLabel("Listening")
        self.txt_port.Disable()
        self.txt_token.Disable()
        self.txt_cmd_next.Disable()
        self.txt_cmd_prev.Disable()
        self.combo_mics.Disable()

        self.thread = threading.Thread(
            target=self.run_recognition,
            args=(int(port_str), token, next_words, prev_words, device_index),
            daemon=True
        )
        self.thread.start()

    def stop_listening(self):
        self.is_running = False
        self.btn_toggle.SetLabel("Start Listening")
        self.lbl_status.SetLabel("Idle")
        self.txt_port.Enable()
        self.txt_token.Enable()
        self.txt_cmd_next.Enable()
        self.txt_cmd_prev.Enable()
        self.combo_mics.Enable()
        self.log("Stop Listening")

    def send_udp_command(self, port, token, cmd):
        try:
            sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
            msg = f"{token}|{cmd}"
            sock.sendto(msg.encode(), (DEFAULT_IP, port))
            self.log(f"{cmd}")
        except Exception as e:
            self.log(f"{e}")

    def run_recognition(self, port, token, next_words, prev_words, device_idx):
        stream = None
        p = None
        try:
            all_words = list(set(next_words + prev_words))
            all_words.append("[unk]")
            grammar_json = json.dumps(all_words)

            self.log("Grammar Mode...")
            model_path = DEFAULT_MODEL_PATH
            if not os.path.isabs(model_path):
                model_path = _resource_path(*model_path.replace("\\", "/").split("/"))
            model = Model(model_path)

            rec = KaldiRecognizer(model, 16000, grammar_json)

            p = pyaudio.PyAudio()
            stream = p.open(format=pyaudio.paInt16, channels=1, rate=16000,
                            input=True, input_device_index=device_idx,
                            frames_per_buffer=4000)

            self.log(f"Mic: {device_idx}")
            stream.start_stream()

            while self.is_running:
                data = stream.read(2000, exception_on_overflow=False)
                if len(data) == 0:
                    break

                if rec.AcceptWaveform(data):
                    res = json.loads(rec.Result())
                    text = res.get('text', '').strip().lower()

                    if text:
                        self.log(f"'{text}'")

                        if text in next_words:
                            self.send_udp_command(port, token, "NEXT")
                        elif text in prev_words:
                            self.send_udp_command(port, token, "PREV")

        except Exception as e:
            self.log(f"{e}")
            wx.CallAfter(self.stop_listening)
        finally:
            try:
                if stream is not None:
                    stream.stop_stream()
                    stream.close()
            except Exception:
                pass
            try:
                if p is not None:
                    p.terminate()
            except Exception:
                pass


if __name__ == "__main__":
    app = wx.App()
    app_icon = get_app_icon()

    frm = VoiceControllerFrame()
    if app_icon.IsOk():
        frm.SetIcon(app_icon)

    frm.Show()
    app.MainLoop()
