from __future__ import annotations

import os

import fitz  # PyMuPDF
import wx
from wx import adv

from wxReaderConfigUtil import load_config, save_config, update_recent
from wxReaderDialog import TOCDialog, TextExtractionDialog, SearchDialog, ImageExtractionDialog
from wxReaderView import PDFView, PDFDocument

APP_NAME = "wxReader"
APP_VERSION = "0.7"




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


class MainFrame(wx.Frame):
    def __init__(self):
        super().__init__(None, title=APP_NAME, size=(1280, 800))
        self.SetMinSize((600, 400))

        # Initialize state
        self.pdf: PDFDocument | None = None
        self.file_history = wx.FileHistory(12)

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
        btn_sizer = wx.BoxSizer(wx.HORIZONTAL)

        self.btn_go_up = wx.Button(self.files_panel, label="Go Up", size=(-1, 26))
        self.btn_sync_file = wx.Button(self.files_panel, label="Current File", size=(-1, 26))

        btn_sizer.Add(self.btn_go_up, 1, wx.RIGHT, 2)
        btn_sizer.Add(self.btn_sync_file, 1, wx.LEFT, 2)

        files_sizer.Add(btn_sizer, 0, wx.EXPAND | wx.ALL, 5)

        # Directory
        wildcard = "Supported|*.pdf;*.epub;*.mobi;*.fb2;*.cbz;*.txt|All files|*.*"
        self.dir_ctrl = wx.GenericDirCtrl(self.files_panel, dir=os.getcwd(), filter=wildcard,
                                          style=wx.DIRCTRL_SHOW_FILTERS | wx.DIRCTRL_3D_INTERNAL)

        files_sizer.Add(self.dir_ctrl, 1, wx.EXPAND | wx.LEFT | wx.RIGHT | wx.BOTTOM, 0)
        self.files_panel.SetSizer(files_sizer)

        self.sidebar_nb.AddPage(self.files_panel, "Files")

        self.sidebar_main_sizer.Add(self.sidebar_nb, 1, wx.EXPAND)
        self.sidebar.SetSizer(self.sidebar_main_sizer)

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
        self.file_progress = cfg.get("file_progress", {})

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

        for p in reversed(self.recent_files):
            if p and os.path.isfile(p):
                self.file_history.AddFileToHistory(p)

        if last and os.path.isfile(last):
            wx.CallAfter(self._load_pdf, last)

        # --- Events ---
        self.Bind(wx.EVT_CLOSE, self.on_close)
        self.sidebar_tree.Bind(wx.EVT_TREE_ITEM_ACTIVATED, self.on_sidebar_click)
        self.sidebar_search.Bind(wx.EVT_TEXT, self.on_sidebar_search)
        self.Bind(wx.EVT_BUTTON, self.on_nav_go_up, self.btn_go_up)
        self.Bind(wx.EVT_BUTTON, self.on_nav_current, self.btn_sync_file)
        self.Bind(wx.EVT_DIRCTRL_FILEACTIVATED, self.on_file_browser_activated, self.dir_ctrl)
        self.Bind(wx.EVT_MENU, self.on_switch_sidebar_tab, id=self.id_switch_tab)

        self.SetDropTarget(FileDropTarget(self))

        self._update_ui()

    def _build_menus(self):
        menubar = wx.MenuBar()

        # --- File ---
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

        # --- View ---
        m_view = wx.Menu()

        self.id_sidebar_toggle = wx.NewIdRef()
        m_view.AppendCheckItem(self.id_sidebar_toggle, "Show &Sidebar\tF9")
        self.id_switch_tab = wx.NewIdRef()
        m_view.Append(self.id_switch_tab, "Switch Sidebar Tab\tF8")
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

        self.id_zoom_in = wx.NewIdRef()
        self.id_zoom_out = wx.NewIdRef()
        self.id_fit_width = wx.NewIdRef()
        self.id_fit_page = wx.NewIdRef()

        m_view.Append(self.id_zoom_in, "Zoom &In\tCtrl++")
        m_view.Append(self.id_zoom_out, "Zoom &Out\tCtrl+-")
        m_view.AppendSeparator()
        m_view.AppendRadioItem(self.id_fit_width, "Fit &Width\tCtrl+1")
        m_view.AppendRadioItem(self.id_fit_page, "Fit &Page\tCtrl+0")

        m_view.AppendSeparator()
        self.id_bg = wx.NewIdRef()
        m_view.Append(self.id_bg, "Background Color…")

        m_view.AppendSeparator()
        self.id_font_increase = wx.NewIdRef()
        self.id_font_decrease = wx.NewIdRef()
        m_view.Append(self.id_font_increase, "Larger Font\tCtrl+Shift++")
        m_view.Append(self.id_font_decrease, "Smaller Font\tCtrl+Shift+-")

        m_view.AppendSeparator()
        self.id_fullscreen = wx.NewIdRef()
        m_view.AppendCheckItem(self.id_fullscreen, "Full &Screen\tF11")

        menubar.Append(m_view, "&View")

        # --- Navigate ---
        m_nav = wx.Menu()

        self.id_prev = wx.NewIdRef()
        self.id_next = wx.NewIdRef()
        self.id_goto = wx.NewIdRef()
        m_nav.Append(self.id_prev, "Previous Page\tLeft")
        m_nav.Append(self.id_next, "Next Page\tRight")
        m_nav.Append(self.id_goto, "&Go to Page...\tCtrl+G")

        m_nav.AppendSeparator()

        self.id_search = wx.NewIdRef()
        m_nav.Append(self.id_search, "&Find...\tCtrl+F")

        self.id_show_toc_dialog = wx.NewIdRef()
        m_nav.Append(self.id_show_toc_dialog, "Show TOC Dialog...\tCtrl+T")

        menubar.Append(m_nav, "&Navigate")

        # --- Process ---
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

        self.id_extract_images = wx.NewIdRef()
        m_process.Append(self.id_extract_images, "Extract Page Images...")

        menubar.Append(m_process, "&Process")

        # --- Help ---
        m_help = wx.Menu()
        m_about = m_help.Append(wx.ID_ABOUT, "&About")
        menubar.Append(m_help, "&Help")

        self.SetMenuBar(menubar)
        self.file_history.UseMenu(self.m_recent)
        self.file_history.AddFilesToMenu(self.m_recent)

        # --- Bindings ---
        self.Bind(wx.EVT_MENU, self.on_open, m_open)
        self.Bind(wx.EVT_MENU, self.on_close_pdf, m_close)
        self.Bind(wx.EVT_MENU_RANGE, self.on_open_recent, id=wx.ID_FILE1, id2=wx.ID_FILE9)
        self.Bind(wx.EVT_MENU, self.on_clear_history, id=self.id_clear_history)
        self.Bind(wx.EVT_MENU, lambda e: self.Close(), m_exit)

        # View Bindings
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
        self.Bind(wx.EVT_MENU, self.on_background_color, id=int(self.id_bg))
        self.Bind(wx.EVT_MENU, self.on_change_epub_font, id=self.id_font_increase)
        self.Bind(wx.EVT_MENU, self.on_change_epub_font, id=self.id_font_decrease)
        self.Bind(wx.EVT_MENU, self.on_fullscreen, id=self.id_fullscreen)

        # Navigate Bindings
        self.Bind(wx.EVT_MENU, lambda e: self.view.go_prev(), id=self.id_prev)
        self.Bind(wx.EVT_MENU, lambda e: self.view.go_next(), id=self.id_next)
        self.Bind(wx.EVT_MENU, self.on_goto_page, id=self.id_goto)
        self.Bind(wx.EVT_MENU, self.on_show_search, id=self.id_search)
        self.Bind(wx.EVT_MENU, self.on_show_toc_dialog, id=self.id_show_toc_dialog)

        # Process Bindings
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
        self.Bind(wx.EVT_MENU, self.on_extract_images, id=self.id_extract_images)

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
        if self.pdf and self.pdf.path:
            self.file_progress[self.pdf.path] = self.view.page
            self.pdf.close()

        try:
            self.pdf = PDFDocument(path)
            self._restore_epub_font()
        except Exception as e:
            wx.MessageBox(f"Error: {e}")
            return

        self.view.set_document(self.pdf)

        if path in self.file_progress:
            saved_page = self.file_progress[path]
            if 0 <= saved_page < self.pdf.page_count:
                self.view.go_to_page(saved_page)

        self.recent_files = update_recent(self.recent_files, path, limit=12)
        self.file_history.AddFileToHistory(path)

        self._populate_sidebar()

        if self.pdf.get_toc() and not self.splitter.IsSplit():
            self.splitter.SplitVertically(self.sidebar, self.view, 250)

        self._update_ui()
        self.view.SetFocus()

        self.on_nav_current(None)

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

    def on_show_search(self, evt):
        if not self.pdf:
            wx.MessageBox("Please open a document first.", "No Document")
            return

        def navigate_to_page(page_index):
            self.view.go_to_page(page_index)
            self._update_ui()
            # self.Raise()

        dlg = SearchDialog(self, self.pdf, navigate_to_page)
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
        if self.pdf and self.pdf.path:
            folder = os.path.dirname(self.pdf.path)
            if os.path.exists(folder):
                self.dir_ctrl.SetPath(folder)
                self.dir_ctrl.SetPath(self.pdf.path)

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
            self._load_pdf(filepath)

    def on_switch_sidebar_tab(self, evt):
        if not self.splitter.IsSplit():
            return

        count = self.sidebar_nb.GetPageCount()
        if count > 1:
            current = self.sidebar_nb.GetSelection()
            next_page = (current + 1) % count
            self.sidebar_nb.SetSelection(next_page)

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

    def on_extract_images(self, evt):
        if not self.pdf:
            return

        visible_pages = self.view._spread_pages()
        found_images = []

        wx.BeginBusyCursor()
        try:
            import io

            for page_idx in visible_pages:
                if page_idx < 0 or page_idx >= self.pdf.page_count:
                    continue

                page = self.pdf.doc.load_page(page_idx)

                # Reflowable Documents
                if self.pdf.doc.is_reflowable:
                    blocks = page.get_text("dict")["blocks"]
                    image_blocks = [b for b in blocks if b["type"] == 1]

                    for idx, block in enumerate(image_blocks):
                        image_bytes = block["image"]
                        ext = block["ext"]
                        w_orig = block["width"]
                        h_orig = block["height"]

                        desc = f"Pg {page_idx + 1} - Img {idx + 1} ({w_orig}x{h_orig}, {ext})"

                        bmp = self._generate_preview(None, image_bytes, w_orig, h_orig)

                        found_images.append({
                            "desc": desc,
                            "bitmap": bmp,
                            "bytes": image_bytes,
                            "ext": ext
                        })

                # Fixed Layout Documents
                else:
                    img_info_list = page.get_images(full=True)

                    for idx, img_info in enumerate(img_info_list):
                        xref = img_info[0]

                        base_image = self.pdf.doc.extract_image(xref)
                        image_bytes = base_image["image"]
                        ext = base_image["ext"]
                        w_orig, h_orig = base_image["width"], base_image["height"]

                        desc = f"Pg {page_idx + 1} - Img {idx + 1} ({w_orig}x{h_orig}, {ext})"

                        bmp = self._generate_preview(xref, None, w_orig, h_orig)

                        found_images.append({
                            "desc": desc,
                            "bitmap": bmp,
                            "bytes": image_bytes,
                            "ext": ext
                        })

        except Exception as e:
            wx.EndBusyCursor()
            wx.MessageBox(f"Error extracting images: {e}", "Error")
            return

        wx.EndBusyCursor()

        if not found_images:
            wx.MessageBox("No images found on the visible page(s).", "Info")
            return

        dlg = ImageExtractionDialog(self, found_images)
        dlg.ShowModal()
        dlg.Destroy()

    def _generate_preview(self, xref, data, w_orig, h_orig):
        try:
            if xref is not None:
                # PDF Path: Load from XREF
                pix = fitz.Pixmap(self.pdf.doc, xref)
            else:
                # EPUB Path: Load from raw bytes
                pix = fitz.Pixmap(data)

            if pix.n - pix.alpha > 3:
                pix = fitz.Pixmap(fitz.csRGB, pix)

            png_data = pix.tobytes()

            import io
            stream = io.BytesIO(png_data)
            wx_img = wx.Image(stream)

            if not wx_img.IsOk():
                raise ValueError("Converted image data is invalid.")

            if w_orig > 800 or h_orig > 800:
                scale = 800 / max(w_orig, h_orig)
                preview_w = int(w_orig * scale)
                preview_h = int(h_orig * scale)
                wx_img = wx_img.Scale(preview_w, preview_h, wx.IMAGE_QUALITY_HIGH)

            return wx.Bitmap(wx_img)

        except Exception as e:
            print(f"Preview generation warning: {e}")
            # a grey placeholder
            ph = wx.Image(100, 100)
            ph.SetRGB(wx.Rect(0, 0, 100, 100), 200, 200, 200)
            return wx.Bitmap(ph)

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
        if self.pdf and self.view:
            self.file_progress[self.pdf.path] = self.view.page

        if self.view:
            self.view.stop_worker()
            self.view.pdf = None
            self.view._bmp_cache.clear()

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
                "file_progress": self.file_progress,
            }

            save_config(cfg)
            print("Configuration saved successfully.")

        except Exception as e:
            print(f"Save failed: {e}")

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
