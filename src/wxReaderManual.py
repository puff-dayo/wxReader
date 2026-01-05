import wx
import wx.html

from wxReaderIcon import get_app_icon

# Format: List of tuples -> (Title, HTML_Content, [List of Children Tuples])
# HTML_Content can be None if just a category

MANUAL_TREE = [
    ("Introduction", """
        <h3>Welcome to wxReader</h3>
        <p>wxReader is a program for viewing documents and comics. It works with PDF, ePub, and compressed archive files (ZIP, CBZ). Mobi and fb2 files are not tested.</p>
        <p>You can use the <b>Contents</b> list on the left to browse this help file.</p>
    """, []),

    ("Interface", """
        <h3>Using the Interface</h3>
        <p>The main window has a Sidebar on the left and a View area on the right.</p>
        <ul>
            <li><b>Sidebar:</b> Shows the chapters or files. Press <b>F9</b> to hide or show it.</li>
            <li><b>Main View:</b> Shows the document page.</li>
        </ul>
    """, [
        ("Gallery Mode", """
            <h3>Using Gallery Mode</h3>
            <p>Gallery Mode shows you pictures of all the documents in the current folder. To use it, click <b>File</b>, then click <b>Gallery Mode</b>.</p>
            <p>Click on a picture to open that file.</p>
        """, []),
        ("Search and Outline", """
            <h3>Finding Your Place</h3>
            <p><b>The Outline Tab</b></p>
            <p>This tab lists the chapters in your document. Click a chapter to go to it.</p>
            <p>If your file (like a ZIP or CBZ) does not have chapters, wxReader makes a list for you:</p>
            <ul>
                <li><b>Small files:</b> Every page is listed.</li>
                <li><b>Large files (over 500 pages):</b> Every 10th page is listed.</li>
            </ul>
            <p><b>Searching</b></p>
            <p>Press <b>Ctrl+F</b> to search for text. Click on a result to go to that page.</p>
        """, []),
        ("Keyboard Shortcuts", """
            <h3>Keyboard Shortcuts</h3>
            <p>You can use these keys to control the program:</p>
            <table border="1" cellpadding="5" cellspacing="0" width="100%">
                <tr style="background-color: #c0c0c0;"><th><b>To do this...</b></th><th><b>Press this...</b></th></tr>
                <tr><td>Open a file</td><td>Ctrl + O</td></tr>
                <tr><td>Close a file</td><td>Ctrl + W</td></tr>
                <tr><td>Show/Hide Sidebar</td><td>F9</td></tr>
                <tr><td>Switch Sidebar Tab</td><td>F8</td></tr>
                <tr><td>Full Screen</td><td>F11</td></tr>
                <tr><td colspan="2"><b>Changing Views</b></td></tr>
                <tr><td>Single Page</td><td>Ctrl + 1</td></tr>
                <tr><td>Two Pages</td><td>Ctrl + 2</td></tr>
                <tr><td>Fit to Width</td><td>Ctrl + 3</td></tr>
                <tr><td>Fit to Window</td><td>Ctrl + 4</td></tr>
                <tr><td>Zoom In / Out</td><td>Ctrl + (+) / (-)</td></tr>
                <tr><td colspan="2"><b>Moving Around</b></td></tr>
                <tr><td>Next / Previous Page</td><td>Right / Left Arrow</td></tr>
                <tr><td>Go to specific page</td><td>Ctrl + G</td></tr>
                <tr><td>Find text</td><td>Ctrl + F</td></tr>
                <tr><td>View Table of Contents</td><td>Ctrl + T</td></tr>
                <tr><td colspan="2"><b>Tools</b></td></tr>
                <tr><td>Copy Text</td><td>Ctrl + E</td></tr>
                <tr><td>Save Images</td><td>Ctrl + I</td></tr>
            </table>
        """, []),
        ("Keyboard Customization", """
            <h3>Edit Keyboard Shortcuts</h3>
            <p>You can change the keyboard shortcuts to how you like.</p>
            <p><b>To customize shortcuts:</b></p>
            <ol>
                <li>Click the <b>File</b> menu. </li>
                <li>Click <b>Preferences</b>.</li>
                <li>Find the action you want to change.</li>
                <li>Double-click the shortcut field and press the new keys you want to use.</li>
                <li>Click OK to save. </li>
            </ol>
            <p>Your custom shortcuts are saved and will be used every time you open the program.</p>
        """, []),
    ]),

    ("Files and Folders", """
        <h3>Working with Your Files</h3>
        <p>This section explains how to manage your book collection and folders.</p>
    """, [
        ("File Browser and Folder List", """
            <h3>Browse Your Folders</h3>
            <p>The tabs at the sidebar helps you navigate through all your files and folders.</p>
            <p>To use it:</p>
            <ol>
                <li>Look at the tabs on the left side.</li>
                <li>Click to navigate in tab <b>File Browser</b> or sort and list all files inside tab <b>Folder List</b>.</li>
                <li>Double-click on any file to open it.</li>
            </ol>
            <p>A toolbar at the top of the sidebar gives you quick buttons for common tasks.</p>
        """, []),
        ("Recent Files", """
            <h3>Open Files You've Used Before</h3>
            <p>The Recent Files dialog keeps track of the files you have opened. </p>
            <p><b>To open the Recent Files dialog:</b></p>
            <ol>
                <li>Click <b>File</b> in the menu. </li>
                <li>Click <b>Recent Files</b>.</li>
            </ol>
            <p>Click on any file in the list to open it right away.</p>
        """, []),
        ("Password Manager", """
            <h3>Managing Your Passwords</h3>
            <p>If you have many password-protected files, the Password Manager dialog helps you organize them.</p>
            <p><b>To open the Password Manager:</b></p>
            <ol>
                <li>Click <b>File</b> in the menu.</li>
                <li>Click <b>Manage Passwords</b>.</li>
            </ol>
            <p>Here you can add, edit, or remove passwords from the password list.  This is easier than editing the text file directly.</p>
            <p style="border:  1px solid #000; padding: 10px; background-color: #ffffcc;">
                <b>WARNING:</b><br>
                The <code>pswd.txt</code> file is a plain text file. Anyone using this computer can open it and read your passwords.  <b>Do not</b> use this feature on a public or shared computer. 
            </p>
        """, []),
    ]),

    ("Reading Experience", """
        <h3>Reading Documents</h3>
        <p>You can change how pages are displayed on the screen.</p>
    """, [
        ("Page Layout", """
            <h3>Page Layouts</h3>
            <p>Click the <b>View</b> menu to choose a layout:</p>
            <ul>
                <li><b>Single Page View:</b> Shows one page at a time. Scroll down to see more.</li>
                <li><b>Two Page View:</b> Shows two pages side-by-side, like a book.</li>
            </ul>
            <p><b>Page Direction</b></p>
            <p>You can change the reading order. Use <b>Left-to-Right</b> for English books. Use <b>Right-to-Left</b> for Manga.</p>
        """, []),
        ("Visual Customization", """
            <h3>Customizing the View</h3>
            <p><b>Margins & Gaps</b></p>
            <p>Click <b>View</b>, then <b>Set Margin and Gap</b> to change the empty space around the pages.</p>
            <p><b>Background Color</b></p>
            <p>Click <b>View</b>, then <b>Background Color</b> to pick a new color for the area behind the pages.</p>
        """, []),
    ]),

    ("Tools and Processing", None, [
        ("Content Extraction", """
            <h3>Copying Content</h3>
            <p><b>Extract Page Text (Ctrl+E)</b></p>
            <p>This opens a window with the text from the current page. You can copy it to the clipboard.</p>
            <p><b>Extract Page Images (Ctrl+I)</b></p>
            <p>This finds all pictures on the current page. You can save them to your computer.</p>
        """, []),
        ("Visual Effects", """
            <h3>Using Visual Effects</h3>
            <p>You can change how the document looks using filters. These run on your video card.</p>
            <p>To use a filter:</p>
            <ol>
                <li>Click the <b>Process</b> menu.</li>
                <li>Expand a subfolder.</li>
                <li>Click on an effect name.</li>
            </ol>
            <p>The effect happens instantly. To turn off the visual effects, use the same menu.</p>
        """, []),
        ("Render Quality", """
            <h3>Image Scaling Quality</h3>
            <p>This setting changes how pictures are scaled (made larger or smaller) on your screen. A higher quality setting looks better but may be slower on older computers. A lower quality setting is faster.</p>
            <p>To change the setting, click the <b>View</b> menu, go to <b>Render Quality</b>, and click on the setting you want.</p>
        """, []),
    ]),

    ("Advanced Customization", None, [
        ("Custom GPU Shaders", """
            <h3>Creating Custom Effects</h3>
            <p>Advanced users can create new effects by writing shader files.</p>
            <p><b>How to add a filter:</b></p>
            <ol>
                <li>Open the <code>filters</code> folder in the program directory.</li>
                <li>Create a text file with a <code>.frag</code> extension.</li>
            </ol>
            <p>The program sends these uniforms to your shader:</p>
            <table border="1" cellpadding="5" cellspacing="0" width="100%">
                <tr style="background-color: #c0c0c0;"><th><b>Variable</b></th><th><b>Type</b></th><th><b>What it is</b></th></tr>
                <tr><td><b>uTex</b></td><td>sampler2D</td><td>The image of the page.</td></tr>
                <tr><td><b>uResolution</b></td><td>vec2</td><td>The screen size (width, height).</td></tr>
                <tr><td><b>uTime</b></td><td>float</td><td>A timer counting and loops from 0 to 1000.</td></tr>
                <tr><td><b>uSeed</b></td><td>float</td><td>A random number.</td></tr>
                <tr><td><b>uStrength</b></td><td>float</td><td>The strength setting. You can adjust this with the Strength slider in <b>Process->Shader Settings</b>.</td></tr>
            </table>
        """, []),
    ]),

    ("FAQ", """
        <h3>Common Questions</h3>
    """, [
        ("Fixing Misaligned Spreads", """
            <h3>Why are the pages on the wrong side?</h3>
            <p>In <b>Two Page View</b>, the first page might belong on the right side, but the program puts it on the left.</p>
            <p><b>To fix this:</b></p>
            <ol>
                <li>Click the <b>View</b> menu.</li>
                <li>Click <b>Add Blank Page at Start</b>.</li>
            </ol>
            <p>This adds an empty space at the start, pushing all pages to the correct side.</p>
        """, []),
        ("Version Information", """
            <h3>What Version Do I Have?</h3>
            <p>To see what version of wxReader you are using: </p>
            <ol>
                <li>Click <b>Info</b> in the menu.</li>
                <li>Click <b>About</b>.</li>
            </ol>
            <p>This window shows the version number and other information about the program.</p>
        """, []),
        ("Checking for Updates", """
            <h3>Get New Features and Fixes</h3>
            <p>wxReader can check if a newer version is available. </p>
            <p>To check for updates manually:</p>
            <ol>
                <li>Click <b>Info</b> in the menu.</li>
                <li>Click <b>Check for Updates...</b>.</li>
            </ol>
            <p>To upgrade from older versions, just simply copy the <b>wxReader.cfg</b> and <b>pswd.txt</b> files containing all user settings to the folder of a new version. All wxReader releases are portable.</p>
        """, []),
    ])
]


class ManualDialog(wx.Frame):
    def __init__(self, parent):
        super().__init__(parent, title="wxReader Help", size=(850, 768))

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

        app_icon = get_app_icon()
        if app_icon.IsOk():
            self.SetIcon(app_icon)

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
