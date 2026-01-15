import os
import platform
import sys
from functools import lru_cache
import time
import threading
import ctypes
from ctypes import wintypes
from dataclasses import dataclass
from collections import deque
import socket
from pathlib import Path

import pywinstyles

import cv2
import wx

import warnings

warnings.filterwarnings(
    "ignore",
    message=r".*SymbolDatabase\.GetPrototype\(\) is deprecated.*",
    category=UserWarning,
    module=r"google\.protobuf\.symbol_database",
)

from eyetrax import GazeEstimator, run_9_point_calibration, make_kalman

DEFAULT_MODEL_PATH = "gaze_model.pkl"
DEFAULT_IP = "127.0.0.1"

ROI_L_X0_RATIO = 0.005
ROI_L_X1_RATIO = 0.15
ROI_R_X0_RATIO = 0.85
ROI_R_X1_RATIO = 0.995
ROI_Y0_RATIO = 0.40
ROI_Y1_RATIO = 0.60

COLORKEY_R = 255
COLORKEY_G = 0
COLORKEY_B = 255

user32 = ctypes.windll.user32

GWL_EXSTYLE = -20
WS_EX_LAYERED = 0x00080000
WS_EX_TRANSPARENT = 0x00000020
WS_EX_NOACTIVATE = 0x08000000
LWA_COLORKEY = 0x00000001


def _base_dir() -> Path:
    if getattr(sys, "frozen", False):
        return Path(getattr(sys, "_MEIPASS", Path(sys.executable).parent))
    return Path(__file__).resolve().parent


def _resource_path(*parts) -> str:
    return str(_base_dir().joinpath(*parts))


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


def _rgb(r: int, g: int, b: int) -> int:
    return (b << 16) | (g << 8) | r


def set_window_click_through_and_colorkey(hwnd: int, r: int, g: int, b: int):
    ex_style = user32.GetWindowLongW(hwnd, GWL_EXSTYLE)
    ex_style |= (WS_EX_LAYERED | WS_EX_TRANSPARENT | WS_EX_NOACTIVATE)
    user32.SetWindowLongW(hwnd, GWL_EXSTYLE, ex_style)
    colorkey = _rgb(r, g, b)
    user32.SetLayeredWindowAttributes(
        wintypes.HWND(hwnd),
        wintypes.COLORREF(colorkey),
        wintypes.BYTE(0),
        wintypes.DWORD(LWA_COLORKEY),
    )


@dataclass
class DetectParams:
    double_blink_window_sec: float = 1.2
    last_gaze_valid_sec: float = 0.25
    smoothing_window: int = 10
    roi_frames: int = 3
    roi_hint_margin_px: int = 140
    filter_mode: str = "Kalman"


@dataclass
class ROIRatios:
    l_x0: float = ROI_L_X0_RATIO
    l_x1: float = ROI_L_X1_RATIO
    r_x0: float = ROI_R_X0_RATIO
    r_x1: float = ROI_R_X1_RATIO
    y0: float = ROI_Y0_RATIO
    y1: float = ROI_Y1_RATIO


def list_available_cameras(max_index: int = 10):
    available = []
    for i in range(max_index):
        cap = cv2.VideoCapture(i, cv2.CAP_DSHOW)
        if not cap.isOpened():
            cap.release()
            continue
        ret, _ = cap.read()
        cap.release()
        if ret:
            available.append(i)
    return available


class OverlayFrame(wx.Frame):
    def __init__(self, parent=None, roi: ROIRatios | None = None):
        style = wx.FRAME_NO_TASKBAR | wx.STAY_ON_TOP | wx.BORDER_NONE
        super().__init__(parent, title="EyeTrack Overlay", style=style)

        self.SetBackgroundStyle(wx.BG_STYLE_PAINT)
        self.SetBackgroundColour(wx.Colour(COLORKEY_R, COLORKEY_G, COLORKEY_B))

        self.screen_w, self.screen_h = wx.GetDisplaySize()
        self.SetSize((self.screen_w, self.screen_h))
        self.SetPosition((0, 0))

        self._lock = threading.Lock()
        self.last_xy = None
        self.last_blink = False
        self.show_left_roi = False
        self.show_right_roi = False
        self.success_flash_until = 0.0
        self.success_side = None

        self.roi = roi if roi is not None else ROIRatios()

        self.Bind(wx.EVT_PAINT, self.on_paint)

        self.timer = wx.Timer(self)
        self.Bind(wx.EVT_TIMER, self.on_timer, self.timer)
        self.timer.Start(16)

        self.Show()

        hwnd = self.GetHandle()
        set_window_click_through_and_colorkey(hwnd, COLORKEY_R, COLORKEY_G, COLORKEY_B)

    def set_roi_ratios(self, roi: ROIRatios):
        with self._lock:
            self.roi = ROIRatios(
                l_x0=float(roi.l_x0),
                l_x1=float(roi.l_x1),
                r_x0=float(roi.r_x0),
                r_x1=float(roi.r_x1),
                y0=float(roi.y0),
                y1=float(roi.y1),
            )

    def get_roi_rects(self):
        sw, sh = self.screen_w, self.screen_h
        with self._lock:
            roi = self.roi

        y0 = int(sh * roi.y0)
        y1 = int(sh * roi.y1)

        lx0 = int(sw * roi.l_x0)
        lx1 = int(sw * roi.l_x1)

        rx0 = int(sw * roi.r_x0)
        rx1 = int(sw * roi.r_x1)

        left = (lx0, y0, lx1 - lx0, y1 - y0)
        right = (rx0, y0, rx1 - rx0, y1 - y0)
        return left, right

    def set_state(self, x: float, y: float, blink: bool, show_left_roi: bool, show_right_roi: bool):
        with self._lock:
            self.last_xy = (x, y)
            self.last_blink = bool(blink)
            self.show_left_roi = bool(show_left_roi)
            self.show_right_roi = bool(show_right_roi)

    def flash_success(self, side: str, duration_sec: float = 0.4):
        with self._lock:
            self.success_side = side
            self.success_flash_until = time.time() + duration_sec

    def on_timer(self, evt):
        self.Refresh(False)

    def on_paint(self, evt):
        dc = wx.AutoBufferedPaintDC(self)
        gc = wx.GraphicsContext.Create(dc)

        dc.SetBackground(wx.Brush(wx.Colour(COLORKEY_R, COLORKEY_G, COLORKEY_B)))
        dc.Clear()

        with self._lock:
            xy = self.last_xy
            blink = self.last_blink
            show_l = self.show_left_roi
            show_r = self.show_right_roi
            flash_until = self.success_flash_until
            flash_side = self.success_side

        left_rect, right_rect = self.get_roi_rects()

        def draw_roi(rect):
            x, y, w, h = rect
            pen = wx.Pen(wx.Colour(255, 255, 0), 3)
            gc.SetPen(pen)
            gc.SetBrush(wx.Brush(wx.Colour(0, 0, 0, 0)))
            gc.DrawRectangle(x, y, w, h)

        if show_l:
            draw_roi(left_rect)
        if show_r:
            draw_roi(right_rect)

        if xy is not None:
            gx, gy = xy
            r = 10

            pen_cursor = wx.Pen(wx.Colour(0, 255, 255), 3)
            gc.SetPen(pen_cursor)
            gc.SetBrush(wx.Brush(wx.Colour(0, 0, 0, 0)))
            gc.DrawEllipse(gx - r, gy - r, r * 2, r * 2)

            gc.StrokeLine(gx - 16, gy, gx + 16, gy)
            gc.StrokeLine(gx, gy - 16, gx, gy + 16)

            if blink:
                gc.SetFont(
                    wx.Font(12, wx.FONTFAMILY_DEFAULT, wx.FONTSTYLE_NORMAL, wx.FONTWEIGHT_BOLD),
                    wx.Colour(255, 255, 255),
                )
                gc.DrawText("BLINK", gx + 14, gy + 8)

        if time.time() < flash_until and flash_side in ("L", "R"):
            text = "LEFT OK" if flash_side == "L" else "RIGHT OK"
            gc.SetFont(
                wx.Font(26, wx.FONTFAMILY_DEFAULT, wx.FONTSTYLE_NORMAL, wx.FONTWEIGHT_BOLD),
                wx.Colour(255, 255, 255),
            )
            gc.DrawText(text, int(self.screen_w * 0.42), int(self.screen_h * 0.08))


class MainFrame(wx.Frame):
    def __init__(self):
        super().__init__(None, title="wxReader EyeTrack Commander", size=(640, 768))
        panel = wx.Panel(self)

        self.SetFont(get_app_font(0))

        self.estimator = GazeEstimator()
        self.model_path = DEFAULT_MODEL_PATH
        self.model_loaded = False

        self.tracking_thread = None
        self.stop_event = threading.Event()
        self.overlay = None

        self.params_lock = threading.Lock()
        self.params = DetectParams()

        self.roi_lock = threading.Lock()
        self.roi = ROIRatios()

        self.kalman_filter = None
        self.kalman_mode = False

        self.blink_times_L = deque(maxlen=6)
        self.blink_times_R = deque(maxlen=6)
        self.last_blink_flag = False

        self.xy_buffer = deque(maxlen=self.params.smoothing_window)
        self.last_xy = None
        self.last_xy_time = 0.0

        self.in_left_streak = 0
        self.in_right_streak = 0

        self.device_map = {}

        left_panel = wx.Panel(panel)
        self.main_panel = panel
        self.left_panel = left_panel

        root = wx.BoxSizer(wx.VERTICAL)
        panel.SetSizer(root)

        root.Add(left_panel, 1, wx.EXPAND | wx.ALL, 10)

        left_panel.SetMinSize((600, -1))

        vbox_left = wx.BoxSizer(wx.VERTICAL)
        left_panel.SetSizer(vbox_left)

        header = wx.BoxSizer(wx.HORIZONTAL)
        title = wx.StaticText(left_panel, label="EyeTrack Commander")
        title.SetFont(get_app_font(3))
        self.lbl_status = wx.StaticText(left_panel, label="Idle")
        header.Add(title, 1, wx.ALIGN_CENTER_VERTICAL | wx.LEFT, 6)
        header.Add(self.lbl_status, 0, wx.ALIGN_CENTER_VERTICAL | wx.RIGHT, 6)
        vbox_left.Add(header, 0, wx.EXPAND | wx.TOP | wx.BOTTOM, 6)

        cams = list_available_cameras(10)
        if not cams:
            cams = [0]
        self.cams = cams

        row_cam = wx.BoxSizer(wx.HORIZONTAL)
        row_cam.Add(wx.StaticText(left_panel, label="Camera:"), 0, wx.ALIGN_CENTER_VERTICAL | wx.RIGHT, 8)
        self.combo_cam = wx.ComboBox(left_panel, choices=[f"Camera {i}" for i in cams], style=wx.CB_READONLY)
        self.combo_cam.SetSelection(0)
        row_cam.Add(self.combo_cam, 1, wx.EXPAND)
        vbox_left.Add(row_cam, 0, wx.EXPAND | wx.LEFT | wx.RIGHT | wx.BOTTOM, 10)

        top_row = wx.BoxSizer(wx.HORIZONTAL)

        sb_conn = wx.StaticBox(left_panel, label="Connection")
        sbs_conn = wx.StaticBoxSizer(sb_conn, wx.VERTICAL)

        grid_conn = wx.FlexGridSizer(2, 2, 6, 8)
        grid_conn.AddGrowableCol(1, 1)

        lbl_port = wx.StaticText(left_panel, label="Port")
        self.txt_port = wx.TextCtrl(left_panel, value="", size=(120, -1))

        lbl_token = wx.StaticText(left_panel, label="Token")
        self.txt_token = wx.TextCtrl(left_panel, value="")

        grid_conn.Add(lbl_port, 0, wx.ALIGN_CENTER_VERTICAL)
        grid_conn.Add(self.txt_port, 1, wx.EXPAND)
        grid_conn.Add(lbl_token, 0, wx.ALIGN_CENTER_VERTICAL)
        grid_conn.Add(self.txt_token, 1, wx.EXPAND)

        sbs_conn.Add(grid_conn, 0, wx.EXPAND | wx.ALL, 8)
        top_row.Add(sbs_conn, 1, wx.EXPAND | wx.RIGHT, 10)

        sb_model = wx.StaticBox(left_panel, label="Model")
        sbs_model = wx.StaticBoxSizer(sb_model, wx.VERTICAL)

        row_model = wx.BoxSizer(wx.HORIZONTAL)
        self.txt_model = wx.TextCtrl(left_panel, value=self.model_path)
        self.btn_browse = wx.Button(left_panel, label="Load model...", size=(120, -1))
        self.btn_browse.Bind(wx.EVT_BUTTON, self.on_load_model)
        row_model.Add(self.txt_model, 1, wx.EXPAND | wx.RIGHT, 8)
        row_model.Add(self.btn_browse, 0)
        sbs_model.Add(row_model, 0, wx.EXPAND | wx.ALL, 8)

        top_row.Add(sbs_model, 1, wx.EXPAND)

        vbox_left.Add(top_row, 0, wx.EXPAND | wx.LEFT | wx.RIGHT | wx.BOTTOM, 10)

        self.cp_params = wx.CollapsiblePane(
            left_panel,
            label="Detection Parameters",
            style=wx.CP_DEFAULT_STYLE | wx.CP_NO_TLW_RESIZE
        )
        self.Bind(wx.EVT_COLLAPSIBLEPANE_CHANGED, self.on_collapsible_changed, self.cp_params)

        params_pane = self.cp_params.GetPane()
        sizer_params = wx.BoxSizer(wx.VERTICAL)

        grid = wx.FlexGridSizer(rows=0, cols=4, vgap=8, hgap=10)
        grid.AddGrowableCol(1, 1)
        grid.AddGrowableCol(3, 1)

        grid.Add(wx.StaticText(params_pane, label="Smoothing window (N):"), 0, wx.ALIGN_CENTER_VERTICAL)
        self.spin_smoothing = wx.SpinCtrl(params_pane, min=1, max=30, initial=self.params.smoothing_window)
        grid.Add(self.spin_smoothing, 0, wx.EXPAND)

        grid.Add(wx.StaticText(params_pane, label="ROI frames:"), 0, wx.ALIGN_CENTER_VERTICAL)
        self.spin_dwell = wx.SpinCtrl(params_pane, min=1, max=20, initial=self.params.roi_frames)
        grid.Add(self.spin_dwell, 0, wx.EXPAND)

        grid.Add(wx.StaticText(params_pane, label="Double blink window (sec):"), 0, wx.ALIGN_CENTER_VERTICAL)
        self.spin_double = wx.SpinCtrlDouble(
            params_pane,
            min=0.2,
            max=3.0,
            inc=0.05,
            initial=self.params.double_blink_window_sec
        )
        self.spin_double.SetDigits(2)
        grid.Add(self.spin_double, 0, wx.EXPAND)

        grid.Add(wx.StaticText(params_pane, label="Last gaze valid (sec):"), 0, wx.ALIGN_CENTER_VERTICAL)
        self.spin_gaze_valid = wx.SpinCtrlDouble(
            params_pane,
            min=0.05,
            max=1.5,
            inc=0.05,
            initial=self.params.last_gaze_valid_sec
        )
        self.spin_gaze_valid.SetDigits(2)
        grid.Add(self.spin_gaze_valid, 0, wx.EXPAND)

        grid.Add(wx.StaticText(params_pane, label="ROI hint margin (px):"), 0, wx.ALIGN_CENTER_VERTICAL)
        self.spin_hint = wx.SpinCtrl(params_pane, min=0, max=800, initial=self.params.roi_hint_margin_px)
        grid.Add(self.spin_hint, 0, wx.EXPAND)

        grid.Add(wx.StaticText(params_pane, label="Filter:"), 0, wx.ALIGN_CENTER_VERTICAL)
        self.combo_filter = wx.ComboBox(params_pane, choices=["MovingAvg", "Kalman"], style=wx.CB_READONLY)
        self.combo_filter.SetSelection(0)
        grid.Add(self.combo_filter, 0, wx.EXPAND)

        grid.Add(wx.StaticText(params_pane, label=""), 0)
        self.btn_apply_params = wx.Button(params_pane, label="Apply parameters")
        self.btn_apply_params.Bind(wx.EVT_BUTTON, self.on_apply_params)
        grid.Add(self.btn_apply_params, 0, wx.EXPAND)

        sizer_params.Add(grid, 0, wx.EXPAND | wx.ALL, 10)
        params_pane.SetSizer(sizer_params)

        vbox_left.Add(self.cp_params, 0, wx.EXPAND | wx.LEFT | wx.RIGHT | wx.BOTTOM, 10)
        self.cp_params.Collapse(True)

        self.cp_roi = wx.CollapsiblePane(
            left_panel,
            label="ROI Ratios",
            style=wx.CP_DEFAULT_STYLE | wx.CP_NO_TLW_RESIZE
        )
        self.Bind(wx.EVT_COLLAPSIBLEPANE_CHANGED, self.on_collapsible_changed, self.cp_roi)

        roi_pane = self.cp_roi.GetPane()
        sizer_roi = wx.BoxSizer(wx.VERTICAL)

        grid_roi = wx.FlexGridSizer(rows=0, cols=4, vgap=8, hgap=10)
        grid_roi.AddGrowableCol(1, 1)
        grid_roi.AddGrowableCol(3, 1)

        self.spin_roi_lx0 = wx.SpinCtrlDouble(roi_pane, min=0.0, max=1.0, inc=0.001, initial=self.roi.l_x0)
        self.spin_roi_lx1 = wx.SpinCtrlDouble(roi_pane, min=0.0, max=1.0, inc=0.001, initial=self.roi.l_x1)
        self.spin_roi_rx0 = wx.SpinCtrlDouble(roi_pane, min=0.0, max=1.0, inc=0.001, initial=self.roi.r_x0)
        self.spin_roi_rx1 = wx.SpinCtrlDouble(roi_pane, min=0.0, max=1.0, inc=0.001, initial=self.roi.r_x1)
        self.spin_roi_y0 = wx.SpinCtrlDouble(roi_pane, min=0.0, max=1.0, inc=0.001, initial=self.roi.y0)
        self.spin_roi_y1 = wx.SpinCtrlDouble(roi_pane, min=0.0, max=1.0, inc=0.001, initial=self.roi.y1)

        for s in [
            self.spin_roi_lx0,
            self.spin_roi_lx1,
            self.spin_roi_rx0,
            self.spin_roi_rx1,
            self.spin_roi_y0,
            self.spin_roi_y1,
        ]:
            s.SetDigits(3)

        grid_roi.Add(wx.StaticText(roi_pane, label="ROI_L_X0_RATIO:"), 0, wx.ALIGN_CENTER_VERTICAL)
        grid_roi.Add(self.spin_roi_lx0, 0, wx.EXPAND)

        grid_roi.Add(wx.StaticText(roi_pane, label="ROI_L_X1_RATIO:"), 0, wx.ALIGN_CENTER_VERTICAL)
        grid_roi.Add(self.spin_roi_lx1, 0, wx.EXPAND)

        grid_roi.Add(wx.StaticText(roi_pane, label="ROI_R_X0_RATIO:"), 0, wx.ALIGN_CENTER_VERTICAL)
        grid_roi.Add(self.spin_roi_rx0, 0, wx.EXPAND)

        grid_roi.Add(wx.StaticText(roi_pane, label="ROI_R_X1_RATIO:"), 0, wx.ALIGN_CENTER_VERTICAL)
        grid_roi.Add(self.spin_roi_rx1, 0, wx.EXPAND)

        grid_roi.Add(wx.StaticText(roi_pane, label="ROI_Y0_RATIO:"), 0, wx.ALIGN_CENTER_VERTICAL)
        grid_roi.Add(self.spin_roi_y0, 0, wx.EXPAND)

        grid_roi.Add(wx.StaticText(roi_pane, label="ROI_Y1_RATIO:"), 0, wx.ALIGN_CENTER_VERTICAL)
        grid_roi.Add(self.spin_roi_y1, 0, wx.EXPAND)

        self.btn_apply_roi = wx.Button(roi_pane, label="Apply ROI ratios")
        self.btn_apply_roi.Bind(wx.EVT_BUTTON, self.on_apply_roi)

        sizer_roi.Add(grid_roi, 0, wx.EXPAND | wx.ALL, 10)
        sizer_roi.Add(self.btn_apply_roi, 0, wx.EXPAND | wx.LEFT | wx.RIGHT | wx.BOTTOM, 10)

        roi_pane.SetSizer(sizer_roi)

        vbox_left.Add(self.cp_roi, 0, wx.EXPAND | wx.LEFT | wx.RIGHT | wx.BOTTOM, 10)
        self.cp_roi.Collapse(True)

        row_btn = wx.BoxSizer(wx.HORIZONTAL)

        self.btn_calib = wx.Button(left_panel, label="Calibrate (9-point)", size=(160, 36))
        self.btn_calib.Bind(wx.EVT_BUTTON, self.on_calibrate)
        row_btn.Add(self.btn_calib, 0, wx.RIGHT, 10)

        self.btn_start = wx.Button(left_panel, label="Start tracking", size=(160, 36))
        self.btn_start.Bind(wx.EVT_BUTTON, self.on_start)
        row_btn.Add(self.btn_start, 0, wx.RIGHT, 10)

        self.btn_stop = wx.Button(left_panel, label="Stop", size=(120, 36))
        self.btn_stop.Bind(wx.EVT_BUTTON, self.on_stop)
        self.btn_stop.Disable()
        row_btn.Add(self.btn_stop, 0, wx.RIGHT, 10)

        self.btn_exit = wx.Button(left_panel, label="Exit", size=(120, 36))
        self.btn_exit.Bind(wx.EVT_BUTTON, self.on_exit)
        row_btn.Add(self.btn_exit, 0)

        vbox_left.Add(row_btn, 0, wx.ALL, 10)

        self.txt_status = wx.StaticText(left_panel, label="Status: model not loaded")
        vbox_left.Add(self.txt_status, 0, wx.LEFT | wx.RIGHT | wx.BOTTOM, 10)

        vbox_left.Add(wx.StaticLine(left_panel), 0, wx.EXPAND | wx.LEFT | wx.RIGHT | wx.BOTTOM, 10)

        log_header = wx.BoxSizer(wx.HORIZONTAL)
        log_label = wx.StaticText(left_panel, label="Activity")
        log_label.SetFont(get_app_font(1))
        self.btn_clear_log = wx.Button(left_panel, label="Clear", size=(80, -1))
        self.btn_clear_log.Bind(wx.EVT_BUTTON, lambda e: self.txt_log.SetValue(""))
        log_header.Add(log_label, 1, wx.ALIGN_CENTER_VERTICAL)
        log_header.Add(self.btn_clear_log, 0, wx.ALIGN_CENTER_VERTICAL)
        vbox_left.Add(log_header, 0, wx.EXPAND | wx.LEFT | wx.RIGHT | wx.BOTTOM, 10)

        self.txt_log = wx.TextCtrl(left_panel, style=wx.TE_MULTILINE | wx.TE_READONLY)
        vbox_left.Add(self.txt_log, 1, wx.EXPAND | wx.LEFT | wx.RIGHT | wx.BOTTOM, 10)

        panel.Layout()

        self.refresh_model_state(auto_try_load=False)

        self.Centre()
        msw_set_theme(self)

    def on_collapsible_changed(self, evt):
        self.left_panel.Layout()
        self.main_panel.Layout()
        self.SendSizeEvent()

    def log(self, msg: str):
        wx.CallAfter(self.txt_log.AppendText, f"{msg}\n")

    def on_apply_roi(self, evt):
        lx0 = float(self.spin_roi_lx0.GetValue())
        lx1 = float(self.spin_roi_lx1.GetValue())
        rx0 = float(self.spin_roi_rx0.GetValue())
        rx1 = float(self.spin_roi_rx1.GetValue())
        y0 = float(self.spin_roi_y0.GetValue())
        y1 = float(self.spin_roi_y1.GetValue())

        ok = True
        if not (0.0 <= lx0 < lx1 <= 1.0):
            ok = False
        if not (0.0 <= rx0 < rx1 <= 1.0):
            ok = False
        if not (0.0 <= y0 < y1 <= 1.0):
            ok = False

        if not ok:
            wx.MessageBox("Invalid ROI ratios. Ensure X0 < X1 and Y0 < Y1 and all in [0..1].", "Error",
                          wx.OK | wx.ICON_ERROR)
            return

        with self.roi_lock:
            self.roi = ROIRatios(l_x0=lx0, l_x1=lx1, r_x0=rx0, r_x1=rx1, y0=y0, y1=y1)

        if self.overlay is not None:
            wx.CallAfter(self.overlay.set_roi_ratios, self.roi)

        self.txt_status.SetLabel("Status: ROI ratios updated")
        self.log(f"ROI updated: L({lx0:.3f}-{lx1:.3f}) R({rx0:.3f}-{rx1:.3f}) Y({y0:.3f}-{y1:.3f})")

    def get_selected_camera_index(self) -> int:
        idx = self.combo_cam.GetSelection()
        return self.cams[idx] if idx >= 0 else 0

    def roi_rects(self):
        sw, sh = wx.GetDisplaySize()
        with self.roi_lock:
            roi = self.roi

        y0 = int(sh * roi.y0)
        y1 = int(sh * roi.y1)
        lx0 = int(sw * roi.l_x0)
        lx1 = int(sw * roi.l_x1)
        rx0 = int(sw * roi.r_x0)
        rx1 = int(sw * roi.r_x1)
        return (lx0, y0, lx1, y1), (rx0, y0, rx1, y1)

    def point_in_rect(self, x: float, y: float, rect) -> bool:
        x0, y0, x1, y1 = rect
        return (x0 <= x <= x1) and (y0 <= y <= y1)

    def point_near_rect(self, x: float, y: float, rect, margin_px: int) -> bool:
        x0, y0, x1, y1 = rect
        x0 -= margin_px
        y0 -= margin_px
        x1 += margin_px
        y1 += margin_px
        return (x0 <= x <= x1) and (y0 <= y <= y1)

    def parse_conn(self):
        port_str = self.txt_port.GetValue().strip()
        token = self.txt_token.GetValue().strip()
        if not port_str.isdigit() or not token:
            return None, None
        return int(port_str), token

    def send_udp_command(self, cmd: str):
        port, token = self.parse_conn()
        if port is None:
            self.log("Connection invalid: Port/Token required")
            return
        try:
            sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
            msg = f"{token}|{cmd}"
            sock.sendto(msg.encode(), (DEFAULT_IP, port))
            self.log(cmd)
        except Exception as e:
            self.log(str(e))
        finally:
            try:
                sock.close()
            except Exception:
                pass

    def on_left_success(self):
        self.send_udp_command("PREV")
        self.log("Left ROI success")

    def on_right_success(self):
        self.send_udp_command("NEXT")
        self.log("Right ROI success")

    def refresh_model_state(self, auto_try_load: bool = False):
        path = self.txt_model.GetValue().strip()
        self.model_path = path
        exists = os.path.exists(path)

        if auto_try_load and exists and not self.model_loaded:
            try:
                self.estimator = GazeEstimator()
                self.estimator.load_model(path)
                self.model_loaded = True
            except Exception as e:
                self.model_loaded = False
                self.txt_status.SetLabel(f"Status: load failed: {e}")

        if self.model_loaded:
            self.txt_status.SetLabel(f"Status: model loaded ({path})")
            self.btn_start.Enable()
        else:
            if exists:
                self.txt_status.SetLabel(f"Status: model file exists ({path}), start enabled")
                self.btn_start.Enable()
            else:
                self.txt_status.SetLabel("Status: model file not found (load or calibrate)")
                self.btn_start.Disable()

    def on_apply_params(self, evt):
        mode = self.combo_filter.GetStringSelection()

        with self.params_lock:
            self.params.smoothing_window = int(self.spin_smoothing.GetValue())
            self.params.roi_frames = int(self.spin_dwell.GetValue())
            self.params.double_blink_window_sec = float(self.spin_double.GetValue())
            self.params.last_gaze_valid_sec = float(self.spin_gaze_valid.GetValue())
            self.params.roi_hint_margin_px = int(self.spin_hint.GetValue())
            self.params.filter_mode = "kalman" if mode == "Kalman" else "ma"
        self.txt_status.SetLabel(
            "Status: parameters updated"
            + (" (tracking running)" if self.tracking_thread and self.tracking_thread.is_alive() else "")
        )

    def on_load_model(self, evt):
        with wx.FileDialog(
                self,
                "Select model (.pkl)",
                wildcard="Pickle files (*.pkl)|*.pkl|All files (*.*)|*.*",
                style=wx.FD_OPEN | wx.FD_FILE_MUST_EXIST,
        ) as dlg:
            if dlg.ShowModal() == wx.ID_CANCEL:
                return
            path = dlg.GetPath()
            self.txt_model.SetValue(path)

        try:
            self.estimator = GazeEstimator()
            self.estimator.load_model(path)
            self.model_loaded = True
            self.log(f"Model loaded: {path}")
        except Exception as e:
            self.model_loaded = False
            wx.MessageBox(f"Model load failed:\n{e}", "Error", wx.OK | wx.ICON_ERROR)
            self.log(f"Model load failed: {e}")

        self.refresh_model_state()

    def on_calibrate(self, evt):
        self.btn_calib.Disable()
        self.btn_start.Disable()
        self.btn_browse.Disable()
        self.combo_cam.Disable()

        self.lbl_status.SetLabel("Calibrating")
        self.txt_status.SetLabel("Status: calibrating...")

        cam_index = self.get_selected_camera_index()
        model_path = self.txt_model.GetValue().strip()

        def calib_job():
            try:
                self.estimator = GazeEstimator()
                try:
                    run_9_point_calibration(self.estimator, camera=cam_index)
                except TypeError:
                    run_9_point_calibration(self.estimator)

                self.estimator.save_model(model_path)
                self.model_loaded = True
                wx.CallAfter(self.txt_status.SetLabel, f"Status: calibrated and saved ({model_path})")
                wx.CallAfter(self.log, f"Calibrated and saved: {model_path}")
            except Exception as e:
                self.model_loaded = False
                wx.CallAfter(self.txt_status.SetLabel, f"Status: calibration failed: {e}")
                wx.CallAfter(wx.MessageBox, f"Calibration failed:\n{e}", "Error", wx.OK | wx.ICON_ERROR)
                wx.CallAfter(self.log, f"Calibration failed: {e}")
            finally:
                wx.CallAfter(self.btn_calib.Enable)
                wx.CallAfter(self.btn_browse.Enable)
                wx.CallAfter(self.combo_cam.Enable)
                wx.CallAfter(self.refresh_model_state)
                wx.CallAfter(self.lbl_status.SetLabel, "Idle")

        threading.Thread(target=calib_job, daemon=True).start()

    def reset_filter_state(self, use_kalman: bool):
        self.kalman_mode = bool(use_kalman)
        self.kalman_filter = make_kalman() if use_kalman else None

    def kalman_step(self, x: float, y: float):
        kf = self.kalman_filter
        if kf is None:
            self.kalman_filter = make_kalman()
            kf = self.kalman_filter

        for args in [(x, y), ([x, y],), ((x, y),)]:
            try:
                out = kf(*args) if callable(kf) else None
                if out is None:
                    continue
                if isinstance(out, (list, tuple)) and len(out) >= 2:
                    return float(out[0]), float(out[1])
            except Exception:
                continue

        try:
            if hasattr(kf, "update"):
                out = kf.update(x, y)
                if isinstance(out, (list, tuple)) and len(out) >= 2:
                    return float(out[0]), float(out[1])
        except Exception:
            pass

        return x, y

    def on_start(self, evt):
        self.on_apply_params(None)

        port, token = self.parse_conn()
        if port is None:
            wx.MessageBox("Please enter a valid Port and Token.", "Error", wx.OK | wx.ICON_ERROR)
            return

        self.refresh_model_state(auto_try_load=True)

        if not self.model_loaded:
            if os.path.exists(self.model_path):
                wx.MessageBox("Model exists but failed to load. Try loading manually.", "Error", wx.OK | wx.ICON_ERROR)
            else:
                wx.MessageBox("No model available. Load or calibrate first.", "Warning", wx.OK | wx.ICON_WARNING)
            return

        cam_index = self.get_selected_camera_index()
        self.stop_event.clear()

        if self.overlay is None:
            with self.roi_lock:
                roi_copy = self.roi
            self.overlay = OverlayFrame(self, roi=roi_copy)

        self.btn_start.Disable()
        self.btn_stop.Enable()
        self.btn_calib.Disable()
        self.btn_browse.Disable()
        self.combo_cam.Disable()

        self.txt_port.Disable()
        self.txt_token.Disable()

        self.lbl_status.SetLabel("Tracking")
        self.txt_status.SetLabel("Status: tracking...")

        self.log("Tracking started")

        self.tracking_thread = threading.Thread(
            target=self.tracking_loop,
            args=(cam_index,),
            daemon=True
        )
        self.tracking_thread.start()

    def on_stop(self, evt):
        self.stop_event.set()

        self.btn_stop.Disable()
        self.btn_start.Enable()
        self.btn_calib.Enable()
        self.btn_browse.Enable()
        self.combo_cam.Enable()

        self.txt_port.Enable()
        self.txt_token.Enable()

        self.lbl_status.SetLabel("Idle")
        self.txt_status.SetLabel("Status: stopped")
        self.log("Tracking stopped")

        if self.overlay is not None:
            self.overlay.Destroy()
            self.overlay = None

    def on_exit(self, evt):
        self.stop_event.set()
        if self.overlay is not None:
            self.overlay.Destroy()
            self.overlay = None
        self.Destroy()

    def tracking_loop(self, camera_index: int):
        cap = cv2.VideoCapture(camera_index, cv2.CAP_DSHOW)
        if not cap.isOpened():
            wx.CallAfter(wx.MessageBox, f"Cannot open camera {camera_index}", "Error", wx.OK | wx.ICON_ERROR)
            wx.CallAfter(self.on_stop, None)
            return

        self.blink_times_L.clear()
        self.blink_times_R.clear()
        self.last_blink_flag = False

        with self.params_lock:
            smoothing = self.params.smoothing_window
            use_kalman = (self.params.filter_mode == "kalman")

        self.xy_buffer = deque(maxlen=max(1, smoothing))
        self.reset_filter_state(use_kalman)

        self.last_xy = None
        self.last_xy_time = 0.0

        self.in_left_streak = 0
        self.in_right_streak = 0

        while not self.stop_event.is_set():
            ret, frame = cap.read()
            if not ret:
                continue

            now = time.time()

            with self.params_lock:
                params = DetectParams(
                    double_blink_window_sec=self.params.double_blink_window_sec,
                    last_gaze_valid_sec=self.params.last_gaze_valid_sec,
                    smoothing_window=self.params.smoothing_window,
                    roi_frames=self.params.roi_frames,
                    roi_hint_margin_px=self.params.roi_hint_margin_px,
                    filter_mode=self.params.filter_mode,
                )

            if self.xy_buffer.maxlen != max(1, params.smoothing_window):
                old = list(self.xy_buffer)
                self.xy_buffer = deque(old, maxlen=max(1, params.smoothing_window))

            left_roi, right_roi = self.roi_rects()

            features, blink = self.estimator.extract_features(frame)

            if features is not None and not blink:
                try:
                    x, y = self.estimator.predict([features])[0]
                    x = float(x)
                    y = float(y)

                    if params.filter_mode == "kalman":
                        if not self.kalman_mode:
                            self.reset_filter_state(True)
                        fx, fy = self.kalman_step(x, y)
                        self.last_xy = (fx, fy)
                        self.last_xy_time = now
                    else:
                        if self.kalman_mode:
                            self.reset_filter_state(False)
                        self.xy_buffer.append((x, y))
                        avg_x = sum(p[0] for p in self.xy_buffer) / len(self.xy_buffer)
                        avg_y = sum(p[1] for p in self.xy_buffer) / len(self.xy_buffer)
                        self.last_xy = (avg_x, avg_y)
                        self.last_xy_time = now
                except Exception:
                    print(Exception)

            in_left = False
            in_right = False
            show_left_hint = False
            show_right_hint = False

            if self.last_xy is not None:
                gx, gy = self.last_xy
                in_left = self.point_in_rect(gx, gy, left_roi)
                in_right = self.point_in_rect(gx, gy, right_roi)
                show_left_hint = self.point_near_rect(gx, gy, left_roi, params.roi_hint_margin_px)
                show_right_hint = self.point_near_rect(gx, gy, right_roi, params.roi_hint_margin_px)

            if in_left:
                self.in_left_streak += 1
            else:
                self.in_left_streak = 0

            if in_right:
                self.in_right_streak += 1
            else:
                self.in_right_streak = 0

            left_stable = self.in_left_streak >= max(1, params.roi_frames)
            right_stable = self.in_right_streak >= max(1, params.roi_frames)

            if (not self.last_blink_flag) and blink:
                gaze_fresh = (self.last_xy is not None) and ((now - self.last_xy_time) <= params.last_gaze_valid_sec)
                if gaze_fresh and left_stable:
                    self.blink_times_L.append(now)
                if gaze_fresh and right_stable:
                    self.blink_times_R.append(now)

            self.last_blink_flag = bool(blink)

            def check_double_blink(blinks: deque) -> bool:
                if len(blinks) >= 2:
                    return (blinks[-1] - blinks[-2]) <= params.double_blink_window_sec
                return False

            if check_double_blink(self.blink_times_L):
                self.blink_times_L.clear()
                wx.CallAfter(self.on_left_success)
                if self.overlay is not None:
                    wx.CallAfter(self.overlay.flash_success, "L")

            if check_double_blink(self.blink_times_R):
                self.blink_times_R.clear()
                wx.CallAfter(self.on_right_success)
                if self.overlay is not None:
                    wx.CallAfter(self.overlay.flash_success, "R")

            if self.overlay is not None and self.last_xy is not None:
                wx.CallAfter(
                    self.overlay.set_state,
                    self.last_xy[0],
                    self.last_xy[1],
                    bool(blink),
                    bool(show_left_hint),
                    bool(show_right_hint),
                )

        cap.release()


def main():
    app = wx.App(False)
    app_icon = get_app_icon()

    frm = MainFrame()

    if app_icon.IsOk():
        frm.SetIcon(app_icon)

    frm.Show()
    app.MainLoop()


if __name__ == "__main__":
    main()
