from __future__ import annotations

import colorsys
import os

import wx
import wx.dataview as dv
from wx import adv

from wxReaderString import *
from wxReaderIcon import get_app_font


class TOCDialog(wx.Dialog):
    def __init__(self, parent, toc_list, current_page_idx, on_navigate_callback):
        super().__init__(parent, title="Table of Contents", size=(450, 650),
                         style=wx.DEFAULT_DIALOG_STYLE | wx.RESIZE_BORDER)

        self.SetFont(get_app_font())

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


class TextExtractionDialog(wx.Dialog):
    def __init__(self, parent, text, title="Page Text"):
        super().__init__(parent, title=title, size=(600, 500),
                         style=wx.DEFAULT_DIALOG_STYLE | wx.RESIZE_BORDER)

        sizer = wx.BoxSizer(wx.VERTICAL)

        self.text_ctrl = wx.TextCtrl(self, value=text,
                                     style=wx.TE_MULTILINE | wx.TE_READONLY | wx.HSCROLL)

        self.text_ctrl.SetFont(get_app_font())

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


class ImageExtractionDialog(wx.Dialog):
    def __init__(self, parent, image_list):
        """
          {
            "desc": str (listbox label),
            "bitmap": wx.Bitmap (for preview),
            "bytes": bytes (raw data),
            "ext": str (e.g. 'jpeg', 'png')
          }
        """
        super().__init__(parent, title="Extract Images", size=(700, 500),
                         style=wx.DEFAULT_DIALOG_STYLE | wx.RESIZE_BORDER)

        self.SetFont(get_app_font())

        self.image_list = image_list
        self.current_sel = 0

        main_sizer = wx.BoxSizer(wx.HORIZONTAL)

        # Left: ListBox
        left_sizer = wx.BoxSizer(wx.VERTICAL)
        choices = [img['desc'] for img in self.image_list]
        self.list_box = wx.ListBox(self, choices=choices, style=wx.LB_SINGLE)
        if choices:
            self.list_box.SetSelection(0)

        left_sizer.Add(wx.StaticText(self, label="Detected Images:"), 0, wx.ALL, 5)
        left_sizer.Add(self.list_box, 1, wx.EXPAND | wx.ALL, 5)

        # Right: Preview
        right_sizer = wx.BoxSizer(wx.VERTICAL)

        self.scroll_win = wx.ScrolledWindow(self, style=wx.BORDER_SUNKEN)
        self.scroll_win.SetScrollRate(10, 10)
        self.preview_bmp = wx.StaticBitmap(self.scroll_win, wx.ID_ANY, wx.NullBitmap)

        scroll_sizer = wx.BoxSizer(wx.VERTICAL)
        scroll_sizer.Add(self.preview_bmp, 0, wx.ALL, 10)
        self.scroll_win.SetSizer(scroll_sizer)

        right_sizer.Add(wx.StaticText(self, label="Preview:"), 0, wx.ALL, 5)
        right_sizer.Add(self.scroll_win, 1, wx.EXPAND | wx.ALL, 5)

        # Buttons
        btn_sizer = wx.BoxSizer(wx.HORIZONTAL)
        self.btn_copy = wx.Button(self, label="Copy")
        self.btn_save = wx.Button(self, label="Save to...")
        btn_close = wx.Button(self, wx.ID_CANCEL, "Close")

        btn_sizer.Add(self.btn_copy, 0, wx.RIGHT, 10)
        btn_sizer.Add(self.btn_save, 0, wx.RIGHT, 10)
        btn_sizer.Add(btn_close, 0)

        right_sizer.Add(btn_sizer, 0, wx.ALIGN_RIGHT | wx.ALL, 10)

        main_sizer.Add(left_sizer, 1, wx.EXPAND | wx.ALL, 5)
        main_sizer.Add(right_sizer, 2, wx.EXPAND | wx.ALL, 5)

        self.SetSizer(main_sizer)

        # --- Bindings ---
        self.list_box.Bind(wx.EVT_LISTBOX, self.on_select)
        self.btn_copy.Bind(wx.EVT_BUTTON, self.on_copy)
        self.btn_save.Bind(wx.EVT_BUTTON, self.on_save)

        self.update_preview()

    def update_preview(self):
        sel = self.list_box.GetSelection()
        if sel != wx.NOT_FOUND and sel < len(self.image_list):
            self.current_sel = sel
            bmp = self.image_list[sel]['bitmap']
            self.preview_bmp.SetBitmap(bmp)

            self.scroll_win.SetVirtualSize(bmp.GetSize())
            self.scroll_win.Refresh()
        else:
            self.preview_bmp.SetBitmap(wx.NullBitmap)

    def on_select(self, evt):
        self.update_preview()

    def on_copy(self, evt):
        if self.current_sel < 0 or self.current_sel >= len(self.image_list):
            return

        bmp_obj = wx.BitmapDataObject(self.image_list[self.current_sel]['bitmap'])
        if wx.TheClipboard.Open():
            wx.TheClipboard.SetData(bmp_obj)
            wx.TheClipboard.Close()
        else:
            wx.MessageBox("Could not access clipboard.", "Error")

    def on_save(self, evt):
        if self.current_sel < 0 or self.current_sel >= len(self.image_list):
            return

        img_data = self.image_list[self.current_sel]
        ext = img_data['ext']
        default_name = f"extracted_image_{self.current_sel + 1}.{ext}"
        wildcard = f"{ext.upper()} files (*.{ext})|*.{ext}|All files (*.*)|*.*"

        with wx.FileDialog(self, "Save Image", defaultFile=default_name,
                           wildcard=wildcard, style=wx.FD_SAVE | wx.FD_OVERWRITE_PROMPT) as dlg:
            if dlg.ShowModal() == wx.ID_OK:
                path = dlg.GetPath()
                try:
                    with open(path, "wb") as f:
                        f.write(img_data['bytes'])
                    wx.MessageBox(f"Saved to {path}", "Success")
                except Exception as e:
                    wx.MessageBox(f"Failed to save file:\n{e}", "Error")


class SearchDialog(wx.Dialog):
    def __init__(self, parent, pdf_doc, navigation_callback):
        super().__init__(parent, title="Search Document", size=(600, 450),
                         style=wx.DEFAULT_DIALOG_STYLE | wx.RESIZE_BORDER)

        self.SetFont(get_app_font())

        self.pdf_doc = pdf_doc
        self.nav_cb = navigation_callback

        panel = wx.Panel(self)
        main_sizer = wx.BoxSizer(wx.VERTICAL)

        # top bar
        top_sizer = wx.BoxSizer(wx.HORIZONTAL)

        self.search_input = wx.SearchCtrl(panel, style=wx.TE_PROCESS_ENTER)
        self.search_input.SetDescriptiveText("Type text to search...")

        self.btn_find = wx.Button(panel, label="Find")

        top_sizer.Add(self.search_input, 1, wx.EXPAND | wx.RIGHT, 5)
        top_sizer.Add(self.btn_find, 0, wx.ALIGN_CENTER_VERTICAL)

        main_sizer.Add(top_sizer, 0, wx.EXPAND | wx.ALL, 10)

        # results list
        self.result_list = wx.ListCtrl(panel, style=wx.LC_REPORT | wx.LC_SINGLE_SEL | wx.LC_VRULES | wx.LC_HRULES)
        self.result_list.InsertColumn(0, "Page", width=60)
        self.result_list.InsertColumn(1, "Context Snippet", width=480)

        main_sizer.Add(self.result_list, 1, wx.EXPAND | wx.LEFT | wx.RIGHT, 10)

        # status bar
        self.lbl_status = wx.StaticText(panel, label="Ready")
        main_sizer.Add(self.lbl_status, 0, wx.EXPAND | wx.ALL, 10)

        panel.SetSizer(main_sizer)

        # --- Events ---
        self.Bind(wx.EVT_BUTTON, self.on_search, self.btn_find)
        self.search_input.Bind(wx.EVT_TEXT_ENTER, self.on_search)
        self.search_input.Bind(wx.EVT_SEARCHCTRL_SEARCH_BTN, self.on_search)
        self.result_list.Bind(wx.EVT_LIST_ITEM_ACTIVATED, self.on_item_activated)

        self.CenterOnParent()
        wx.CallAfter(self.search_input.SetFocus)

    def on_search(self, evt):
        query = self.search_input.GetValue().strip()
        if not query:
            return

        self.result_list.DeleteAllItems()
        self.lbl_status.SetLabel("Searching...")
        self.btn_find.Disable()

        wx.Yield()

        results_count = 0
        query_lower = query.lower()

        # todo: move it to run in a separate thread.
        for i in range(self.pdf_doc.page_count):

            # temp workaround
            if i % 10 == 0:
                wx.Yield()

            try:
                page = self.pdf_doc.doc.load_page(i)
                text = page.get_text("text")

                if not text:
                    continue

                text_lower = text.lower()
                start_idx = 0

                while True:
                    idx = text_lower.find(query_lower, start_idx)
                    if idx == -1:
                        break

                    ctx_start = max(0, idx - 30)
                    ctx_end = min(len(text), idx + len(query) + 30)

                    raw_snippet = text[ctx_start:ctx_end]
                    clean_snippet = raw_snippet.replace('\n', ' ').replace('\r', '')
                    display_snippet = f"...{clean_snippet}..."

                    list_idx = self.result_list.InsertItem(self.result_list.GetItemCount(), str(i + 1))
                    self.result_list.SetItem(list_idx, 1, display_snippet)
                    self.result_list.SetItemData(list_idx, i)

                    results_count += 1
                    start_idx = idx + len(query)

            except Exception as e:
                print(f"Search error on page {i}: {e}")

        self.lbl_status.SetLabel(f"Search complete. Found {results_count} matches.")
        self.btn_find.Enable()
        self.search_input.SetFocus()

    def on_item_activated(self, evt):
        list_idx = evt.GetIndex()
        page_index = self.result_list.GetItemData(list_idx)

        if self.nav_cb:
            self.nav_cb(page_index)


class SetMarginGapDialog(wx.Dialog):
    def __init__(self, parent, title, default_margin="1", default_gap="1"):
        super(SetMarginGapDialog, self).__init__(parent, title=title)

        self.SetFont(get_app_font())

        vbox = wx.BoxSizer(wx.VERTICAL)

        # Margin
        hbox1 = wx.BoxSizer(wx.HORIZONTAL)
        label1 = wx.StaticText(self, label="Margin:")
        hbox1.Add(label1, flag=wx.RIGHT | wx.ALIGN_CENTER_VERTICAL, border=8)
        self.margin_ctrl = wx.TextCtrl(self, value=default_margin)
        hbox1.Add(self.margin_ctrl, proportion=1)
        vbox.Add(hbox1, flag=wx.EXPAND | wx.ALL, border=10)

        # Gap
        hbox2 = wx.BoxSizer(wx.HORIZONTAL)
        label2 = wx.StaticText(self, label="Gap:")
        hbox2.Add(label2, flag=wx.RIGHT | wx.ALIGN_CENTER_VERTICAL, border=8)
        self.gap_ctrl = wx.TextCtrl(self, value=default_gap)
        hbox2.Add(self.gap_ctrl, proportion=1)
        vbox.Add(hbox2, flag=wx.EXPAND | wx.LEFT | wx.RIGHT | wx.BOTTOM, border=10)

        sdb = self.CreateStdDialogButtonSizer(wx.OK | wx.CANCEL)
        vbox.Add(sdb, flag=wx.ALIGN_CENTER | wx.ALL, border=10)

        self.SetSizer(vbox)
        self.Fit()

    def GetValues(self):
        """Returns the entered margin and gap values."""
        return self.margin_ctrl.GetValue(), self.gap_ctrl.GetValue()


class ColorPreviewPanel(wx.Panel):
    def __init__(self, parent, old_color, new_color):
        super().__init__(parent, size=(100, 100))
        self.SetFont(get_app_font())

        self.old_color = old_color
        self.new_color = new_color
        self.SetBackgroundStyle(wx.BG_STYLE_PAINT)
        self.Bind(wx.EVT_PAINT, self.OnPaint)

    def UpdateNewColor(self, color):
        self.new_color = color
        self.Refresh()

    def OnPaint(self, evt):
        dc = wx.AutoBufferedPaintDC(self)
        w, h = self.GetSize()

        dc.SetPen(wx.Pen(self.old_color))
        dc.SetBrush(wx.Brush(self.old_color))
        dc.DrawRectangle(0, 0, w, h // 2)

        dc.SetPen(wx.Pen(self.new_color))
        dc.SetBrush(wx.Brush(self.new_color))
        dc.DrawRectangle(0, h // 2, w, h - (h // 2))

        dc.SetPen(wx.Pen(wx.Colour(100, 100, 100)))
        dc.SetBrush(wx.Brush(wx.Colour(0, 0, 0), wx.TRANSPARENT))
        dc.DrawRectangle(0, 0, w, h)

        dc.SetTextForeground(wx.WHITE if sum(self.old_color[:3]) < 382 else wx.BLACK)
        dc.DrawText("Current", 5, 5)

        dc.SetTextForeground(wx.WHITE if sum(self.new_color[:3]) < 382 else wx.BLACK)
        dc.DrawText("New", 5, h // 2 + 5)


class ModernColorDialog(wx.Dialog):
    def __init__(self, parent, initial_color=wx.BLACK, title="Select Color"):
        super().__init__(parent, title=title, style=wx.DEFAULT_DIALOG_STYLE | wx.RESIZE_BORDER)

        self.color = wx.Colour(initial_color)
        self.initial_color = self.color
        self._updating = False

        self.SetFont(get_app_font())

        # Layout
        main_sizer = wx.BoxSizer(wx.VERTICAL)
        content_sizer = wx.BoxSizer(wx.HORIZONTAL)

        self.preview = ColorPreviewPanel(self, self.initial_color, self.color)
        content_sizer.Add(self.preview, 0, wx.ALL | wx.EXPAND, 10)

        controls_sizer = wx.BoxSizer(wx.VERTICAL)

        sb_rgb = wx.StaticBoxSizer(wx.VERTICAL, self, "RGB")
        self.sl_r, self.sp_r = self._create_slider_row(sb_rgb, "R", 0, 255, self.OnRGBChanged)
        self.sl_g, self.sp_g = self._create_slider_row(sb_rgb, "G", 0, 255, self.OnRGBChanged)
        self.sl_b, self.sp_b = self._create_slider_row(sb_rgb, "B", 0, 255, self.OnRGBChanged)
        controls_sizer.Add(sb_rgb, 0, wx.EXPAND | wx.BOTTOM, 5)

        sb_hsb = wx.StaticBoxSizer(wx.VERTICAL, self, "HSB (HSV)")
        self.sl_h, self.sp_h = self._create_slider_row(sb_hsb, "H", 0, 360, self.OnHSBChanged)
        self.sl_s, self.sp_s = self._create_slider_row(sb_hsb, "S", 0, 100, self.OnHSBChanged)
        self.sl_v, self.sp_v = self._create_slider_row(sb_hsb, "B", 0, 100, self.OnHSBChanged)
        controls_sizer.Add(sb_hsb, 0, wx.EXPAND | wx.BOTTOM, 5)

        content_sizer.Add(controls_sizer, 1, wx.EXPAND | wx.ALL, 5)
        main_sizer.Add(content_sizer, 1, wx.EXPAND | wx.ALL, 5)

        hex_sizer = wx.BoxSizer(wx.HORIZONTAL)
        hex_sizer.Add(wx.StaticText(self, label="Hex Code: #"), 0, wx.ALIGN_CENTER_VERTICAL | wx.RIGHT, 5)
        self.hex_ctrl = wx.TextCtrl(self, size=(80, -1))
        self.hex_ctrl.Bind(wx.EVT_TEXT, self.OnHexChanged)
        hex_sizer.Add(self.hex_ctrl, 0, wx.ALIGN_CENTER_VERTICAL)

        main_sizer.Add(hex_sizer, 0, wx.ALIGN_CENTER | wx.BOTTOM, 10)

        btn_sizer = wx.StdDialogButtonSizer()
        btn_sizer.AddButton(wx.Button(self, wx.ID_OK))
        btn_sizer.AddButton(wx.Button(self, wx.ID_CANCEL))
        btn_sizer.Realize()
        main_sizer.Add(btn_sizer, 0, wx.ALIGN_RIGHT | wx.ALL, 10)

        self.SetSizer(main_sizer)
        self.Fit()

        self._sync_ui_from_color(self.color)
        self.CenterOnParent()

    def _create_slider_row(self, sizer, label, min_val, max_val, handler):
        row = wx.BoxSizer(wx.HORIZONTAL)
        row.Add(wx.StaticText(self, label=label, size=(15, -1)), 0, wx.ALIGN_CENTER_VERTICAL)

        slider = wx.Slider(self, minValue=min_val, maxValue=max_val, size=(150, -1))
        slider.Bind(wx.EVT_SLIDER, handler)
        row.Add(slider, 1, wx.ALIGN_CENTER_VERTICAL | wx.LEFT | wx.RIGHT, 5)

        spin = wx.SpinCtrl(self, min=min_val, max=max_val, size=(60, -1))
        spin.Bind(wx.EVT_SPINCTRL, handler)
        row.Add(spin, 0, wx.ALIGN_CENTER_VERTICAL)

        sizer.Add(row, 0, wx.EXPAND | wx.ALL, 2)
        return slider, spin

    def GetColorData(self):
        class Data:
            def __init__(self, c): self.c = c

            def GetColour(self): return self.c

        return Data(self.color)

    def _sync_ui_from_color(self, color):
        self._updating = True

        r, g, b = color.Red(), color.Green(), color.Blue()

        for ctrl in [self.sl_r, self.sp_r]: ctrl.SetValue(r)
        for ctrl in [self.sl_g, self.sp_g]: ctrl.SetValue(g)
        for ctrl in [self.sl_b, self.sp_b]: ctrl.SetValue(b)

        h, s, v = colorsys.rgb_to_hsv(r / 255.0, g / 255.0, b / 255.0)
        h_deg = int(h * 360)
        s_per = int(s * 100)
        v_per = int(v * 100)

        for ctrl in [self.sl_h, self.sp_h]: ctrl.SetValue(h_deg)
        for ctrl in [self.sl_s, self.sp_s]: ctrl.SetValue(s_per)
        for ctrl in [self.sl_v, self.sp_v]: ctrl.SetValue(v_per)

        if self.FindFocus() != self.hex_ctrl:
            self.hex_ctrl.SetValue(f"{r:02X}{g:02X}{b:02X}")

        self.preview.UpdateNewColor(color)

        self._updating = False

    def OnRGBChanged(self, evt):
        if self._updating: return
        r = self.sl_r.GetValue() if isinstance(evt.GetEventObject(), wx.Slider) else self.sp_r.GetValue()
        g = self.sl_g.GetValue() if isinstance(evt.GetEventObject(), wx.Slider) else self.sp_g.GetValue()
        b = self.sl_b.GetValue() if isinstance(evt.GetEventObject(), wx.Slider) else self.sp_b.GetValue()

        self.color = wx.Colour(r, g, b)
        self._sync_ui_from_color(self.color)

    def OnHSBChanged(self, evt):
        if self._updating: return

        h_deg = self.sl_h.GetValue() if isinstance(evt.GetEventObject(), wx.Slider) else self.sp_h.GetValue()
        s_per = self.sl_s.GetValue() if isinstance(evt.GetEventObject(), wx.Slider) else self.sp_s.GetValue()
        v_per = self.sl_v.GetValue() if isinstance(evt.GetEventObject(), wx.Slider) else self.sp_v.GetValue()

        r_f, g_f, b_f = colorsys.hsv_to_rgb(h_deg / 360.0, s_per / 100.0, v_per / 100.0)

        self.color = wx.Colour(int(r_f * 255), int(g_f * 255), int(b_f * 255))
        self._sync_ui_from_color(self.color)

    def OnHexChanged(self, evt):
        if self._updating: return

        hex_val = self.hex_ctrl.GetValue().strip().lstrip('#')
        if len(hex_val) == 6:
            try:
                r = int(hex_val[0:2], 16)
                g = int(hex_val[2:4], 16)
                b = int(hex_val[4:6], 16)
                self.color = wx.Colour(r, g, b)

                self._updating = True

                # RGB
                for ctrl in [self.sl_r, self.sp_r]: ctrl.SetValue(r)
                for ctrl in [self.sl_g, self.sp_g]: ctrl.SetValue(g)
                for ctrl in [self.sl_b, self.sp_b]: ctrl.SetValue(b)

                # HSB
                h, s, v = colorsys.rgb_to_hsv(r / 255.0, g / 255.0, b / 255.0)
                for ctrl in [self.sl_h, self.sp_h]: ctrl.SetValue(int(h * 360))
                for ctrl in [self.sl_s, self.sp_s]: ctrl.SetValue(int(s * 100))
                for ctrl in [self.sl_v, self.sp_v]: ctrl.SetValue(int(v * 100))

                self.preview.UpdateNewColor(self.color)
                self._updating = False

            except ValueError:
                pass


class AboutDialog(wx.Dialog):
    def __init__(self, parent):
        super().__init__(parent, title="About", style=wx.DEFAULT_DIALOG_STYLE)

        self.SetBackgroundColour(wx.WHITE)
        self.SetFont(get_app_font())

        wrapper = wx.BoxSizer(wx.VERTICAL)
        main_sizer = wx.BoxSizer(wx.VERTICAL)

        if os.path.exists("icon.png"):
            img = wx.Image("icon.png", wx.BITMAP_TYPE_ANY)
            img.Rescale(48, 48, wx.IMAGE_QUALITY_HIGH)

            icon_img = wx.StaticBitmap(self, bitmap=wx.Bitmap(img))
            main_sizer.Add(icon_img, 0, wx.CENTER | wx.BOTTOM, 5)

        lbl_name = wx.StaticText(self, label=APP_NAME)
        lbl_name.SetFont(get_app_font(4))
        main_sizer.Add(lbl_name, 0, wx.CENTER | wx.BOTTOM, 2)

        lbl_ver = wx.StaticText(self, label=f"Version {APP_VERSION}")
        lbl_ver.SetForegroundColour(wx.Colour(100, 100, 100))
        main_sizer.Add(lbl_ver, 0, wx.CENTER)

        line = wx.StaticLine(self)
        main_sizer.Add(line, 0, wx.EXPAND | wx.TOP | wx.BOTTOM, 10)

        tech_sizer = wx.FlexGridSizer(cols=3, hgap=10, vgap=4)

        def _add_tech_row(label, value, license_name=""):
            l1 = wx.StaticText(self, label=label)
            l2 = wx.StaticText(self, label=value)
            l3 = wx.StaticText(self, label=license_name)
            l3.SetForegroundColour(wx.Colour(120, 120, 120))

            tech_sizer.Add(l1, 0, wx.ALIGN_LEFT | wx.ALIGN_CENTER_VERTICAL)
            tech_sizer.Add(l2, 0, wx.ALIGN_LEFT | wx.ALIGN_CENTER_VERTICAL)
            tech_sizer.Add(l3, 0, wx.ALIGN_LEFT | wx.ALIGN_CENTER_VERTICAL)

        _add_tech_row("GUI kit:", f"wxPython (wxWidgets 3.2.8)", "LGPL")
        _add_tech_row("PDF engine:", "PyMuPDF 1.23.8", "AGPL")
        _add_tech_row("Post process:", "OpenGL (PyOpenGL)", "BSD")
        _add_tech_row("Image:", "pyvips (libvips)", "LGPL")
        _add_tech_row("Runtime:", "Python 3.12.9", "PSFL")

        main_sizer.Add(tech_sizer, 0, wx.CENTER)

        main_sizer.AddSpacer(10)

        link = adv.HyperlinkCtrl(self, label="Visit GitHub Repository", url="https://github.com/puff-dayo/wxReader/")
        main_sizer.Add(link, 0, wx.CENTER | wx.BOTTOM, 10)

        btn = wx.Button(self, wx.ID_OK, label="Close")
        btn.SetDefault()
        main_sizer.Add(btn, 0, wx.CENTER)

        wrapper.Add(main_sizer, 1, wx.EXPAND | wx.ALL, 15)

        self.SetSizerAndFit(wrapper)
        self.CenterOnParent()


class RecentFilesDialog(wx.Dialog):
    def __init__(self, parent, recent_files):
        super().__init__(parent, title="Recent Files", size=(700, 500),
                         style=wx.DEFAULT_DIALOG_STYLE | wx.RESIZE_BORDER)

        self.recent_files = list(recent_files)

        self.file_to_open = None

        self.CenterOnParent()

        self.SetFont(get_app_font())

        panel = wx.Panel(self)
        main_sizer = wx.BoxSizer(wx.VERTICAL)

        search_sizer = wx.BoxSizer(wx.HORIZONTAL)
        self.search_ctrl = wx.SearchCtrl(panel, style=wx.TE_PROCESS_ENTER)
        self.search_ctrl.SetDescriptiveText("Search filename or path...")
        self.search_ctrl.ShowCancelButton(True)
        search_sizer.Add(self.search_ctrl, 1, wx.ALIGN_CENTER_VERTICAL | wx.ALL, 5)
        main_sizer.Add(search_sizer, 0, wx.EXPAND | wx.ALL, 10)

        self.dv_list = dv.DataViewListCtrl(panel, style=dv.DV_ROW_LINES | dv.DV_VERT_RULES | dv.DV_SINGLE)

        self.dv_list.AppendTextColumn("#", width=40, mode=dv.DATAVIEW_CELL_INERT, align=wx.ALIGN_CENTER)
        self.dv_list.AppendTextColumn("Filename", width=250, mode=dv.DATAVIEW_CELL_INERT)
        self.dv_list.AppendTextColumn("Location", width=400, mode=dv.DATAVIEW_CELL_INERT)

        main_sizer.Add(self.dv_list, 1, wx.EXPAND | wx.LEFT | wx.RIGHT, 15)

        btn_sizer = wx.BoxSizer(wx.HORIZONTAL)

        self.btn_clear = wx.Button(panel, label="Forget All")
        self.btn_remove = wx.Button(panel, label="Forget Item")
        self.btn_open = wx.Button(panel, label="Open")
        self.btn_close = wx.Button(panel, label="Close")

        self.btn_open.SetDefault()

        btn_sizer.Add(self.btn_clear, 0, wx.ALIGN_CENTER_VERTICAL | wx.RIGHT, 10)
        btn_sizer.AddStretchSpacer(1)
        btn_sizer.Add(self.btn_remove, 0, wx.ALIGN_CENTER_VERTICAL | wx.RIGHT, 10)
        btn_sizer.Add(self.btn_open, 0, wx.ALIGN_CENTER_VERTICAL | wx.RIGHT, 10)
        btn_sizer.Add(self.btn_close, 0, wx.ALIGN_CENTER_VERTICAL)

        main_sizer.Add(btn_sizer, 0, wx.EXPAND | wx.ALL, 15)
        panel.SetSizer(main_sizer)

        self._populate_list()
        self.on_selection_changed(None)

        self.Bind(wx.EVT_BUTTON, self.on_open, self.btn_open)
        self.Bind(wx.EVT_BUTTON, self.on_remove, self.btn_remove)
        self.Bind(wx.EVT_BUTTON, self.on_clear, self.btn_clear)
        self.Bind(wx.EVT_BUTTON, self.on_close, self.btn_close)

        self.dv_list.Bind(dv.EVT_DATAVIEW_ITEM_ACTIVATED, self.on_double_click)
        self.dv_list.Bind(dv.EVT_DATAVIEW_SELECTION_CHANGED, self.on_selection_changed)
        self.search_ctrl.Bind(wx.EVT_TEXT, self.on_search)
        self.search_ctrl.Bind(wx.EVT_SEARCHCTRL_CANCEL_BTN, self.on_search_cancel)

    def _populate_list(self, filter_text=""):
        self.dv_list.DeleteAllItems()
        filter_text = filter_text.lower()
        current_idx = 1

        for file_path in self.recent_files:
            if not file_path: continue

            name = os.path.basename(file_path)

            if filter_text and (filter_text not in name.lower() and filter_text not in file_path.lower()):
                continue

            self.dv_list.AppendItem([str(current_idx), name, file_path])
            current_idx += 1

    def get_selected_path(self):
        row = self.dv_list.GetSelectedRow()
        if row == wx.NOT_FOUND: return None
        return self.dv_list.GetTextValue(row, 2)

    def on_selection_changed(self, evt):
        selected = self.dv_list.GetSelectedRow() != wx.NOT_FOUND
        self.btn_open.Enable(selected)
        self.btn_remove.Enable(selected)

    def on_search(self, evt):
        self._populate_list(self.search_ctrl.GetValue())

    def on_search_cancel(self, evt):
        self.search_ctrl.SetValue("")
        self._populate_list("")

    def on_open(self, evt):
        path = self.get_selected_path()
        if path:
            if not os.path.exists(path):
                wx.MessageBox(f"File not found:\n{path}", "Error", wx.OK)
                return

            self.file_to_open = path
            self.EndModal(wx.ID_OK)

    def on_double_click(self, evt):
        self.on_open(None)

    def on_remove(self, evt):
        path = self.get_selected_path()
        if path and path in self.recent_files:
            self.recent_files.remove(path)  # Update local copy
            self._populate_list(self.search_ctrl.GetValue())
            self.on_selection_changed(None)

    def on_clear(self, evt):
        if not self.recent_files: return
        dlg = wx.MessageDialog(self, "Clear all recent files history?", "Confirm Clear", wx.YES_NO | wx.ICON_WARNING)
        if dlg.ShowModal() == wx.ID_YES:
            self.recent_files.clear()  # Update local copy
            self._populate_list()
        dlg.Destroy()

    def on_close(self, evt):
        self.EndModal(wx.ID_CANCEL)


class PswdManagerDialog(wx.Dialog):
    def __init__(self, parent=None):
        super().__init__(parent, title="Password Editor", size=(500, 600))

        self.file_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'pswd.txt')

        self.InitUI()
        self.LoadPasswords()
        self.Center()

    def InitUI(self):
        panel = wx.Panel(self)
        main_sizer = wx.BoxSizer(wx.VERTICAL)

        desc_label = wx.StaticText(panel, label="Enter one password per line.")
        warn_label = wx.StaticText(panel, label="WARNING: Passwords are stored in PLAIN TEXT.")
        warn_label.SetForegroundColour(wx.Colour("#bb707c"))

        main_sizer.Add(desc_label, 0, wx.CENTRE | wx.TOP, 15)
        main_sizer.Add(warn_label, 0, wx.CENTRE | wx.BOTTOM, 10)

        self.text_editor = wx.TextCtrl(panel, style=wx.TE_MULTILINE | wx.TE_RICH2)
        self.text_editor.SetFont(get_app_font(1))

        main_sizer.Add(self.text_editor, 1, wx.EXPAND | wx.LEFT | wx.RIGHT, 15)

        footer_sizer = wx.BoxSizer(wx.HORIZONTAL)
        self.btn_save = wx.Button(panel, label="Save")
        self.btn_close = wx.Button(panel, label="Cancel")

        footer_sizer.AddStretchSpacer()
        footer_sizer.Add(self.btn_save, 0, wx.ALL, 10)
        footer_sizer.Add(self.btn_close, 0, wx.ALL, 10)

        main_sizer.Add(footer_sizer, 0, wx.EXPAND)

        # Bindings
        self.Bind(wx.EVT_BUTTON, self.OnSave, self.btn_save)
        self.Bind(wx.EVT_BUTTON, self.OnClose, self.btn_close)

        panel.SetSizer(main_sizer)

    def LoadPasswords(self):
        if not os.path.exists(self.file_path):
            return

        try:
            with open(self.file_path, 'r', encoding='utf-8') as f:
                content = f.read()
            self.text_editor.SetValue(content)
        except Exception as e:
            wx.MessageBox(f"Failed to load file:\n{e}", "Error", wx.ICON_ERROR)

    def OnSave(self, event):
        try:
            content = self.text_editor.GetValue()
            with open(self.file_path, 'w', encoding='utf-8') as f:
                f.write(content)

            self.EndModal(wx.ID_OK)
        except Exception as e:
            wx.MessageBox(f"Failed to save:\n{e}", "Error", wx.ICON_ERROR)

    def OnClose(self, event):
        if self.text_editor.IsModified():
            res = wx.MessageBox("You have unsaved changes. Exit anyway?", "Confirm", wx.YES_NO | wx.ICON_WARNING)
            if res == wx.NO:
                return

        self.EndModal(wx.ID_CANCEL)
