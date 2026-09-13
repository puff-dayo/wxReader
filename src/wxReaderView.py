from __future__ import annotations

import math
import queue
import threading
import webbrowser
from collections import OrderedDict

import fitz  # PyMuPDF
import numpy as np
import wx

from wxReaderIcon import get_app_font
from wxReaderProvider import ContentProvider


def _(text):
    return wx.GetTranslation(text)


MEMORY_PROFILES = {
    "potato": {
        "label": "Potato",
        "bitmap_cache_pages": 4,
        "source_image_cache_pages": 2,
        "prerender_before": 0,
        "prerender_after": 1,
        "max_pending_render_tasks": 1,
    },
    "low": {
        "label": "Low",
        "bitmap_cache_pages": 8,
        "source_image_cache_pages": 4,
        "prerender_before": 0,
        "prerender_after": 2,
        "max_pending_render_tasks": 2,
    },
    "balanced": {
        "label": "Balanced",
        "bitmap_cache_pages": 18,
        "source_image_cache_pages": 8,
        "prerender_before": 1,
        "prerender_after": 3,
        "max_pending_render_tasks": 4,
    },
    "default": {
        "label": "Default",
        "bitmap_cache_pages": 36,
        "source_image_cache_pages": 32,
        "prerender_before": 4,
        "prerender_after": 5,
        "max_pending_render_tasks": 10,
    },
    "performance": {
        "label": "Performance",
        "bitmap_cache_pages": 64,
        "source_image_cache_pages": 48,
        "prerender_before": 6,
        "prerender_after": 10,
        "max_pending_render_tasks": 16,
    },
}


class PDFView(wx.ScrolledWindow):
    MODE_SINGLE = "single"
    MODE_TWO = "two"
    MODE_FLOW = "flow"

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
        self.effects_enabled = False

        self.main_frame = None

        self.render_queue = queue.Queue()
        self.worker_thread = threading.Thread(target=self._worker_loop, daemon=True)
        self.worker_thread.start()
        self._requested_pages = set()

        self.memory_profile_name = "default"
        self.memory_profile = MEMORY_PROFILES["default"]
        self.max_bitmap_cache_pages = self.memory_profile["bitmap_cache_pages"]
        self.prerender_before = self.memory_profile["prerender_before"]
        self.prerender_after = self.memory_profile["prerender_after"]
        self.max_pending_render_tasks = self.memory_profile["max_pending_render_tasks"]

        # State
        self.content_provider: ContentProvider | None = None
        self.page = 0  # current page (0-based)
        self.zoom = 1.0
        self.zoom_mode = self.ZOOM_FIT_PAGE

        self.mode = self.MODE_TWO
        self.direction = self.DIR_LTR
        self.pad_start = False

        self.is_scroll_locked = False

        # Right-button radial menu
        self._radial_hold_ms = 32
        self._radial_deadzone = 18
        self._radial_outer_radius = 182
        self._radial_inner_radius = 45
        self._radial_cancel_margin = 256

        self._radial_timer = wx.Timer(self)
        self.Bind(wx.EVT_TIMER, self._on_radial_timer, self._radial_timer)

        self._right_down = False
        self._right_press_pos = wx.Point(0, 0)
        self._radial_visible = False
        self._radial_center = wx.Point(0, 0)
        self._radial_hover_index = -1
        self._radial_items = []

        # {(page_index, zoom_key, effect_revision): wx.Bitmap}
        self._bmp_cache: OrderedDict[tuple[int, int, int], wx.Bitmap] = OrderedDict()
        self._pre_render_timer = wx.Timer(self)
        self.Bind(wx.EVT_TIMER, self._on_pre_render_timer, self._pre_render_timer)

        # Layout
        self.margin = 2
        self.gap = 2
        self._current_bitmaps: list[tuple[int, wx.Bitmap]] = []  # [(page_index, bmp), ...]
        self._flow_page_rects: list[wx.Rect] = []
        self._flow_page_zooms = []
        self._flow_base_width_pt = 0.0

        # Panning
        self._panning = False
        self._pan_start_mouse = wx.Point(0, 0)
        self._pan_start_view = (0, 0)
        self._left_down = False
        self._left_dragged = False
        self._drag_threshold = 4
        self._pan_button = None  # "left" or "right"

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
        self.Bind(wx.EVT_LEFT_UP, self.on_left_up)
        self.Bind(wx.EVT_SCROLLWIN, self.on_scroll)
        self.Bind(wx.EVT_LEAVE_WINDOW, self.on_mouse_leave)

    def _build_radial_items(self):
        return [
            {"label": _("Nav Up"), "action": self.go_prev},
            {"label": _("Nav Down"), "action": self.go_next},
            {"label": _("Single P"), "action": lambda: self.set_mode(self.MODE_SINGLE)},
            {"label": _("Double P"), "action": lambda: self.set_mode(self.MODE_TWO)},
            {"label": _("Zoom In"), "action": self._radial_zoom_in},
            {"label": _("Zoom Out"), "action": self._radial_zoom_out},
            {"label": _("Fit Page"), "action": lambda: self.set_zoom_mode(self.ZOOM_FIT_PAGE)},
            {"label": _("Fit Width"), "action": lambda: self.set_zoom_mode(self.ZOOM_FIT_WIDTH)},
        ]

    # --------------------------
    # public api
    # --------------------------
    def set_content_provider(self, provider: ContentProvider | None):
        self._bmp_cache.clear()
        self._current_bitmaps.clear()
        self._requested_pages.clear()
        self.content_provider = provider

        if self.content_provider and hasattr(self.content_provider, "set_memory_profile"):
            self.content_provider.set_memory_profile(self.memory_profile)

        self.page = 0
        self.zoom = 1.0
        self.zoom_mode = self.ZOOM_FIT_PAGE
        self._last_cache_zoom = self.zoom
        self._refresh_layout()
        self.Refresh()

    def set_mode(self, mode: str):
        if mode not in (self.MODE_SINGLE, self.MODE_TWO, self.MODE_FLOW):
            return
        self.mode = mode
        self._refresh_layout()
        self.Refresh()

    def on_effect_chain_changed(self, refresh_layout: bool = True):
        if self.main_frame and hasattr(self.main_frame, "gl_filters"):
            filters = self.main_frame.gl_filters
            if hasattr(filters, "get_revision"):
                filters.get_revision()

        self._bmp_cache.clear()
        self._requested_pages.clear()
        self._current_bitmaps.clear()
        if refresh_layout:
            self._refresh_layout()
        self.Refresh()

    def _has_active_effects(self) -> bool:
        if not self.effects_enabled:
            return False

        if not self.main_frame or not hasattr(self.main_frame, "gl_filters"):
            return False

        chain = getattr(self.main_frame.gl_filters, "effect_chain", [])
        return any(stage.enabled for stage in chain)

    def _effect_cache_revision(self) -> int:
        if not self._has_active_effects():
            return 0

        filters = self.main_frame.gl_filters
        if hasattr(filters, "get_revision"):
            try:
                return int(filters.get_revision())
            except Exception:
                pass

        chain = getattr(filters, "effect_chain", [])
        signature = tuple(
            (stage.name, float(stage.strength), bool(stage.enabled))
            for stage in chain
        )
        return hash(signature)

    def _make_cache_key(
            self,
            page_index: int,
            zoom: float,
            effect_revision: int | None = None
    ) -> tuple[int, int, int]:
        if effect_revision is None:
            effect_revision = self._effect_cache_revision()
        return page_index, int(zoom * 10000), int(effect_revision)

    def _queue_page_render(self, page_index: int, zoom: float, provider=None) -> bool:
        provider = self.content_provider if provider is None else provider
        if provider is None:
            return False

        cache_key = self._make_cache_key(page_index, zoom)
        if cache_key in self._bmp_cache or cache_key in self._requested_pages:
            return False

        max_pending = getattr(self, "max_pending_render_tasks", 10)
        if len(self._requested_pages) >= max_pending:
            return False

        self._requested_pages.add(cache_key)
        self.render_queue.put((page_index, zoom, provider, cache_key[2]))
        return True

    @staticmethod
    def _render_page_array(provider, page_index: int, zoom: float) -> np.ndarray | None:
        if provider is None or not (0 <= page_index < provider.page_count):
            return None

        raw_result = provider.render_to_data(page_index, zoom)
        if not raw_result:
            return None

        width, height, data = raw_result
        try:
            return np.frombuffer(data, dtype=np.uint8).reshape((height, width, 3)).copy()
        except (TypeError, ValueError):
            return None

    def _shader_neighbor_arrays(
            self,
            page_index: int,
            zoom: float,
            current_arr: np.ndarray,
            provider
    ) -> tuple[np.ndarray, np.ndarray]:
        if provider is None or provider.page_count <= 0 or page_index < 0:
            return current_arr, current_arr

        last_index = provider.page_count - 1
        current_index = max(0, min(page_index, last_index))
        previous_index = max(0, current_index - 1)
        next_index = min(last_index, current_index + 1)

        if previous_index == current_index:
            previous_arr = current_arr
        else:
            previous_arr = self._render_page_array(provider, previous_index, zoom)
            if previous_arr is None:
                previous_arr = current_arr

        if next_index == current_index:
            next_arr = current_arr
        else:
            next_arr = self._render_page_array(provider, next_index, zoom)
            if next_arr is None:
                next_arr = current_arr

        return previous_arr, next_arr

    def _apply_effect_chain(
            self,
            arr: np.ndarray,
            previous_arr: np.ndarray | None = None,
            next_arr: np.ndarray | None = None
    ) -> np.ndarray:
        if not self._has_active_effects():
            return arr

        previous_arr = arr if previous_arr is None else previous_arr
        next_arr = arr if next_arr is None else next_arr

        try:
            if hasattr(self.main_frame, "apply_shader_effects"):
                out = self.main_frame.apply_shader_effects(
                    arr,
                    previous_rgb=previous_arr,
                    next_rgb=next_arr
                )
            else:
                try:
                    out = self.main_frame.gl_filters.apply_chain(
                        arr,
                        prev_rgb=previous_arr,
                        next_rgb=next_arr
                    )
                except TypeError as exc:
                    if "unexpected keyword argument" not in str(exc):
                        raise
                    out = self.main_frame.gl_filters.apply_chain(arr)

            return out if out is not None else arr
        except Exception as e:
            print(f"GL Effect Chain error: {e}")
            return arr

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

    def set_memory_profile_name(self, name: str):
        if name not in MEMORY_PROFILES:
            name = "default"
        self.set_memory_profile(name, MEMORY_PROFILES[name])

    def set_memory_profile(self, name: str, profile: dict):
        self.memory_profile_name = name
        self.memory_profile = profile

        self.max_bitmap_cache_pages = int(profile.get("bitmap_cache_pages", self.MAX_CACHE_SIZE))
        self.prerender_before = int(profile.get("prerender_before", 4))
        self.prerender_after = int(profile.get("prerender_after", 5))
        self.max_pending_render_tasks = int(profile.get("max_pending_render_tasks", 10))

        self._trim_bitmap_cache()

        if self.content_provider and hasattr(self.content_provider, "set_memory_profile"):
            self.content_provider.set_memory_profile(profile)

    def _trim_bitmap_cache(self):
        limit = getattr(self, "max_bitmap_cache_pages", self.MAX_CACHE_SIZE)
        while len(self._bmp_cache) > limit:
            self._bmp_cache.popitem(last=False)

    def go_next(self):
        if not self.content_provider:
            return
        if self.mode == self.MODE_FLOW:
            self.go_to_page(self.page + 1)
            return

        step = 1 if self.mode == self.MODE_SINGLE else 2
        self.page = min(self.page + step, self.content_provider.page_count - 1)
        self._refresh_layout()
        self.Refresh()

    def go_prev(self):
        if not self.content_provider:
            return
        if self.mode == self.MODE_FLOW:
            self.go_to_page(self.page - 1)
            return

        step = 1 if self.mode == self.MODE_SINGLE else 2
        self.page = max(self.page - step, 0)
        self._refresh_layout()
        self.Refresh()

    def go_to_page(self, page_index: int):
        if not self.content_provider:
            return

        old_page = self.page
        self.page = max(0, min(page_index, self.content_provider.page_count - 1))

        if self.mode == self.MODE_FLOW:
            if hasattr(self, '_flow_page_rects') and self.page < len(self._flow_page_rects):
                target_rect = self._flow_page_rects[self.page]
                spx, spy = self.GetScrollPixelsPerUnit()

                vx, vy = self.GetViewStart()
                scroll_y = vy * spy if spy > 0 else 0
                ch = self.GetClientSize().height

                is_visible = (target_rect.GetBottom() > scroll_y and target_rect.GetTop() < scroll_y + ch)

                if old_page != self.page or not is_visible:
                    if spy > 0:
                        self.Scroll(-1, target_rect.y // spy)

            self._update_visible_flow_pages()
        else:
            self._refresh_layout()
            self.Refresh()

    def stop_worker(self):
        if self._pre_render_timer.IsRunning():
            self._pre_render_timer.Stop()

    # --------------------------
    # Threading Logic
    # --------------------------
    def _process_image_data(
            self,
            data: bytes,
            width: int,
            height: int,
            *,
            page_index: int | None = None,
            zoom: float | None = None,
            provider=None
    ) -> bytes:
        if not self._has_active_effects():
            return data

        try:
            arr = np.frombuffer(data, dtype=np.uint8).reshape((height, width, 3)).copy()
            previous_arr = arr
            next_arr = arr

            if page_index is not None and zoom is not None:
                previous_arr, next_arr = self._shader_neighbor_arrays(
                    page_index,
                    zoom,
                    arr,
                    provider if provider is not None else self.content_provider
                )

            arr = self._apply_effect_chain(arr, previous_arr, next_arr)
            return arr.tobytes()
        except Exception as e:
            print(f"Effect chain processing error: {e}")
            return data

    def _worker_loop(self):
        while True:
            task = self.render_queue.get()
            try:
                page_idx, zoom, provider, task_revision = task
                cache_key = self._make_cache_key(page_idx, zoom, task_revision)

                if provider != self.content_provider:
                    wx.CallAfter(self._requested_pages.discard, cache_key)
                    continue

                if task_revision != self._effect_cache_revision():
                    wx.CallAfter(self._requested_pages.discard, cache_key)
                    continue

                if self.mode != self.MODE_FLOW and abs(zoom - self.zoom) > 0.01:
                    wx.CallAfter(self._requested_pages.discard, cache_key)
                    continue

                if not provider.is_valid:
                    wx.CallAfter(self._requested_pages.discard, cache_key)
                    continue

                raw_result = provider.render_to_data(page_idx, zoom)
                if not raw_result:
                    print(f"[WARN] render_to_data failed in worker: page={page_idx}, zoom={zoom:.4f}")
                    wx.CallAfter(self._requested_pages.discard, cache_key)
                    continue

                width, height, data = raw_result

                try:
                    arr = np.frombuffer(data, dtype=np.uint8).reshape((height, width, 3)).copy()
                except Exception as e:
                    print(f"Numpy conversion error: {e}")
                    wx.CallAfter(self._requested_pages.discard, cache_key)
                    continue

                previous_arr = None
                next_arr = None
                if self._has_active_effects():
                    previous_arr, next_arr = self._shader_neighbor_arrays(
                        page_idx,
                        zoom,
                        arr,
                        provider
                    )

                wx.CallAfter(
                    self._on_worker_result,
                    page_idx,
                    zoom,
                    width,
                    height,
                    arr,
                    previous_arr,
                    next_arr,
                    provider,
                    task_revision
                )

            except Exception as e:
                print(f"Worker error: {e}")
            finally:
                self.render_queue.task_done()

    def _on_worker_result(
            self,
            page_idx,
            zoom,
            width,
            height,
            arr,
            previous_arr,
            next_arr,
            task_provider,
            task_revision
    ):
        cache_key = self._make_cache_key(page_idx, zoom, task_revision)
        self._requested_pages.discard(cache_key)

        if task_provider != self.content_provider:
            return
        if task_revision != self._effect_cache_revision():
            return
        if self.mode != self.MODE_FLOW and abs(self.zoom - zoom) > 0.01:
            return

        if self._has_active_effects():
            try:
                arr = self._apply_effect_chain(arr, previous_arr, next_arr)
            except Exception as e:
                print(f"GL Filter error on main thread: {e}")

        # Do not cache a result if the chain changed during GL processing
        if task_revision != self._effect_cache_revision():
            return

        img = wx.Image(width, height, arr.tobytes())
        bmp = wx.Bitmap(img)

        self._bmp_cache[cache_key] = bmp

        if self.mode == self.MODE_FLOW:
            if any(p == page_idx for p, _ in self._current_bitmaps):
                wx.CallAfter(self._update_visible_flow_pages)
        else:
            if self._is_page_visible(page_idx):
                self.Refresh(eraseBackground=False)

    def _is_page_visible(self, page_index):
        return any(p_idx == page_index for p_idx, _ in self._current_bitmaps)

    # --------------------------
    # Internals
    # --------------------------
    def _begin_pan(self, evt: wx.MouseEvent, button: str):
        if not self.content_provider:
            return
        self._panning = True
        self._pan_button = button
        self._pan_start_mouse = evt.GetPosition()
        self._pan_start_view = self.GetViewStart()
        if not self.HasCapture():
            self.CaptureMouse()

    def _end_pan(self):
        self._panning = False
        self._pan_button = None
        if self.HasCapture():
            self.ReleaseMouse()

    def _radial_zoom_in(self):
        self.set_zoom_mode(self.ZOOM_MANUAL)
        self.zoom = min(self.MAX_ZOOM, self.zoom * 1.2)
        self._refresh_layout()
        self.Refresh()
        if self.main_frame:
            self.main_frame._update_ui()

    def _radial_zoom_out(self):
        self.set_zoom_mode(self.ZOOM_MANUAL)
        self.zoom = max(self.MIN_ZOOM, self.zoom / 1.2)
        self._refresh_layout()
        self.Refresh()
        if self.main_frame:
            self.main_frame._update_ui()

    def _ensure_cache_zoom(self):
        if abs(self.zoom - self._last_cache_zoom) > 1e-9:
            self._bmp_cache.clear()
            self._last_cache_zoom = self.zoom

    def _get_bitmap(self, page_index: int, zoom: float) -> wx.Bitmap:
        cache_key = self._make_cache_key(page_index, zoom)

        if cache_key in self._bmp_cache:
            self._bmp_cache.move_to_end(cache_key)
            return self._bmp_cache[cache_key]

        limit = getattr(self, "max_bitmap_cache_pages", self.MAX_CACHE_SIZE)
        if len(self._bmp_cache) >= limit:
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
            print(f"[WARN] render_to_data failed: page={page_index}, zoom={zoom:.4f}")
            return wx.NullBitmap

        w, h, data = res
        processed_data = self._process_image_data(
            data,
            w,
            h,
            page_index=page_index,
            zoom=zoom,
            provider=self.content_provider
        )

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
            if 0 <= left_idx < n:
                pages.append(left_idx)
            elif left_idx == -1 and self.pad_start:
                pages.append(-1)
            if 0 <= right_idx < n:
                pages.append(right_idx)
        else:
            if 0 <= right_idx < n:
                pages.append(right_idx)
            if 0 <= left_idx < n:
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
        else:
            return [self.zoom, self.zoom]

        z1 = z0 * (h0 / h1)
        return [max(self.MIN_ZOOM, z) for z in [z0, z1]]

    def _start_pre_rendering(self):
        if not self.content_provider:
            return
        self._pre_render_timer.Stop()
        self._pre_render_timer.Start(200, wx.TIMER_ONE_SHOT)

    def _on_pre_render_timer(self, evt):
        if not self.content_provider:
            return

        before = getattr(self, "prerender_before", 4)
        after = getattr(self, "prerender_after", 5)
        max_pending = getattr(self, "max_pending_render_tasks", 10)

        if len(self._requested_pages) >= max_pending:
            return

        anchor = self.page
        pages_to_check = range(anchor - before, anchor + after + 1)

        for page_index in pages_to_check:
            if len(self._requested_pages) >= max_pending:
                break

            if not (0 <= page_index < self.content_provider.page_count):
                continue

            self._queue_page_render(page_index, self.zoom, self.content_provider)

    def _refresh_layout(self):
        if not self.content_provider:
            self.SetVirtualSize((0, 0))
            return

        if self.mode == self.MODE_FLOW:
            self._refresh_layout_flow()
        else:
            self._refresh_layout_paged()

    def _refresh_layout_flow(self):
        if not self.content_provider or self.content_provider.page_count == 0:
            self.SetVirtualSize((0, 0))
            self._current_bitmaps = []
            self._flow_page_rects = []
            self._flow_page_zooms = []
            return

        num_pages = self.content_provider.page_count
        cw, ch = self.GetClientSize()
        avail_w = max(1, cw - 2 * self.margin)

        self._flow_page_rects = []
        self._flow_page_zooms = []

        widths_pt = []
        for i in range(num_pages):
            w_pt, h_pt = self.content_provider.get_page_size(i)
            if w_pt > 0 and h_pt > 0:
                widths_pt.append(w_pt)

        if not widths_pt:
            self.SetVirtualSize((0, 0))
            return

        widths_pt.sort()
        base_w_pt = widths_pt[len(widths_pt) // 2]
        self._flow_base_width_pt = base_w_pt

        if self.zoom_mode == self.ZOOM_MANUAL:
            target_w = max(1, int(round(base_w_pt * self.zoom)))
        else:
            target_w = avail_w
            self.zoom = target_w / base_w_pt

        current_y = self.margin
        max_w = 0

        for i in range(num_pages):
            w_pt, h_pt = self.content_provider.get_page_size(i)
            if w_pt <= 0 or h_pt <= 0:
                self._flow_page_zooms.append(self.zoom)
                self._flow_page_rects.append(wx.Rect(self.margin, current_y, 1, 1))
                current_y += 1 + self.gap
                continue

            zoom_i = target_w / w_pt
            zoom_i = max(self.MIN_ZOOM, min(zoom_i, self.MAX_ZOOM))

            w_px = max(1, int(round(w_pt * zoom_i)))
            h_px = max(1, int(round(h_pt * zoom_i)))

            x = self.margin
            if avail_w > w_px:
                x = self.margin + (avail_w - w_px) // 2

            self._flow_page_zooms.append(zoom_i)
            self._flow_page_rects.append(wx.Rect(x, current_y, w_px, h_px))

            current_y += h_px + self.gap
            max_w = max(max_w, w_px)

        total_w = max_w + 2 * self.margin
        total_h = current_y + self.margin
        self.SetVirtualSize((total_w, total_h))

        if not self._panning and self.page < len(self._flow_page_rects):
            target_rect = self._flow_page_rects[self.page]
            spx, spy = self.GetScrollPixelsPerUnit()
            if spy > 0:
                self.Scroll(-1, target_rect.y // spy)

        self._update_visible_flow_pages()

    def _refresh_layout_paged(self):
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
            content_h = max(heights[0], heights[1])

        total_w = content_w + 2 * self.margin
        total_h = content_h + 2 * self.margin
        self.SetVirtualSize((total_w, total_h))
        self.SetFocus()

        if not self.is_scroll_locked:
            self.Scroll(0, 0)

        if self.main_frame:
            wx.CallAfter(self.main_frame._update_ui)
        self._start_pre_rendering()

    def _update_visible_flow_pages(self):
        if not self.content_provider or not hasattr(self, '_flow_page_rects') or not self._flow_page_rects:
            return

        vx, vy = self.GetViewStart()
        spx, spy = self.GetScrollPixelsPerUnit()
        scroll_x = vx * spx
        scroll_y = vy * spy
        cw, ch = self.GetClientSize()

        view_rect = wx.Rect(scroll_x, scroll_y, cw, ch)

        visible_pages = []
        max_area = 0
        best_page = self.page

        for i, rect in enumerate(self._flow_page_rects):
            if rect.Intersects(view_rect):
                visible_pages.append(i)

                intersect = wx.Rect(view_rect)
                intersect.Intersect(rect)
                area = intersect.width * intersect.height

                if area > max_area:
                    max_area = area
                    best_page = i
            elif rect.y > view_rect.GetBottom():
                break

        self._current_bitmaps = []
        for i in visible_pages:
            zoom_i = self._flow_page_zooms[i] if i < len(self._flow_page_zooms) else self.zoom
            cache_key = self._make_cache_key(i, zoom_i)
            if cache_key in self._bmp_cache:
                self._bmp_cache.move_to_end(cache_key)
                self._current_bitmaps.append((i, self._bmp_cache[cache_key]))
            else:
                self._current_bitmaps.append((i, wx.NullBitmap))
                self._queue_page_render(i, zoom_i, self.content_provider)

        self._trim_bitmap_cache()

        if visible_pages:
            first_vis = visible_pages[0]
            last_vis = visible_pages[-1]

            for i in range(max(0, first_vis - 2), min(self.content_provider.page_count, last_vis + 3)):
                zoom_i = self._flow_page_zooms[i] if i < len(self._flow_page_zooms) else self.zoom
                self._queue_page_render(i, zoom_i, self.content_provider)

        if best_page != self.page:
            self.page = best_page
            if self.main_frame:
                wx.CallAfter(self.main_frame._update_ui)

        self.Refresh(eraseBackground=False)

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

    def _draw_flow(self, dc: wx.DC):
        if not self._current_bitmaps:
            return

        origin_x, origin_y = self.GetViewStart()
        spx, spy = self.GetScrollPixelsPerUnit()
        ox, oy = origin_x * spx, origin_y * spy

        for page_index, bmp in self._current_bitmaps:
            if page_index < len(self._flow_page_rects):
                rect = self._flow_page_rects[page_index]
                if bmp and bmp.IsOk():
                    dc.DrawBitmap(bmp, rect.x - ox, rect.y - oy, True)
                else:
                    dc.SetBrush(wx.Brush(wx.WHITE))
                    dc.SetPen(wx.Pen(wx.Colour(200, 200, 200)))
                    dc.DrawRectangle(rect.x - ox, rect.y - oy, rect.width, rect.height)

    @staticmethod
    def _make_radial_sector_path(gc, cx, cy, inner_r, outer_r, a0_deg, a1_deg):
        a0 = math.radians(-a0_deg)
        a1 = math.radians(-a1_deg)

        path = gc.CreatePath()

        x0o = cx + math.cos(a0) * outer_r
        y0o = cy + math.sin(a0) * outer_r
        x1o = cx + math.cos(a1) * outer_r
        y1o = cy + math.sin(a1) * outer_r

        x1i = cx + math.cos(a1) * inner_r
        y1i = cy + math.sin(a1) * inner_r
        x0i = cx + math.cos(a0) * inner_r
        y0i = cy + math.sin(a0) * inner_r

        path.MoveToPoint(x0o, y0o)
        path.AddArc(cx, cy, outer_r, a0, a1, False)
        path.AddLineToPoint(x1i, y1i)
        path.AddArc(cx, cy, inner_r, a1, a0, True)
        path.CloseSubpath()

        return path

    def _draw_radial_menu(self, gc: wx.GraphicsContext):
        cx = float(self._radial_center.x)
        cy = float(self._radial_center.y)

        items = self._radial_items
        count = len(items)
        if count == 0:
            return

        outer_r = float(self._radial_outer_radius)
        inner_r = float(self._radial_inner_radius)
        text_r = (outer_r + inner_r) / 2.0

        font = get_app_font(2)
        gc.SetFont(font, wx.Colour(245, 245, 245))

        gc.SetPen(wx.Pen(wx.Colour(0, 0, 0, 0), 0))
        gc.SetBrush(wx.Brush(wx.Colour(0, 0, 0, 60)))
        gc.DrawEllipse(cx - outer_r - 4, cy - outer_r + 5, outer_r * 2, outer_r * 2)

        sector_size = 360.0 / count
        start_offset = -sector_size / 2.0

        for i, item in enumerate(items):
            a0 = start_offset + i * sector_size
            a1 = a0 + sector_size

            path = self._make_radial_sector_path(gc, cx, cy, inner_r, outer_r, a0, a1)

            hovered = (i == self._radial_hover_index)

            if hovered:
                pen = wx.Pen(wx.Colour(255, 210, 110, 235), 2)
                brush = wx.Brush(wx.Colour(255, 210, 110, 125))
            else:
                pen = wx.Pen(wx.Colour(235, 235, 235, 60), 1)
                brush = wx.Brush(wx.Colour(52, 56, 64, 220))

            gc.SetPen(pen)
            gc.SetBrush(brush)
            gc.FillPath(path)
            gc.StrokePath(path)

        gc.SetPen(wx.Pen(wx.Colour(255, 255, 255, 40), 1))
        gc.SetBrush(wx.Brush(wx.Colour(28, 30, 36, 235)))
        gc.DrawEllipse(cx - inner_r, cy - inner_r, inner_r * 2, inner_r * 2)

        center_label = _("Cancel")
        tw, th = gc.GetTextExtent(center_label)
        gc.SetFont(font, wx.Colour(230, 230, 230))
        gc.DrawText(center_label, cx - tw / 2, cy - th / 2)

        gc.SetPen(wx.Pen(wx.Colour(255, 255, 255, 35), 1))
        for i in range(count):
            angle_deg = start_offset + i * sector_size
            rad = math.radians(angle_deg)
            x0 = cx + math.cos(rad) * inner_r
            y0 = cy - math.sin(rad) * inner_r
            x1 = cx + math.cos(rad) * outer_r
            y1 = cy - math.sin(rad) * outer_r
            gc.StrokeLine(x0, y0, x1, y1)

        for i, item in enumerate(items):
            mid_deg = start_offset + (i + 0.5) * sector_size
            rad = math.radians(mid_deg)

            tx = cx + math.cos(rad) * text_r
            ty = cy - math.sin(rad) * text_r

            label = item["label"]

            if i == self._radial_hover_index:
                gc.SetFont(font, wx.Colour(255, 248, 220))
            else:
                gc.SetFont(font, wx.Colour(245, 245, 245))

            tw, th = gc.GetTextExtent(label)
            gc.DrawText(label, tx - tw / 2, ty - th / 2)

    def _update_radial_hover(self, pos: wx.Point):
        dx = pos.x - self._radial_center.x
        dy = pos.y - self._radial_center.y
        dist = math.hypot(dx, dy)

        if dist < self._radial_inner_radius:
            self._radial_hover_index = -1
            return

        if dist > self._radial_outer_radius + self._radial_cancel_margin:
            self._radial_hover_index = -1
            return

        angle = math.degrees(math.atan2(-dy, dx)) % 360.0

        sector_count = len(self._radial_items)
        sector_size = 360.0 / sector_count

        angle = (angle + sector_size / 2.0) % 360.0
        self._radial_hover_index = int(angle // sector_size)

    # --------------------------
    # Event handlers
    # --------------------------
    def on_paint(self, evt):
        dc = wx.AutoBufferedPaintDC(self)
        dc.SetBackground(wx.Brush(self.bgColor))
        dc.Clear()

        if self.content_provider and self.content_provider.is_valid:
            try:
                if self.mode == self.MODE_FLOW:
                    self._draw_flow(dc)
                else:
                    self._draw_centered(dc)
            except Exception as e:
                print(f"Paint error: {e}")

        if self._radial_visible:
            gc = wx.GraphicsContext.Create(dc)
            if gc:
                self._draw_radial_menu(gc)

    def on_scroll(self, evt):
        evt.Skip()
        if self.mode == self.MODE_FLOW:
            wx.CallAfter(self._update_visible_flow_pages)

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

            self._bmp_cache.clear()
            self._requested_pages.clear()

            self.Freeze()
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

            if self.mode == self.MODE_FLOW:
                self._update_visible_flow_pages()
            self.Thaw()
            self.Refresh()

            if self.main_frame:
                self.main_frame._update_ui()
        else:
            evt.Skip()
            if self.mode == self.MODE_FLOW:
                wx.CallAfter(self._update_visible_flow_pages)

    def on_right_down(self, evt: wx.MouseEvent):
        if not self.content_provider:
            evt.Skip()
            return

        self._right_down = True
        self._radial_visible = False
        self._radial_hover_index = -1
        self._right_press_pos = evt.GetPosition()
        self._radial_center = evt.GetPosition()
        self._radial_items = self._build_radial_items()

        self._radial_timer.Stop()
        self._radial_timer.Start(self._radial_hold_ms, wx.TIMER_ONE_SHOT)

        if not self.HasCapture():
            self.CaptureMouse()

    def _on_radial_timer(self, evt):
        if not self._right_down:
            return

        self._radial_visible = True
        self._radial_center = wx.Point(self._right_press_pos.x, self._right_press_pos.y)
        self._radial_hover_index = -1
        self.Refresh(False)

    def on_right_up(self, evt: wx.MouseEvent):
        trigger_index = self._radial_hover_index if self._radial_visible else -1

        self._radial_timer.Stop()
        self._right_down = False

        if self.HasCapture():
            self.ReleaseMouse()

        was_visible = self._radial_visible
        self._radial_visible = False
        self._radial_hover_index = -1
        self.Refresh(False)

        if was_visible and 0 <= trigger_index < len(self._radial_items):
            action = self._radial_items[trigger_index].get("action")
            if callable(action):
                action()

    def on_mouse_leave(self, evt):
        if self._radial_visible:
            self._radial_hover_index = -1
            self.Refresh(False)
        evt.Skip()

    def on_mouse_move(self, evt: wx.MouseEvent):
        if self._right_down and self._radial_visible:
            self._update_radial_hover(evt.GetPosition())
            self.Refresh(False)
            return

        if not (self._panning and evt.Dragging()):
            evt.Skip()
            return

        if self._pan_button == "left" and not evt.LeftIsDown():
            self._end_pan()
            return
        if self._pan_button == "right" and not evt.RightIsDown():
            self._end_pan()
            return

        spx, spy = self.GetScrollPixelsPerUnit()
        if spx == 0 or spy == 0:
            return

        dx = evt.GetPosition().x - self._pan_start_mouse.x
        dy = evt.GetPosition().y - self._pan_start_mouse.y

        if self._pan_button == "left":
            if abs(dx) >= self._drag_threshold or abs(dy) >= self._drag_threshold:
                self._left_dragged = True

        start_x, start_y = self._pan_start_view
        self.Scroll(max(0, start_x - int(dx / spx)), max(0, start_y - int(dy / spy)))

        if self.mode == self.MODE_FLOW:
            self._update_visible_flow_pages()
        else:
            self.Refresh(False)

    def on_char_hook(self, evt: wx.KeyEvent):
        if not self.content_provider:
            evt.Skip()
            return

        key = evt.GetKeyCode()

        if key == wx.WXK_HOME:
            self.go_to_page(0)
            if self.main_frame:
                self.main_frame._update_ui()
            return

        if key == wx.WXK_END:
            self.go_to_page(self.content_provider.page_count - 1)
            if self.main_frame:
                self.main_frame._update_ui()
            return

        if self.mode == self.MODE_FLOW:
            if key in (wx.WXK_UP, wx.WXK_DOWN, wx.WXK_PAGEUP, wx.WXK_PAGEDOWN, wx.WXK_SPACE, wx.WXK_LEFT, wx.WXK_RIGHT):
                evt.Skip()
                wx.CallAfter(self._update_visible_flow_pages)
                return

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

        self._left_down = True
        self._left_dragged = False
        self._begin_pan(evt, "left")

    def on_left_up(self, evt: wx.MouseEvent):
        was_dragged = self._left_dragged
        self._left_down = False

        if self._pan_button == "left":
            self._end_pan()

        if was_dragged:
            return

        if not self.content_provider:
            evt.Skip()
            return

        click_pos = self.CalcUnscrolledPosition(evt.GetPosition())

        if self.mode == self.MODE_FLOW:
            if not hasattr(self, '_flow_page_rects'):
                evt.Skip()
                return

            for page_index, bmp in self._current_bitmaps:
                if page_index < len(self._flow_page_rects):
                    page_rect = self._flow_page_rects[page_index]
                    if page_rect.Contains(click_pos) and page_index >= 0:
                        links = self.content_provider.get_links(page_index)
                        for link in links:
                            link_rect_pdf = link['from']
                            zoom_i = self._flow_page_zooms[page_index] if page_index < len(
                                self._flow_page_zooms) else self.zoom
                            link_wx_rect = wx.Rect(
                                round(page_rect.x + link_rect_pdf.x0 * zoom_i),
                                round(page_rect.y + link_rect_pdf.y0 * zoom_i),
                                round(link_rect_pdf.width * zoom_i),
                                round(link_rect_pdf.height * zoom_i)
                            )
                            if link_wx_rect.Contains(click_pos):
                                self.handle_link_click(link)
                                return
            evt.Skip()
            return

        cw, ch = self.GetClientSize()
        widths = [bmp.GetWidth() for _, bmp in self._current_bitmaps if bmp.IsOk()]
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
            if not bmp.IsOk(): continue
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
                        return
            current_x += bmp.GetWidth() + self.gap
        evt.Skip()

    def on_size(self, evt):
        self._refresh_layout()
        self.Refresh(eraseBackground=True)
        evt.Skip()
