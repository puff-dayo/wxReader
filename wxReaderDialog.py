from __future__ import annotations

import wx


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
