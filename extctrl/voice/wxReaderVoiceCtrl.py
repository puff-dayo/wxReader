import os
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


class VoiceControllerFrame(wx.Frame):
    def __init__(self):
        super().__init__(None, title="wxReader Voice Commander", size=(450, 550))

        self.is_running = False
        self.thread = None
        self.pa = pyaudio.PyAudio()

        self.init_ui()
        self.SetFont(get_app_font(0))
        self.Center()
        msw_set_theme(self)

    def init_ui(self):
        panel = wx.Panel(self)
        vbox = wx.BoxSizer(wx.VERTICAL)

        sb_conn = wx.StaticBox(panel, label="Connection")
        sbs_conn = wx.StaticBoxSizer(sb_conn, wx.VERTICAL)

        flex_grid = wx.FlexGridSizer(2, 2, 10, 10)

        flex_grid.Add(wx.StaticText(panel, label="Port:"), 0, wx.ALIGN_CENTER_VERTICAL)
        self.txt_port = wx.TextCtrl(panel, value="")
        flex_grid.Add(self.txt_port, 1, wx.EXPAND)

        # Token
        flex_grid.Add(wx.StaticText(panel, label="Token:"), 0, wx.ALIGN_CENTER_VERTICAL)
        self.txt_token = wx.TextCtrl(panel, value="")
        self.txt_token.SetHint("")
        flex_grid.Add(self.txt_token, 1, wx.EXPAND)

        flex_grid.AddGrowableCol(1, 1)
        sbs_conn.Add(flex_grid, 0, wx.EXPAND | wx.ALL, 10)
        vbox.Add(sbs_conn, 0, wx.EXPAND | wx.ALL, 10)

        sb_audio = wx.StaticBox(panel, label="Microphone")
        sbs_audio = wx.StaticBoxSizer(sb_audio, wx.VERTICAL)

        hbox_mic = wx.BoxSizer(wx.HORIZONTAL)
        self.combo_mics = wx.ComboBox(panel, style=wx.CB_READONLY)
        self.refresh_mics()

        btn_refresh = wx.Button(panel, label="↻", size=(30, -1))
        btn_refresh.Bind(wx.EVT_BUTTON, lambda e: self.refresh_mics())

        hbox_mic.Add(self.combo_mics, 1, wx.EXPAND | wx.RIGHT, 5)
        hbox_mic.Add(btn_refresh, 0, wx.ALIGN_CENTER_VERTICAL)
        sbs_audio.Add(hbox_mic, 0, wx.EXPAND | wx.ALL, 10)
        vbox.Add(sbs_audio, 0, wx.EXPAND | wx.LEFT | wx.RIGHT, 10)

        sb_cmd = wx.StaticBox(panel, label="Custom Keywords")
        sbs_cmd = wx.StaticBoxSizer(sb_cmd, wx.VERTICAL)

        sbs_cmd.Add(wx.StaticText(panel, label="Go next page:"), 0, wx.TOP, 5)
        self.txt_cmd_next = wx.TextCtrl(panel, value="next, next page, go, down, yes")
        sbs_cmd.Add(self.txt_cmd_next, 0, wx.EXPAND | wx.BOTTOM, 10)

        sbs_cmd.Add(wx.StaticText(panel, label="Go priv page:"), 0, wx.TOP, 5)
        self.txt_cmd_prev = wx.TextCtrl(panel, value="back, previous, up, last")
        sbs_cmd.Add(self.txt_cmd_prev, 0, wx.EXPAND | wx.BOTTOM, 5)

        sbs_cmd.Add(wx.StaticText(panel, label="* dont add too much words"), 0, wx.ALIGN_RIGHT)
        vbox.Add(sbs_cmd, 0, wx.EXPAND | wx.ALL, 10)

        self.txt_log = wx.TextCtrl(panel, style=wx.TE_MULTILINE | wx.TE_READONLY)
        vbox.Add(self.txt_log, 1, wx.EXPAND | wx.LEFT | wx.RIGHT, 10)

        self.btn_toggle = wx.Button(panel, label="Start Listening")
        self.btn_toggle.Bind(wx.EVT_BUTTON, self.on_toggle)
        vbox.Add(self.btn_toggle, 0, wx.EXPAND | wx.ALL, 15)

        panel.SetSizer(vbox)

    def refresh_mics(self):
        self.combo_mics.Clear()
        self.device_map = {}  # index -> device_info

        info = self.pa.get_host_api_info_by_index(0)
        numdevices = info.get('deviceCount')

        idx = 0
        for i in range(0, numdevices):
            if (self.pa.get_device_info_by_host_api_device_index(0, i).get('maxInputChannels')) > 0:
                name = self.pa.get_device_info_by_host_api_device_index(0, i).get('name')
                try:
                    pass
                except:
                    pass

                label = f"{i}: {name}"
                self.combo_mics.Append(label)
                self.device_map[idx] = i
                idx += 1

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
        port_str = self.txt_port.GetValue()
        token = self.txt_token.GetValue()
        if not port_str.isdigit() or not token:
            wx.MessageBox("if not port_str.isdigit() or not token", "Error")
            return

        next_words = [w.strip().lower() for w in self.txt_cmd_next.GetValue().split(",") if w.strip()]
        prev_words = [w.strip().lower() for w in self.txt_cmd_prev.GetValue().split(",") if w.strip()]

        if not next_words or not prev_words:
            wx.MessageBox("not next_words or not prev_words", "Error")
            return

        selection = self.combo_mics.GetSelection()
        if selection == wx.NOT_FOUND:
            wx.MessageBox("wx.NOT_FOUND", "Error")
            return
        device_index = self.device_map[selection]

        self.is_running = True
        self.btn_toggle.SetLabel("Stop")
        self.txt_port.Disable()
        self.txt_token.Disable()
        self.txt_cmd_next.Disable()
        self.txt_cmd_prev.Disable()

        self.thread = threading.Thread(
            target=self.run_recognition,
            args=(int(port_str), token, next_words, prev_words, device_index),
            daemon=True
        )
        self.thread.start()

    def stop_listening(self):
        self.is_running = False
        self.btn_toggle.SetLabel("Start Listening")
        self.txt_port.Enable()
        self.txt_token.Enable()
        self.txt_cmd_next.Enable()
        self.txt_cmd_prev.Enable()
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
        try:
            all_words = list(set(next_words + prev_words))
            all_words.append("[unk]")
            grammar_json = json.dumps(all_words)

            self.log(f"Grammar Mode...")
            model = Model(DEFAULT_MODEL_PATH)

            rec = KaldiRecognizer(model, 16000, grammar_json)

            p = pyaudio.PyAudio()
            stream = p.open(format=pyaudio.paInt16, channels=1, rate=16000,
                            input=True, input_device_index=device_idx,
                            frames_per_buffer=4000)

            self.log(f"ID: {device_idx})")

            stream.start_stream()

            while self.is_running:
                data = stream.read(2000, exception_on_overflow=False)
                if len(data) == 0:
                    break

                if rec.AcceptWaveform(data):
                    res = json.loads(rec.Result())
                    text = res.get('text', '')

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
                stream.stop_stream()
                stream.close()
                p.terminate()
            except:
                pass


if __name__ == "__main__":
    app = wx.App()
    app_icon = get_app_icon()

    frm = VoiceControllerFrame()
    if app_icon.IsOk():
        frm.SetIcon(app_icon)

    frm.Show()
    app.MainLoop()
