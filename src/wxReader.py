from __future__ import annotations

import functools
import io
import os

import wx
from wx import adv

from wxReaderConfigUtil import load_config, save_config, update_recent
from wxReaderDialog import TOCDialog, TextExtractionDialog, SearchDialog, ImageExtractionDialog, SetMarginGapDialog, \
    ModernColorDialog
from wxReaderGlUtil import GLFilterTool
from wxReaderLibrary import LibraryFrame
from wxReaderManual import ManualDialog
from wxReaderProvider import ContentProvider, PdfContentProvider, ArchiveContentProvider
from wxReaderView import PDFView

APP_NAME = "wxReader"
APP_VERSION = "1.3"
SUPPORTED_EXTENSIONS = {".pdf", ".epub", ".mobi", ".fb2", ".txt", ".zip", ".cbz"}
SUPPORTED_EXTENSIONS_STRING = ";".join("*" + ext for ext in SUPPORTED_EXTENSIONS)
SUPPORTED_WILDCARDS = f"Supported files ({SUPPORTED_EXTENSIONS_STRING})|{SUPPORTED_EXTENSIONS_STRING}|All files (*.*)|*.*"


class FileDropTarget(wx.FileDropTarget):
    def __init__(self, frame):
        super().__init__()
        self.frame = frame

    def _accept(self, filenames):
        if not filenames:
            return False
        path = filenames[0]
        ext = os.path.splitext(path)[1].lower()
        return os.path.isfile(path) and ext in SUPPORTED_EXTENSIONS

    def OnEnter(self, x, y, d):
        return wx.DragCopy

    def OnDragOver(self, x, y, d):
        return wx.DragCopy if self._accept(getattr(self, "_last_filenames", [""])) else wx.DragNone

    def OnDropFiles(self, x, y, filenames):
        if not self._accept(filenames):
            wx.Bell()
            return False
        wx.CallAfter(self.frame._load_file, filenames[0])
        return True


def get_icon(art_id):
    return wx.ArtProvider.GetBitmapBundle(art_id, wx.ART_BUTTON, wx.Size(16, 16))


def get_icon_v2(art_id):
    return wx.ArtProvider.GetBitmapBundle(art_id, wx.ART_OTHER, wx.Size(16, 16))


class MainFrame(wx.Frame):
    def __init__(self):
        super().__init__(None, title=APP_NAME, size=(1280, 800))
        self.SetMinSize((600, 400))

        # Initialize state
        self.content_provider: ContentProvider | None = None
        self.file_history = wx.FileHistory(12)
        self.quality_preference = 1

        self.epub_font_size = 12

        # --- Layout ---
        self.splitter = wx.SplitterWindow(self, style=wx.SP_LIVE_UPDATE | wx.SP_3D)
        self.splitter.SetMinimumPaneSize(50)

        # 1. Sidebar
        self.sidebar = wx.Panel(self.splitter)
        self.sidebar_main_sizer = wx.BoxSizer(wx.VERTICAL)

        self.sidebar_nb = wx.Notebook(self.sidebar)

        # Tab 1: TOC (Outline)
        self.toc_panel = wx.Panel(self.sidebar_nb)
        toc_sizer = wx.BoxSizer(wx.VERTICAL)

        self.sidebar_search = wx.SearchCtrl(self.toc_panel, style=wx.TE_PROCESS_ENTER)
        self.sidebar_search.SetDescriptiveText("Search Outline")

        self.sidebar_tree = wx.TreeCtrl(self.toc_panel, style=wx.TR_DEFAULT_STYLE | wx.TR_HIDE_ROOT |
                                                              wx.TR_FULL_ROW_HIGHLIGHT | wx.TR_NO_LINES | wx.TR_TWIST_BUTTONS)
        self.sidebar_tree.SetBackgroundColour(wx.Colour(245, 245, 245))

        toc_sizer.Add(self.sidebar_search, 0, wx.EXPAND | wx.ALL, 5)
        toc_sizer.Add(self.sidebar_tree, 1, wx.EXPAND | wx.LEFT | wx.RIGHT | wx.BOTTOM, 0)
        self.toc_panel.SetSizer(toc_sizer)

        self.sidebar_nb.AddPage(self.toc_panel, "Outline")

        # Tab 2: File Browser
        self.files_panel = wx.Panel(self.sidebar_nb)
        files_sizer = wx.BoxSizer(wx.VERTICAL)

        # Buttons
        btn_sizer = wx.GridSizer(1, 3, 0, 5)

        self.btn_go_up = wx.Button(self.files_panel, label="Dir Up")
        self.btn_go_up.SetBitmap(get_icon(wx.ART_GO_UP))

        self.btn_sync_file = wx.Button(self.files_panel, label="Locate")
        self.btn_sync_file.SetBitmap(get_icon(wx.ART_HELP_PAGE))

        self.btn_open_library = wx.Button(self.files_panel, label="Gallery")
        self.btn_open_library.SetBitmap(get_icon_v2(wx.ART_FIND))

        for btn in [self.btn_go_up, self.btn_sync_file, self.btn_open_library]:
            btn.SetBitmapMargins((4, 2))

        btn_sizer.Add(self.btn_go_up, 0, wx.EXPAND)
        btn_sizer.Add(self.btn_sync_file, 0, wx.EXPAND)
        btn_sizer.Add(self.btn_open_library, 0, wx.EXPAND)

        files_sizer.Add(btn_sizer, 0, wx.EXPAND | wx.ALL, 5)

        # Directory
        self.dir_ctrl = wx.GenericDirCtrl(self.files_panel, dir=os.getcwd(), filter=SUPPORTED_WILDCARDS,
                                          style=wx.DIRCTRL_SHOW_FILTERS | wx.DIRCTRL_3D_INTERNAL)

        files_sizer.Add(self.dir_ctrl, 1, wx.EXPAND | wx.LEFT | wx.RIGHT | wx.BOTTOM, 0)
        self.files_panel.SetSizer(files_sizer)

        self.sidebar_nb.AddPage(self.files_panel, "File Browser")

        self.sidebar_main_sizer.Add(self.sidebar_nb, 1, wx.EXPAND)
        self.sidebar.SetSizer(self.sidebar_main_sizer)

        # 2. Main Content
        self.view = PDFView(self.splitter)
        self.view.main_frame = self

        self.splitter.SplitVertically(self.sidebar, self.view, 250)
        self.splitter.SetSashGravity(0.0)
        self.splitter.Unsplit(self.sidebar)

        self.CreateStatusBar(1)

        filters_dir = os.path.join(os.path.dirname(__file__), "filters")
        self.gl_filters = GLFilterTool(self, filters_dir)
        self.gl_filters.load_filters()
        root = wx.BoxSizer(wx.VERTICAL)
        root.Add(self.splitter, 1, wx.EXPAND)
        root.Add(self.gl_filters.canvas, 0)
        self.SetSizer(root)
        self.Layout()

        self._build_menus()

        self.recent_files = []

        cfg = load_config()

        self.file_progress = cfg.get("file_progress", {})

        try:
            win_rect = cfg.get("window_rect")
            if win_rect and len(win_rect) == 4:
                x, y, w, h = win_rect
                display_rect = wx.Display(wx.Display.GetFromPoint((x, y))).GetGeometry()

                if display_rect.Contains((x, y)):
                    self.SetSize(wx.Rect(x, y, w, h))
                else:
                    self.Center()

            if cfg.get("window_maximized", False):
                self.Maximize()

            if cfg.get("window_fullscreen", False):
                self.ShowFullScreen(True)
                self.GetMenuBar().Check(self.id_fullscreen, True)
        except Exception as e:
            print(f"[ERROR] wxReader Failed to restore window state: {e}")

        try:
            show_sidebar = bool(cfg.get("show_sidebar", False))
            if show_sidebar and not self.splitter.IsSplit():
                self.splitter.SplitVertically(self.sidebar, self.view, 250)
        except Exception as e:
            print(f"[ERROR] wxReader Failed to restore sidebar state: {e}")

        try:
            self.view.set_mode(cfg.get("view_mode", PDFView.MODE_TWO))
            self.view.set_direction(cfg.get("direction", PDFView.DIR_LTR))
            self.view.set_pad_start(bool(cfg.get("pad_start", False)))
            self.view.set_zoom_mode(cfg.get("zoom_mode", PDFView.ZOOM_FIT_PAGE))
        except Exception as e:
            print(f"[ERROR] wxReader Failed to restore view mode: {e}")

        self.view.set_background_color(wx.Colour(134, 180, 118))

        self.epub_font_size = int(cfg.get("epub_font_size", self.epub_font_size))

        self.recent_files = cfg.get("recent_files", []) or []
        last = cfg.get("last_file", "")

        for p in reversed(self.recent_files):
            if p and os.path.isfile(p):
                self.file_history.AddFileToHistory(p)

        if last and os.path.isfile(last):
            wx.CallAfter(self._load_file, last)

        # --- Events ---
        self.Bind(wx.EVT_CLOSE, self.on_close)
        self.sidebar_tree.Bind(wx.EVT_TREE_ITEM_ACTIVATED, self.on_sidebar_click)
        self.sidebar_search.Bind(wx.EVT_TEXT, self.on_sidebar_search)
        self.Bind(wx.EVT_BUTTON, self.on_nav_go_up, self.btn_go_up)
        self.Bind(wx.EVT_BUTTON, self.on_nav_current, self.btn_sync_file)
        self.Bind(wx.EVT_BUTTON, self.on_open_library, self.btn_open_library)
        self.Bind(wx.EVT_DIRCTRL_FILEACTIVATED, self.on_file_browser_activated, self.dir_ctrl)
        self.Bind(wx.EVT_MENU, self.on_switch_sidebar_tab, id=self.id_switch_tab)

        self.SetDropTarget(FileDropTarget(self))

        self._update_ui()
        self.Raise()

    def _build_menus(self):
        menubar = wx.MenuBar()

        def _add_item(menu, id, label, art_id=None, help_text=""):
            item = wx.MenuItem(menu, id, label, help_text)

            if art_id:
                bmp = wx.ArtProvider.GetBitmapBundle(art_id, wx.ART_MENU, wx.Size(16, 16))
                item.SetBitmap(bmp)

            menu.Append(item)
            return item

        # --- File ---
        m_file = wx.Menu()

        m_open = _add_item(m_file, wx.ID_OPEN, "&Open...\tCtrl+O", wx.ART_FILE_OPEN)

        m_close = _add_item(m_file, wx.ID_CLOSE, "&Close\tCtrl+W")

        m_file.AppendSeparator()

        self.id_library = wx.NewIdRef()
        _add_item(m_file, self.id_library, "&Gallery Mode")

        m_file.AppendSeparator()

        self.m_recent = wx.Menu()
        m_file.AppendSubMenu(self.m_recent, "Open &Recent")

        self.id_clear_history = wx.NewIdRef()
        _add_item(m_file, self.id_clear_history, "Clear Recent Files")

        m_file.AppendSeparator()

        m_exit = _add_item(m_file, wx.ID_EXIT, "E&xit", wx.ART_QUIT)

        menubar.Append(m_file, "&File")

        # --- View ---
        m_view = wx.Menu()

        self.id_sidebar_toggle = wx.NewIdRef()
        item = wx.MenuItem(m_view, self.id_sidebar_toggle, "Show &Sidebar\tF9", kind=wx.ITEM_CHECK)
        m_view.Append(item)

        self.id_switch_tab = wx.NewIdRef()
        _add_item(m_view, self.id_switch_tab, "Switch Sidebar Tab\tF8")

        m_view.AppendSeparator()

        self.id_single_page = wx.NewIdRef()
        self.id_two_page = wx.NewIdRef()
        m_view.AppendRadioItem(self.id_single_page, "Single Page View\tCtrl+1")
        m_view.AppendRadioItem(self.id_two_page, "Two Page View\tCtrl+2")
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

        self.id_zoom_in = wx.NewIdRef()
        self.id_zoom_out = wx.NewIdRef()
        self.id_fit_width = wx.NewIdRef()
        self.id_fit_page = wx.NewIdRef()

        _add_item(m_view, self.id_zoom_in, "Zoom &In\tCtrl++")
        _add_item(m_view, self.id_zoom_out, "Zoom &Out\tCtrl+-")
        m_view.AppendSeparator()

        m_view.AppendRadioItem(self.id_fit_width, "Fit &Width\tCtrl+3")
        m_view.AppendRadioItem(self.id_fit_page, "Fit &Page\tCtrl+4")
        m_view.AppendSeparator()

        m_quality = wx.Menu()

        self.id_quality_hq = wx.NewIdRef()
        self.id_quality_mq = wx.NewIdRef()
        self.id_quality_lq = wx.NewIdRef()
        item_hq = m_quality.AppendRadioItem(self.id_quality_hq, "Box+DeMoiré")
        item_mq = m_quality.AppendRadioItem(self.id_quality_mq, "Lanczos")
        item_lq = m_quality.AppendRadioItem(self.id_quality_lq, "Bilinear")

        item_lq.Check(True)

        m_view.AppendSubMenu(m_quality, "Render Quality")
        m_view.AppendSeparator()

        self.id_setmg = wx.NewIdRef()
        _add_item(m_view, self.id_setmg, "Set Margin and Gap")

        m_view.AppendSeparator()
        self.id_bg = wx.NewIdRef()
        _add_item(m_view, self.id_bg, "Background Color…")

        m_view.AppendSeparator()
        self.id_font_increase = wx.NewIdRef()
        self.id_font_decrease = wx.NewIdRef()
        _add_item(m_view, self.id_font_increase, "Larger Font\tCtrl+Shift++")
        _add_item(m_view, self.id_font_decrease, "Smaller Font\tCtrl+Shift+-")

        m_view.AppendSeparator()
        self.id_fullscreen = wx.NewIdRef()
        m_view.AppendCheckItem(self.id_fullscreen, "Full &Screen\tF11")

        menubar.Append(m_view, "&View")

        # --- Navigate ---
        m_nav = wx.Menu()

        self.id_prev = wx.NewIdRef()
        self.id_next = wx.NewIdRef()
        self.id_goto = wx.NewIdRef()

        _add_item(m_nav, self.id_prev, "Previous Page\tLeft", wx.ART_GO_BACK)
        _add_item(m_nav, self.id_next, "Next Page\tRight", wx.ART_GO_FORWARD)
        _add_item(m_nav, self.id_goto, "&Go to Page...\tCtrl+G")

        m_nav.AppendSeparator()

        self.id_search = wx.NewIdRef()
        _add_item(m_nav, self.id_search, "&Find...\tCtrl+F", wx.ART_FIND)

        self.id_show_toc_dialog = wx.NewIdRef()
        _add_item(m_nav, self.id_show_toc_dialog, "Show TOC Dialog...\tCtrl+T")

        menubar.Append(m_nav, "&Navigate")

        # --- Process ---
        m_process = wx.Menu()

        self.id_extract_text = wx.NewIdRef()
        _add_item(m_process, self.id_extract_text, "Extract Page Text\tCtrl+E")

        self.id_extract_images = wx.NewIdRef()
        _add_item(m_process, self.id_extract_images, "Extract Page Images\tCtrl+I")

        m_process.AppendSeparator()

        self.id_custom_none = wx.NewIdRef()
        m_process.AppendCheckItem(self.id_custom_none, "None / Turn Off")
        self.Bind(wx.EVT_MENU, lambda e: self._select_custom_filter(None), id=self.id_custom_none)

        self.filter_menu_map = {}

        def _populate_custom_filters_menu():
            filters_dir = os.path.join(os.path.dirname(__file__), "filters")
            print(f"[INFO] Loading filters from: {filters_dir}")
            if not os.path.exists(filters_dir):
                print("[ERROR] The filters folder was not found.")
                return

            loaded_filters = set(self.gl_filters.filters.keys())

            try:
                entries = sorted(os.listdir(filters_dir))
            except OSError:
                entries = []

            for entry in entries:
                print(f"[INFO] Loading filters from list: {entry}")
                full_path = os.path.join(filters_dir, entry)

                if os.path.isdir(full_path):
                    submenu = wx.Menu()
                    has_items = False

                    sub_files = sorted(os.listdir(full_path))
                    for f in sub_files:
                        name, ext = os.path.splitext(f)
                        if name in loaded_filters:
                            mid = wx.NewIdRef()
                            submenu.AppendCheckItem(mid, name)
                            self.Bind(wx.EVT_MENU, functools.partial(self._on_custom_filter_menu, name=name), id=mid)

                            self.filter_menu_map[name] = mid
                            has_items = True

                    if has_items:
                        m_process.AppendSubMenu(submenu, entry)

            self.GetMenuBar().Check(self.id_custom_none, True)

        self._populate_custom_filters_menu = _populate_custom_filters_menu

        menubar.Append(m_process, "&Process")

        # --- Help ---
        m_help = wx.Menu()
        m_about = _add_item(m_help, wx.ID_ABOUT, "&About", wx.ART_INFORMATION)
        menubar.Append(m_help, "&Info")

        m_help.AppendSeparator()

        self.id_manual = wx.NewIdRef()
        _add_item(m_help, self.id_manual, "&Help Topics\tF1")

        self.SetMenuBar(menubar)
        self.file_history.UseMenu(self.m_recent)
        self.file_history.AddFilesToMenu(self.m_recent)

        self._populate_custom_filters_menu()

        # --- Bindings ---
        self.Bind(wx.EVT_MENU, self.on_open, m_open)
        self.Bind(wx.EVT_MENU, self.on_open_library, id=self.id_library)
        self.Bind(wx.EVT_MENU, self.on_close_pdf, m_close)
        self.Bind(wx.EVT_MENU_RANGE, self.on_open_recent, id=wx.ID_FILE1, id2=wx.ID_FILE9)
        self.Bind(wx.EVT_MENU, self.on_clear_history, id=self.id_clear_history)
        self.Bind(wx.EVT_MENU, lambda e: self.Close(), m_exit)

        # View
        self.Bind(wx.EVT_MENU, self.on_toggle_sidebar, id=self.id_sidebar_toggle)
        self.Bind(wx.EVT_MENU, self.on_switch_sidebar_tab, id=self.id_switch_tab)
        self.Bind(wx.EVT_MENU, lambda e: (self.view.set_mode(PDFView.MODE_SINGLE), self._update_ui()),
                  id=self.id_single_page)
        self.Bind(wx.EVT_MENU, lambda e: (self.view.set_mode(PDFView.MODE_TWO), self._update_ui()), id=self.id_two_page)
        self.Bind(wx.EVT_MENU, self.on_toggle_pad_start, id=self.id_pad_start)
        self.Bind(wx.EVT_MENU, lambda e: (self.view.set_direction(PDFView.DIR_LTR), self._update_ui()), id=self.id_ltr)
        self.Bind(wx.EVT_MENU, lambda e: (self.view.set_direction(PDFView.DIR_RTL), self._update_ui()), id=self.id_rtl)
        self.Bind(wx.EVT_MENU, self.on_zoom_in, id=self.id_zoom_in)
        self.Bind(wx.EVT_MENU, self.on_zoom_out, id=self.id_zoom_out)
        self.Bind(wx.EVT_MENU, self.on_fit_width, id=self.id_fit_width)
        self.Bind(wx.EVT_MENU, self.on_fit_page, id=self.id_fit_page)
        self.Bind(wx.EVT_MENU, self.on_setmg, id=self.id_setmg)
        self.Bind(wx.EVT_MENU, self.on_background_color, id=int(self.id_bg))
        self.Bind(wx.EVT_MENU, self.on_change_epub_font, id=self.id_font_increase)
        self.Bind(wx.EVT_MENU, self.on_change_epub_font, id=self.id_font_decrease)
        self.Bind(wx.EVT_MENU, self.on_fullscreen, id=self.id_fullscreen)
        self.Bind(wx.EVT_MENU, self.on_quality_change, id=self.id_quality_hq)
        self.Bind(wx.EVT_MENU, self.on_quality_change, id=self.id_quality_mq)
        self.Bind(wx.EVT_MENU, self.on_quality_change, id=self.id_quality_lq)

        # Navigate
        self.Bind(wx.EVT_MENU, lambda e: self.view.go_prev(), id=self.id_prev)
        self.Bind(wx.EVT_MENU, lambda e: self.view.go_next(), id=self.id_next)
        self.Bind(wx.EVT_MENU, self.on_goto_page, id=self.id_goto)
        self.Bind(wx.EVT_MENU, self.on_show_search, id=self.id_search)
        self.Bind(wx.EVT_MENU, self.on_show_toc_dialog, id=self.id_show_toc_dialog)

        # Process
        self.Bind(wx.EVT_MENU, self.on_extract_text, id=self.id_extract_text)
        self.Bind(wx.EVT_MENU, self.on_extract_images, id=self.id_extract_images)

        self.Bind(wx.EVT_MENU, self.on_about, m_about)
        self.Bind(wx.EVT_MENU, self.on_manual, id=self.id_manual)

    def _populate_sidebar(self, filter_text=None):
        if not self.content_provider:
            return
        toc = self.content_provider.get_toc()
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
        if not self.content_provider:
            return
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
        has_provider = self.content_provider is not None
        is_reflowable = has_provider and self.content_provider.is_reflowable

        mb = self.GetMenuBar()
        mb.Enable(self.id_sidebar_toggle, has_provider)
        mb.Check(self.id_sidebar_toggle, self.splitter.IsSplit())

        mb.Enable(int(self.id_clear_history), bool(getattr(self, "recent_files", [])))

        mb.Enable(self.id_font_increase, is_reflowable)
        mb.Enable(self.id_font_decrease, is_reflowable)

        mb.Enable(wx.ID_CLOSE, has_provider)

        mb.Check(self.id_single_page, self.view.mode == PDFView.MODE_SINGLE)
        mb.Check(self.id_two_page, self.view.mode == PDFView.MODE_TWO)

        mb.Check(self.id_pad_start, self.view.pad_start)
        mb.Enable(self.id_pad_start, has_provider and self.view.mode == PDFView.MODE_TWO)

        mb.Check(self.id_ltr, self.view.direction == PDFView.DIR_LTR)
        mb.Check(self.id_rtl, self.view.direction == PDFView.DIR_RTL)

        for item_id in [self.id_prev, self.id_next, self.id_goto, self.id_zoom_in,
                        self.id_zoom_out, self.id_fit_width, self.id_fit_page]:
            mb.Enable(item_id, has_provider)

        mb.Check(self.id_fit_width, self.view.zoom_mode == PDFView.ZOOM_FIT_WIDTH)
        mb.Check(self.id_fit_page, self.view.zoom_mode == PDFView.ZOOM_FIT_PAGE)

        if has_provider:
            shown = self.view._spread_pages()

            current_page_display = self.view.page + 1

            direction_str = "RTL" if self.view.direction == PDFView.DIR_RTL else "LTR"
            pad_str = " [Padded]" if self.view.pad_start else ""

            status_txt = (f"{os.path.basename(self.content_provider.path)}  |  "
                          f"Page {current_page_display} of {self.content_provider.page_count}  |  "
                          f"{direction_str}{pad_str}  |  "
                          f"Zoom: {int(self.view.zoom * 100)}%")
            if is_reflowable:
                status_txt += f" | Font Size: {self.epub_font_size}pt"
            self.SetStatusText(status_txt)
        else:
            self.SetStatusText("Welcome to wxReader - File -> Open to begin")
            if self.splitter.IsSplit():
                self.splitter.Unsplit(self.sidebar)

    # --- Actions ---

    def on_open(self, evt):
        with wx.FileDialog(self, "Open a file", wildcard=SUPPORTED_WILDCARDS,
                           style=wx.FD_OPEN | wx.FD_FILE_MUST_EXIST) as dlg:
            if dlg.ShowModal() == wx.ID_OK:
                self._load_file(dlg.GetPath())

    def _load_file(self, path):
        if self.content_provider:
            self.file_progress[self.content_provider.path] = self.view.page
            self.content_provider.close()
            self.content_provider = None

        ext = os.path.splitext(path)[1].lower()

        try:
            if ext in {".pdf", ".epub", ".mobi", ".fb2", ".txt"}:
                self.content_provider = PdfContentProvider(path)
                self._restore_epub_font()
            elif ext in {".zip", ".cbz"}:
                self.content_provider = ArchiveContentProvider(path)
            else:
                wx.MessageBox(f"Unsupported file type: {ext}", "Error")
                return

        except Exception as e:
            wx.MessageBox(f"Error opening file: {e}", "Error")
            if self.content_provider:
                self.content_provider.close()
            self.content_provider = None
            return

        self.file_history.AddFileToHistory(path)

        self._populate_sidebar()

        self.view.set_content_provider(self.content_provider)

        if path in self.file_progress:
            saved_page = self.file_progress[path]
            if 0 <= saved_page < self.content_provider.page_count:
                self.view.go_to_page(saved_page)

        self.recent_files = update_recent(self.recent_files, path, limit=24)

        if not self.splitter.IsSplit():
            self.splitter.SplitVertically(self.sidebar, self.view, 250)
            if not self.content_provider.get_toc():
                self.on_switch_sidebar_tab(None)

        self._update_ui()
        self.view.SetFocus()

        self.on_nav_current(None)

    def on_close_pdf(self, evt):
        if self.content_provider:
            self.content_provider.close()
        self.content_provider = None

        self.view.set_content_provider(None)
        self.sidebar_tree.DeleteAllItems()

        if not self.splitter.IsSplit():
            self.splitter.SplitVertically(self.sidebar, self.view, 250)

        if self.sidebar_nb.GetPageCount() > 1:
            self.sidebar_nb.SetSelection(1)

        self._update_ui()

    def on_open_recent(self, evt):
        path = self.file_history.GetHistoryFile(evt.GetId() - wx.ID_FILE1)
        if path and os.path.isfile(path):
            self._load_file(path)
        else:
            wx.Bell()

    def on_manual(self, evt):
        if hasattr(self, 'manual_window') and self.manual_window:
            try:
                self.manual_window.Raise()
                return
            except RuntimeError:
                # Window was destroyed
                pass

        self.manual_window = ManualDialog(self)
        self.manual_window.Show()

    def on_open_library(self, evt):
        current_dir = os.getcwd()

        if hasattr(self, 'dir_ctrl'):
            path = self.dir_ctrl.GetPath()
            if path and os.path.isdir(path):
                current_dir = path
            elif path and os.path.isfile(path):
                current_dir = os.path.dirname(path)
        elif self.content_provider and self.content_provider.path:
            current_dir = os.path.dirname(self.content_provider.path)

        def _open_from_lib(path):
            self.Raise()
            self._load_file(path)

        lib_frame = LibraryFrame(self, current_dir, _open_from_lib)
        lib_frame.Show()

    def on_clear_history(self, evt):
        for i in range(self.file_history.GetCount() - 1, -1, -1):
            self.file_history.RemoveFileFromHistory(i)

        self.recent_files = []

        self.file_history.AddFilesToMenu(self.m_recent)
        self._update_ui()

    def on_show_toc_dialog(self, evt):
        if not self.content_provider:
            return
        toc = self.content_provider.get_toc()
        if not toc:
            wx.MessageBox("No TOC found.")
            return
        dlg = TOCDialog(self, toc, self.view.page, lambda p: (self.view.go_to_page(p), self._update_ui()))
        dlg.ShowModal()
        dlg.Destroy()

    def on_show_search(self, evt):
        if not self.content_provider:
            wx.MessageBox("Please open a document first.", "No Document")
            return

        def navigate_to_page(page_index):
            self.view.go_to_page(page_index)
            self._update_ui()
            # self.Raise()

        dlg = SearchDialog(self, self.content_provider, navigate_to_page)
        dlg.Show()

    def on_nav_go_up(self, evt):
        current_path = self.dir_ctrl.GetPath()
        if not current_path:
            return

        # idk...
        if os.path.isfile(current_path):
            parent = os.path.dirname(os.path.dirname(current_path))
        else:
            parent = os.path.dirname(current_path)

        if os.path.exists(parent):
            self.dir_ctrl.SetPath(parent)

    def on_nav_current(self, evt):
        if self.content_provider and self.content_provider.path:
            folder = os.path.dirname(self.content_provider.path)
            if os.path.exists(folder):
                self.dir_ctrl.SetPath(folder)
                self.dir_ctrl.SetPath(self.content_provider.path)

                tree = self.dir_ctrl.GetTreeCtrl()

                if tree:
                    def _do_scroll_left():
                        tree.SetScrollPos(wx.HORIZONTAL, 0)

                    if wx.Platform == '__WXMSW__':
                        import ctypes
                        # WM_HSCROLL = 0x114 (276), SB_LEFT = 6
                        hwnd = tree.GetHandle()
                        ctypes.windll.user32.SendMessageW(hwnd, 276, 6, 0)

                    wx.CallAfter(_do_scroll_left)

    def on_file_browser_activated(self, evt):
        filepath = self.dir_ctrl.GetFilePath()
        if filepath and os.path.isfile(filepath):
            self._load_file(filepath)

    def on_switch_sidebar_tab(self, evt):
        if not self.splitter.IsSplit():
            return

        count = self.sidebar_nb.GetPageCount()
        if count > 1:
            current = self.sidebar_nb.GetSelection()
            next_page = (current + 1) % count
            self.sidebar_nb.SetSelection(next_page)

    def on_extract_text(self, evt):
        if not self.content_provider:
            return

        try:
            visible_pages = self.view._spread_pages()
            extracted_parts = []

            for page_idx in visible_pages:
                if page_idx < 0:
                    continue

                raw_text = self.content_provider.get_page_text(page_idx)

                if raw_text:
                    header = f"=== Page {page_idx + 1} ==="
                    extracted_parts.append(f"{header}\n{raw_text}")

            full_text = "\n\n".join(extracted_parts)
            if not full_text.strip():
                full_text = "<No text found on visible pages.>"

            dlg = TextExtractionDialog(self, full_text, title="Extracted Page Text")
            dlg.ShowModal()
            dlg.Destroy()

        except Exception as e:
            wx.MessageBox(f"Failed to extract text: {e}", "Error")

    def on_extract_images(self, evt):
        if not self.content_provider:
            return

        visible_pages = self.view._spread_pages()
        found_images_data = []

        wx.BeginBusyCursor()
        try:
            for i, page_idx in enumerate(visible_pages):
                if page_idx < 0:
                    continue

                images_on_page = self.content_provider.get_page_images(page_idx)

                for j, img_dict in enumerate(images_on_page):
                    desc = (f"Pg {page_idx + 1} - Img {j + 1} "
                            f"({img_dict['width']}x{img_dict['height']}, {img_dict['ext']})")

                    bmp = self._generate_preview(img_dict['bytes'], img_dict['width'], img_dict['height'])

                    found_images_data.append({
                        "desc": desc,
                        "bitmap": bmp,
                        "bytes": img_dict['bytes'],
                        "ext": img_dict['ext']
                    })

        except Exception as e:
            wx.EndBusyCursor()
            wx.MessageBox(f"Error extracting images: {e}", "Error")
            return
        finally:
            if wx.IsBusy():
                wx.EndBusyCursor()

        if not found_images_data:
            wx.MessageBox("No images found on the visible page(s).", "Info")
            return

        dlg = ImageExtractionDialog(self, found_images_data)
        dlg.ShowModal()
        dlg.Destroy()

    def _generate_preview(self, data: bytes, w_orig: int, h_orig: int) -> wx.Bitmap:
        try:
            stream = io.BytesIO(data)
            wx_img = wx.Image(stream)

            if not wx_img.IsOk():
                raise ValueError("Image data is invalid or format not supported by wx.Image")

            if w_orig > 800 or h_orig > 800:
                scale = 800 / max(w_orig, h_orig)
                preview_w = int(w_orig * scale)
                preview_h = int(h_orig * scale)
                if preview_w > 0 and preview_h > 0:
                    wx_img = wx_img.Scale(preview_w, preview_h, wx.IMAGE_QUALITY_HIGH)

            return wx.Bitmap(wx_img)

        except Exception as e:
            print(f"Preview generation warning: {e}")
            ph = wx.Image(100, 100)
            ph.SetRGB(wx.Rect(0, 0, 100, 100), 200, 200, 200)
            return wx.Bitmap(ph)

    def on_goto_page(self, evt):
        if not self.content_provider: return
        dlg = wx.TextEntryDialog(self, f"Enter page number (1-{self.content_provider.page_count}):", "Go to Page")
        if dlg.ShowModal() == wx.ID_OK:
            try:
                val = int(dlg.GetValue())
                if 1 <= val <= self.content_provider.page_count:
                    self.view.go_to_page(val - 1)
                    self._update_ui()
                else:
                    wx.MessageBox("Page number out of range.")
            except ValueError:
                wx.MessageBox("Invalid number.")
        dlg.Destroy()

    def on_setmg(self, evt):
        dlg = SetMarginGapDialog(self, title="Set Margin and Gap")

        if dlg.ShowModal() == wx.ID_OK:
            margin_str, gap_str = dlg.GetValues()
            try:
                m_val = int(margin_str)
                g_val = int(gap_str)

                if 0 <= m_val <= 999 and 0 <= g_val <= 999:
                    self.view.set_margin_gap(m=m_val, g=g_val)
                    self._update_ui()
                else:
                    wx.MessageBox("Numbers must be between 0 and 999.", "Range Error", wx.OK | wx.ICON_ERROR)
            except ValueError:
                wx.MessageBox("Please enter integers only.", "Input Error",
                              wx.OK | wx.ICON_ERROR)

        dlg.Destroy()

    def on_zoom_out(self, evt):
        self.view.set_zoom_mode(PDFView.ZOOM_MANUAL)
        self.view.zoom = max(PDFView.MIN_ZOOM, self.view.zoom / 1.2)
        self.view._refresh_layout()
        self.view.Refresh()
        self._update_ui()

    def on_zoom_in(self, evt):
        self.view.set_zoom_mode(PDFView.ZOOM_MANUAL)
        self.view.zoom = min(PDFView.MAX_ZOOM, self.view.zoom * 1.2)
        self.view._refresh_layout()
        self.view.Refresh()
        self._update_ui()

    def _restore_epub_font(self):
        if not (isinstance(self.content_provider, PdfContentProvider) and self.content_provider.is_reflowable):
            return

        try:
            w_pt, h_pt = self.content_provider.get_page_size(0)
            self.content_provider.doc.layout(width=w_pt, height=h_pt, fontsize=self.epub_font_size)
        except Exception as e:
            print(f"Warning: Failed to restore EPUB font settings: {e}")

    def on_change_epub_font(self, evt):
        if not (isinstance(self.content_provider, PdfContentProvider) and self.content_provider.is_reflowable):
            return

        event_id = evt.GetId()
        if event_id == self.id_font_increase:
            self.epub_font_size += 1
        else:
            self.epub_font_size = max(8, self.epub_font_size - 1)

        w_pt, h_pt = self.content_provider.get_page_size(0)

        self.content_provider.doc.layout(width=w_pt, height=h_pt, fontsize=self.epub_font_size)
        current_page = self.view.page
        self.view.set_content_provider(self.content_provider)

        self.view.go_to_page(current_page)
        self._update_ui()

    def on_fit_width(self, evt):
        self.view.set_zoom_mode(PDFView.ZOOM_FIT_WIDTH)
        self._update_ui()

    def on_fit_page(self, evt):
        self.view.set_zoom_mode(PDFView.ZOOM_FIT_PAGE)
        self._update_ui()

    def on_quality_change(self, event):
        event_id = event.GetId()
        quality_map = {
            self.id_quality_hq: 2,
            self.id_quality_mq: 1,
            self.id_quality_lq: 0
        }
        self.quality_preference = quality_map.get(event_id, 1)

        if not self.content_provider:
            return

        current_page = self.view.page

        self.content_provider.set_render_quality(self.quality_preference)

        if hasattr(self.view, '_bmp_cache'):
            self.view._bmp_cache.clear()
            print("[INFO] View cache cleared.")

        self.view.Refresh()
        self.view.Update()

        self.view.go_to_page(current_page)

        print(f"[INFO] Render quality set to: {self.quality_preference}.")

    def on_background_color(self, evt):
        current_color = self.view.GetBackgroundColour()

        dlg = ModernColorDialog(self, initial_color=current_color, title="Change background color")

        if dlg.ShowModal() == wx.ID_OK:
            new_color = dlg.GetColorData().GetColour()
            self.view.set_background_color(new_color)
            self._update_ui()

        dlg.Destroy()

    def on_fullscreen(self, evt):
        is_full = self.IsFullScreen()

        self.ShowFullScreen(not is_full, style=wx.FULLSCREEN_ALL)

        self._update_ui()

    def _on_custom_filter_menu(self, evt, name: str):
        self._select_custom_filter(name)

    def _select_custom_filter(self, name: str | None):
        if self.view:
            self.view.set_custom_filter(name)

        mb = self.GetMenuBar()
        if not mb: return

        if name is None:
            mb.Check(self.id_custom_none, True)
            for fid in self.filter_menu_map.values():
                mb.Check(fid, False)
        else:
            mb.Check(self.id_custom_none, False)

            for fname, fid in self.filter_menu_map.items():
                should_check = (fname == name)
                mb.Check(fid, should_check)

        self._update_ui()

    def on_about(self, event):
        info = adv.AboutDialogInfo()

        try:
            from wxReaderIcon import APP_ICON
            info.SetIcon(icon=APP_ICON)
        except Exception:
            print(Exception)
        info.SetName(APP_NAME)
        info.SetVersion(APP_VERSION)
        info.SetDescription(
            f"wxPython v{wx.version()} (LGPL)\n"
            "PyMuPDF v1.23.8 with MuPDF v1.23.7 (AGPL)\n"
            "OpenGL (PyOpenGL, BSD)\n"
            "Pillow (MIT-CMU)\n"
            "Python 3.12.9"
        )
        info.SetWebSite(url=r"https://github.com/puff-dayo/wxReader/")

        wx.adv.AboutBox(info)

    def on_close(self, evt):
        if self.content_provider and self.view:
            self.file_progress[self.content_provider.path] = self.view.page

        if self.view:
            self.view.stop_worker()
            self.view.content_provider = None
            self.view._bmp_cache.clear()

        try:
            cfg = load_config()
            current_cfg = {
                "show_sidebar": self.splitter.IsSplit(),
                "view_mode": self.view.mode,
                "direction": self.view.direction,
                "pad_start": self.view.pad_start,
                "zoom_mode": self.view.zoom_mode,
                "epub_font_size": self.epub_font_size,
                "recent_files": self.recent_files,
                "last_file": (self.content_provider.path if self.content_provider else ""),
                "file_progress": self.file_progress,
            }
            cfg.update(current_cfg)

            if not self.IsIconized():
                is_maximized = self.IsMaximized()
                is_fullscreen = self.IsFullScreen()

                cfg["window_maximized"] = is_maximized
                cfg["window_fullscreen"] = is_fullscreen

                if not is_maximized and not is_fullscreen:
                    rect = self.GetRect()
                    cfg["window_rect"] = [rect.x, rect.y, rect.width, rect.height]

            save_config(cfg)
            print("Configuration saved successfully.")

        except Exception as e:
            print(f"Save failed: {e}")

        evt.Skip()


class WxPDFReaderApp(wx.App):
    def OnInit(self):
        frame = MainFrame()

        from wxReaderIcon import APP_ICON
        if APP_ICON.IsOk():
            frame.SetIcon(APP_ICON)
        frame.Show()

        return True


if __name__ == "__main__":
    app = WxPDFReaderApp(False)
    app.MainLoop()
