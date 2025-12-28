import wx
import wx.html

# Format: List of tuples -> (Title, HTML_Content, [List of Children Tuples])
# HTML_Content can be None if just a category

MANUAL_TREE = [
    ("Introduction", """
        <h3>Welcome to wxReader</h3>
        <p><b>wxReader</b> is a specialized document viewing environment designed for efficiency and readability. It combines standard navigation features with advanced rendering capabilities, including GPU-accelerated filtering and content extraction tools.</p>
        <p>Use the <b>Contents</b> pane on the left to navigate this help file.</p>
    """, []),

    ("Interface & Navigation", """
        <h3>Interface Overview</h3>
        <p>The application workspace is divided into the Sidebar and the Main View.</p>
        <ul>
            <li><b>Sidebar:</b> Provides document structure (Outline) and file system navigation. Toggle visibility via <b>View &gt; Show Sidebar</b> (F9).</li>
            <li><b>Main View:</b> Displays the rendered document content.</li>
        </ul>
        <p>Use the tabs at the bottom of the sidebar to switch between the <b>Outline</b> and the <b>File Browser</b>.</p>
    """, [
        ("Gallery Mode", """
            <h3>Gallery Mode</h3>
            <p>The Gallery Mode (File &gt; Gallery Mode) provides a visual overview of your document library. It scans the current directory and displays thumbnails for supported files, allowing for quick visual selection.</p>
        """, []),
        ("Search & Outline", """
            <h3>Search & Outline</h3>
            <p><b>Outline:</b> If the document contains a Table of Contents, it will be displayed in the 'Outline' tab. Click an entry to jump to that section.</p>
            <p><b>Search:</b> Press <b>Ctrl+F</b> to open the Find dialog. Search results will list page numbers and context; clicking a result navigates directly to that location.</p>
        """, []),
        ("Keyboard Shortcuts", """
            <h3>Keyboard Shortcuts</h3>
            <p>The following shortcuts are available to streamline navigation and view management:</p>
            <table border="1" cellpadding="5" cellspacing="0" width="100%">
                <tr style="background-color: #f0f0f0;"><th><b>Action</b></th><th><b>Shortcut</b></th></tr>
                <tr><td>Open File</td><td>Ctrl + O</td></tr>
                <tr><td>Close File</td><td>Ctrl + W</td></tr>
                <tr><td>Toggle Sidebar</td><td>F9</td></tr>
                <tr><td>Switch Sidebar Tab</td><td>F8</td></tr>
                <tr><td>Full Screen</td><td>F11</td></tr>
                <tr><td colspan="2"><b>View Modes</b></td></tr>
                <tr><td>Single Page View</td><td>Ctrl + 1</td></tr>
                <tr><td>Two Page View</td><td>Ctrl + 2</td></tr>
                <tr><td>Fit Width</td><td>Ctrl + 3</td></tr>
                <tr><td>Fit Page</td><td>Ctrl + 4</td></tr>
                <tr><td>Zoom In / Out</td><td>Ctrl + (+) / (-)</td></tr>
                <tr><td colspan="2"><b>Navigation</b></td></tr>
                <tr><td>Next / Previous Page</td><td>Right / Left Arrow</td></tr>
                <tr><td>Go to Page...</td><td>Ctrl + G</td></tr>
                <tr><td>Find...</td><td>Ctrl + F</td></tr>
                <tr><td>Show TOC Dialog</td><td>Ctrl + T</td></tr>
                <tr><td colspan="2"><b>Tools</b></td></tr>
                <tr><td>Extract Text</td><td>Ctrl + E</td></tr>
                <tr><td>Extract Images</td><td>Ctrl + I</td></tr>
            </table>
        """, [])
    ]),

    ("Reading Experience", """
        <h3>Reading Experience</h3>
        <p>wxReader offers multiple view modes to emulate different reading environments.</p>
    """, [
        ("Page Layout", """
            <h3>Page Layout Modes</h3>
            <p>Access these settings under the <b>View</b> menu:</p>
            <ul>
                <li><b>Single Page View (Ctrl+1):</b> Standard vertical scrolling.</li>
                <li><b>Two Page View (Ctrl+2):</b> Simulates a physical book spread.</li>
            </ul>
            <p><b>Page Direction:</b> Toggle between <b>Left-to-Right (LTR)</b> and <b>Right-to-Left (RTL)</b> to accommodate different languages.</p>
        """, []),
        ("Visual Customization", """
            <h3>Visual Customization</h3>
            <p><b>Margins & Gaps:</b> Select <b>View &gt; Set Margin and Gap</b> to define the spacing between pages and the window edge. Values are in pixels.</p>
            <p><b>Background Color:</b> Use <b>View &gt; Background Color...</b> to change the canvas area behind the document pages.</p>
        """, []),
    ]),

    ("Tools & Processing", None, [
        ("Content Extraction", """
            <h3>Content Extraction</h3>
            <p>wxReader allows you to extract raw data from the document.</p>
            <h4>Extract Page Text (Ctrl+E)</h4>
            <p>Parses the currently visible pages and displays the raw text in a dialog window, ready for copying to the clipboard.</p>
            <h4>Extract Page Images (Ctrl+I)</h4>
            <p>Scans the visible pages for embedded image resources. A dialog will present the found images, allowing you to view their native resolution and format.</p>
        """, []),
        ("Filters (CPU)", """
            <h3>Enhancement Filters (CPU)</h3>
            <p>Located under the <b>Process</b> menu, CPU-based filters provide software-level image processing to improve legibility.</p>
            <h4>Enhancement Modes</h4>
            <ul>
                <li><b>Sharpen:</b> Increases edge contrast to clarify blurred text.</li>
                <li><b>Soften:</b> Applies a blur to reduce noise or scanning artifacts.</li>
                <li><b>Soften + Sharpen:</b> A combined pass that reduces noise before sharpening edges for balanced clarity.</li>
            </ul>
            <h4>Color Modes</h4>
            <ul>
                <li><b>Invert Colors:</b> Reverses the color palette (e.g., white text on black background) for low-light reading.</li>
                <li><b>Green/Brown Filter:</b> Applies a tinted overlay to reduce eye strain during prolonged reading sessions.</li>
            </ul>
        """, []),
    ]),

    ("Advanced Customization", None, [
        ("Custom GPU Shaders", """
            <h3>Custom GPU Shaders</h3>
            <p>wxReader supports custom GLSL fragment shaders for advanced visual post-processing.</p>
            <h4>Shader Organization</h4>
            <p>Shaders are loaded from the <code>filters</code> directory in the application root. You may organize shaders into subdirectories (e.g., <code>filters/Retro/crt.frag</code>). The application will automatically create corresponding submenus under <b>Process &gt; Shaders (GPU)</b> based on the folder structure.</p>
            <h4>Shader Development Guide</h4>
            <p>To create a filter, add a text file with the <code>.frag</code> extension. The application exposes the following uniforms to the shader program:</p>
            <table border="1" cellpadding="5" cellspacing="0" width="100%">
                <tr style="background-color: #f0f0f0;"><th><b>Uniform Type</b></th><th><b>Name</b></th><th><b>Description</b></th></tr>
                <tr><td><code>sampler2D</code></td><td><b>uTex</b></td><td>The texture containing the rendered page content.</td></tr>
                <tr><td><code>float</code></td><td><b>uTime</b></td><td>Elapsed time in seconds. Loops from 0.0 to 1000.0. Use this for animated effects.</td></tr>
                <tr><td><code>float</code></td><td><b>uSeed</b></td><td>A random float value generated at initialization.</td></tr>
                <tr><td><code>float</code></td><td><b>uStrength</b></td><td>Effect intensity value (currently fixed at 0.8).</td></tr>
            </table>
            <p><b>Note:</b> Standard texture coordinates should be used to sample <code>uTex</code>.</p>
        """, []),
    ]),

    ("FAQ", """
        <h3>Frequently Asked Questions</h3>
    """, [
        ("Fixing Misaligned Spreads", """
            <h3>Why are the left and right pages reversed?</h3>
            <p>In <b>Two Page View</b>, the application defaults to placing the first page on the left (LTR mode) or right (RTL mode). However, many books dedicate the first page to the cover, which should be displayed alone.</p>
            <p><b>Solution:</b></p>
            <ol>
                <li>Go to the <b>View</b> menu.</li>
                <li>Check the option <b>Add Blank Page at Start</b>.</li>
            </ol>
            <p>This inserts a virtual padding page at the beginning of the document, shifting all subsequent pages by one slot and correcting the spread alignment.</p>
        """, []),
    ])
]



class ManualDialog(wx.Frame):
    def __init__(self, parent):
        super().__init__(parent, title="wxReader Help", size=(850, 600))

        if parent:
            self.SetIcon(parent.GetIcon())

        self.splitter = wx.SplitterWindow(self, style=wx.SP_3D | wx.SP_LIVE_UPDATE)
        self.splitter.SetMinimumPaneSize(200)

        self.nav_panel = wx.Panel(self.splitter)
        nav_sizer = wx.BoxSizer(wx.VERTICAL)

        self.tree = wx.TreeCtrl(self.nav_panel,
                                style=wx.TR_DEFAULT_STYLE | wx.TR_HIDE_ROOT | wx.TR_FULL_ROW_HIGHLIGHT | wx.TR_NO_LINES | wx.TR_TWIST_BUTTONS)
        self.tree.SetBackgroundColour(wx.Colour(240, 240, 240))

        nav_sizer.Add(self.tree, 1, wx.EXPAND)
        self.nav_panel.SetSizer(nav_sizer)

        self.html_window = wx.html.HtmlWindow(self.splitter)
        self.html_window.SetStandardFonts(size=11)

        self.splitter.SplitVertically(self.nav_panel, self.html_window, 250)

        self.root_id = self.tree.AddRoot("Root")
        self._populate_tree(self.root_id, MANUAL_TREE)

        self.tree.ExpandAll()

        self.tree.Bind(wx.EVT_TREE_SEL_CHANGED, self.on_selection_changed)
        self.Bind(wx.EVT_CLOSE, self.on_close)

        first_child, cookie = self.tree.GetFirstChild(self.root_id)
        if first_child.IsOk():
            self.tree.SelectItem(first_child)

        self.Center()
        from wxReaderIcon import APP_ICON
        self.SetIcon(APP_ICON)

    def _populate_tree(self, parent_id, nodes):
        for title, content, children in nodes:
            item_id = self.tree.AppendItem(parent_id, title)

            if content is None:
                content = f"<h3>{title}</h3><p>Select a sub-topic from the tree to view details.</p>"

            self.tree.SetItemData(item_id, content)

            if children:
                self._populate_tree(item_id, children)

    def on_selection_changed(self, evt):
        item_id = evt.GetItem()
        if item_id.IsOk():
            content = self.tree.GetItemData(item_id)
            if content:
                self._display_html(content)

    def _display_html(self, body_content):
        # Wrap content in a standard Windows Help style template
        full_html = f"""
        <html>
        <head>
            <style>
                body {{ font-family: 'Segoe UI', Tahoma, Arial, sans-serif; font-size: 10pt; color: #333; }}
                h3 {{ color: #003399; border-bottom: 1px solid #a0a0a0; padding-bottom: 5px; }}
                h4 {{ color: #333; margin-top: 15px; margin-bottom: 5px; }}
                li {{ margin-bottom: 5px; }}
                code {{ background-color: #f0f0f0; padding: 2px 4px; font-family: Consolas, monospace; }}
            </style>
        </head>
        <body>
            {body_content}
        </body>
        </html>
        """
        self.html_window.SetPage(full_html)

    def on_close(self, evt):
        self.Destroy()
