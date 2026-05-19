import concurrent.futures
import os
import queue
import threading
import time

import wx

from wxReaderIcon import get_app_icon
from wxReaderProvider import PdfContentProvider, ArchiveContentProvider
from wxReaderProvider import SevenZipContentProvider
from wxReaderString import SUPPORTED_EXTENSIONS


def _(text):
    return wx.GetTranslation(text)


THUMB_WIDTH = 140
THUMB_HEIGHT = 200
PANEL_HEIGHT = THUMB_HEIGHT + 55
MAX_WORKERS = max(1, (os.cpu_count() or 2) - 1)
LIGHT_GALLERY_THEME = {
    "bg": wx.Colour(240, 240, 240),
    "card": wx.Colour(240, 240, 240),
    "card_hover": wx.Colour(154, 200, 138),
    "border": wx.Colour(210, 210, 210),
    "text": wx.Colour(40, 40, 40),
    "placeholder": wx.Colour(220, 220, 220),
}
DARK_GALLERY_THEME = {
    "bg": wx.Colour(32, 32, 32),
    "card": wx.Colour(42, 42, 42),
    "card_hover": wx.Colour(76, 122, 92),
    "border": wx.Colour(78, 78, 78),
    "text": wx.Colour(230, 230, 230),
    "placeholder": wx.Colour(68, 68, 68),
}


def get_gallery_theme(dark_mode: bool):
    return DARK_GALLERY_THEME if dark_mode else LIGHT_GALLERY_THEME


def process_cover_with_provider(file_path, thumb_width, thumb_height):
    provider = None
    ext = os.path.splitext(file_path)[1].lower()

    try:
        if ext in {".pdf", ".epub", ".mobi", ".fb2"}:
            provider = PdfContentProvider(file_path)
        elif ext in {".zip", ".cbz"}:
            provider = ArchiveContentProvider(file_path)
        elif ext in {".7z"}:
            provider = SevenZipContentProvider(file_path)
        else:
            return file_path, 0, 0, None

        thumb_data = provider.get_thumbnail(thumb_width, thumb_height)

        if thumb_data:
            w, h, raw_bytes = thumb_data
            return file_path, w, h, raw_bytes

    except Exception as e:
        print(f"[ERROR] wxReader failed to process cover: {e}")
    finally:
        if provider:
            provider.close()

    return file_path, 0, 0, None


class VirtualThumbnailCanvas(wx.ScrolledWindow):
    CELL_WIDTH = THUMB_WIDTH + 20
    CELL_HEIGHT = PANEL_HEIGHT + 20
    OUTER_MARGIN = 10

    def __init__(self, parent, placeholder_bmp, callback, theme):
        super().__init__(parent, style=wx.VSCROLL | wx.BORDER_NONE)

        self.placeholder_bmp = placeholder_bmp
        self.callback = callback
        self.theme = theme

        self.files = []
        self.bitmap_map = {}
        self.hover_index = -1
        self.columns = 1

        self.SetBackgroundColour(self.theme["bg"])
        self.SetBackgroundStyle(wx.BG_STYLE_PAINT)
        self.SetScrollRate(0, 20)

        self.Bind(wx.EVT_PAINT, self.on_paint)
        self.Bind(wx.EVT_SIZE, self.on_size)
        self.Bind(wx.EVT_LEFT_DOWN, self.on_left_down)
        self.Bind(wx.EVT_MOTION, self.on_mouse_move)
        self.Bind(wx.EVT_LEAVE_WINDOW, self.on_mouse_leave)

    def clear(self):
        self.files.clear()
        self.bitmap_map.clear()
        self.hover_index = -1
        self.SetVirtualSize((self.GetClientSize().width, 0))
        self.Scroll(0, 0)
        self.Refresh(False)

    def set_files(self, files, keep_scroll=False):
        old_view = self.GetViewStart()

        self.files = list(files)
        self._recalc_virtual_size()

        if keep_scroll:
            self.Scroll(old_view[0], old_view[1])
        else:
            self.Scroll(0, 0)

        self.Refresh(False)

    def update_bitmap(self, file_path, bitmap):
        self.bitmap_map[file_path] = bitmap

        try:
            index = self.files.index(file_path)
        except ValueError:
            return

        if self._index_is_visible(index):
            self.Refresh(False)

    def _recalc_virtual_size(self):
        client_w = max(1, self.GetClientSize().width)

        usable_w = max(1, client_w - self.OUTER_MARGIN * 2)
        self.columns = max(1, usable_w // self.CELL_WIDTH)

        rows = (len(self.files) + self.columns - 1) // self.columns
        total_h = self.OUTER_MARGIN * 2 + rows * self.CELL_HEIGHT

        self.SetVirtualSize((client_w, total_h))

    def _index_rect(self, index):
        row = index // self.columns
        col = index % self.columns

        cell_x = self.OUTER_MARGIN + col * self.CELL_WIDTH
        cell_y = self.OUTER_MARGIN + row * self.CELL_HEIGHT

        card_x = cell_x + (self.CELL_WIDTH - THUMB_WIDTH) // 2
        card_y = cell_y

        return wx.Rect(card_x, card_y, THUMB_WIDTH, PANEL_HEIGHT)

    def _index_from_mouse(self, x, y):
        ux, uy = self.CalcUnscrolledPosition(x, y)

        ux -= self.OUTER_MARGIN
        uy -= self.OUTER_MARGIN

        if ux < 0 or uy < 0:
            return -1

        col = ux // self.CELL_WIDTH
        row = uy // self.CELL_HEIGHT

        if col >= self.columns:
            return -1

        index = row * self.columns + col
        if index >= len(self.files):
            return -1

        return index

    def _index_is_visible(self, index):
        if index < 0 or index >= len(self.files):
            return False

        _, view_y_units = self.GetViewStart()
        _, ppu_y = self.GetScrollPixelsPerUnit()
        visible_y = view_y_units * ppu_y
        visible_h = self.GetClientSize().height

        rect = self._index_rect(index)
        return rect.Bottom >= visible_y and rect.Top <= visible_y + visible_h

    def on_size(self, evt):
        old_view = self.GetViewStart()
        self._recalc_virtual_size()
        self.Scroll(old_view[0], old_view[1])
        self.Refresh(False)
        evt.Skip()

    def on_left_down(self, evt):
        index = self._index_from_mouse(evt.GetX(), evt.GetY())
        if index >= 0 and self.callback:
            self.callback(self.files[index])

    def on_mouse_move(self, evt):
        index = self._index_from_mouse(evt.GetX(), evt.GetY())
        if index != self.hover_index:
            self.hover_index = index

            if index >= 0:
                self.SetToolTip(os.path.basename(self.files[index]))
            else:
                self.SetToolTip(None)

            self.Refresh(False)

        evt.Skip()

    def on_mouse_leave(self, evt):
        if self.hover_index != -1:
            self.hover_index = -1
            self.SetToolTip(None)
            self.Refresh(False)

        evt.Skip()

    def on_paint(self, evt):
        dc = wx.AutoBufferedPaintDC(self)
        self.PrepareDC(dc)

        dc.SetBackground(wx.Brush(self.theme["bg"]))
        dc.Clear()

        if not self.files:
            return

        _, view_y_units = self.GetViewStart()
        _, ppu_y = self.GetScrollPixelsPerUnit()

        visible_y = view_y_units * ppu_y
        visible_h = self.GetClientSize().height

        first_row = max(0, (visible_y - self.OUTER_MARGIN) // self.CELL_HEIGHT)
        last_row = max(0, (visible_y + visible_h - self.OUTER_MARGIN) // self.CELL_HEIGHT + 1)

        start_index = first_row * self.columns
        end_index = min(len(self.files), (last_row + 1) * self.columns)

        for index in range(start_index, end_index):
            self._draw_item(dc, index)

    def _draw_item(self, dc, index):
        file_path = self.files[index]
        rect = self._index_rect(index)

        fill = self.theme["card_hover"] if index == self.hover_index else self.theme["card"]

        dc.SetBrush(wx.Brush(fill))
        dc.SetPen(wx.Pen(self.theme["border"]))
        dc.DrawRoundedRectangle(rect.x, rect.y, rect.width, rect.height, 2)

        bmp = self.bitmap_map.get(file_path, self.placeholder_bmp)

        bmp_w = bmp.GetWidth()
        bmp_h = bmp.GetHeight()

        draw_x = rect.x + max(0, (THUMB_WIDTH - bmp_w) // 2)
        draw_y = rect.y + max(0, (THUMB_HEIGHT - bmp_h) // 2)

        dc.DrawBitmap(bmp, draw_x, draw_y, True)

        font = dc.GetFont()
        font.SetPointSize(9)
        dc.SetFont(font)
        dc.SetTextForeground(self.theme["text"])

        label_rect = wx.Rect(
            rect.x + 4,
            rect.y + THUMB_HEIGHT + 6,
            rect.width - 8,
            PANEL_HEIGHT - THUMB_HEIGHT - 10
        )

        self._draw_filename(dc, os.path.basename(file_path), label_rect)

    def _draw_filename(self, dc, text, rect):
        lines = self._split_text_to_two_lines(dc, text, rect.width)

        line_h = dc.GetTextExtent("Ag")[1]
        total_h = len(lines) * line_h
        y = rect.y + max(0, (rect.height - total_h) // 2)

        for line in lines:
            text_w, _ = dc.GetTextExtent(line)
            x = rect.x + max(0, (rect.width - text_w) // 2)
            dc.DrawText(line, x, y)
            y += line_h

    def _split_text_to_two_lines(self, dc, text, max_width):
        if dc.GetTextExtent(text)[0] <= max_width:
            return [text]

        first_line = ""
        split_pos = 0

        for i, ch in enumerate(text):
            candidate = first_line + ch
            if dc.GetTextExtent(candidate)[0] <= max_width:
                first_line = candidate
                split_pos = i + 1
            else:
                break

        remaining = text[split_pos:]

        if dc.GetTextExtent(remaining)[0] <= max_width:
            return [first_line, remaining]

        second_line = self._ellipsize(dc, remaining, max_width)
        return [first_line, second_line]

    def _ellipsize(self, dc, text, max_width):
        ellipsis = "…"

        if dc.GetTextExtent(text)[0] <= max_width:
            return text

        result = ""

        for ch in text:
            candidate = result + ch + ellipsis
            if dc.GetTextExtent(candidate)[0] <= max_width:
                result += ch
            else:
                break

        return result + ellipsis if result else ellipsis


class GalleryProgressLine(wx.Panel):
    def __init__(self, parent, theme, range=100):
        super().__init__(parent, size=(-1, 4), style=wx.BORDER_NONE)

        self.theme = theme
        self._range = max(1, int(range))
        self._value = 0

        self._pulsing = False
        self._pulse_pos = 0
        self._pulse_timer = wx.Timer(self)

        self.SetMinSize((-1, 4))
        self.SetBackgroundStyle(wx.BG_STYLE_PAINT)

        self.Bind(wx.EVT_PAINT, self.on_paint)
        self.Bind(wx.EVT_TIMER, self.on_pulse_timer, self._pulse_timer)
        self.Bind(wx.EVT_SIZE, lambda evt: (self.Refresh(False), evt.Skip()))

    def SetRange(self, value: int):
        self._range = max(1, int(value))
        self._value = min(self._value, self._range)
        self._stop_pulse()
        self.Refresh(False)

    def GetRange(self) -> int:
        return self._range

    def SetValue(self, value: int):
        self._value = max(0, min(int(value), self._range))
        self._stop_pulse()
        self.Refresh(False)

    def GetValue(self) -> int:
        return self._value

    def Pulse(self):
        self._pulsing = True
        self._pulse_pos = 0
        if not self._pulse_timer.IsRunning():
            self._pulse_timer.Start(30)
        self.Refresh(False)

    def _stop_pulse(self):
        self._pulsing = False
        if self._pulse_timer.IsRunning():
            self._pulse_timer.Stop()

    def on_pulse_timer(self, evt):
        self._pulse_pos = (self._pulse_pos + 10) % 140
        self.Refresh(False)

    def on_paint(self, evt):
        dc = wx.BufferedPaintDC(self)
        w, h = self.GetClientSize()

        dc.SetBackground(wx.Brush(self.theme["bg"]))
        dc.Clear()

        if w <= 0 or h <= 0:
            return

        line_h = 3
        y = max(0, (h - line_h) // 2)

        track_colour = self.theme["border"]
        fill_colour = self.theme["card_hover"]

        dc.SetPen(wx.TRANSPARENT_PEN)

        dc.SetBrush(wx.Brush(track_colour))
        dc.DrawRectangle(0, y, w, line_h)

        if self._pulsing:
            pulse_w = max(40, w // 5)
            x = int((w + pulse_w) * self._pulse_pos / 140) - pulse_w

            dc.SetBrush(wx.Brush(fill_colour))
            dc.DrawRectangle(x, y, pulse_w, line_h)
            return

        fill_w = int(w * self._value / self._range)
        if fill_w > 0:
            dc.SetBrush(wx.Brush(fill_colour))
            dc.DrawRectangle(0, y, fill_w, line_h)


class LibraryManagerThread(threading.Thread):
    def __init__(self, files, result_queue):
        super().__init__()
        self.files = files
        self.result_queue = result_queue
        self.running = True
        self.daemon = True

    def stop(self):
        self.running = False

    def run(self):
        with concurrent.futures.ThreadPoolExecutor(max_workers=MAX_WORKERS) as executor:
            future_to_file = {
                executor.submit(process_cover_with_provider, f, THUMB_WIDTH, THUMB_HEIGHT): f
                for f in self.files
            }

            for future in concurrent.futures.as_completed(future_to_file):
                if not self.running:
                    for f in future_to_file:
                        f.cancel()
                    executor.shutdown(wait=False)
                    return
                try:
                    res = future.result()
                    self.result_queue.put(res)
                except Exception as e:
                    print(f"[ERROR] wxReader background thread failed: {e}")


class LibraryFrame(wx.Frame):
    def __init__(self, parent, directory, open_callback=None, dark_mode=False):
        super().__init__(parent, title=_("wxReader Gallery"), size=(1200, 960))

        self.directory = directory
        self.open_callback = open_callback
        self.theme = get_gallery_theme(dark_mode)

        self.manager_thread = None
        self.result_queue = queue.Queue()
        self.supported_exts = SUPPORTED_EXTENSIONS

        self.file_metadata = {}
        self.files_to_create = []

        self.SetBackgroundColour(self.theme["bg"])

        app_icon = get_app_icon()
        if app_icon.IsOk():
            self.SetIcon(app_icon)

        main_sizer = wx.BoxSizer(wx.VERTICAL)
        self.placeholder_bmp = self._create_placeholder()

        top_panel = wx.Panel(self)
        top_panel.SetBackgroundColour(self.theme["bg"])
        top_sizer = wx.BoxSizer(wx.HORIZONTAL)

        self.combo_sort = wx.ComboBox(top_panel, choices=[_("Name (A-Z)"), _("Name (Z-A)"),
                                                          _("Modified (Newest First)"), _("Modified (Oldest First)")],
                                      style=wx.CB_READONLY)
        self.combo_sort.SetSelection(1)
        self.btn_refresh = wx.Button(top_panel, label=_("Refresh"))

        sort_lbl = wx.StaticText(top_panel, label=_("Sort by: "))
        sort_lbl.SetForegroundColour(self.theme["text"])

        top_sizer.Add(sort_lbl, 0, wx.ALIGN_CENTER_VERTICAL | wx.ALL, 5)
        top_sizer.Add(self.combo_sort, 0, wx.ALIGN_CENTER_VERTICAL | wx.ALL, 5)
        top_sizer.Add(self.btn_refresh, 0, wx.ALIGN_CENTER_VERTICAL | wx.ALL, 5)

        top_sizer.AddStretchSpacer(1)

        self.chk_stay_on_top = wx.CheckBox(top_panel, label=_("Stay on top"))
        self.chk_stay_on_top.SetValue(False)
        top_sizer.Add(self.chk_stay_on_top, 0, wx.ALIGN_CENTER_VERTICAL | wx.RIGHT, 10)

        top_panel.SetSizer(top_sizer)

        self.gallery = VirtualThumbnailCanvas(
            self,
            self.placeholder_bmp,
            self.on_thumb_click,
            self.theme
        )

        self.gauge = GalleryProgressLine(self, self.theme, range=100)
        self.status_lbl = wx.StaticText(self, label=_("Ready"))

        main_sizer.Add(top_panel, 0, wx.EXPAND | wx.ALL, 5)
        main_sizer.Add(self.gallery, 1, wx.EXPAND | wx.LEFT | wx.RIGHT, 10)
        main_sizer.Add(self.gauge, 0, wx.EXPAND | wx.LEFT | wx.RIGHT, 0)
        main_sizer.Add(self.status_lbl, 0, wx.EXPAND | wx.ALL, 5)

        self.SetSizer(main_sizer)
        self.Layout()

        self.combo_sort.Bind(wx.EVT_COMBOBOX, self.on_sort_change)
        self.btn_refresh.Bind(wx.EVT_BUTTON, self.on_refresh)
        self.chk_stay_on_top.Bind(wx.EVT_CHECKBOX, self.on_toggle_top)
        self.Bind(wx.EVT_CLOSE, self.on_close)

        self.chk_stay_on_top.SetForegroundColour(self.theme["text"])

        self.status_lbl.SetForegroundColour(self.theme["text"])

        self.update_timer = wx.Timer(self)
        self.Bind(wx.EVT_TIMER, self.on_update_timer, self.update_timer)

        wx.CallAfter(self.load_files)

    def _create_placeholder(self):
        img = wx.Image(THUMB_WIDTH, THUMB_HEIGHT)
        c = self.theme["placeholder"]
        img.SetRGB(wx.Rect(0, 0, THUMB_WIDTH, THUMB_HEIGHT), c.Red(), c.Green(), c.Blue())
        return wx.Bitmap(img)

    def load_files(self):
        if self.manager_thread and self.manager_thread.is_alive():
            self.manager_thread.stop()

        self.update_timer.Stop()

        while not self.result_queue.empty():
            try:
                self.result_queue.get_nowait()
            except queue.Empty:
                break

        self.gallery.clear()
        self.file_metadata.clear()
        self.files_to_create.clear()

        self.status_lbl.SetLabel(_("Scanning directory..."))
        self.gauge.Pulse()

        current_dir = self.directory
        sort_mode = self.combo_sort.GetSelection()

        threading.Thread(
            target=self._scan_worker,
            args=(current_dir, sort_mode),
            daemon=True
        ).start()

        self.Raise()

    def _scan_worker(self, directory, sort_mode):
        try:
            all_files = os.listdir(directory)
            valid_files = []
            metadata = {}

            with os.scandir(directory) as it:
                for entry in it:
                    if entry.is_file():
                        ext = os.path.splitext(entry.name)[1].lower()
                        if ext in self.supported_exts:
                            full_path = entry.path
                            valid_files.append(full_path)
                            metadata[full_path] = entry.stat().st_mtime

            if sort_mode == 0:
                valid_files.sort(key=lambda x: os.path.basename(x).lower())
            elif sort_mode == 1:
                valid_files.sort(key=lambda x: os.path.basename(x).lower(), reverse=True)
            elif sort_mode == 2:
                valid_files.sort(key=lambda x: metadata[x], reverse=True)
            elif sort_mode == 3:
                valid_files.sort(key=lambda x: metadata[x])

            wx.CallAfter(self._on_scan_complete, valid_files, metadata)

        except Exception as e:
            wx.CallAfter(self.status_lbl.SetLabel, _("Scan Error") + f": {e}")

    def _on_scan_complete(self, valid_files, metadata):
        self.file_metadata = metadata
        self.files_to_create = valid_files[:]

        self.gallery.set_files(self.files_to_create)

        self.gauge.SetRange(len(self.files_to_create))
        self.gauge.SetValue(0)

        self.status_lbl.SetLabel(
            _("Found {} files. Creating thumbnails...").format(len(self.files_to_create))
        )

        self.processed_count = 0

        if not self.files_to_create:
            self.status_lbl.SetLabel(_("Done."))
            return

        self.manager_thread = LibraryManagerThread(
            self.files_to_create,
            self.result_queue
        )
        self.manager_thread.start()

        self.update_timer.Start(30)

        self.Raise()

    def on_sort_change(self, evt):
        if not self.files_to_create:
            return

        sort_mode = self.combo_sort.GetSelection()

        if sort_mode == 0:
            self.files_to_create.sort(
                key=lambda path: os.path.basename(path).lower()
            )
        elif sort_mode == 1:
            self.files_to_create.sort(
                key=lambda path: os.path.basename(path).lower(),
                reverse=True
            )
        elif sort_mode == 2:
            self.files_to_create.sort(
                key=lambda path: self.file_metadata.get(path, 0),
                reverse=True
            )
        elif sort_mode == 3:
            self.files_to_create.sort(
                key=lambda path: self.file_metadata.get(path, 0)
            )

        self.gallery.set_files(self.files_to_create, keep_scroll=True)

    def on_update_timer(self, evt):
        start_time = time.time()
        TIME_BUDGET = 0.040
        updates_made = False

        try:
            while not self.result_queue.empty():
                if time.time() - start_time > TIME_BUDGET:
                    break
                try:
                    res = self.result_queue.get_nowait()
                    path, w, h, data = res
                    if data:
                        self._apply_cover_raw(path, w, h, data)
                    self.processed_count += 1
                    updates_made = True
                except queue.Empty:
                    break

            if updates_made:
                self.gauge.SetValue(self.processed_count)
                if self.processed_count % 5 == 0:
                    self.status_lbl.SetLabel(_("Loading thumbnails...")+f"{self.processed_count}/{self.gauge.GetRange()}")

            if self.processed_count >= self.gauge.GetRange() and self.result_queue.empty():
                self.update_timer.Stop()
                self.status_lbl.SetLabel(_("Done."))
                self.gauge.SetValue(self.gauge.GetRange())
        except Exception as e:
            print(f"[ERROR]: {e}")

    def _apply_cover_raw(self, file_path, w, h, data):
        if not data or w <= 0 or h <= 0:
            return

        expected_len = w * h * 3
        if len(data) != expected_len:
            return

        try:
            img = wx.Image(w, h, data)
            if img.IsOk():
                self.gallery.update_bitmap(file_path, wx.Bitmap(img))
        except Exception as e:
            print(f"Failed to create image for {file_path}: {e}")

    def on_refresh(self, evt):
        self.load_files()

    def on_toggle_top(self, evt):
        if self.chk_stay_on_top.GetValue():
            self.SetWindowStyle(self.GetWindowStyle() | wx.STAY_ON_TOP)
        else:
            self.SetWindowStyle(self.GetWindowStyle() & ~wx.STAY_ON_TOP)

        self.Refresh()

    def on_thumb_click(self, path):
        if self.open_callback:
            self.open_callback(path)

    def on_close(self, evt):
        self.update_timer.Stop()
        if self.manager_thread:
            self.manager_thread.stop()
        evt.Skip()
