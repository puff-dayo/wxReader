from __future__ import annotations

import os
import webbrowser

import fitz  # PyMuPDF
import numpy as np
import wx
from wx import adv

from wxReaderConfigUtil import load_config, save_config, update_recent

APP_NAME = "wxReader"
APP_VERSION = "0.6.1"


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


class TOCDialog(wx.Dialog):
    def __init__(self, parent, toc_list, current_page_idx, on_navigate_callback):
        super().__init__(parent, title="Table of Contents", size=(450, 650),
                         style=wx.DEFAULT_DIALOG_STYLE | wx.RESIZE_BORDER)

        self.toc_list = toc_list
        self.on_navigate = on_navigate_callback

        self.SetBackgroundColour(wx.SystemSettings.GetColour(wx.SYS_COLOUR_WINDOW))

        # --- Layout ---
        main_sizer = wx.BoxSizer(wx.VERTICAL)

        # 1. Search Bar
        search_sizer = wx.BoxSizer(wx.HORIZONTAL)
        self.search_ctrl = wx.SearchCtrl(self, style=wx.TE_PROCESS_ENTER)
        self.search_ctrl.ShowCancelButton(True)
        self.search_ctrl.SetDescriptiveText("Filter sections...")
        search_sizer.Add(self.search_ctrl, 1, wx.EXPAND | wx.ALL, 8)
        main_sizer.Add(search_sizer, 0, wx.EXPAND)

        # 2. Tree Control
        tree_style = (wx.TR_DEFAULT_STYLE | wx.TR_HIDE_ROOT |
                      wx.TR_FULL_ROW_HIGHLIGHT | wx.TR_NO_LINES | wx.TR_TWIST_BUTTONS)
        self.tree = wx.TreeCtrl(self, style=tree_style)
        self.tree.SetDoubleBuffered(True)
        main_sizer.Add(self.tree, 1, wx.EXPAND | wx.LEFT | wx.RIGHT | wx.BOTTOM, 8)

        # 3. Action Buttons
        btn_sizer = wx.BoxSizer(wx.HORIZONTAL)

        self.info_lbl = wx.StaticText(self, label=f"{len(toc_list)} sections")
        self.info_lbl.SetForegroundColour(wx.Colour(100, 100, 100))
        btn_sizer.Add(self.info_lbl, 1, wx.ALIGN_CENTER_VERTICAL | wx.LEFT, 10)

        btn_close = wx.Button(self, wx.ID_CANCEL, "Close")
        btn_sizer.Add(btn_close, 0, wx.LEFT, 10)

        main_sizer.Add(btn_sizer, 0, wx.EXPAND | wx.ALL, 10)
        self.SetSizer(main_sizer)

        # --- Events ---
        self.tree.Bind(wx.EVT_TREE_ITEM_ACTIVATED, self.on_item_activated)
        self.search_ctrl.Bind(wx.EVT_TEXT, self.on_search)
        self.search_ctrl.Bind(wx.EVT_SEARCHCTRL_CANCEL_BTN, self.on_search_cancel)

        # --- Populate ---
        self._populate_tree(current_page_idx=current_page_idx)
        self.search_ctrl.SetFocus()
        self.CenterOnParent()

    def _populate_tree(self, filter_text=None, current_page_idx=-1):
        self.tree.DeleteAllItems()
        root = self.tree.AddRoot("Root")

        if filter_text:
            filter_text = filter_text.lower()
            for entry in self.toc_list:
                title = entry[1]
                if filter_text in title.lower():
                    page_num = entry[2]
                    target_page_idx = max(0, page_num - 1)
                    item = self.tree.AppendItem(root, title)
                    self.tree.SetItemData(item, target_page_idx)
            self.tree.ExpandAll()
        else:
            parents = {0: root}
            best_item = None
            best_page_found = -1

            for entry in self.toc_list:
                lvl = entry[0]
                title = entry[1]
                page_num = entry[2]
                target_page_idx = max(0, page_num - 1)

                parent_item = parents.get(lvl - 1, root)
                new_item = self.tree.AppendItem(parent_item, title)
                self.tree.SetItemData(new_item, target_page_idx)
                parents[lvl] = new_item

                if current_page_idx >= 0 and target_page_idx <= current_page_idx:
                    if target_page_idx >= best_page_found:
                        best_page_found = target_page_idx
                        best_item = new_item

            if best_item:
                self.tree.SelectItem(best_item)
                self.tree.EnsureVisible(best_item)

    def on_search(self, evt):
        txt = self.search_ctrl.GetValue()
        self._populate_tree(filter_text=txt)

    def on_search_cancel(self, evt):
        self.search_ctrl.SetValue("")
        self._populate_tree()

    def on_item_activated(self, evt):
        item = self.tree.GetSelection()
        if item and item.IsOk() and item != self.tree.GetRootItem():
            data = self.tree.GetItemData(item)
            if data is not None:
                self.on_navigate(data)
                self.EndModal(wx.ID_OK)


class FileDropTarget(wx.FileDropTarget):
    def __init__(self, frame):
        super().__init__()
        self.frame = frame
        self.allowed = {".pdf", ".epub", ".mobi", ".fb2", ".cbz", ".txt"}

    def _accept(self, filenames):
        if not filenames:
            return False
        path = filenames[0]
        ext = os.path.splitext(path)[1].lower()
        return os.path.isfile(path) and ext in self.allowed

    def OnEnter(self, x, y, d):
        return wx.DragCopy

    def OnDragOver(self, x, y, d):
        return wx.DragCopy if self._accept(getattr(self, "_last_filenames", [""])) else wx.DragCopy

    def OnDropFiles(self, x, y, filenames):
        if not self._accept(filenames):
            wx.Bell()
            return False
        wx.CallAfter(self.frame._load_pdf, filenames[0])
        return True


class TextExtractionDialog(wx.Dialog):
    def __init__(self, parent, text, title="Page Text"):
        super().__init__(parent, title=title, size=(600, 500),
                         style=wx.DEFAULT_DIALOG_STYLE | wx.RESIZE_BORDER)

        sizer = wx.BoxSizer(wx.VERTICAL)

        self.text_ctrl = wx.TextCtrl(self, value=text,
                                     style=wx.TE_MULTILINE | wx.TE_READONLY | wx.HSCROLL)

        font = wx.Font(10, wx.FONTFAMILY_TELETYPE, wx.FONTSTYLE_NORMAL, wx.FONTWEIGHT_NORMAL)
        self.text_ctrl.SetFont(font)

        sizer.Add(self.text_ctrl, 1, wx.EXPAND | wx.ALL, 10)

        # Buttons
        btn_sizer = wx.BoxSizer(wx.HORIZONTAL)
        btn_copy = wx.Button(self, label="Copy All")
        btn_close = wx.Button(self, wx.ID_CANCEL, "Close")

        btn_sizer.Add(btn_copy, 0, wx.RIGHT, 10)
        btn_sizer.Add(btn_close, 0)

        sizer.Add(btn_sizer, 0, wx.ALIGN_RIGHT | wx.BOTTOM | wx.RIGHT, 10)

        self.SetSizer(sizer)

        # Events
        btn_copy.Bind(wx.EVT_BUTTON, self.on_copy)

    def on_copy(self, evt):
        if wx.TheClipboard.Open():
            wx.TheClipboard.SetData(wx.TextDataObject(self.text_ctrl.GetValue()))
            wx.TheClipboard.Close()
            wx.MessageBox("Text copied to clipboard!", "Success")
        else:
            wx.MessageBox("Could not open clipboard.", "Error")


class MainFrame(wx.Frame):
    def __init__(self):
        super().__init__(None, title=APP_NAME, size=(1200, 850))
        self.SetMinSize((600, 400))

        # Initialize state
        self.pdf: PDFDocument | None = None
        self.file_history = wx.FileHistory(12)

        self.epub_font_size = 12

        # --- Layout ---
        self.splitter = wx.SplitterWindow(self, style=wx.SP_LIVE_UPDATE | wx.SP_3D)
        self.splitter.SetMinimumPaneSize(50)

        # 1. Sidebar (Inline TOC)
        self.sidebar = wx.Panel(self.splitter)
        self.sidebar_sizer = wx.BoxSizer(wx.VERTICAL)

        self.sidebar_search = wx.SearchCtrl(self.sidebar, style=wx.TE_PROCESS_ENTER)
        self.sidebar_search.SetDescriptiveText("Search Outline")

        self.sidebar_tree = wx.TreeCtrl(self.sidebar, style=wx.TR_DEFAULT_STYLE | wx.TR_HIDE_ROOT |
                                                            wx.TR_FULL_ROW_HIGHLIGHT | wx.TR_NO_LINES | wx.TR_TWIST_BUTTONS)
        self.sidebar_tree.SetBackgroundColour(wx.Colour(245, 245, 245))

        self.sidebar_sizer.Add(self.sidebar_search, 0, wx.EXPAND | wx.ALL, 5)
        self.sidebar_sizer.Add(self.sidebar_tree, 1, wx.EXPAND | wx.LEFT | wx.RIGHT | wx.BOTTOM, 0)
        self.sidebar.SetSizer(self.sidebar_sizer)

        # 2. Main Content
        self.view = PDFView(self.splitter)
        self.view.main_frame = self

        self.splitter.SplitVertically(self.sidebar, self.view, 250)
        self.splitter.SetSashGravity(0.0)
        self.splitter.Unsplit(self.sidebar)

        self.CreateStatusBar(1)

        self._build_menus()

        self.recent_files = []

        cfg = load_config()

        try:
            show_sidebar = bool(cfg.get("show_sidebar", False))
            if show_sidebar and not self.splitter.IsSplit():
                self.splitter.SplitVertically(self.sidebar, self.view, 250)
        except Exception:
            pass

        try:
            self.view.set_mode(cfg.get("view_mode", PDFView.MODE_TWO))
            self.view.set_direction(cfg.get("direction", PDFView.DIR_LTR))
            self.view.set_pad_start(bool(cfg.get("pad_start", False)))
            self.view.set_zoom_mode(cfg.get("zoom_mode", PDFView.ZOOM_FIT_PAGE))
        except Exception as e:
            print(f"Error loading view modes: {e}")

        self.view.set_background_color(wx.Colour(134, 180, 118))

        self.epub_font_size = int(cfg.get("epub_font_size", self.epub_font_size))

        self.recent_files = cfg.get("recent_files", []) or []
        last = cfg.get("last_file", "")

        for p in self.recent_files:
            if p and os.path.isfile(p):
                self.file_history.AddFileToHistory(p)
        self.file_history.AddFilesToMenu(self.m_recent)

        if last and os.path.isfile(last):
            wx.CallAfter(self._load_pdf, last)

        # --- Events ---
        self.Bind(wx.EVT_CLOSE, self.on_close)
        self.sidebar_tree.Bind(wx.EVT_TREE_ITEM_ACTIVATED, self.on_sidebar_click)
        self.sidebar_search.Bind(wx.EVT_TEXT, self.on_sidebar_search)
        self.SetDropTarget(FileDropTarget(self))

        self._update_ui()

    def _build_menus(self):
        menubar = wx.MenuBar()

        # --- File Menu ---
        m_file = wx.Menu()
        m_open = m_file.Append(wx.ID_OPEN, "&Open...\tCtrl+O")
        m_close = m_file.Append(wx.ID_CLOSE, "&Close\tCtrl+W")

        m_file.AppendSeparator()

        self.m_recent = wx.Menu()
        m_file.AppendSubMenu(self.m_recent, "Open &Recent")

        self.id_clear_history = wx.NewIdRef()
        m_file.Append(self.id_clear_history, "Clear Recent Files")

        m_file.AppendSeparator()
        m_exit = m_file.Append(wx.ID_EXIT, "E&xit")
        menubar.Append(m_file, "&File")

        # --- View Menu ---
        m_view = wx.Menu()

        self.id_sidebar_toggle = wx.NewIdRef()
        m_view.AppendCheckItem(self.id_sidebar_toggle, "Show &Sidebar\tF9")
        m_view.AppendSeparator()

        self.id_single_page = wx.NewIdRef()
        self.id_two_page = wx.NewIdRef()
        m_view.AppendRadioItem(self.id_single_page, "Single Page View")
        m_view.AppendRadioItem(self.id_two_page, "Two Page View")
        m_view.AppendSeparator()

        self.id_pad_start = wx.NewIdRef()
        m_view.AppendCheckItem(self.id_pad_start, "Add Blank Page at Start")
        m_view.AppendSeparator()

        m_dir = wx.Menu()
        self.id_ltr = wx.NewIdRef()
        self.id_rtl = wx.NewIdRef()
        m_dir.AppendRadioItem(self.id_ltr, "Left-to-Right")
        m_dir.AppendRadioItem(self.id_rtl, "Right-to-Left")
        m_view.AppendSubMenu(m_dir, "Page &Direction")
        m_view.AppendSeparator()

        self.id_prev = wx.NewIdRef()
        self.id_next = wx.NewIdRef()
        self.id_goto = wx.NewIdRef()
        m_view.Append(self.id_prev, "Previous Page\tLeft")
        m_view.Append(self.id_next, "Next Page\tRight")
        m_view.Append(self.id_goto, "&Go to Page...\tCtrl+G")
        m_view.AppendSeparator()

        self.id_zoom_in = wx.NewIdRef()
        self.id_zoom_out = wx.NewIdRef()
        self.id_fit_width = wx.NewIdRef()
        self.id_fit_page = wx.NewIdRef()

        m_view.Append(self.id_zoom_in, "Zoom &In\tCtrl++")
        m_view.Append(self.id_zoom_out, "Zoom &Out\tCtrl+-")
        m_view.AppendSeparator()
        m_view.AppendRadioItem(self.id_fit_width, "Fit &Width\tCtrl+1")
        m_view.AppendRadioItem(self.id_fit_page, "Fit &Page\tCtrl+0")

        self.id_bg = wx.NewIdRef()
        m_view.Append(self.id_bg, "Background Color…")

        m_view.AppendSeparator()
        self.id_font_increase = wx.NewIdRef()
        self.id_font_decrease = wx.NewIdRef()
        m_view.Append(self.id_font_increase, "Larger Font\tCtrl+Shift++")
        m_view.Append(self.id_font_decrease, "Smaller Font\tCtrl+Shift+-")

        m_view.AppendSeparator()
        self.id_show_toc_dialog = wx.NewIdRef()
        m_view.Append(self.id_show_toc_dialog, "Show TOC Dialog...\tCtrl+T")

        self.id_fullscreen = wx.NewIdRef()
        m_view.AppendCheckItem(self.id_fullscreen, "Full &Screen\tF11")

        menubar.Append(m_view, "&View")

        # --- Process Menu ---
        m_process = wx.Menu()

        m_enh = wx.Menu()
        self.id_enh_none = wx.NewIdRef()
        self.id_enh_sharpen = wx.NewIdRef()
        self.id_enh_soften = wx.NewIdRef()
        self.id_enh_soften_sharpen = wx.NewIdRef()

        m_enh.AppendRadioItem(self.id_enh_none, "None")
        m_enh.AppendRadioItem(self.id_enh_sharpen, "Sharpen")
        m_enh.AppendRadioItem(self.id_enh_soften, "Soften")
        m_enh.AppendRadioItem(self.id_enh_soften_sharpen, "Soften + Sharpen")

        m_col = wx.Menu()
        self.id_col_none = wx.NewIdRef()
        self.id_col_invert = wx.NewIdRef()
        self.id_col_green = wx.NewIdRef()
        self.id_col_brown = wx.NewIdRef()

        m_col.AppendRadioItem(self.id_col_none, "None")
        m_col.AppendRadioItem(self.id_col_invert, "Invert Colors")
        m_col.AppendRadioItem(self.id_col_green, "Green Filter")
        m_col.AppendRadioItem(self.id_col_brown, "Brown Filter")

        m_process.AppendSubMenu(m_enh, "Enhance")
        m_process.AppendSubMenu(m_col, "Color")

        m_process.AppendSeparator()
        self.id_extract_text = wx.NewIdRef()
        m_process.Append(self.id_extract_text, "Extract Page Text...\tCtrl+E")

        menubar.Append(m_process, "&Process")

        # --- Help Menu ---
        m_help = wx.Menu()
        m_about = m_help.Append(wx.ID_ABOUT, "&About")
        menubar.Append(m_help, "&Help")

        self.SetMenuBar(menubar)
        self.file_history.UseMenu(self.m_recent)
        self.file_history.AddFilesToMenu(self.m_recent)

        # --- Bindings ---
        self.Bind(wx.EVT_MENU, self.on_open, m_open)
        self.Bind(wx.EVT_MENU, self.on_close_pdf, m_close)
        self.Bind(wx.EVT_MENU_RANGE, self.on_open_recent, id=wx.ID_FILE1, id2=wx.ID_FILE9)  # wx uses ID_FILE1.. for history
        self.Bind(wx.EVT_MENU, self.on_clear_history, id=self.id_clear_history)
        self.Bind(wx.EVT_MENU, lambda e: self.Close(), m_exit)

        self.Bind(wx.EVT_MENU, self.on_toggle_sidebar, id=self.id_sidebar_toggle)

        self.Bind(wx.EVT_MENU, lambda e: (self.view.set_mode(PDFView.MODE_SINGLE), self._update_ui()),
                  id=self.id_single_page)
        self.Bind(wx.EVT_MENU, lambda e: (self.view.set_mode(PDFView.MODE_TWO), self._update_ui()), id=self.id_two_page)

        self.Bind(wx.EVT_MENU, self.on_toggle_pad_start, id=self.id_pad_start)

        self.Bind(wx.EVT_MENU, lambda e: (self.view.set_direction(PDFView.DIR_LTR), self._update_ui()), id=self.id_ltr)
        self.Bind(wx.EVT_MENU, lambda e: (self.view.set_direction(PDFView.DIR_RTL), self._update_ui()), id=self.id_rtl)

        self.Bind(wx.EVT_MENU, lambda e: self.view.go_prev(), id=self.id_prev)
        self.Bind(wx.EVT_MENU, lambda e: self.view.go_next(), id=self.id_next)
        self.Bind(wx.EVT_MENU, self.on_goto_page, id=self.id_goto)

        self.Bind(wx.EVT_MENU, self.on_zoom_in, id=self.id_zoom_in)
        self.Bind(wx.EVT_MENU, self.on_zoom_out, id=self.id_zoom_out)
        self.Bind(wx.EVT_MENU, self.on_fit_width, id=self.id_fit_width)
        self.Bind(wx.EVT_MENU, self.on_fit_page, id=self.id_fit_page)

        self.Bind(wx.EVT_MENU, self.on_background_color, id=int(self.id_bg))

        self.Bind(wx.EVT_MENU, self.on_change_epub_font, id=self.id_font_increase)
        self.Bind(wx.EVT_MENU, self.on_change_epub_font, id=self.id_font_decrease)

        self.Bind(wx.EVT_MENU, lambda e: self.view.set_enhance_mode(PDFView.ENH_NONE), id=self.id_enh_none)
        self.Bind(wx.EVT_MENU, lambda e: self.view.set_enhance_mode(PDFView.ENH_SHARPEN), id=self.id_enh_sharpen)
        self.Bind(wx.EVT_MENU, lambda e: self.view.set_enhance_mode(PDFView.ENH_SOFTEN), id=self.id_enh_soften)
        self.Bind(wx.EVT_MENU, lambda e: self.view.set_enhance_mode(PDFView.ENH_SOFTEN_SHARPEN),
                  id=self.id_enh_soften_sharpen)

        self.Bind(wx.EVT_MENU, lambda e: self.view.set_color_mode(PDFView.COL_NONE), id=self.id_col_none)
        self.Bind(wx.EVT_MENU, lambda e: self.view.set_color_mode(PDFView.COL_INVERT), id=self.id_col_invert)
        self.Bind(wx.EVT_MENU, lambda e: self.view.set_color_mode(PDFView.COL_GREEN), id=self.id_col_green)
        self.Bind(wx.EVT_MENU, lambda e: self.view.set_color_mode(PDFView.COL_BROWN), id=self.id_col_brown)

        self.Bind(wx.EVT_MENU, self.on_extract_text, id=self.id_extract_text)
        self.Bind(wx.EVT_MENU, self.on_fullscreen, id=self.id_fullscreen)

        self.Bind(wx.EVT_MENU, self.on_show_toc_dialog, id=self.id_show_toc_dialog)
        self.Bind(wx.EVT_MENU, self.on_about, m_about)

    def _populate_sidebar(self, filter_text=None):
        if not self.pdf: return
        toc = self.pdf.get_toc()
        self.sidebar_tree.DeleteAllItems()
        root = self.sidebar_tree.AddRoot("Root")

        parents = {0: root}

        for entry in toc:
            lvl, title, page_num = entry[0], entry[1], entry[2]

            if filter_text and filter_text.lower() not in title.lower():
                continue

            target_page_idx = max(0, page_num - 1)

            if filter_text:
                parent_item = root
            else:
                parent_item = parents.get(lvl - 1, root)

            new_item = self.sidebar_tree.AppendItem(parent_item, title)
            self.sidebar_tree.SetItemData(new_item, target_page_idx)
            parents[lvl] = new_item

        if not filter_text:
            item, cookie = self.sidebar_tree.GetFirstChild(root)
            while item.IsOk():
                self.sidebar_tree.Expand(item)
                item, cookie = self.sidebar_tree.GetNextChild(root, cookie)
        else:
            self.sidebar_tree.ExpandAll()

    def on_sidebar_search(self, evt):
        if not self.pdf: return
        self._populate_sidebar(self.sidebar_search.GetValue())

    def on_sidebar_click(self, evt):
        item = self.sidebar_tree.GetSelection()
        if item and item.IsOk():
            data = self.sidebar_tree.GetItemData(item)
            if data is not None:
                self.view.go_to_page(data)
                self._update_ui()

    def on_toggle_sidebar(self, evt):
        if self.splitter.IsSplit():
            self.splitter.Unsplit(self.sidebar)
        else:
            self.splitter.SplitVertically(self.sidebar, self.view, 250)
        self.Layout()
        self._update_ui()

    def on_toggle_pad_start(self, evt):
        val = evt.IsChecked()
        self.view.set_pad_start(val)
        self._update_ui()

    def _update_ui(self):
        has_pdf = self.pdf is not None
        is_epub = has_pdf and self.pdf.doc.is_reflowable

        mb = self.GetMenuBar()
        mb.Enable(self.id_sidebar_toggle, has_pdf)
        mb.Check(self.id_sidebar_toggle, self.splitter.IsSplit())

        mb.Enable(int(self.id_clear_history), bool(getattr(self, "recent_files", [])))

        mb.Enable(self.id_font_increase, is_epub)
        mb.Enable(self.id_font_decrease, is_epub)

        mb.Enable(wx.ID_CLOSE, has_pdf)

        mb.Check(self.id_single_page, self.view.mode == PDFView.MODE_SINGLE)
        mb.Check(self.id_two_page, self.view.mode == PDFView.MODE_TWO)

        mb.Check(self.id_pad_start, self.view.pad_start)
        mb.Enable(self.id_pad_start, has_pdf and self.view.mode == PDFView.MODE_TWO)

        mb.Check(self.id_ltr, self.view.direction == PDFView.DIR_LTR)
        mb.Check(self.id_rtl, self.view.direction == PDFView.DIR_RTL)

        for item_id in [self.id_prev, self.id_next, self.id_goto, self.id_zoom_in,
                        self.id_zoom_out, self.id_fit_width, self.id_fit_page]:
            mb.Enable(item_id, has_pdf)

        mb.Check(self.id_fit_width, self.view.zoom_mode == PDFView.ZOOM_FIT_WIDTH)
        mb.Check(self.id_fit_page, self.view.zoom_mode == PDFView.ZOOM_FIT_PAGE)

        for item_id in [
            self.id_enh_none, self.id_enh_sharpen, self.id_enh_soften, self.id_enh_soften_sharpen,
            self.id_col_none, self.id_col_invert, self.id_col_green, self.id_col_brown
        ]:
            mb.Enable(item_id, has_pdf)

        if has_pdf:
            shown = self.view._spread_pages()

            current_page_display = self.view.page + 1

            direction_str = "RTL" if self.view.direction == PDFView.DIR_RTL else "LTR"
            pad_str = " [Padded]" if self.view.pad_start else ""

            status_txt = (f"{os.path.basename(self.pdf.path)}  |  "
                          f"Page {current_page_display} of {self.pdf.page_count}  |  "
                          f"{direction_str}{pad_str}  |  "
                          f"Zoom: {int(self.view.zoom * 100)}%")
            if is_epub:
                status_txt += f" | Font Size: {self.epub_font_size}pt"
            self.SetStatusText(status_txt)
        else:
            self.SetStatusText("Welcome to wxReader - File -> Open to begin")
            if self.splitter.IsSplit():
                self.splitter.Unsplit(self.sidebar)

    # --- Actions ---

    def on_open(self, evt):
        wildcard = "Supported files (*.pdf;*.epub;*.mobi;*fb2;*cbz;*.txt)|*.pdf;*.epub;*.mobi;*fb2;*cbz;*.txt|All files (*.*)|*.*"
        with wx.FileDialog(self, "Open a file", wildcard=wildcard,
                           style=wx.FD_OPEN | wx.FD_FILE_MUST_EXIST) as dlg:
            if dlg.ShowModal() == wx.ID_OK:
                self._load_pdf(dlg.GetPath())

    def _load_pdf(self, path):
        if self.pdf: self.pdf.close()
        try:
            self.pdf = PDFDocument(path)
            self._restore_epub_font()
        except Exception as e:
            wx.MessageBox(f"Error: {e}")
            return

        self.view.set_document(self.pdf)
        self.recent_files = update_recent(self.recent_files, path, limit=12)
        self.file_history.AddFileToHistory(path)

        self._populate_sidebar()

        # auto-open sidebar if TOC exists
        if self.pdf.get_toc() and not self.splitter.IsSplit():
            self.splitter.SplitVertically(self.sidebar, self.view, 250)

        self._update_ui()
        self.view.SetFocus()

    def on_close_pdf(self, evt):
        if self.pdf: self.pdf.close()
        self.pdf = None
        self.view.set_document(None)
        self.sidebar_tree.DeleteAllItems()
        self._update_ui()

    def on_open_recent(self, evt):
        path = self.file_history.GetHistoryFile(evt.GetId() - wx.ID_FILE1)
        if path and os.path.isfile(path):
            self._load_pdf(path)
        else:
            wx.Bell()

    def on_clear_history(self, evt):
        for i in range(self.file_history.GetCount() - 1, -1, -1):
            self.file_history.RemoveFileFromHistory(i)

        self.recent_files = []

        self.file_history.AddFilesToMenu(self.m_recent)
        self._update_ui()

    def on_show_toc_dialog(self, evt):
        if not self.pdf: return
        toc = self.pdf.get_toc()
        if not toc:
            wx.MessageBox("No TOC found.")
            return
        dlg = TOCDialog(self, toc, self.view.page, lambda p: (self.view.go_to_page(p), self._update_ui()))
        dlg.ShowModal()
        dlg.Destroy()

    def on_extract_text(self, evt):
        if not self.pdf:
            return

        try:
            visible_pages = self.view._spread_pages()

            extracted_parts = []

            for page_idx in visible_pages:
                # _spread_pages might return -1 for blank padding pages (skip them)
                if page_idx < 0 or page_idx >= self.pdf.page_count:
                    continue

                page_obj = self.pdf.doc.load_page(page_idx)
                raw_text = page_obj.get_text()

                header = f"=== Page {page_idx + 1} ==="
                extracted_parts.append(f"{header}\n{raw_text}")

            full_text = "\n\n".join(extracted_parts)

            if not full_text.strip():
                full_text = "<No text found on visible pages. They might be images without OCR.>"

            # Show the dialog
            dlg = TextExtractionDialog(self, full_text, title="Extracted Page Text")
            dlg.ShowModal()
            dlg.Destroy()

        except Exception as e:
            wx.MessageBox(f"Failed to extract text: {e}", "Error")

    def on_goto_page(self, evt):
        if not self.pdf: return
        dlg = wx.TextEntryDialog(self, f"Enter page number (1-{self.pdf.page_count}):", "Go to Page")
        if dlg.ShowModal() == wx.ID_OK:
            try:
                val = int(dlg.GetValue())
                if 1 <= val <= self.pdf.page_count:
                    self.view.go_to_page(val - 1)
                    self._update_ui()
                else:
                    wx.MessageBox("Page number out of range.")
            except ValueError:
                wx.MessageBox("Invalid number.")
        dlg.Destroy()

    def on_zoom_out(self, evt):
        self.view.set_zoom_mode(PDFView.ZOOM_MANUAL)
        self.view.zoom = max(0.2, self.view.zoom / 1.2)
        self.view._refresh_layout()
        self.view.Refresh()
        self._update_ui()

    def on_zoom_in(self, evt):
        self.view.set_zoom_mode(PDFView.ZOOM_MANUAL)
        self.view.zoom = min(6.0, self.view.zoom * 1.2)
        self.view._refresh_layout()
        self.view.Refresh()
        self._update_ui()

    def _restore_epub_font(self):
        if not self.pdf or not self.pdf.doc.is_reflowable:
            return

        try:
            w_pt, h_pt = self.pdf.get_page_size(0)
            self.pdf.doc.layout(width=w_pt, height=h_pt, fontsize=self.epub_font_size)
        except Exception as e:
            print(f"Warning: Failed to restore EPUB font settings: {e}")

    def on_change_epub_font(self, evt):
        if not self.pdf or not self.pdf.doc.is_reflowable:
            return

        event_id = evt.GetId()
        if event_id == self.id_font_increase:
            self.epub_font_size += 1
        else:
            self.epub_font_size = max(8, self.epub_font_size - 1)

        w_pt, h_pt = self.pdf.get_page_size(0)
        self.pdf.doc.layout(width=w_pt, height=h_pt, fontsize=self.epub_font_size)

        current_page = self.view.page
        self.view.set_document(self.pdf)
        self.view.go_to_page(current_page)
        self._update_ui()

    def on_fit_width(self, evt):
        self.view.set_zoom_mode(PDFView.ZOOM_FIT_WIDTH)
        self._update_ui()

    def on_fit_page(self, evt):
        self.view.set_zoom_mode(PDFView.ZOOM_FIT_PAGE)
        self._update_ui()

    def on_background_color(self, evt):
        data = wx.ColourData()
        data.SetColour(self.view.GetBackgroundColour())
        with wx.ColourDialog(self, data) as dlg:
            if dlg.ShowModal() == wx.ID_OK:
                self.view.set_background_color(dlg.GetColourData().GetColour())

    def on_fullscreen(self, evt):
        is_full = self.IsFullScreen()

        self.ShowFullScreen(not is_full, style=wx.FULLSCREEN_ALL)

        self._update_ui()

    def on_about(self, event):
        info = adv.AboutDialogInfo()

        info.SetName(APP_NAME)
        info.SetVersion(APP_VERSION)
        info.SetDescription(
            f"wxPython v{wx.version()}\n"
            "PyMuPDF v1.23.8 with MuPDF v1.23.7\n"
            "Python 3.12.9"
        )

        info.AddDeveloper("Setsuna")

        wx.adv.AboutBox(info)

    def on_close(self, evt):
        if self.view:
            self.view.pdf = None
            self._bmp_cache = {}

        try:
            cfg = {
                "show_sidebar": self.splitter.IsSplit(),
                "view_mode": self.view.mode,
                "direction": self.view.direction,
                "pad_start": self.view.pad_start,
                "zoom_mode": self.view.zoom_mode,
                "epub_font_size": self.epub_font_size,
                "recent_files": self.recent_files,
                "last_file": (self.pdf.path if self.pdf else ""),
            }

            save_config(cfg)
            print("Configuration saved successfully.")

        except Exception as e:
            print(f"Save failed: {e}")

        # CLOSE THE PDF HANDLE
        if self.pdf:
            self.pdf.close()
            self.pdf = None

        evt.Skip()


class WxPDFReaderApp(wx.App):
    def OnInit(self):
        frame = MainFrame()

        app_icon = wx.Icon('icon.png', wx.BITMAP_TYPE_ANY)
        if app_icon.IsOk():
            frame.SetIcon(app_icon)
        frame.Show()

        return True


if __name__ == "__main__":
    app = WxPDFReaderApp(False)
    app.MainLoop()
