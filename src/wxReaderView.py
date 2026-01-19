from __future__ import annotations

import queue
import threading
import webbrowser

import fitz  # PyMuPDF
import numpy as np
import wx
from collections import OrderedDict

from wxReaderProvider import ContentProvider


class PDFView(wx.ScrolledWindow):
    MODE_SINGLE = "single"
    MODE_TWO = "two"

    DIR_LTR = "ltr"
    DIR_RTL = "rtl"

    ZOOM_MANUAL = "manual"
    ZOOM_FIT_WIDTH = "fit_width"
    ZOOM_FIT_PAGE = "fit_page"

    MIN_ZOOM = 0.01
    MAX_ZOOM = 10.0

    MAX_CACHE_SIZE = 36

    def __init__(self, parent):
        super().__init__(parent, style=wx.HSCROLL | wx.VSCROLL | wx.WANTS_CHARS)
        self.SetBackgroundStyle(wx.BG_STYLE_PAINT)
        self.bgColor = wx.Colour(134, 180, 118)
        self.custom_filter: str | None = None

        self.main_frame = None

        self.render_queue = queue.Queue()
        self.worker_thread = threading.Thread(target=self._worker_loop, daemon=True)
        self.worker_thread.start()
        self._requested_pages = set()

        # State
        self.content_provider: ContentProvider | None = None
        self.page = 0  # current page (0-based)
        self.zoom = 1.0
        self.zoom_mode = self.ZOOM_FIT_PAGE

        self.mode = self.MODE_TWO
        self.direction = self.DIR_LTR
        self.pad_start = False

        # {(page_index): wx.Bitmap}
        self._bmp_cache: OrderedDict[tuple[int, int], wx.Bitmap] = OrderedDict()
        self._pre_render_timer = wx.Timer(self)
        self.Bind(wx.EVT_TIMER, self._on_pre_render_timer, self._pre_render_timer)

        # Layout
        self.margin = 2
        self.gap = 2
        self._current_bitmaps: list[tuple[int, wx.Bitmap]] = []  # [(page_index, bmp), ...]

        # Panning
        self._panning = False
        self._pan_start_mouse = wx.Point(0, 0)
        self._pan_start_view = (0, 0)

        self.SetScrollRate(20, 20)

        # Events
        self.Bind(wx.EVT_PAINT, self.on_paint)
        self.Bind(wx.EVT_SIZE, self.on_size)
        self.Bind(wx.EVT_MOUSEWHEEL, self.on_mousewheel)
        self.Bind(wx.EVT_RIGHT_DOWN, self.on_right_down)
        self.Bind(wx.EVT_RIGHT_UP, self.on_right_up)
        self.Bind(wx.EVT_MOTION, self.on_mouse_move)
        self.Bind(wx.EVT_CHAR_HOOK, self.on_char_hook)
        self.Bind(wx.EVT_LEFT_DOWN, self.on_left_down)

    # --------------------------
    # public api
    # --------------------------
    def set_content_provider(self, provider: ContentProvider | None):
        self._bmp_cache.clear()
        self._current_bitmaps.clear()
        self.content_provider = provider
        self.page = 0
        self.zoom = 1.0
        self.zoom_mode = self.ZOOM_FIT_PAGE
        self._last_cache_zoom = self.zoom
        self._refresh_layout()
        self.Refresh()

    def set_mode(self, mode: str):
        if mode not in (self.MODE_SINGLE, self.MODE_TWO):
            return
        self.mode = mode
        self._refresh_layout()
        self.Refresh()

    def set_custom_filter(self, name: str | None):
        if self.custom_filter != name:
            self.custom_filter = name
            self._bmp_cache.clear()
            self._refresh_layout()
            self.Refresh()

    def set_pad_start(self, pad: bool):
        if self.pad_start != pad:
            self.pad_start = pad
            self._bmp_cache.clear()
            self._refresh_layout()
            self.Refresh()

    def set_direction(self, direction: str):
        if direction not in (self.DIR_LTR, self.DIR_RTL):
            return
        self.direction = direction
        self._refresh_layout()
        self.Refresh()

    def set_zoom_mode(self, mode: str):
        if mode not in (self.ZOOM_MANUAL, self.ZOOM_FIT_WIDTH, self.ZOOM_FIT_PAGE):
            return
        self.zoom_mode = mode
        self._refresh_layout()
        self.Refresh()

    def set_background_color(self, color: wx.Colour):
        self.bgColor = color
        self.SetBackgroundColour(color)
        self.Refresh()

    def set_margin_gap(self, m: int, g: int):
        self.margin = m
        self.gap = g
        self._refresh_layout()
        self.Refresh()

    def go_next(self):
        if not self.content_provider:
            return
        step = 1 if self.mode == self.MODE_SINGLE else 2
        self.page = min(self.page + step, self.content_provider.page_count - 1)
        self._refresh_layout()
        self.Refresh()

    def go_prev(self):
        if not self.content_provider:
            return
        step = 1 if self.mode == self.MODE_SINGLE else 2
        self.page = max(self.page - step, 0)
        self._refresh_layout()
        self.Refresh()

    def go_to_page(self, page_index: int):
        if not self.content_provider:
            return
        self.page = max(0, min(page_index, self.content_provider.page_count - 1))
        self._refresh_layout()
        self.Refresh()

    def stop_worker(self):
        if self._pre_render_timer.IsRunning():
            self._pre_render_timer.Stop()

    # --------------------------
    # Threading Logic
    # --------------------------
    def _process_image_data(self, data: bytes, width: int, height: int) -> bytes:
        if not self.custom_filter:
            return data

        try:
            arr = np.frombuffer(data, dtype=np.uint8).reshape((height, width, 3))
            arr = arr.copy()

            if self.main_frame and hasattr(self.main_frame, "gl_filters"):
                out = self.main_frame.gl_filters.apply(self.custom_filter, arr)
                if out is not None:
                    arr[:] = out

            return arr.tobytes()

        except Exception as e:
            print(f"Background processing error: {e}")
            return data

    def _worker_loop(self):
        while True:
            task = self.render_queue.get()
            try:
                page_idx, zoom, provider = task

                if provider != self.content_provider or abs(zoom - self.zoom) > 0.01:
                    continue
                if not provider.is_valid:
                    continue

                raw_result = provider.render_to_data(page_idx, zoom)
                if not raw_result:
                    continue

                width, height, data = raw_result

                try:
                    arr = np.frombuffer(data, dtype=np.uint8).reshape((height, width, 3)).copy()
                except Exception as e:
                    print(f"Numpy conversion error: {e}")
                    continue

                wx.CallAfter(self._on_worker_result, page_idx, zoom, width, height, arr, provider)

            except Exception as e:
                print(f"Worker error: {e}")
            finally:
                self.render_queue.task_done()

    def _on_worker_result(self, page_idx, zoom, width, height, arr, task_provider):
        if task_provider != self.content_provider:
            return
        if abs(self.zoom - zoom) > 0.01:
            return

        cache_key = (page_idx, int(zoom * 10000))
        if cache_key in self._requested_pages:
            self._requested_pages.remove(cache_key)

        if self.custom_filter and self.main_frame and hasattr(self.main_frame, "gl_filters"):
            try:
                out = self.main_frame.gl_filters.apply(self.custom_filter, arr)
                if out is not None:
                    arr[:] = out
            except Exception as e:
                print(f"GL Filter error on main thread: {e}")

        img = wx.Image(width, height, arr.tobytes())
        bmp = wx.Bitmap(img)

        self._bmp_cache[cache_key] = bmp

        if self._is_page_visible(page_idx):
            self.Refresh(eraseBackground=False)


    def _is_page_visible(self, page_index):
        return any(p_idx == page_index for p_idx, _ in self._current_bitmaps)

    # --------------------------
    # Internals
    # --------------------------
    def _ensure_cache_zoom(self):
        if abs(self.zoom - self._last_cache_zoom) > 1e-9:
            self._bmp_cache.clear()
            self._last_cache_zoom = self.zoom

    def _get_bitmap(self, page_index: int, zoom: float) -> wx.Bitmap:
        cache_key = (page_index, int(zoom * 10000))

        if cache_key in self._bmp_cache:
            self._bmp_cache.move_to_end(cache_key)
            return self._bmp_cache[cache_key]

        if len(self._bmp_cache) >= self.MAX_CACHE_SIZE:
            self._bmp_cache.popitem(last=False)

        if page_index < 0:
            ref_idx = max(0, min(self.page, self.content_provider.page_count - 1))
            w_pt, h_pt = self.content_provider.get_page_size(ref_idx)
            w_px = int(w_pt * zoom)
            h_px = int(h_pt * zoom)

            size = w_px * h_px * 3
            white_data = b'\xff' * size

            processed_data = self._process_image_data(white_data, w_px, h_px)

            img = wx.Image(w_px, h_px, processed_data)
            bmp = wx.Bitmap(img)
            self._bmp_cache[cache_key] = bmp
            return bmp

        res = self.content_provider.render_to_data(page_index, zoom)
        if not res:
            return wx.NullBitmap

        w, h, data = res

        processed_data = self._process_image_data(data, w, h)

        img = wx.Image(w, h, processed_data)
        bmp = wx.Bitmap(img)

        self._bmp_cache[cache_key] = bmp
        return bmp

    def _spread_pages(self) -> list[int]:
        if not self.content_provider:
            return []

        n = self.content_provider.page_count
        p = max(0, min(self.page, n - 1))

        if self.mode == self.MODE_SINGLE:
            return [p]

        shift = 1 if self.pad_start else 0

        v_p = p + shift

        v_base = v_p if (v_p % 2 == 0) else (v_p - 1)

        left_idx = v_base - shift
        right_idx = v_base + 1 - shift

        pages = []
        if self.direction == self.DIR_LTR:
            if left_idx >= 0 and left_idx < n:
                pages.append(left_idx)
            elif left_idx == -1 and self.pad_start:
                pages.append(-1)

            if right_idx >= 0 and right_idx < n:
                pages.append(right_idx)
        else:
            if right_idx >= 0 and right_idx < n:
                pages.append(right_idx)

            if left_idx >= 0 and left_idx < n:
                pages.append(left_idx)
            elif left_idx == -1 and self.pad_start:
                pages.append(-1)

        return pages

    def _page_size_points(self, page_index: int) -> tuple[float, float]:
        if page_index < 0:
            ref_idx = max(0, min(self.page, self.content_provider.page_count - 1))
            return self.content_provider.get_page_size(ref_idx)
        return self.content_provider.get_page_size(page_index)

    def _compute_auto_zoom(self) -> list[float] | None:
        if not self.content_provider:
            return None

        cw, ch = self.GetClientSize()
        if cw <= 0 or ch <= 0:
            return None

        pages = self._spread_pages()
        if not pages:
            return None

        avail_w = max(1, cw - 2 * self.margin)
        avail_h = max(1, ch - 2 * self.margin)

        sizes = [self._page_size_points(pi) for pi in pages]

        if len(sizes) == 1:
            pw, ph = sizes[0]
            if self.zoom_mode == self.ZOOM_FIT_WIDTH:
                return [avail_w / pw]
            if self.zoom_mode == self.ZOOM_FIT_PAGE:
                return [min(avail_w / pw, avail_h / ph)]
            return None

        if len(sizes) != 2:
            return None

        (w0, h0), (w1, h1) = sizes

        if h0 <= 0 or h1 <= 0:
            sum_w = w0 + w1 if w0 + w1 > 0 else 1
            max_h = max(h0, h1) if max(h0, h1) > 0 else 1
            z = min((avail_w - self.gap) / sum_w, avail_h / max_h)
            return [z, z]

        total_effective_width = w0 + w1 * (h0 / h1)
        width_based_z0 = (avail_w - self.gap) / total_effective_width if total_effective_width > 0 else 0

        height_based_z0 = avail_h / h0

        z0 = 0.0
        if self.zoom_mode == self.ZOOM_FIT_WIDTH:
            z0 = width_based_z0
        elif self.zoom_mode == self.ZOOM_FIT_PAGE:
            z0 = min(width_based_z0, height_based_z0)
        else:  # Manual zoom
            return [self.zoom, self.zoom]

        z1 = z0 * (h0 / h1)

        return [max(self.MIN_ZOOM, z) for z in [z0, z1]]

    def _apply_auto_zoom_if_needed(self):
        if self.zoom_mode == self.ZOOM_MANUAL:
            return
        z = self._compute_auto_zoom()
        if z is None:
            return
        z = max(self.MIN_ZOOM, min(z, self.MAX_ZOOM))

        if abs(z - self.zoom) > 1e-9:
            self.zoom = z
            self._ensure_cache_zoom()

    def _start_pre_rendering(self):
        if not self.content_provider:
            return
        self._pre_render_timer.Stop()
        self._pre_render_timer.Start(200, wx.TIMER_ONE_SHOT)

    def _on_pre_render_timer(self, evt):
        if not self.content_provider:
            return

        anchor = self.page
        pages_to_check = range(anchor - 4, anchor + 6)

        for page_index in pages_to_check:
            if not (0 <= page_index < self.content_provider.page_count):
                continue

            cache_key = (page_index, int(self.zoom * 10000))

            if cache_key in self._bmp_cache:
                continue

            if cache_key in self._requested_pages:
                continue

            self._requested_pages.add(cache_key)
            self.render_queue.put((page_index, self.zoom, self.content_provider))

    def _refresh_layout(self):
        if not self.content_provider:
            self.SetVirtualSize((0, 0))
            return

        pages = self._spread_pages()
        if not pages:
            self.SetVirtualSize((0, 0))
            self._current_bitmaps = []
            return

        zooms = []
        if self.zoom_mode == self.ZOOM_MANUAL:
            zooms = [self.zoom] * len(pages)
        else:
            computed_zooms = self._compute_auto_zoom()
            if computed_zooms and len(computed_zooms) == len(pages):
                zooms = computed_zooms
                if zooms:
                    new_base_zoom = zooms[0] if self.direction == self.DIR_LTR else zooms[-1]
                    new_base_zoom = max(self.MIN_ZOOM, min(new_base_zoom, self.MAX_ZOOM))
                    if abs(new_base_zoom - self.zoom) > 1e-9:
                        self.zoom = new_base_zoom
            else:
                zooms = [self.zoom] * len(pages)

        self._current_bitmaps = []
        for i, page_index in enumerate(pages):
            zoom_for_page = zooms[i]
            bmp = self._get_bitmap(page_index, zoom_for_page)
            self._current_bitmaps.append((page_index, bmp))

        widths = [bmp.GetWidth() for _, bmp in self._current_bitmaps]
        heights = [bmp.GetHeight() for _, bmp in self._current_bitmaps]

        if not widths or not heights:
            self.SetVirtualSize((0, 0))
            return

        if self.mode == self.MODE_SINGLE or len(widths) == 1:
            content_w = widths[0]
            content_h = heights[0]
        else:
            content_w = widths[0] + self.gap + widths[1]
            content_h = heights[0]

        total_w = content_w + 2 * self.margin
        total_h = content_h + 2 * self.margin
        self.SetVirtualSize((total_w, total_h))
        self.SetFocus()

        if self.main_frame:
            wx.CallAfter(self.main_frame._update_ui)
        self._start_pre_rendering()

    def _draw_centered(self, dc: wx.DC):
        if not self._current_bitmaps:
            return

        origin_x, origin_y = self.GetViewStart()
        spx, spy = self.GetScrollPixelsPerUnit()
        ox, oy = origin_x * spx, origin_y * spy
        cw, ch = self.GetClientSize()

        widths = [bmp.GetWidth() for _, bmp in self._current_bitmaps]
        heights = [bmp.GetHeight() for _, bmp in self._current_bitmaps]

        if self.mode == self.MODE_SINGLE or len(widths) == 1:
            content_w, content_h = widths[0], heights[0]
        else:
            content_w = widths[0] + self.gap + widths[1]
            content_h = max(heights[0], heights[1])

        base_x = self.margin
        available_w = cw - 2 * self.margin
        if available_w > content_w:
            base_x = self.margin + (available_w - content_w) // 2

        base_y = self.margin
        if len(self._current_bitmaps) == 1:
            _, bmp = self._current_bitmaps[0]
            dc.DrawBitmap(bmp, base_x - ox, base_y - oy, True)
        elif len(self._current_bitmaps) == 2:
            (_, bmp0), (_, bmp1) = self._current_bitmaps
            dc.DrawBitmap(bmp0, base_x - ox, base_y - oy, True)
            x1 = base_x + bmp0.GetWidth() + self.gap
            dc.DrawBitmap(bmp1, x1 - ox, base_y - oy, True)

    # --------------------------
    # Event handlers
    # --------------------------
    def on_paint(self, evt):
        dc = wx.AutoBufferedPaintDC(self)
        dc.SetBackground(wx.Brush(self.bgColor))
        dc.Clear()
        if self.content_provider and self.content_provider.is_valid:
            try:
                self._draw_centered(dc)
            except Exception:
                pass

    def on_mousewheel(self, evt: wx.MouseEvent):
        if evt.ControlDown():
            if not self.content_provider or evt.GetWheelRotation() == 0:
                return

            steps = evt.GetWheelRotation() / evt.GetWheelDelta()
            factor = 1.1 ** steps

            old_zoom = self.zoom
            self.zoom = max(self.MIN_ZOOM, min(self.zoom * factor, self.MAX_ZOOM))

            if abs(self.zoom - old_zoom) < 1e-9:
                return

            self.zoom_mode = self.ZOOM_MANUAL
            mx, my = evt.GetPosition()
            vx, vy = self.GetViewStart()
            spx, spy = self.GetScrollPixelsPerUnit()
            anchor_x = vx * spx + mx
            anchor_y = vy * spy + my

            self.Freeze()
            self._refresh_layout()
            scale = self.zoom / old_zoom
            new_scroll_px_x = max(0, int(anchor_x * scale - mx))
            new_scroll_px_y = max(0, int(anchor_y * scale - my))

            self.Scroll(new_scroll_px_x // spx if spx else 0, new_scroll_px_y // spy if spy else 0)
            self.Thaw()

            self.Refresh()
        else:
            evt.Skip()

    def on_right_down(self, evt: wx.MouseEvent):
        if not self.content_provider: return
        self._panning = True
        self._pan_start_mouse = evt.GetPosition()
        self._pan_start_view = self.GetViewStart()
        self.CaptureMouse()

    def on_right_up(self, evt: wx.MouseEvent):
        if self._panning:
            self._panning = False
            if self.HasCapture(): self.ReleaseMouse()

    def on_mouse_move(self, evt: wx.MouseEvent):
        if not (self._panning and evt.Dragging() and evt.RightIsDown()): return
        spx, spy = self.GetScrollPixelsPerUnit()
        if spx == 0 or spy == 0: return

        dx, dy = evt.GetPosition().x - self._pan_start_mouse.x, evt.GetPosition().y - self._pan_start_mouse.y
        start_x, start_y = self._pan_start_view
        self.Scroll(max(0, start_x - int(dx / spx)), max(0, start_y - int(dy / spy)))
        self.Refresh(False)

    def on_char_hook(self, evt: wx.KeyEvent):
        if not self.content_provider:
            evt.Skip()
            return

        key = evt.GetKeyCode()
        if self.direction == self.DIR_LTR:
            next_keys = {wx.WXK_RIGHT, wx.WXK_DOWN, wx.WXK_PAGEDOWN, wx.WXK_SPACE}
            prev_keys = {wx.WXK_LEFT, wx.WXK_UP, wx.WXK_PAGEUP, wx.WXK_BACK}
        else:
            next_keys = {wx.WXK_LEFT, wx.WXK_DOWN, wx.WXK_PAGEDOWN, wx.WXK_SPACE}
            prev_keys = {wx.WXK_RIGHT, wx.WXK_UP, wx.WXK_PAGEUP, wx.WXK_BACK}

        if key in next_keys:
            self.go_next()
        elif key in prev_keys:
            self.go_prev()
        else:
            evt.Skip()

    def handle_link_click(self, link: dict):
        kind = link.get("kind")
        if kind == fitz.LINK_GOTO:
            dest_page = link.get("page", 0)
            if 0 <= dest_page < self.content_provider.page_count:
                self.go_to_page(dest_page)
        elif kind == fitz.LINK_URI:
            uri = link.get("uri", "")
            if uri: webbrowser.open(uri)

    def on_left_down(self, evt: wx.MouseEvent):
        if not self.content_provider:
            evt.Skip()
            return

        click_pos = self.CalcUnscrolledPosition(evt.GetPosition())
        cw, ch = self.GetClientSize()
        widths = [bmp.GetWidth() for _, bmp in self._current_bitmaps]
        if not widths:
            evt.Skip()
            return

        content_w = widths[0] if self.mode == self.MODE_SINGLE or len(widths) == 1 else widths[0] + self.gap + widths[1]
        base_x = self.margin
        if (available_w := cw - 2 * self.margin) > content_w:
            base_x = self.margin + (available_w - content_w) // 2
        base_y = self.margin

        current_x = base_x
        for page_index, bmp in self._current_bitmaps:
            page_rect = wx.Rect(current_x, base_y, bmp.GetWidth(), bmp.GetHeight())
            if page_rect.Contains(click_pos) and page_index >= 0:
                links = self.content_provider.get_links(page_index)
                for link in links:
                    link_rect_pdf = link['from']
                    link_wx_rect = wx.Rect(
                        round(page_rect.x + link_rect_pdf.x0 * self.zoom),
                        round(page_rect.y + link_rect_pdf.y0 * self.zoom),
                        round(link_rect_pdf.width * self.zoom),
                        round(link_rect_pdf.height * self.zoom)
                    )
                    if link_wx_rect.Contains(click_pos):
                        self.handle_link_click(link)
                        evt.Skip()
                        return
            current_x += bmp.GetWidth() + self.gap
        evt.Skip()

    def on_size(self, evt):
        self._refresh_layout()
        self.Refresh(eraseBackground=True)

        evt.Skip()
