import concurrent.futures
import os
import queue
import threading
import time

import wx

from wxReaderProvider import PdfContentProvider, ArchiveContentProvider

THUMB_WIDTH = 140
THUMB_HEIGHT = 200
PANEL_HEIGHT = THUMB_HEIGHT + 55
BG_COLOR = wx.Colour(240, 240, 240)
TEXT_COLOR = wx.Colour(40, 40, 40)
MAX_WORKERS = max(1, (os.cpu_count() or 2) - 1)


def process_cover_with_provider(file_path, thumb_width, thumb_height):
    provider = None
    ext = os.path.splitext(file_path)[1].lower()

    try:
        if ext in {".pdf", ".epub", ".mobi", ".fb2"}:
            provider = PdfContentProvider(file_path)
        elif ext in {".zip", ".cbz"}:
            provider = ArchiveContentProvider(file_path)
        else:
            return file_path, 0, 0, None  # Unsupported

        raw_bytes = provider.get_thumbnail(thumb_width, thumb_height)

        if raw_bytes:
            img = wx.Image(thumb_width, thumb_height, raw_bytes)
            if img.IsOk():
                return file_path, img.GetWidth(), img.GetHeight(), raw_bytes

    except Exception:
        pass
    finally:
        if provider:
            provider.close()

    return file_path, 0, 0, None


class ThumbnailPanel(wx.Panel):
    def __init__(self, parent, file_path, bitmap, callback):
        super().__init__(parent, size=(THUMB_WIDTH, PANEL_HEIGHT))
        self.file_path = file_path
        self.callback = callback

        self.SetBackgroundColour(BG_COLOR)

        sizer = wx.BoxSizer(wx.VERTICAL)

        # cover
        self.bmp = wx.StaticBitmap(self, bitmap=bitmap, size=(THUMB_WIDTH, THUMB_HEIGHT))

        # filename
        name = os.path.basename(file_path)
        self.lbl = wx.StaticText(self, label=name, style=wx.ALIGN_CENTER)
        self.lbl.SetForegroundColour(TEXT_COLOR)
        self.lbl.SetToolTip(name)

        font = self.lbl.GetFont()
        font.SetPointSize(9)
        self.lbl.SetFont(font)

        self.lbl.Wrap(THUMB_WIDTH - 4)

        sizer.Add(self.bmp, 0, wx.ALIGN_CENTER, 0)
        sizer.Add(self.lbl, 1, wx.TOP | wx.EXPAND, 5)

        self.SetSizer(sizer)

        # events
        self.bmp.Bind(wx.EVT_LEFT_DOWN, self.on_click)
        self.lbl.Bind(wx.EVT_LEFT_DOWN, self.on_click)
        self.Bind(wx.EVT_LEFT_DOWN, self.on_click)
        self.bmp.Bind(wx.EVT_ENTER_WINDOW, self.on_enter)
        self.bmp.Bind(wx.EVT_LEAVE_WINDOW, self.on_leave)
        self.lbl.Bind(wx.EVT_ENTER_WINDOW, self.on_enter)
        self.lbl.Bind(wx.EVT_LEAVE_WINDOW, self.on_leave)

    def update_image(self, bitmap):
        self.bmp.SetBitmap(bitmap)
        self.Refresh()

    def on_click(self, evt):
        if self.callback:
            self.callback(self.file_path)

    def on_enter(self, evt):
        self.SetBackgroundColour(wx.Colour(220, 230, 240))
        self.Refresh()

    def on_leave(self, evt):
        self.SetBackgroundColour(BG_COLOR)
        self.Refresh()


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
                    executor.shutdown(wait=False, cancel_futures=True)
                    return
                try:
                    res = future.result()
                    self.result_queue.put(res)
                except Exception:
                    pass


class LibraryFrame(wx.Frame):
    def __init__(self, parent, directory, open_callback=None):
        super().__init__(parent, title="wxReader Gallery", size=(900, 600))
        self.directory = directory
        self.open_callback = open_callback

        self.manager_thread = None
        self.result_queue = queue.Queue()
        self.supported_exts = {".pdf", ".epub", ".mobi", ".fb2", ".zip", ".cbz"}

        self.thumb_panels = []
        self.item_map = {}
        self.file_metadata = {}  # Cache

        self.SetBackgroundColour(BG_COLOR)

        from wxReaderIcon import APP_ICON
        self.SetIcon(APP_ICON)

        main_sizer = wx.BoxSizer(wx.VERTICAL)

        top_panel = wx.Panel(self)
        top_panel.SetBackgroundColour(BG_COLOR)
        top_sizer = wx.BoxSizer(wx.HORIZONTAL)

        self.combo_sort = wx.ComboBox(top_panel, choices=["Name (A-Z)", "Name (Z-A)",
                                                          "Modified (Newest First)", "Modified (Oldest First)"],
                                      style=wx.CB_READONLY)
        self.combo_sort.SetSelection(1)
        self.btn_refresh = wx.Button(top_panel, label="Refresh")

        top_sizer.Add(wx.StaticText(top_panel, label="Sort by: "), 0, wx.ALIGN_CENTER_VERTICAL | wx.ALL, 5)
        top_sizer.Add(self.combo_sort, 0, wx.ALIGN_CENTER_VERTICAL | wx.ALL, 5)
        top_sizer.Add(self.btn_refresh, 0, wx.ALIGN_CENTER_VERTICAL | wx.ALL, 5)
        top_panel.SetSizer(top_sizer)

        self.scrolled = wx.ScrolledWindow(self, style=wx.VSCROLL)
        self.scrolled.SetBackgroundColour(BG_COLOR)
        self.scrolled.SetScrollRate(0, 20)

        self.gallery_sizer = wx.WrapSizer(wx.HORIZONTAL)
        self.scrolled.SetSizer(self.gallery_sizer)

        self.gauge = wx.Gauge(self, range=100, size=(-1, 4))
        self.status_lbl = wx.StaticText(self, label="Ready")

        main_sizer.Add(top_panel, 0, wx.EXPAND | wx.ALL, 5)
        main_sizer.Add(self.scrolled, 1, wx.EXPAND | wx.LEFT | wx.RIGHT, 10)
        main_sizer.Add(self.gauge, 0, wx.EXPAND | wx.LEFT | wx.RIGHT, 0)
        main_sizer.Add(self.status_lbl, 0, wx.EXPAND | wx.ALL, 5)

        self.SetSizer(main_sizer)
        self.Layout()

        self.combo_sort.Bind(wx.EVT_COMBOBOX, self.on_sort_change)
        self.btn_refresh.Bind(wx.EVT_BUTTON, self.on_refresh)
        self.Bind(wx.EVT_CLOSE, self.on_close)
        self.scrolled.Bind(wx.EVT_SIZE, self.on_resize)

        self.update_timer = wx.Timer(self)
        self.Bind(wx.EVT_TIMER, self.on_update_timer, self.update_timer)

        self.placeholder_bmp = self._create_placeholder()

        wx.CallAfter(self.load_files)

    def _create_placeholder(self):
        img = wx.Image(THUMB_WIDTH, THUMB_HEIGHT)
        img.SetRGB(wx.Rect(0, 0, THUMB_WIDTH, THUMB_HEIGHT), 220, 220, 220)
        return wx.Bitmap(img)

    def load_files(self):
        if self.manager_thread and self.manager_thread.is_alive():
            self.manager_thread.stop()
        self.update_timer.Stop()

        while not self.result_queue.empty():
            try:
                self.result_queue.get_nowait()
            except:
                pass

        self.scrolled.Freeze()
        self.gallery_sizer.Clear(delete_windows=True)
        self.item_map.clear()
        self.thumb_panels.clear()
        self.file_metadata.clear()
        self.scrolled.Thaw()

        self.status_lbl.SetLabel("Scanning directory...")
        self.gauge.Pulse()

        current_dir = self.directory
        sort_mode = self.combo_sort.GetSelection()

        threading.Thread(target=self._scan_worker, args=(current_dir, sort_mode), daemon=True).start()

    def _scan_worker(self, directory, sort_mode):
        try:
            all_files = os.listdir(directory)
            valid_files = []
            metadata = {}

            for f in all_files:
                ext = os.path.splitext(f)[1].lower()
                if ext in self.supported_exts:
                    full_path = os.path.join(directory, f)
                    if os.path.isfile(full_path):
                        valid_files.append(full_path)
                        metadata[full_path] = os.path.getmtime(full_path)

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
            wx.CallAfter(self.status_lbl.SetLabel, f"Scan Error: {e}")

    def _on_scan_complete(self, valid_files, metadata):
        self.file_metadata = metadata
        self.gauge.SetRange(len(valid_files))
        self.gauge.SetValue(0)
        self.status_lbl.SetLabel(f"Found {len(valid_files)} files. Creating thumbnails...")

        self.files_to_create = valid_files[:]
        self.creation_index = 0

        self._batch_create_placeholders()

    def _batch_create_placeholders(self):
        BATCH_SIZE = 10
        count = 0

        self.scrolled.Freeze()
        try:
            while self.creation_index < len(self.files_to_create) and count < BATCH_SIZE:
                f_path = self.files_to_create[self.creation_index]

                thumb = ThumbnailPanel(self.scrolled, f_path, self.placeholder_bmp, self.on_thumb_click)
                self.gallery_sizer.Add(thumb, 0, wx.ALL, 10)

                self.item_map[f_path] = thumb
                self.thumb_panels.append(thumb)

                self.creation_index += 1
                count += 1
        finally:
            self.scrolled.Thaw()

        if count > 0:
            self.scrolled.Layout()
            self.scrolled.FitInside()

        if self.creation_index < len(self.files_to_create):
            self.gauge.SetValue(self.creation_index)
            wx.CallLater(1, self._batch_create_placeholders)
        else:
            self.status_lbl.SetLabel("Generating covers...")
            self.processed_count = 0
            self.gauge.SetValue(0)

            self.scrolled.FitInside()

            self.manager_thread = LibraryManagerThread(self.files_to_create, self.result_queue)
            self.manager_thread.start()

            self.update_timer.Start(30)

    def on_sort_change(self, evt):
        if not self.thumb_panels:
            return

        sort_mode = self.combo_sort.GetSelection()

        if sort_mode == 0:
            self.thumb_panels.sort(key=lambda p: os.path.basename(p.file_path).lower())
        elif sort_mode == 1:
            self.thumb_panels.sort(key=lambda p: os.path.basename(p.file_path).lower(), reverse=True)
        elif sort_mode == 2:
            self.thumb_panels.sort(key=lambda p: self.file_metadata.get(p.file_path, 0), reverse=True)
        elif sort_mode == 3:
            self.thumb_panels.sort(key=lambda p: self.file_metadata.get(p.file_path, 0))

        self.scrolled.Freeze()
        self.gallery_sizer.Clear(delete_windows=False)

        for panel in self.thumb_panels:
            self.gallery_sizer.Add(panel, 0, wx.ALL, 10)

        self.scrolled.Layout()
        self.scrolled.FitInside()
        self.scrolled.Thaw()

    def on_update_timer(self, evt):
        start_time = time.time()
        TIME_BUDGET = 0.15
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
                    self.status_lbl.SetLabel(f"Loading thumbnails... {self.processed_count}/{self.gauge.GetRange()}")

            if self.processed_count >= self.gauge.GetRange() and self.result_queue.empty():
                self.update_timer.Stop()
                self.status_lbl.SetLabel("Done.")
                self.gauge.SetValue(self.gauge.GetRange())
        except Exception:
            pass

    def _apply_cover_raw(self, file_path, w, h, data):
        thumb = self.item_map.get(file_path)
        if thumb and data and len(data) == w * h * 3:
            try:
                img = wx.Image(w, h, data)
                if img.IsOk():
                    thumb.update_image(wx.Bitmap(img))
            except Exception:
                pass

    def on_refresh(self, evt):
        self.load_files()

    def on_thumb_click(self, path):
        if self.open_callback:
            self.open_callback(path)

    def on_resize(self, evt):
        w, h = self.scrolled.GetClientSize()
        self.scrolled.SetVirtualSize(w, -1)
        self.scrolled.Layout()
        evt.Skip()

    def on_close(self, evt):
        self.update_timer.Stop()
        if self.manager_thread:
            self.manager_thread.stop()
        evt.Skip()
