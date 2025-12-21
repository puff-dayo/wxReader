from __future__ import annotations

import webbrowser

import fitz  # PyMuPDF
import numpy as np
import wx


class PDFDocument:
    def __init__(self, path: str):
        self.path = path
        self.doc = fitz.open(path)

    @property
    def page_count(self) -> int:
        return self.doc.page_count

    def get_toc(self) -> list:
        """
        Format: [[lvl, title, page, ...], ...]
        Note: page numbers from PyMuPDF are 1-based.
        """
        try:
            return self.doc.get_toc(simple=True)
        except Exception:
            return []

    def close(self):
        try:
            self.doc.close()
        except Exception:
            pass

    def render_page_to_bitmap(self, page_index: int, zoom: float) -> wx.Bitmap:
        """
        Render a page (0-based index) at 'zoom' scale into a wx.Bitmap.
        page point * zoom => pixels
        """
        # Safety check
        if page_index < 0 or page_index >= self.page_count:
            return wx.Bitmap(1, 1)

        page = self.doc.load_page(page_index)

        mat = fitz.Matrix(zoom, zoom)
        pix = page.get_pixmap(matrix=mat, alpha=False)

        w, h = pix.width, pix.height
        img = wx.Image(w, h)
        img.SetData(pix.samples)  # RGB bytes
        return wx.Bitmap(img)

    def get_page_size(self, page_index: int) -> tuple[float, float]:
        """Get logical size of a page in points."""
        try:
            p_idx = max(0, min(page_index, self.page_count - 1))
            page = self.doc.load_page(p_idx)
            r = page.rect
            return r.width, r.height
        except Exception:
            return 595.0, 842.0  # Fallback A4


class PDFView(wx.ScrolledWindow):
    MODE_SINGLE = "single"
    MODE_TWO = "two"

    DIR_LTR = "ltr"
    DIR_RTL = "rtl"

    ZOOM_MANUAL = "manual"
    ZOOM_FIT_WIDTH = "fit_width"
    ZOOM_FIT_PAGE = "fit_page"

    # enhance group
    ENH_NONE = "enh_none"
    ENH_SHARPEN = "enh_sharpen"
    ENH_SOFTEN = "enh_soften"
    ENH_SOFTEN_SHARPEN = "enh_soften_sharpen"

    # color group
    COL_NONE = "col_none"
    COL_INVERT = "col_invert"
    COL_GREEN = "col_green"
    COL_BROWN = "col_brown"

    def __init__(self, parent):
        super().__init__(parent, style=wx.HSCROLL | wx.VSCROLL | wx.WANTS_CHARS)
        self.SetBackgroundStyle(wx.BG_STYLE_PAINT)
        self.bgColor = wx.Colour(134, 180, 118)
        self.enhance_mode = self.ENH_NONE
        self.color_mode = self.COL_NONE

        self.main_frame = None

        # State
        self.pdf: PDFDocument | None = None
        self.page = 0  # current page (0-based)
        self.zoom = 1.0
        self.zoom_mode = self.ZOOM_FIT_PAGE

        self.mode = self.MODE_TWO
        self.direction = self.DIR_LTR
        self.pad_start = False

        # Render cache for current zoom: {(page_index): wx.Bitmap}
        self._bmp_cache: dict[int, wx.Bitmap] = {}
        self._last_cache_zoom = self.zoom
        self._pre_render_timer = wx.Timer(self)
        self.Bind(wx.EVT_TIMER, self._on_pre_render_timer, self._pre_render_timer)

        # Layout
        self.margin = 6
        self.gap = 6
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
    def set_document(self, pdf: PDFDocument | None):
        self._bmp_cache.clear()
        self._current_bitmaps.clear()
        self.pdf = pdf
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

    def set_enhance_mode(self, mode: str):
        if mode not in (self.ENH_NONE, self.ENH_SHARPEN, self.ENH_SOFTEN, self.ENH_SOFTEN_SHARPEN):
            return
        if self.enhance_mode != mode:
            self.enhance_mode = mode
            self._bmp_cache.clear()
            self._refresh_layout()
            self.Refresh()

    def set_color_mode(self, mode: str):
        if mode not in (self.COL_NONE, self.COL_INVERT, self.COL_GREEN, self.COL_BROWN):
            return
        if self.color_mode != mode:
            self.color_mode = mode
            self._bmp_cache.clear()
            self._refresh_layout()
            self.Refresh()

    def set_pad_start(self, pad: bool):
        if self.pad_start != pad:
            self.pad_start = pad
            self._bmp_cache.clear()  # Clear cache to be safe (indices might shift visually)
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

    def go_next(self):
        if not self.pdf:
            return
        step = 1 if self.mode == self.MODE_SINGLE else 2
        self.page = min(self.page + step, self.pdf.page_count - 1)
        self._refresh_layout()
        self.Refresh()

    def go_prev(self):
        if not self.pdf:
            return
        step = 1 if self.mode == self.MODE_SINGLE else 2
        self.page = max(self.page - step, 0)
        self._refresh_layout()
        self.Refresh()

    def go_to_page(self, page_index: int):
        """Direct jump to a page index."""
        if not self.pdf:
            return
        self.page = max(0, min(page_index, self.pdf.page_count - 1))
        self._refresh_layout()
        self.Refresh()

    def stop_worker(self):
        """Stops the preload timer to prevent crashes on exit."""
        if self._pre_render_timer.IsRunning():
            self._pre_render_timer.Stop()

    # --------------------------
    # Internals
    # --------------------------
    def _ensure_cache_zoom(self):
        if abs(self.zoom - self._last_cache_zoom) > 1e-9:
            self._bmp_cache.clear()
            self._last_cache_zoom = self.zoom

    def _prune_cache(self):
        if not self.pdf:
            return

        current_page = self.page
        keep_range = 10

        keys_to_delete = []
        for p_idx in self._bmp_cache:
            if abs(p_idx - current_page) > keep_range:
                keys_to_delete.append(p_idx)

        for k in keys_to_delete:
            del self._bmp_cache[k]

    def _get_bitmap(self, page_index: int) -> wx.Bitmap:
        self._ensure_cache_zoom()

        if page_index in self._bmp_cache:
            return self._bmp_cache[page_index]

        if len(self._bmp_cache) > 36:
            self._prune_cache()

        # Blank page index: -1
        if page_index < 0:
            ref_idx = max(0, min(self.page, self.pdf.page_count - 1))
            w_pt, h_pt = self.pdf.get_page_size(ref_idx)
            w_px = int(w_pt * self.zoom)
            h_px = int(h_pt * self.zoom)

            img = wx.Image(w_px, h_px)
            img.SetRGB(wx.Rect(0, 0, w_px, h_px), 255, 255, 255)
            bmp = wx.Bitmap(img)

            bmp = self._apply_processing(bmp)
            self._bmp_cache[page_index] = bmp
            return bmp

        bmp = self.pdf.render_page_to_bitmap(page_index, self.zoom)
        bmp = self._apply_processing(bmp)

        self._bmp_cache[page_index] = bmp
        return bmp

    def _spread_pages(self) -> list[int]:
        if not self.pdf:
            return []

        n = self.pdf.page_count
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
            ref_idx = max(0, min(self.page, self.pdf.page_count - 1))
            return self.pdf.get_page_size(ref_idx)
        return self.pdf.get_page_size(page_index)

    def _compute_auto_zoom(self) -> float | None:
        if not self.pdf:
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
                return avail_w / pw
            if self.zoom_mode == self.ZOOM_FIT_PAGE:
                return min(avail_w / pw, avail_h / ph)
            return None

        if len(sizes) != 2:
            return None

        (w0, h0), (w1, h1) = sizes
        sum_w = w0 + w1
        max_h = max(h0, h1)

        if self.zoom_mode == self.ZOOM_FIT_WIDTH:
            return max(0.01, (avail_w - self.gap) / sum_w)

        if self.zoom_mode == self.ZOOM_FIT_PAGE:
            zw = max(0.01, (avail_w - self.gap) / sum_w)
            zh = avail_h / max_h
            return min(zw, zh)

        return None

    def _apply_auto_zoom_if_needed(self):
        if self.zoom_mode == self.ZOOM_MANUAL:
            return
        z = self._compute_auto_zoom()
        if z is None:
            return
        z = max(0.2, min(z, 6.0))
        if abs(z - self.zoom) > 1e-9:
            self.zoom = z
            self._ensure_cache_zoom()

    def _apply_processing(self, bmp: wx.Bitmap) -> wx.Bitmap:
        if self.enhance_mode == self.ENH_NONE and self.color_mode == self.COL_NONE:
            return bmp

        img = bmp.ConvertToImage()
        w, h = img.GetWidth(), img.GetHeight()
        if w <= 0 or h <= 0:
            return bmp

        try:
            buf = img.GetDataBuffer()
            arr = np.frombuffer(memoryview(buf), dtype=np.uint8).reshape((h, w, 3))
        except Exception:
            # Fallback
            print("WARNING: Fallback to slow processing.")
            arr = np.frombuffer(img.GetData(), dtype=np.uint8).reshape((h, w, 3)).copy()

        def box_blur_u8(a: np.ndarray, r: int = 1, intensity: float = 1.0) -> np.ndarray:
            if r <= 0 or intensity <= 0:
                return a.copy()

            intensity = min(intensity, 1.0)

            k = 2 * r + 1
            pad = np.pad(a, ((r, r), (r, r), (0, 0)), mode="edge").astype(np.uint32)

            integ = pad.cumsum(axis=0).cumsum(axis=1)
            integ = np.pad(integ, ((1, 0), (1, 0), (0, 0)), mode="constant", constant_values=0)

            blurred_out = (integ[k:, k:] - integ[:-k, k:] - integ[k:, :-k] + integ[:-k, :-k]) // (k * k)

            if intensity == 1.0:
                return blurred_out.astype(np.uint8)

            intensity_factor = int(intensity * 100)
            inv_intensity_factor = 100 - intensity_factor

            original_u32 = a.astype(np.uint32)

            blended_res = (original_u32 * inv_intensity_factor + blurred_out * intensity_factor) // 100

            return blended_res.astype(np.uint8)

        # Enhance group
        if self.enhance_mode != self.ENH_NONE:
            if self.enhance_mode == self.ENH_SOFTEN:
                arr[:] = box_blur_u8(arr, r=1, intensity=0.5)

            elif self.enhance_mode == self.ENH_SHARPEN:
                blur = box_blur_u8(arr, r=1)
                a = arr.astype(np.int16)
                b = blur.astype(np.int16)
                # Unsharp mask (amount=1.0)
                res = a + (a - b)
                arr[:] = np.clip(res, 0, 255).astype(np.uint8)

            elif self.enhance_mode == self.ENH_SOFTEN_SHARPEN:
                blur = box_blur_u8(arr, r=1)
                a = arr.astype(np.int16)
                b = blur.astype(np.int16)

                sharpened_res = a + (a - b)
                sharpened_arr = np.clip(sharpened_res, 0, 255).astype(np.uint8)
                final_arr = box_blur_u8(sharpened_arr, r=1, intensity=0.3)

                arr[:] = final_arr

        # color group
        if self.color_mode == self.COL_INVERT:
            arr[:] = 255 - arr


        elif self.color_mode == self.COL_GREEN:
            arr[..., 0] = (arr[..., 0].astype(np.uint16) * 89 // 100).astype(np.uint8)
            arr[..., 1] = np.minimum(255, (arr[..., 1].astype(np.uint16) * 120 // 100)).astype(np.uint8)
            arr[..., 2] = (arr[..., 2].astype(np.uint16) * 79 // 100).astype(np.uint8)


        elif self.color_mode == self.COL_BROWN:
            intensity = 0.65

            r = arr[..., 0].astype(np.uint32)
            g = arr[..., 1].astype(np.uint32)
            b = arr[..., 2].astype(np.uint32)

            tr = (393 * r + 769 * g + 189 * b) // 1000
            tg = (349 * r + 686 * g + 168 * b) // 1000
            tb = (272 * r + 534 * g + 131 * b) // 1000

            intensity_factor = int(intensity * 100)

            inv_intensity_factor = 100 - intensity_factor

            final_r = (r * inv_intensity_factor + tr * intensity_factor) // 100
            final_g = (g * inv_intensity_factor + tg * intensity_factor) // 100
            final_b = (b * inv_intensity_factor + tb * intensity_factor) // 100

            arr[..., 0] = np.minimum(255, final_r).astype(np.uint8)
            arr[..., 1] = np.minimum(255, final_g).astype(np.uint8)
            arr[..., 2] = np.minimum(255, final_b).astype(np.uint8)

        if not hasattr(img, "GetDataBuffer"):
            img.SetData(arr.tobytes())

        return wx.Bitmap(img)

    def _start_pre_rendering(self):
        if not self.pdf:
            return
        self._pre_render_timer.Stop()
        self._pre_render_timer.Start(200, wx.TIMER_ONE_SHOT)

    def _on_pre_render_timer(self, evt):
        if not self or not self.pdf or not self.pdf.doc or self.pdf.doc.is_closed:
            return

        current_pages_indices = self._spread_pages()
        if not current_pages_indices:
            return

        pages_to_prerender = set()
        anchor = self.page

        for i in range(anchor - 2, anchor + 4):
            if 0 <= i < self.pdf.page_count:
                pages_to_prerender.add(i)

        for page_index in pages_to_prerender:
            if not self.pdf or self.pdf.doc.is_closed:
                return

            self._ensure_cache_zoom()
            if page_index not in self._bmp_cache:
                self._get_bitmap(page_index)

    def _pre_render_worker(self):
        if not self or not self.pdf or not self.pdf.doc or self.pdf.doc.is_closed:
            return

        current_pages_indices = self._spread_pages()
        if not current_pages_indices:
            return

        pages_to_prerender = set()

        anchor = self.page
        for i in range(anchor - 2, anchor + 4):
            if 0 <= i < self.pdf.page_count:
                pages_to_prerender.add(i)

        for page_index in pages_to_prerender:
            self._ensure_cache_zoom()
            if page_index not in self._bmp_cache:
                self._get_bitmap(page_index)

    def _refresh_layout(self):
        if not self.pdf:
            self.SetVirtualSize((0, 0))
            return

        self._apply_auto_zoom_if_needed()
        pages = self._spread_pages()
        self._current_bitmaps = [(pi, self._get_bitmap(pi)) for pi in pages]

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
            content_h = max(heights[0], heights[1])

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
        if self.pdf and self.pdf.doc and not self.pdf.doc.is_closed:
            try:
                self._draw_centered(dc)
            except Exception:
                pass

    def on_mousewheel(self, evt: wx.MouseEvent):
        if evt.ControlDown():
            if not self.pdf or evt.GetWheelRotation() == 0:
                return

            steps = evt.GetWheelRotation() / evt.GetWheelDelta()
            factor = 1.1 ** steps
            old_zoom, self.zoom = self.zoom, max(0.2, min(self.zoom * factor, 6.0))
            if abs(self.zoom - old_zoom) < 1e-9:
                return

            self.zoom_mode = self.ZOOM_MANUAL
            mx, my = evt.GetPosition()
            vx, vy = self.GetViewStart()
            spx, spy = self.GetScrollPixelsPerUnit()
            anchor_x = vx * spx + mx
            anchor_y = vy * spy + my

            self._refresh_layout()
            scale = self.zoom / old_zoom
            new_scroll_px_x = max(0, int(anchor_x * scale - mx))
            new_scroll_px_y = max(0, int(anchor_y * scale - my))

            self.Scroll(new_scroll_px_x // spx if spx else 0, new_scroll_px_y // spy if spy else 0)
            self.Refresh()
        else:
            evt.Skip()

    def on_right_down(self, evt: wx.MouseEvent):
        if not self.pdf: return
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
        if not self.pdf:
            evt.Skip();
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
            if 0 <= dest_page < self.pdf.page_count:
                self.go_to_page(dest_page)
        elif kind == fitz.LINK_URI:
            uri = link.get("uri", "")
            if uri: webbrowser.open(uri)

    def on_left_down(self, evt: wx.MouseEvent):
        if not self.pdf:
            evt.Skip();
            return

        click_pos = self.CalcUnscrolledPosition(evt.GetPosition())
        cw, ch = self.GetClientSize()
        widths = [bmp.GetWidth() for _, bmp in self._current_bitmaps]
        if not widths:
            evt.Skip();
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
                links = self.pdf.doc.load_page(page_index).get_links()
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
                        evt.Skip();
                        return
            current_x += bmp.GetWidth() + self.gap
        evt.Skip()

    def on_size(self, evt):
        self._refresh_layout()
        self.Refresh(eraseBackground=True)

        evt.Skip()
