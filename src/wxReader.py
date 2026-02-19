from __future__ import annotations

import ctypes

try:
    ctypes.windll.user32.SetProcessDpiAwarenessContext(ctypes.c_void_p(-4))
except Exception:
    print(Exception)

import functools
import io
import os
import threading

import wx

from wxReaderIcon import msw_set_theme, get_app_icon, get_app_font
from wxReaderConfigUtil import load_config, save_config, update_recent
from wxReaderDialog import TOCDialog, TextExtractionDialog, SearchDialog, ImageExtractionDialog, SetMarginGapDialog, \
    ModernColorDialog, AboutDialog, RecentFilesDialog, PswdManagerDialog, KeymapDialog, FilterSettingsDialog
from wxReaderGlUtil import GLFilterTool
from wxReaderLibrary import LibraryFrame
from wxReaderManual import ManualDialog
from wxReaderProvider import ContentProvider, PdfContentProvider, ArchiveContentProvider, SevenZipContentProvider
from wxReaderString import *
from wxReaderKeyBinds import DEFAULT_KEYBINDS, get_menu_label
from wxReaderView import PDFView
from wxReaderToast import show_toast
from wxReaderExtCtrl import ControlServer


def _(text):
    return wx.GetTranslation(text)


GWL_STYLE = -16
TVS_NOTOOLTIPS = 0x0080


class FileDropTarget(wx.FileDropTarget):
    def __init__(self, frame):
        super().__init__()
        self.frame = frame

    @staticmethod
    def _accept(filenames):
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
    def __init__(self, lang=wx.LANGUAGE_ENGLISH):
        cfg = load_config()

        self.keybinds = DEFAULT_KEYBINDS.copy()
        if "keybinds" in cfg:
            self.keybinds.update(cfg["keybinds"])

        style = wx.DEFAULT_FRAME_STYLE
        is_maximized = cfg.get("window_maximized", False)
        if is_maximized:
            style |= wx.MAXIMIZE
        initial_pos = wx.DefaultPosition
        initial_size = (1280, 800)

        win_rect = cfg.get("window_rect")
        if win_rect and len(win_rect) == 4 and not is_maximized:
            x, y, w, h = win_rect
            if wx.Display.GetFromPoint((x, y)) != wx.NOT_FOUND:
                initial_pos = (x, y)
                initial_size = (w, h)

        super().__init__(None, title=APP_NAME, pos=initial_pos, size=initial_size, style=style)
        self.SetMinSize((600, 400))

        self.SetFont(wx.GetApp().global_font)

        # Initialize state
        self.content_provider: ContentProvider | None = None
        self.quality_preference = 0

        self.epub_font_size = 12

        self.splitter = wx.SplitterWindow(self, style=wx.SP_LIVE_UPDATE | wx.SP_3D)
        self.splitter.SetMinimumPaneSize(50)

        self.cur_lang = lang
        self.lang_to_change = None

        # START Sidebar

        # 0. Sidebar Container
        self.sidebar = wx.Panel(self.splitter)
        self.sidebar_main_sizer = wx.BoxSizer(wx.VERTICAL)

        self.sidebar_nb = wx.Notebook(self.sidebar)

        # 1. Outline
        self.toc_panel = wx.Panel(self.sidebar_nb)
        toc_sizer = wx.BoxSizer(wx.VERTICAL)

        self.sidebar_search = wx.SearchCtrl(self.toc_panel, style=wx.TE_PROCESS_ENTER)
        self.sidebar_search.SetDescriptiveText(_("Search Outline"))

        self.sidebar_tree = wx.TreeCtrl(self.toc_panel, style=wx.TR_DEFAULT_STYLE | wx.TR_HIDE_ROOT |
                                                              wx.TR_FULL_ROW_HIGHLIGHT | wx.TR_NO_LINES | wx.TR_TWIST_BUTTONS)
        self.sidebar_tree.SetBackgroundColour(wx.Colour(245, 245, 245))

        toc_sizer.Add(self.sidebar_search, 0, wx.EXPAND | wx.ALL, 5)
        toc_sizer.Add(self.sidebar_tree, 1, wx.EXPAND | wx.LEFT | wx.RIGHT | wx.BOTTOM, 0)
        self.toc_panel.SetSizer(toc_sizer)

        self.sidebar_nb.AddPage(self.toc_panel, _("Outline"))

        # 2. Browser
        self.files_panel = wx.Panel(self.sidebar_nb)
        files_sizer = wx.BoxSizer(wx.VERTICAL)

        # 2.1 Buttons
        btn_sizer = wx.GridSizer(1, 3, 0, 5)

        self.btn_go_up = wx.Button(self.files_panel, label=_("Dir Up"))
        self.btn_go_up.SetBitmap(get_icon(wx.ART_GO_UP))

        self.btn_sync_file = wx.Button(self.files_panel, label=_("Locate"))
        self.btn_sync_file.SetBitmap(get_icon(wx.ART_HELP_PAGE))

        self.btn_open_library = wx.Button(self.files_panel, label=_("Gallery"))
        self.btn_open_library.SetBitmap(get_icon_v2(wx.ART_FIND))

        for btn in [self.btn_go_up, self.btn_sync_file, self.btn_open_library]:
            btn.SetBitmapMargins((4, 2))

        btn_sizer.Add(self.btn_go_up, 0, wx.EXPAND)
        btn_sizer.Add(self.btn_sync_file, 0, wx.EXPAND)
        btn_sizer.Add(self.btn_open_library, 0, wx.EXPAND)

        files_sizer.Add(btn_sizer, 0, wx.EXPAND | wx.ALL, 5)

        # 2.2 Directory control
        self.dir_ctrl = wx.GenericDirCtrl(self.files_panel, dir=os.getcwd(), filter=SUPPORTED_WILDCARDS,
                                          style=wx.DIRCTRL_SHOW_FILTERS | wx.DIRCTRL_3D_INTERNAL)
        self.dir_tree = self.dir_ctrl.GetTreeCtrl()

        files_sizer.Add(self.dir_ctrl, 1, wx.EXPAND | wx.LEFT | wx.RIGHT | wx.BOTTOM, 0)
        self.files_panel.SetSizer(files_sizer)

        self.sidebar_nb.AddPage(self.files_panel, _("File Browser"))

        # 3. Folder List
        self.fv_panel = wx.Panel(self.sidebar_nb)
        fv_sizer = wx.BoxSizer(wx.VERTICAL)

        # 3.1 Toolbar Line
        fv_toolbar_sizer = wx.BoxSizer(wx.HORIZONTAL)

        self.btn_fv_refresh = wx.Button(self.fv_panel, label=_("Refresh"))

        self.btn_fv_gallery = wx.Button(self.fv_panel, label=_("Gallery"))

        self.fv_sort_choice = wx.Choice(self.fv_panel, choices=[
            "A-Z",
            "Z-A",
            _("Newest"),
            _("Oldest")
        ])
        self.fv_sort_choice.SetSelection(2)

        btn_sizer = wx.GridSizer(1, 2, 5, 0)
        btn_sizer.Add(self.btn_fv_refresh, 0, wx.EXPAND)
        btn_sizer.Add(self.btn_fv_gallery, 0, wx.EXPAND)

        fv_toolbar_sizer.Add(self.fv_sort_choice, 1, wx.EXPAND | wx.RIGHT, 5)

        fv_toolbar_sizer.Add(btn_sizer, 0, wx.EXPAND)

        fv_sizer.Add(fv_toolbar_sizer, 0, wx.EXPAND | wx.ALL, 5)

        # 3.2 File List
        self.fv_listbox = wx.ListBox(self.fv_panel, style=wx.LB_SINGLE | wx.LB_HSCROLL | wx.LB_NEEDED_SB)
        fv_sizer.Add(self.fv_listbox, 1, wx.EXPAND | wx.LEFT | wx.RIGHT | wx.BOTTOM, 5)

        self.fv_panel.SetSizer(fv_sizer)
        self.sidebar_nb.AddPage(self.fv_panel, _("Folder List"))

        # END Sidebar
        self.sidebar_main_sizer.Add(self.sidebar_nb, 1, wx.EXPAND)
        self.sidebar.SetSizer(self.sidebar_main_sizer)

        # START Main Content
        self.view = PDFView(self.splitter)
        self.view.main_frame = self

        self.splitter.SplitVertically(self.sidebar, self.view, 250)
        self.splitter.SetSashGravity(0.0)
        self.splitter.Unsplit(self.sidebar)

        self.status_bar = self.CreateStatusBar(1)
        self.status_bar.SetFont(get_app_font())

        filters_dir = os.path.join(os.path.dirname(__file__), "filters")
        self.gl_filters = GLFilterTool(self, filters_dir)
        root = wx.BoxSizer(wx.VERTICAL)
        root.Add(self.splitter, 1, wx.EXPAND)
        root.Add(self.gl_filters.canvas, 0)
        self.SetSizer(root)
        self.Layout()

        self._build_menus()
        # END Main Content

        # START Load Config
        self.recent_files = []
        self.file_progress = cfg.get("file_progress", {})

        try:
            if cfg.get("window_fullscreen", False):
                def _do_fullscreen():
                    self.ShowFullScreen(True, style=wx.FULLSCREEN_NOBORDER | wx.FULLSCREEN_NOCAPTION)
                    item = self.menubar.FindMenuItem(self.id_fullscreen)
                    if item:
                        item.Check(True)

                wx.CallAfter(_do_fullscreen)
        except Exception as e:
            print(f"[ERROR] wxReader Failed to restore fullscreen: {e}")

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

        if last and os.path.isfile(last):
            wx.CallLater(300, self._load_file, last)
        # END Load Config

        # --- Events ---
        self.Bind(wx.EVT_CLOSE, self.on_close)
        self.sidebar_tree.Bind(wx.EVT_TREE_ITEM_ACTIVATED, self.on_sidebar_click)
        self.sidebar_search.Bind(wx.EVT_TEXT, self.on_sidebar_search)
        self.Bind(wx.EVT_BUTTON, self.on_nav_go_up, self.btn_go_up)
        self.Bind(wx.EVT_BUTTON, self.on_nav_current, self.btn_sync_file)
        self.Bind(wx.EVT_BUTTON, self.on_open_library, self.btn_open_library)
        self.Bind(wx.EVT_DIRCTRL_FILEACTIVATED, self.on_file_browser_activated, self.dir_ctrl)
        self.fv_sort_choice.Bind(wx.EVT_CHOICE, self.on_fv_sort)
        self.fv_listbox.Bind(wx.EVT_LISTBOX_DCLICK, self.on_fv_item_activated)
        self.fv_listbox.Bind(wx.EVT_MOTION, self.on_fv_hover)
        self.Bind(wx.EVT_BUTTON, lambda e: self._populate_folder_view_list(), self.btn_fv_refresh)
        self.Bind(wx.EVT_BUTTON, self.on_open_library, self.btn_fv_gallery)
        self.Bind(wx.EVT_MENU, self.on_switch_sidebar_tab, id=self.id_switch_tab)

        self.SetDropTarget(FileDropTarget(self))

        self._update_ui()
        self.Raise()

        self.Bind(wx.EVT_ACTIVATE, self.on_window_activate)

        wx.CallAfter(self._post_startup_tasks)

    def _build_menus(self):
        old_mb = self.GetMenuBar()
        if old_mb:
            self.SetMenuBar(None)
            try:
                old_mb.Destroy()
            except Exception:
                pass

        self.menubar = wx.MenuBar()
        self.menubar.SetFont(get_app_font())

        def _add_item(menu: wx.Menu, id, label, art_id=None, help_text="", kind=wx.ITEM_NORMAL, subMenu=None):
            if subMenu is not None:
                item = menu.AppendSubMenu(subMenu, label, help_text)
                return item

            item = wx.MenuItem(menu, id, label, help_text, kind)

            if art_id:
                try:
                    bmp = wx.ArtProvider.GetBitmap(art_id, wx.ART_MENU, wx.Size(16, 16))
                    if bmp and bmp.IsOk():
                        item.SetBitmap(bmp)
                except Exception:
                    print(Exception)

            menu.Append(item)
            return item

        def _find_item(mid):
            try:
                found = self.menubar.FindItem(int(mid))
                return found[0]
            except Exception:
                print(Exception)
                return None

        self._find_menu_item = _find_item

        # --- File ---
        m_file = wx.Menu()

        m_open = _add_item(m_file, wx.ID_OPEN, get_menu_label(_("&Open..."), "open"), wx.ART_FILE_OPEN)
        m_close = _add_item(m_file, wx.ID_CLOSE, get_menu_label(_("&Close"), "close"))

        m_file.AppendSeparator()

        self.id_library = wx.NewIdRef()
        _add_item(m_file, self.id_library, _("&Gallery Mode"))

        m_file.AppendSeparator()

        self.id_recent_dialog = wx.NewIdRef()
        _add_item(m_file, self.id_recent_dialog, _("Recent Files..."))

        m_file.AppendSeparator()

        self.id_pswdmng = wx.NewIdRef()
        _add_item(m_file, self.id_pswdmng, _("Edit pswd.txt"))

        m_file.AppendSeparator()

        self.id_key_binds_editor = wx.NewIdRef()
        _add_item(m_file, self.id_key_binds_editor, _("Preferences"))

        m_lang = wx.Menu()
        self.id_lang_enus = wx.NewIdRef()
        self.id_lang_zhsg = wx.NewIdRef()
        self.id_lang_zhtw = wx.NewIdRef()
        self.id_lang_jajp = wx.NewIdRef()
        m_lang.Append(self.id_lang_enus, "English (US)")
        m_lang.Append(self.id_lang_jajp, "日本語（日本）")
        m_lang.Append(self.id_lang_zhsg, "中文（新加坡）")
        m_lang.Append(self.id_lang_zhtw, "中文（台灣）")
        m_file.AppendMenu(wx.ID_ANY, _("Languages..."), m_lang)

        m_file.AppendSeparator()
        m_exit = _add_item(m_file, wx.ID_EXIT, _("E&xit"), wx.ART_QUIT)

        self.menubar.Append(m_file, _("&File"))

        # --- View ---
        m_view = wx.Menu()

        self.id_sidebar_toggle = wx.NewIdRef()
        _add_item(m_view, self.id_sidebar_toggle, get_menu_label(_("Show &Sidebar"), "toggle_sidebar"),
                  kind=wx.ITEM_CHECK)

        self.id_switch_tab = wx.NewIdRef()
        _add_item(m_view, self.id_switch_tab, get_menu_label(_("Switch Sidebar Tab"), "switch_tab"))

        m_view.AppendSeparator()

        self.id_single_page = wx.NewIdRef()
        self.id_two_page = wx.NewIdRef()
        m_view.AppendRadioItem(self.id_single_page, get_menu_label(_("Single Page View"), "single_page"))
        m_view.AppendRadioItem(self.id_two_page, get_menu_label(_("Two Page View"), "two_page"))
        m_view.AppendSeparator()

        self.id_pad_start = wx.NewIdRef()
        _add_item(m_view, self.id_pad_start, _("Add Blank Page at Start"), kind=wx.ITEM_CHECK)
        m_view.AppendSeparator()

        m_dir = wx.Menu()
        self.id_ltr = wx.NewIdRef()
        self.id_rtl = wx.NewIdRef()
        m_dir.AppendRadioItem(self.id_ltr, _("Left-to-Right"))
        m_dir.AppendRadioItem(self.id_rtl, _("Right-to-Left"))

        _add_item(m_view, wx.ID_ANY, _("Page &Direction"), subMenu=m_dir)

        m_view.AppendSeparator()

        self.id_zoom_in = wx.NewIdRef()
        self.id_zoom_out = wx.NewIdRef()
        self.id_fit_width = wx.NewIdRef()
        self.id_fit_page = wx.NewIdRef()
        self.id_zoom_manual = wx.NewIdRef()

        _add_item(m_view, self.id_zoom_in, get_menu_label(_("Zoom &In"), "zoom_in"))
        _add_item(m_view, self.id_zoom_out, get_menu_label(_("Zoom &Out"), "zoom_out"))
        m_view.AppendSeparator()

        m_view.AppendRadioItem(self.id_fit_width, get_menu_label(_("Fit &Width"), "fit_width"))
        m_view.AppendRadioItem(self.id_fit_page, get_menu_label(_("Fit &Page"), "fit_page"))
        m_view.AppendRadioItem(self.id_zoom_manual, _("Manual Zoom"))
        m_view.AppendSeparator()

        self.id_scrolllock = wx.NewIdRef()
        _add_item(m_view, self.id_scrolllock, _("Scroll Lock") + "\tF6", kind=wx.ITEM_CHECK)
        m_view.AppendSeparator()

        self.id_setmg = wx.NewIdRef()
        _add_item(m_view, self.id_setmg, _("Set Margin and Gap"))

        m_view.AppendSeparator()
        self.id_bg = wx.NewIdRef()
        _add_item(m_view, self.id_bg, _("Background Color…"))

        m_view.AppendSeparator()
        self.id_font_increase = wx.NewIdRef()
        self.id_font_decrease = wx.NewIdRef()
        _add_item(m_view, self.id_font_increase, _("Larger Font") + "\tCtrl+Shift++")
        _add_item(m_view, self.id_font_decrease, _("Smaller Font") + "\tCtrl+Shift+-")

        m_view.AppendSeparator()
        self.id_fullscreen = wx.NewIdRef()
        _add_item(m_view, self.id_fullscreen, get_menu_label(_("Full &Screen"), "fullscreen"), kind=wx.ITEM_CHECK)

        m_view.AppendSeparator()

        m_quality = wx.Menu()

        self.id_quality_hq = wx.NewIdRef()
        self.id_quality_mq = wx.NewIdRef()
        self.id_quality_lq = wx.NewIdRef()

        m_quality.AppendRadioItem(self.id_quality_lq, _("Bilinear"))
        m_quality.AppendRadioItem(self.id_quality_mq, _("Lanczos"))
        m_quality.AppendRadioItem(self.id_quality_hq, _("DeMoiré"))

        item_lq = _find_item(self.id_quality_lq)
        if item_lq:
            item_lq.Check(True)

        _add_item(m_view, wx.ID_ANY, _("Render Quality"), subMenu=m_quality)

        self.menubar.Append(m_view, _("&View"))

        # --- Navigate ---
        m_nav = wx.Menu()

        self.id_prev = wx.NewIdRef()
        self.id_next = wx.NewIdRef()
        self.id_goto = wx.NewIdRef()

        _add_item(m_nav, self.id_prev, get_menu_label(_("Previous Page"), "prev_page"), wx.ART_GO_BACK)
        _add_item(m_nav, self.id_next, get_menu_label(_("Next Page"), "next_page"), wx.ART_GO_FORWARD)
        _add_item(m_nav, self.id_goto, get_menu_label(_("&Go to Page..."), "goto_page"))

        m_nav.AppendSeparator()

        self.id_extctrl_toggle = wx.NewIdRef()
        self.menu_extctrl = _add_item(m_nav, self.id_extctrl_toggle, _("External Control"), kind=wx.ITEM_CHECK)
        self.menu_extctrl.Check(False)

        m_nav.AppendSeparator()

        self.id_search = wx.NewIdRef()
        _add_item(m_nav, self.id_search, get_menu_label(_("&Find..."), "find"), wx.ART_FIND)

        self.id_show_toc_dialog = wx.NewIdRef()
        _add_item(m_nav, self.id_show_toc_dialog, get_menu_label(_("Show TOC Dialog..."), "show_toc"))

        self.menubar.Append(m_nav, _("&Navigate"))

        # --- Process ---
        m_process = wx.Menu()

        self.id_extract_text = wx.NewIdRef()
        _add_item(m_process, self.id_extract_text, get_menu_label(_("Extract Page Text"), "extract_text"))

        self.id_extract_images = wx.NewIdRef()
        _add_item(m_process, self.id_extract_images, get_menu_label(_("Extract Page Images"), "extract_images"))

        m_process.AppendSeparator()

        self.id_filter_settings = wx.NewIdRef()
        _add_item(m_process, self.id_filter_settings, _("Shader Settings..."), wx.ART_EXECUTABLE_FILE)

        m_process.AppendSeparator()

        self.id_custom_none = wx.NewIdRef()
        _add_item(m_process, self.id_custom_none, _("None / Turn Off"), kind=wx.ITEM_CHECK)
        self.Bind(wx.EVT_MENU, lambda e: self._select_custom_filter(None), id=self.id_custom_none)

        self.filter_menu_map = {}

        def _populate_custom_filters_menu():
            filters_dir = os.path.join(os.path.dirname(__file__), "filters")
            if not os.path.exists(filters_dir):
                return

            loaded_filters = set(self.gl_filters.filters.keys())

            try:
                entries = sorted(os.listdir(filters_dir))
            except OSError:
                entries = []

            for entry in entries:
                full_path = os.path.join(filters_dir, entry)

                if os.path.isdir(full_path):
                    submenu = wx.Menu()
                    has_items = False

                    sub_files = sorted(os.listdir(full_path))
                    for f in sub_files:
                        name, ext = os.path.splitext(f)
                        if name in loaded_filters:
                            mid = wx.NewIdRef()
                            item = submenu.AppendCheckItem(mid, name)
                            self.Bind(wx.EVT_MENU, functools.partial(self._on_custom_filter_menu, name=name), id=mid)
                            self.filter_menu_map[name] = mid
                            has_items = True

                    if has_items:
                        m_process.AppendSubMenu(submenu, entry)

            item_none = _find_item(self.id_custom_none)
            if item_none:
                item_none.Check(True)

        self._populate_custom_filters_menu = _populate_custom_filters_menu

        self.menubar.Append(m_process, _("&Process"))

        # --- Help ---
        m_help = wx.Menu()
        m_about = _add_item(m_help, wx.ID_ABOUT, _("&About"), wx.ART_INFORMATION)
        self.menubar.Append(m_help, _("&Info"))

        self.id_check_update = wx.NewIdRef()
        _add_item(m_help, self.id_check_update, _("Check for Updates..."))

        m_help.AppendSeparator()

        self.id_manual = wx.NewIdRef()
        _add_item(m_help, self.id_manual, _("&Help Topics"), "help")

        # --- Integration ---
        self.SetMenuBar(self.menubar)

        # --- Bindings ---
        self.Bind(wx.EVT_MENU, self.on_open, m_open)
        self.Bind(wx.EVT_MENU, self.on_open_library, id=self.id_library)
        self.Bind(wx.EVT_MENU, self.on_show_recent, id=self.id_recent_dialog)
        self.Bind(wx.EVT_MENU, self.on_close_pdf, m_close)
        self.Bind(wx.EVT_MENU, self.on_open_pswdmng, id=self.id_pswdmng)
        self.Bind(wx.EVT_MENU, self.on_edit_keys, id=self.id_key_binds_editor)
        self.Bind(wx.EVT_MENU, lambda e: self.Close(), m_exit)

        self.Bind(wx.EVT_MENU, self.on_lang_change, id=self.id_lang_enus)
        self.Bind(wx.EVT_MENU, self.on_lang_change, id=self.id_lang_jajp)
        self.Bind(wx.EVT_MENU, self.on_lang_change, id=self.id_lang_zhsg)
        self.Bind(wx.EVT_MENU, self.on_lang_change, id=self.id_lang_zhtw)

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
        self.Bind(wx.EVT_MENU, self.on_manual_zoom, id=self.id_zoom_manual)
        self.Bind(wx.EVT_MENU, self.on_scrolllock_change, id=self.id_scrolllock)
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
        self.Bind(wx.EVT_MENU, self.on_toggle_server, id=self.id_extctrl_toggle)
        self.Bind(wx.EVT_MENU, self.on_goto_page, id=self.id_goto)
        self.Bind(wx.EVT_MENU, self.on_show_search, id=self.id_search)
        self.Bind(wx.EVT_MENU, self.on_show_toc_dialog, id=self.id_show_toc_dialog)

        # Process
        self.Bind(wx.EVT_MENU, self.on_extract_text, id=self.id_extract_text)
        self.Bind(wx.EVT_MENU, self.on_extract_images, id=self.id_extract_images)
        self.Bind(wx.EVT_MENU, self.on_filter_settings, id=self.id_filter_settings)

        self.Bind(wx.EVT_MENU, self.on_about, m_about)
        self.Bind(wx.EVT_MENU, self.on_check_update, id=self.id_check_update)
        self.Bind(wx.EVT_MENU, self.on_manual, id=self.id_manual)

    def _post_startup_tasks(self):
        threading.Thread(target=self._load_data_thread, daemon=True).start()

    def _load_data_thread(self):
        self.server = ControlServer(
            on_next_callback=self.view.go_next,
            on_prev_callback=self.view.go_prev,
            on_ready_callback=self._update_ui
        )  # todo: add pswd and port GUI

        self.gl_filters.load_filters()

        wx.CallAfter(self._update_menus_after_load)

    def _update_menus_after_load(self):
        if hasattr(self, '_populate_custom_filters_menu'):
            self._populate_custom_filters_menu()
            self.menubar.Refresh()

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

    def _populate_folder_view_list(self):
        # Ensure we have a valid path
        if not hasattr(self, 'current_folder_path') or not self.current_folder_path or not os.path.exists(
                self.current_folder_path):
            self.fv_listbox.Clear()
            return

        try:
            # List files
            all_files = os.listdir(self.current_folder_path)
        except OSError:
            return

        supported_files = []
        for f in all_files:
            full_path = os.path.join(self.current_folder_path, f)
            if os.path.isfile(full_path):
                ext = os.path.splitext(f)[1].lower()
                if ext in SUPPORTED_EXTENSIONS:
                    supported_files.append(f)

        # Sort
        sort_mode = self.fv_sort_choice.GetSelection()

        if sort_mode == 0:  # A-Z
            supported_files.sort(key=str.lower)
        elif sort_mode == 1:  # Z-A
            supported_files.sort(key=str.lower, reverse=True)
        elif sort_mode == 2 or sort_mode == 3:  # Date
            def get_mtime(fname):
                try:
                    return os.path.getmtime(os.path.join(self.current_folder_path, fname))
                except OSError:
                    return 0

            supported_files.sort(key=get_mtime, reverse=(sort_mode == 2))

        self.fv_listbox.Set(supported_files)

        if self.content_provider:
            current_fname = os.path.basename(self.content_provider.path)
            idx = self.fv_listbox.FindString(current_fname)
            if idx != wx.NOT_FOUND:
                self.fv_listbox.SetSelection(idx)
                self.fv_listbox.EnsureVisible(idx)

    def on_fv_sort(self, evt):
        self._populate_folder_view_list()

    def on_fv_item_activated(self, evt):
        selection_idx = self.fv_listbox.GetSelection()
        if selection_idx != wx.NOT_FOUND:
            fname = self.fv_listbox.GetString(selection_idx)
            full_path = os.path.join(self.current_folder_path, fname)
            if os.path.exists(full_path):
                self._load_file(full_path)

    def on_toggle_server(self, event):
        if self.menu_extctrl.IsChecked():
            self.server.start()
            self._update_ui()
        else:
            self.server.stop()
            self._update_ui()

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

    def _toggle_tree_tooltips(self, enable: bool):
        if not hasattr(self, 'dir_ctrl') or not self.dir_ctrl:
            return

        try:
            tree = self.dir_ctrl.GetTreeCtrl()
            hwnd = tree.GetHandle()

            current_style = ctypes.windll.user32.GetWindowLongW(hwnd, GWL_STYLE)

            if enable:
                new_style = current_style & ~TVS_NOTOOLTIPS
            else:
                new_style = current_style | TVS_NOTOOLTIPS

            if new_style != current_style:
                ctypes.windll.user32.SetWindowLongW(hwnd, GWL_STYLE, new_style)

                # SWP_NOMOVE | SWP_NOSIZE | SWP_NOZORDER | SWP_FRAMECHANGED
                ctypes.windll.user32.SetWindowPos(hwnd, 0, 0, 0, 0, 0, 0x27)
        except Exception:
            print(Exception)

    def on_window_activate(self, evt):
        is_active = evt.GetActive()
        self._toggle_tree_tooltips(is_active)
        evt.Skip()

    def on_fv_hover(self, evt):
        if not self.IsActive():
            evt.Skip()
            return

        pos = evt.GetPosition()
        item_index = self.fv_listbox.HitTest(pos)

        if item_index != wx.NOT_FOUND:
            text = self.fv_listbox.GetString(item_index)
            if self.fv_listbox.GetToolTipText() != text:
                self.fv_listbox.SetToolTip(text)
        else:
            if self.fv_listbox.GetToolTipText():
                self.fv_listbox.UnsetToolTip()

        evt.Skip()

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

        mb = self.menubar

        def _set_enable(mid, val):
            item = self._find_menu_item(mid) if hasattr(self, "_find_menu_item") else None
            if item: item.Enable(val)

        def _set_check(mid, val):
            item = self._find_menu_item(mid) if hasattr(self, "_find_menu_item") else None
            if item: item.Check(val)

        _set_enable(self.id_sidebar_toggle, has_provider)
        _set_check(self.id_sidebar_toggle, self.splitter.IsSplit())

        _set_enable(self.id_font_increase, is_reflowable)
        _set_enable(self.id_font_decrease, is_reflowable)

        _set_enable(wx.ID_CLOSE, has_provider)

        _set_check(self.id_single_page, self.view.mode == PDFView.MODE_SINGLE)
        _set_check(self.id_two_page, self.view.mode == PDFView.MODE_TWO)

        _set_check(self.id_pad_start, self.view.pad_start)
        _set_enable(self.id_pad_start, has_provider and self.view.mode == PDFView.MODE_TWO)

        _set_check(self.id_ltr, self.view.direction == PDFView.DIR_LTR)
        _set_check(self.id_rtl, self.view.direction == PDFView.DIR_RTL)

        for item_id in [self.id_prev, self.id_next, self.id_goto, self.id_zoom_in,
                        self.id_zoom_out, self.id_fit_width, self.id_fit_page]:
            _set_enable(item_id, has_provider)

        _set_check(self.id_fit_width, self.view.zoom_mode == PDFView.ZOOM_FIT_WIDTH)
        _set_check(self.id_fit_page, self.view.zoom_mode == PDFView.ZOOM_FIT_PAGE)
        _set_check(self.id_zoom_manual, self.view.zoom_mode == PDFView.ZOOM_MANUAL)

        server_info = ""
        if self.menu_extctrl.IsChecked():
            try:
                server_info = f"  |  Control: {self.server.get_port()} ({self.server.get_token()})"
            except Exception:
                print("failed to get info")

        if has_provider:
            shown = self.view._spread_pages()

            current_page_display = self.view.page + 1
            total_pages = self.content_provider.page_count
            progress_pct = (current_page_display / total_pages) * 100 if total_pages > 0 else 0

            direction_str = "RTL" if self.view.direction == PDFView.DIR_RTL else "LTR"
            pad_str = " [Padded]" if self.view.pad_start else ""

            status_txt = (f"{os.path.basename(self.content_provider.path)}  |  "
                          f"Page {current_page_display} of {total_pages} ({progress_pct:.1f}%)  |  "
                          f"{direction_str}{pad_str}  |  "
                          f"Zoom: {int(self.view.zoom * 100)}%"
                          f"{server_info}")
            if is_reflowable:
                status_txt += f" | Font Size: {self.epub_font_size}pt"
            self.SetStatusText(status_txt)
        else:
            self.SetStatusText("Welcome to wxReader - File->Open or Drag-and-drop a file to begin.")
            # if self.splitter.IsSplit():
            #     self.splitter.Unsplit(self.sidebar)

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
                self.content_provider = SevenZipContentProvider(path)

        except Exception as e:
            show_toast(self, f"Error opening file: {e}", True)
            if self.content_provider:
                self.content_provider.close()
            self.content_provider = None
            return

        self._populate_sidebar()

        self.view.set_content_provider(self.content_provider)

        if path in self.file_progress:
            saved_page = self.file_progress[path]
            if 0 <= saved_page < self.content_provider.page_count:
                self.view.go_to_page(saved_page)

        self.recent_files = update_recent(self.recent_files, path)

        if not self.splitter.IsSplit():
            self.splitter.SplitVertically(self.sidebar, self.view, 250)
        # if not self.content_provider.get_toc():
        #     self.sidebar_nb.SetSelection(1)
        # else:
        #     self.sidebar_nb.SetSelection(0)

        self._update_ui()
        self.view.SetFocus()

        self.on_nav_current(None)

        self.current_folder_path = os.path.dirname(path)
        self._populate_folder_view_list()

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

    def on_manual(self, evt):
        if hasattr(self, 'manual_window') and self.manual_window:
            try:
                self.manual_window.Raise()
                return
            except RuntimeError:
                # Window was destroyed
                pass

        self.manual_window = ManualDialog(self, lang=self.cur_lang)
        msw_set_theme(self.manual_window)
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
        msw_set_theme(lib_frame)
        lib_frame.Show()

    def on_open_pswdmng(self, evt):
        dlg = PswdManagerDialog(self)
        msw_set_theme(dlg)
        dlg.ShowModal()
        dlg.Destroy()

    def on_show_toc_dialog(self, evt):
        if not self.content_provider:
            return
        toc = self.content_provider.get_toc()
        if not toc:
            show_toast(self, f"No TOC found.")
            return
        dlg = TOCDialog(self, toc, self.view.page, lambda p: (self.view.go_to_page(p), self._update_ui()))
        msw_set_theme(dlg)

        dlg.ShowModal()
        dlg.Destroy()

    def on_show_recent(self, evt):
        dlg = RecentFilesDialog(self, self.recent_files)
        msw_set_theme(dlg)
        dlg.ShowModal()

        updated_recent = dlg.recent_files
        file_to_open = dlg.file_to_open

        dlg.Destroy()

        if updated_recent != self.recent_files:
            self.recent_files = updated_recent

            try:
                cfg = load_config()
                cfg["recent_files"] = self.recent_files
                save_config(cfg)
            except Exception as e:
                print(f"Error saving recent files: {e}")

        if file_to_open:
            wx.CallAfter(self._load_file, file_to_open)

    def on_show_search(self, evt):
        if not self.content_provider:
            show_toast(self, "Please open a document first.")
            return

        def navigate_to_page(page_index):
            self.view.go_to_page(page_index)
            self._update_ui()
            # self.Raise()

        dlg = SearchDialog(self, self.content_provider, navigate_to_page)
        msw_set_theme(dlg)

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
                    header = "=== " + _("Page") + f"{page_idx + 1} ==="
                    extracted_parts.append(f"{header}\n{raw_text}")

            full_text = "\n\n".join(extracted_parts)
            if not full_text.strip():
                full_text = _("<No text found on visible pages.>")

            dlg = TextExtractionDialog(self, text=full_text)
            msw_set_theme(dlg)

            dlg.ShowModal()
            dlg.Destroy()

        except Exception as e:
            show_toast(self, _("Failed to extract text:") + f"{e}", True)

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
            show_toast(self, _("Error extracting images:") + f"{e}", True)
            return
        finally:
            if wx.IsBusy():
                wx.EndBusyCursor()

        if not found_images_data:
            show_toast(self, _("No images found on the visible page(s)."))
            return

        dlg = ImageExtractionDialog(self, found_images_data)
        msw_set_theme(dlg)
        dlg.ShowModal()
        dlg.Destroy()

    def _generate_preview(self, data: bytes, w_orig: int, h_orig: int) -> wx.Bitmap:
        try:
            import pyvips
            img = pyvips.Image.new_from_buffer(data, "")

            if img.hasalpha():
                img = img.flatten(background=[255, 255, 255])
            if img.interpretation != 'srgb':
                img = img.colourspace('srgb')

            scale = 1.0
            if w_orig > 800 or h_orig > 800:
                scale = 800 / max(w_orig, h_orig)
                img = img.resize(scale, kernel='linear')

            mem_buf = img.write_to_memory()
            return wx.Bitmap.FromBuffer(img.width, img.height, mem_buf)

        except Exception as e:
            print(f"[ERROR] libvips preview generation failed: {e}")

        try:
            stream = io.BytesIO(data)
            wx_img = wx.Image(stream)

            if not wx_img.IsOk():
                raise ValueError("Invalid image data")

            if w_orig > 800 or h_orig > 800:
                scale = 800 / max(w_orig, h_orig)
                new_w = int(w_orig * scale)
                new_h = int(h_orig * scale)
                if new_w > 0 and new_h > 0:
                    wx_img = wx_img.Scale(new_w, new_h, wx.IMAGE_QUALITY_HIGH)

            return wx.Bitmap(wx_img)

        except Exception as e:
            print(f"Preview generation error: {e}")
            ph = wx.Image(100, 100)
            ph.SetRGB(wx.Rect(0, 0, 100, 100), 200, 200, 200)
            return wx.Bitmap(ph)

    def on_goto_page(self, evt):
        if not self.content_provider: return
        dlg = wx.TextEntryDialog(self, _("Enter page number") + f" (1-{self.content_provider.page_count}):",
                                 "Go to Page")
        msw_set_theme(dlg)
        if dlg.ShowModal() == wx.ID_OK:
            try:
                val = int(dlg.GetValue())
                if 1 <= val <= self.content_provider.page_count:
                    self.view.go_to_page(val - 1)
                    self._update_ui()
                else:
                    show_toast(self, _("Page number out of range."))
            except ValueError:
                show_toast(self, _("Invalid number."))
        dlg.Destroy()

    def on_edit_keys(self, evt):
        dlg = KeymapDialog(self, self.keybinds)
        msw_set_theme(dlg)

        if dlg.ShowModal() == wx.ID_OK:
            self.keybinds = dlg.GetKeybinds()

            cfg = load_config()
            cfg["keybinds"] = self.keybinds
            save_config(cfg)

            self.Freeze()
            self._build_menus()
            self.Thaw()

            print("[INFO] wxReader Keybinds updated and saved.")

        dlg.Destroy()

    def on_setmg(self, evt):
        dlg = SetMarginGapDialog(self, title=_("Set Margin and Gap"))
        msw_set_theme(dlg)

        if dlg.ShowModal() == wx.ID_OK:
            margin_str, gap_str = dlg.GetValues()
            try:
                m_val = int(margin_str)
                g_val = int(gap_str)

                if 0 <= m_val <= 999 and 0 <= g_val <= 999:
                    self.view.set_margin_gap(m=m_val, g=g_val)
                    self._update_ui()
                else:
                    show_toast(self, _("Numbers must be between 0 and 999."), True)
            except ValueError:
                show_toast(self, _("Please enter integers only."), True)

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

    def on_manual_zoom(self, evt):
        self.view.set_zoom_mode(PDFView.ZOOM_MANUAL)
        self._update_ui()

    def on_quality_change(self, event):
        event_id = event.GetId()
        quality_map = {
            self.id_quality_hq: 2,
            self.id_quality_mq: 1,
            self.id_quality_lq: 0
        }
        self.quality_preference = quality_map.get(event_id, 0)

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

    def on_scrolllock_change(self, evt):
        self.view.is_scroll_locked = not self.view.is_scroll_locked
        _item = self._find_menu_item(self.id_scrolllock)
        _item.Check(self.view.is_scroll_locked)

    def on_background_color(self, evt):
        current_color = self.view.GetBackgroundColour()

        dlg = ModernColorDialog(self, initial_color=current_color, title="Change background color")
        msw_set_theme(dlg)

        if dlg.ShowModal() == wx.ID_OK:
            new_color = dlg.GetColorData().GetColour()
            self.view.set_background_color(new_color)
            self._update_ui()

        dlg.Destroy()

    def on_fullscreen(self, evt):
        is_full = self.IsFullScreen()

        self.ShowFullScreen(not is_full, style=wx.FULLSCREEN_NOBORDER | wx.FULLSCREEN_NOCAPTION)
        self._update_ui()

    def on_filter_settings(self, evt):
        debounce_timer = wx.Timer(self)

        def _do_refresh(timer_evt):
            if hasattr(self.view, '_bmp_cache'):
                self.view._bmp_cache.clear()
            self.view._refresh_layout()
            self.view.Refresh()
            self.view.Update()

        self.Bind(wx.EVT_TIMER, _do_refresh, debounce_timer)

        def _on_change():
            debounce_timer.Start(200, wx.TIMER_ONE_SHOT)

        dlg = FilterSettingsDialog(self, self.gl_filters, _on_change)

        def _on_close_dialog(event):
            if debounce_timer.IsRunning():
                debounce_timer.Stop()
            self.Unbind(wx.EVT_TIMER, debounce_timer)
            event.Skip()

        dlg.Bind(wx.EVT_CLOSE, _on_close_dialog)
        msw_set_theme(dlg)
        dlg.Show()

    def on_check_update(self, evt):
        from wxReaderUpdater import UpdateChecker
        checker = UpdateChecker(self, silent_on_no_update=False)
        checker.check()

    def _on_custom_filter_menu(self, evt, name: str):
        self._select_custom_filter(name)

    def _select_custom_filter(self, name: str | None):
        if self.view:
            self.view.set_custom_filter(name)

        # Update checks on FlatMenuBar
        def _check_id(mid, val):
            item = self._find_menu_item(mid)
            if item: item.Check(val)

        if name is None:
            _check_id(self.id_custom_none, True)
            for fid in self.filter_menu_map.values():
                _check_id(fid, False)
        else:
            _check_id(self.id_custom_none, False)

            for fname, fid in self.filter_menu_map.items():
                should_check = (fname == name)
                _check_id(fid, should_check)

        self._update_ui()

    def on_about(self, event):
        dlg = AboutDialog(self)
        msw_set_theme(dlg)
        dlg.Show()

    def on_lang_change(self, event):
        event_id = event.GetId()
        show_toast(self, message=_("Restart is required."))
        if event_id == self.id_lang_enus:
            self.lang_to_change = wx.LANGUAGE_ENGLISH
        elif event_id == self.id_lang_jajp:
            self.lang_to_change = wx.LANGUAGE_JAPANESE
        elif event_id == self.id_lang_zhsg:
            self.lang_to_change = wx.LANGUAGE_CHINESE_SINGAPORE
        elif event_id == self.id_lang_zhtw:
            self.lang_to_change = wx.LANGUAGE_CHINESE_TAIWAN

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

            cfg["keybinds"] = self.keybinds

            if self.lang_to_change is not None:
                cfg["app_language"] = str(self.lang_to_change)

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

        self.server.stop()

        evt.Skip()


class WxPDFReaderApp(wx.App):
    def __init__(self, redirect=False, filename=None, useBestVisual=False, clearSigInt=True):
        super().__init__(redirect, filename, useBestVisual, clearSigInt)
        self.global_font = None

    def OnInit(self):
        self.global_font = get_app_font()

        lang = wx.LANGUAGE_ENGLISH

        cfg = load_config()
        if "app_language" in cfg:
            lang = cfg.get("app_language", False)
            try:
                lang = int(lang)
            except Exception:
                print(Exception)
                lang = wx.LANGUAGE_ENGLISH
        else:
            lang = wx.LANGUAGE_ENGLISH

        base_path = os.path.dirname(os.path.abspath(__file__))
        locale_dir = os.path.join(base_path, 'locale')
        self.locale = wx.Locale(lang)
        self.locale.AddCatalogLookupPathPrefix(locale_dir)
        self.locale.AddCatalog('messages')

        frame = MainFrame(lang=lang)

        msw_set_theme(frame)

        app_icon = get_app_icon()
        if app_icon.IsOk():
            frame.SetIcon(app_icon)

        frame.Show()

        return True


if __name__ == "__main__":
    app = WxPDFReaderApp(False)
    app.MainLoop()
