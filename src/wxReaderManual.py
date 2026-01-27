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
        ("External Controller", """
            <h3>Control page turning with external programs</h3>
            <p>To use it, click <b>Navigate</b>, then click <b>External Control</b>.</p>
            <p>Connect using the port and the token at the bottom status bar of wxReader.</p>
            <p><b>Communicate</b></p>
            <p>Send a UDP packet to 127.0.0.1 on the active port using the message format <b>TOKEN|COMMAND</b> (for example, Ab1!23|NEXT).<br> Available COMMANDs: "NEXT" or "PREV".</p>
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


MANUAL_TREE_ZHSG = [
    ("简介", """
        <h3>欢迎使用 wxReader</h3>
        <p>wxReader 是用于查看文档和漫画的程序，支持 PDF、ePub 以及压缩归档文件（ZIP、CBZ）。尚未测试 Mobi 和 fb2 文件。</p>
        <p>你可以使用左侧的<b>目录</b>列表浏览本帮助文件。</p>
    """, []),

    ("界面", """
        <h3>使用界面</h3>
        <p>主窗口左侧是侧边栏，右侧是视图区域。</p>
        <ul>
            <li><b>侧边栏：</b>显示章节或文件。按 <b>F9</b> 可隐藏或显示侧边栏。</li>
            <li><b>主视图：</b>显示文档页面。</li>
        </ul>
    """, [
        ("画廊模式", """
            <h3>使用画廊模式</h3>
            <p>画廊模式会显示当前文件夹中所有文档的缩略图。要使用此模式，请单击<b>文件</b>，然后单击<b>画廊模式</b>。</p>
            <p>单击缩略图即可打开对应文件。</p>
        """, []),
        ("搜索与大纲", """
            <h3>快速定位</h3>
            <p><b>大纲选项卡</b></p>
            <p>此选项卡列出文档中的章节。单击章节即可跳转到对应位置。</p>
            <p>如果文件（例如 ZIP 或 CBZ）不包含章节，wxReader 会自动为你生成列表：</p>
            <ul>
                <li><b>小文件：</b>列出每一页。</li>
                <li><b>大文件（超过 500 页）：</b>每 10 页列出一项。</li>
            </ul>
            <p><b>搜索</b></p>
            <p>按 <b>Ctrl+F</b> 可搜索文本。单击结果即可跳转到对应页面。</p>
        """, []),
        ("键盘快捷键", """
            <h3>键盘快捷键</h3>
            <p>你可以使用以下按键控制程序：</p>
            <table border="1" cellpadding="5" cellspacing="0" width="100%">
                <tr style="background-color: #c0c0c0;"><th><b>要执行的操作…</b></th><th><b>请按…</b></th></tr>
                <tr><td>打开文件</td><td>Ctrl + O</td></tr>
                <tr><td>关闭文件</td><td>Ctrl + W</td></tr>
                <tr><td>显示/隐藏侧边栏</td><td>F9</td></tr>
                <tr><td>切换侧边栏选项卡</td><td>F8</td></tr>
                <tr><td>全屏</td><td>F11</td></tr>
                <tr><td colspan="2"><b>更改视图</b></td></tr>
                <tr><td>单页</td><td>Ctrl + 1</td></tr>
                <tr><td>双页</td><td>Ctrl + 2</td></tr>
                <tr><td>适应宽度</td><td>Ctrl + 3</td></tr>
                <tr><td>适应窗口</td><td>Ctrl + 4</td></tr>
                <tr><td>放大/缩小</td><td>Ctrl + (+) / (-)</td></tr>
                <tr><td colspan="2"><b>浏览页面</b></td></tr>
                <tr><td>下一页/上一页</td><td>右方向键 / 左方向键</td></tr>
                <tr><td>跳转到指定页</td><td>Ctrl + G</td></tr>
                <tr><td>查找文本</td><td>Ctrl + F</td></tr>
                <tr><td>查看目录</td><td>Ctrl + T</td></tr>
                <tr><td colspan="2"><b>工具</b></td></tr>
                <tr><td>复制文本</td><td>Ctrl + E</td></tr>
                <tr><td>保存图片</td><td>Ctrl + I</td></tr>
            </table>
        """, []),
        ("自定义快捷键", """
            <h3>编辑键盘快捷键</h3>
            <p>你可以将键盘快捷键更改为你喜欢的设置。</p>
            <p><b>自定义快捷键的方法：</b></p>
            <ol>
                <li>单击<b>文件</b>菜单。</li>
                <li>单击<b>偏好设置</b>。</li>
                <li>找到要更改的操作。</li>
                <li>双击快捷键字段，然后按下要设置的新按键组合。</li>
                <li>单击<b>保存</b>以保存。</li>
            </ol>
            <p>自定义快捷键会保存，并在你每次打开程序时自动生效。</p>
        """, []),
    ]),

    ("文件与文件夹", """
        <h3>管理你的文件</h3>
        <p>本节说明如何管理你的图书收藏与文件夹。</p>
    """, [
        ("文件浏览器与文件夹列表", """
            <h3>浏览文件夹</h3>
            <p>侧边栏中的选项卡可帮助你浏览所有文件与文件夹。</p>
            <p>使用方法：</p>
            <ol>
                <li>查看左侧的选项卡。</li>
                <li>在<b>文件导览</b>选项卡中浏览，或在<b>资料夹列表</b>选项卡中排序并列出文件夹内的所有文件。</li>
                <li>双击任意文件即可打开。</li>
            </ol>
            <p>侧边栏顶部的工具栏提供常用操作的快速按钮。</p>
        """, []),
        ("最近文件", """
            <h3>打开以前使用过的文件</h3>
            <p>“最近文件”对话框会记录你打开过的文件。</p>
            <p><b>打开“最近文件”对话框的方法：</b></p>
            <ol>
                <li>在菜单中单击<b>文件</b>。</li>
                <li>单击<b>最近文件</b>。</li>
            </ol>
            <p>单击列表中的任意文件即可立即打开。</p>
        """, []),
        ("密码管理", """
            <h3>管理密码</h3>
            <p>如果你有多个受密码保护的文件，“密码簿编辑器”对话框可帮助你整理密码。</p>
            <p><b>打开“密码簿编辑器”的方法：</b></p>
            <ol>
                <li>在菜单中单击<b>文件</b>。</li>
                <li>单击<b>编辑密码簿</b>。</li>
            </ol>
            <p>你可以在此添加、编辑或删除密码列表中的密码。这比直接编辑文本文件更方便。</p>
            <p style="border:  1px solid #000; padding: 10px; background-color: #ffffcc;">
                <b>警告：</b><br>
                <code>pswd.txt</code> 是纯文本文件。使用此电脑的任何人都可以打开并读取你的密码。<b>请勿</b>在公共或共享电脑上使用此功能。
            </p>
        """, []),
    ]),

    ("阅读体验", """
        <h3>阅读文档</h3>
        <p>你可以更改页面在屏幕上的显示方式。</p>
    """, [
        ("页面布局", """
            <h3>页面布局</h3>
            <p>单击<b>查看</b>菜单以选择布局：</p>
            <ul>
                <li><b>单页视图：</b>一次显示一页。向下滚动以查看更多内容。</li>
                <li><b>双页视图：</b>并排显示两页，类似书本。</li>
            </ul>
            <p><b>排页方向</b></p>
            <p>你可以更改阅读方向。英文书籍请使用<b>从左往右</b>；漫画请使用<b>从右往左</b>。</p>
        """, []),
        ("视觉自定义", """
            <h3>自定义视图</h3>
            <p><b>页边距与页间距</b></p>
            <p>单击<b>查看</b>，然后单击<b>设置页间距和边距</b>，以更改页面周围的空白区域。</p>
            <p><b>背景颜色</b></p>
            <p>单击<b>查看</b>，然后单击<b>背景颜色</b>，以选择页面后方区域的新颜色。</p>
        """, []),
        ("外部控制器", """
            <h3>使用外部程序控制翻页</h3>
            <p>要使用此功能，请单击<b>导航</b>，然后单击<b>外部控制</b>。</p>
            <p>使用 wxReader 底部状态栏中的端口和令牌进行连接。</p>
            <p><b>通信</b></p>
            <p>将 UDP 数据包发送到 127.0.0.1 的活动端口，并使用消息格式 <b>TOKEN|COMMAND</b>（例如 Ab1!23|NEXT）。<br>可用的 COMMAND：\"NEXT\" 或 \"PREV\"。</p>
        """, []),
    ]),

    ("工具与处理", None, [
        ("内容提取", """
            <h3>复制内容</h3>
            <p><b>提取文字（Ctrl+E）</b></p>
            <p>此操作会打开一个窗口，显示当前页面的文本。你可以将其复制到剪贴板。</p>
            <p><b>提取图片（Ctrl+I）</b></p>
            <p>此操作会查找当前页面上的所有图片。你可以将其保存到电脑。</p>
        """, []),
        ("视觉效果", """
            <h3>使用视觉效果</h3>
            <p>你可以使用滤镜更改文档的外观。这些效果由显卡运行。</p>
            <p>使用滤镜的方法：</p>
            <ol>
                <li>单击<b>处理</b>菜单。</li>
                <li>展开子文件夹。</li>
                <li>单击效果名称。</li>
            </ol>
            <p>效果会立即生效。要关闭视觉效果，请在同一菜单中选择关闭选项。</p>
        """, []),
        ("渲染质量", """
            <h3>图像缩放质量</h3>
            <p>此设置用于控制图片在屏幕上缩放（放大或缩小）时的质量。<br>较费时的渲染方式的显示效果未必更好，但在较旧电脑上可能更慢。</p>
            <p>要更改设置，请单击<b>查看</b>菜单，转到<b>渲染质量</b>，然后单击所需的设置。</p>
        """, []),
    ]),

    ("高级自定义", None, [
        ("自定义 GPU 着色器", """
            <h3>创建自定义效果</h3>
            <p>高级用户可以通过编写着色器文件来创建新效果。</p>
            <p><b>添加滤镜的方法：</b></p>
            <ol>
                <li>打开程序目录中的 <code>filters</code> 文件夹。</li>
                <li>创建一个扩展名为 <code>.frag</code> 的文本文件。</li>
            </ol>
            <p>程序会向你的着色器传递以下 uniform 变量：</p>
            <table border="1" cellpadding="5" cellspacing="0" width="100%">
                <tr style="background-color: #c0c0c0;"><th><b>变量</b></th><th><b>类型</b></th><th><b>说明</b></th></tr>
                <tr><td><b>uTex</b></td><td>sampler2D</td><td>页面图像。</td></tr>
                <tr><td><b>uResolution</b></td><td>vec2</td><td>屏幕大小（宽、高）。</td></tr>
                <tr><td><b>uTime</b></td><td>float</td><td>计时器，从 0 计数并循环到 1000。</td></tr>
                <tr><td><b>uSeed</b></td><td>float</td><td>随机数。</td></tr>
                <tr><td><b>uStrength</b></td><td>float</td><td>强度设置。你可以在<b>处理-&gt;着色器设置</b>中使用“强度”滑块进行调整。</td></tr>
            </table>
        """, []),
    ]),

    ("常见问题", """
        <h3>常见问题</h3>
    """, [
        ("修正跨页错位", """
            <h3>为什么页面出现在错误的一侧？</h3>
            <p>在<b>双页视图</b>中，第一页可能应显示在右侧，但程序将其放在左侧。</p>
            <p><b>解决方法：</b></p>
            <ol>
                <li>单击<b>查看</b>菜单。</li>
                <li>单击<b>添加空白起始页</b>。</li>
            </ol>
            <p>此操作会在开头添加一个空白页，从而将所有页面推到正确的位置。</p>
        """, []),
        ("版本信息", """
            <h3>我正在使用哪个版本？</h3>
            <p>要查看 wxReader 的版本：</p>
            <ol>
                <li>在菜单中单击<b>信息</b>。</li>
                <li>单击<b>关于</b>。</li>
            </ol>
            <p>此窗口会显示版本号及程序的其他信息。</p>
        """, []),
        ("检查更新", """
            <h3>获取新功能与修复</h3>
            <p>wxReader 可以检查是否有更新版本可用。</p>
            <p>要手动检查更新：</p>
            <ol>
                <li>在菜单中单击<b>信息</b>。</li>
                <li>单击<b>检查更新…</b>。</li>
            </ol>
            <p>从旧版本升级时，只需将包含所有用户设置的 <b>wxReader.cfg</b> 和 <b>pswd.txt</b> 文件复制到新版本文件夹中即可。所有 wxReader 发行版均为便携版。</p>
        """, []),
    ])
]


MANUAL_TREE_JAJP = [
    ("はじめに", """
        <h3>wxReaderへようこそ</h3>
        <p>wxReader は、ドキュメントやコミックを表示するためのプログラムです。<br>PDF、ePub、および圧縮アーカイブ（ZIP、CBZ）に対応しています。Mobi と fb2 は未検証です。</p>
        <p>このヘルプは、左側の<b>目次</b>リストから参照できます。</p>
    """, []),

    ("インターフェイス", """
        <h3>画面の使いかた</h3>
        <p>メイン ウィンドウは、左側のサイドバーと右側の表示エリアで構成されています。</p>
        <ul>
            <li><b>サイドバー:</b> 章（チャプター）やファイルを表示します。<b>F9</b> を押すと、表示/非表示を切り替えられます。</li>
            <li><b>メイン表示:</b> ドキュメントのページを表示します。</li>
        </ul>
    """, [
        ("ギャラリーモード", """
            <h3>ギャラリーモードを使う</h3>
            <p>ギャラリーモードでは、現在のフォルダー内にあるドキュメントをサムネイルで表示します。<br>使用するには、<b>ファイル</b>をクリックし、次に<b>ギャラリーモード</b>をクリックします。</p>
            <p>サムネイルをクリックすると、そのファイルを開きます。</p>
        """, []),
        ("検索とアウトライン", """
            <h3>目的の場所を見つける</h3>
            <p><b>アウトライン タブ</b></p>
            <p>このタブには、ドキュメント内の章が一覧表示されます。章をクリックすると、その位置に移動します。</p>
            <p>ファイル（ZIP/CBZ など）に章情報がない場合、wxReader が自動的に一覧を作成します。</p>
            <ul>
                <li><b>小さいファイル:</b> すべてのページを一覧に表示します。</li>
                <li><b>大きいファイル（500 ページ超）:</b> 10 ページごとに一覧に表示します。</li>
            </ul>
            <p><b>検索</b></p>
            <p><b>Ctrl+F</b> を押してテキストを検索できます。結果をクリックすると、そのページに移動します。</p>
        """, []),
        ("キーボード ショートカット", """
            <h3>キーボード ショートカット</h3>
            <p>次のキーでプログラムを操作できます。</p>
            <table border="1" cellpadding="5" cellspacing="0" width="100%">
                <tr style="background-color: #c0c0c0;"><th><b>操作</b></th><th><b>キー</b></th></tr>
                <tr><td>ファイルを開く</td><td>Ctrl + O</td></tr>
                <tr><td>ファイルを閉じる</td><td>Ctrl + W</td></tr>
                <tr><td>サイドバーの表示/非表示</td><td>F9</td></tr>
                <tr><td>サイドバーのタブを切り替える</td><td>F8</td></tr>
                <tr><td>全画面表示</td><td>F11</td></tr>
                <tr><td colspan="2"><b>表示を切り替える</b></td></tr>
                <tr><td>単ページ</td><td>Ctrl + 1</td></tr>
                <tr><td>見開き</td><td>Ctrl + 2</td></tr>
                <tr><td>幅に合わせる</td><td>Ctrl + 3</td></tr>
                <tr><td>ウィンドウに合わせる</td><td>Ctrl + 4</td></tr>
                <tr><td>拡大/縮小</td><td>Ctrl + (+) / (-)</td></tr>
                <tr><td colspan="2"><b>移動</b></td></tr>
                <tr><td>次/前のページ</td><td>→ / ←</td></tr>
                <tr><td>指定ページへ移動</td><td>Ctrl + G</td></tr>
                <tr><td>テキストを検索</td><td>Ctrl + F</td></tr>
                <tr><td>目次を表示</td><td>Ctrl + T</td></tr>
                <tr><td colspan="2"><b>ツール</b></td></tr>
                <tr><td>テキストをコピー</td><td>Ctrl + E</td></tr>
                <tr><td>画像を保存</td><td>Ctrl + I</td></tr>
            </table>
        """, []),
        ("ショートカットのカスタマイズ", """
            <h3>キーボード ショートカットを編集する</h3>
            <p>キーボード ショートカットは、好みに合わせて変更できます。</p>
            <p><b>ショートカットを変更するには:</b></p>
            <ol>
                <li><b>ファイル</b> メニューをクリックします。</li>
                <li><b>設定</b> をクリックします。</li>
                <li>変更したい操作を見つけます。</li>
                <li>ショートカット欄をダブルクリックし、設定したいキーを押します。</li>
                <li><b>OK</b>（または保存）をクリックして保存します。</li>
            </ol>
            <p>カスタム ショートカットは保存され、次回以降も自動的に使用されます。</p>
        """, []),
    ]),

    ("ファイルとフォルダー", """
        <h3>ファイルを管理する</h3>
        <p>このセクションでは、本のコレクションやフォルダーの管理方法を説明します。</p>
    """, [
        ("ファイル ブラウザーとフォルダー一覧", """
            <h3>フォルダーを参照する</h3>
            <p>サイドバーのタブを使って、ファイルとフォルダーを移動できます。</p>
            <p>使いかた:</p>
            <ol>
                <li>左側のタブを確認します。</li>
                <li><b>ファイル ブラウザー</b> タブで移動するか、<b>フォルダー一覧</b> タブでフォルダー内のファイルを一覧表示/並べ替えします。</li>
                <li>ファイルをダブルクリックすると開きます。</li>
            </ol>
            <p>サイドバー上部のツールバーには、よく使う操作のボタンがあります。</p>
        """, []),
        ("最近使ったファイル", """
            <h3>以前開いたファイルを開く</h3>
            <p>「最近使ったファイル」ダイアログには、開いたことのあるファイルが記録されます。</p>
            <p><b>「最近使ったファイル」を開くには:</b></p>
            <ol>
                <li>メニューで <b>ファイル</b> をクリックします。</li>
                <li><b>最近使ったファイル</b> をクリックします。</li>
            </ol>
            <p>一覧からファイルをクリックすると、すぐに開けます。</p>
        """, []),
        ("パスワード マネージャー", """
            <h3>パスワードを管理する</h3>
            <p>パスワード付きファイルが多い場合、パスワード マネージャーで整理できます。</p>
            <p><b>パスワード マネージャーを開くには:</b></p>
            <ol>
                <li>メニューで <b>ファイル</b> をクリックします。</li>
                <li><b>pswd.txt を編集</b>（またはパスワード管理）をクリックします。</li>
            </ol>
            <p>ここでパスワードの追加、編集、削除ができます。テキスト ファイルを直接編集するより簡単です。</p>
            <p style="border:  1px solid #000; padding: 10px; background-color: #ffffcc;">
                <b>警告:</b><br>
                <code>pswd.txt</code> はプレーン テキストです。このコンピューターを使用できる人は誰でも開いてパスワードを読めます。公共または共有のコンピューターでは、この機能を使用しないでください。
            </p>
        """, []),
    ]),

    ("読書体験", """
        <h3>ドキュメントを読む</h3>
        <p>画面上でのページの表示方法を変更できます。</p>
    """, [
        ("ページ レイアウト", """
            <h3>ページ レイアウト</h3>
            <p><b>表示</b> メニューからレイアウトを選択します。</p>
            <ul>
                <li><b>単ページ表示:</b> 1 ページずつ表示します。スクロールして続きを読むことができます。</li>
                <li><b>見開き表示:</b> 2 ページを横に並べて表示します（本のような表示）。</li>
            </ul>
            <p><b>ページ方向</b></p>
            <p>読み方向を変更できます。英語の本は<b>左から右</b>、マンガは<b>右から左</b>を使用します。</p>
        """, []),
        ("表示のカスタマイズ", """
            <h3>表示をカスタマイズする</h3>
            <p><b>余白と間隔</b></p>
            <p><b>表示</b> &gt; <b>余白と間隔を設定</b> をクリックして、ページ周囲の空きスペースを変更します。</p>
            <p><b>背景色</b></p>
            <p><b>表示</b> &gt; <b>背景色</b> をクリックして、ページの背面の色を選択します。</p>
        """, []),
        ("外部コントロール", """
            <h3>外部プログラムでページめくりを制御する</h3>
            <p>使用するには、<b>ナビゲーション</b> をクリックし、次に <b>外部制御</b> をクリックします。</p>
            <p>wxReader の下部ステータス バーに表示されるポートとトークンを使用して接続します。</p>
            <p><b>通信</b></p>
            <p>アクティブなポートの 127.0.0.1 に UDP パケットを送信し、メッセージ形式は <b>TOKEN|COMMAND</b>（例: Ab1!23|NEXT）です。<br>使用可能な COMMAND: \"NEXT\" または \"PREV\"。</p>
        """, []),
    ]),

    ("ツールと処理", None, [
        ("コンテンツの抽出", """
            <h3>コンテンツをコピーする</h3>
            <p><b>ページのテキストを抽出（Ctrl+E）</b></p>
            <p>現在のページのテキストを表示するウィンドウを開きます。クリップボードにコピーできます。</p>
            <p><b>ページの画像を抽出（Ctrl+I）</b></p>
            <p>現在のページに含まれる画像を検出します。コンピューターに保存できます。</p>
        """, []),
        ("視覚効果", """
            <h3>視覚効果を使う</h3>
            <p>フィルターを使用してドキュメントの見た目を変更できます。これらは GPU（ビデオ カード）で実行されます。</p>
            <p>フィルターの使いかた:</p>
            <ol>
                <li><b>処理</b> メニューをクリックします。</li>
                <li>サブフォルダーを展開します。</li>
                <li>効果の名前をクリックします。</li>
            </ol>
            <p>効果はすぐに適用されます。無効にするには、同じメニューからオフ（なし）を選択します。</p>
        """, []),
        ("レンダリング品質", """
            <h3>画像の拡大縮小品質</h3>
            <p>この設定は、画面上で画像を拡大/縮小する際の品質を変更します。高品質は見た目が良い一方、古いコンピューターでは動作が遅くなる場合があります。低品質は高速です。</p>
            <p>設定を変更するには、<b>表示</b> メニューの <b>レンダリング品質</b> から希望の項目をクリックします。</p>
        """, []),
    ]),

    ("高度なカスタマイズ", None, [
        ("カスタム GPU シェーダー", """
            <h3>カスタム効果を作成する</h3>
            <p>上級者は、シェーダー ファイルを作成して新しい効果を追加できます。</p>
            <p><b>フィルターを追加するには:</b></p>
            <ol>
                <li>プログラム ディレクトリ内の <code>filters</code> フォルダーを開きます。</li>
                <li><code>.frag</code> 拡張子のテキスト ファイルを作成します。</li>
            </ol>
            <p>プログラムはシェーダーに次の uniform を渡します。</p>
            <table border="1" cellpadding="5" cellspacing="0" width="100%">
                <tr style="background-color: #c0c0c0;"><th><b>変数</b></th><th><b>型</b></th><th><b>説明</b></th></tr>
                <tr><td><b>uTex</b></td><td>sampler2D</td><td>ページの画像。</td></tr>
                <tr><td><b>uResolution</b></td><td>vec2</td><td>画面サイズ（幅、高さ）。</td></tr>
                <tr><td><b>uTime</b></td><td>float</td><td>0 から 1000 までカウントし、ループするタイマー。</td></tr>
                <tr><td><b>uSeed</b></td><td>float</td><td>乱数。</td></tr>
                <tr><td><b>uStrength</b></td><td>float</td><td>強さの設定。<b>処理-&gt;シェーダー設定</b>の「強さ」スライダーで調整できます。</td></tr>
            </table>
        """, []),
    ]),

    ("よくある質問", """
        <h3>よくある質問</h3>
    """, [
        ("見開きのずれを直す", """
            <h3>ページが左右逆に表示されるのはなぜですか？</h3>
            <p><b>見開き表示</b>では、最初のページが右側に来るべき場合でも、左側に表示されることがあります。</p>
            <p><b>対処方法:</b></p>
            <ol>
                <li><b>表示</b> メニューをクリックします。</li>
                <li><b>先頭に空白ページを追加</b> をクリックします。</li>
            </ol>
            <p>先頭に空白を追加して、以降のページを正しい位置にずらします。</p>
        """, []),
        ("バージョン情報", """
            <h3>使用中のバージョンを確認する</h3>
            <p>wxReader のバージョンを確認するには:</p>
            <ol>
                <li>メニューで <b>情報</b> をクリックします。</li>
                <li><b>このソフトについて</b> をクリックします。</li>
            </ol>
            <p>このウィンドウに、バージョン番号とその他の情報が表示されます。</p>
        """, []),
        ("更新を確認する", """
            <h3>新機能と修正を入手する</h3>
            <p>wxReader は、新しいバージョンがあるかどうかを確認できます。</p>
            <p>手動で更新を確認するには:</p>
            <ol>
                <li>メニューで <b>情報</b> をクリックします。</li>
                <li><b>更新の確認...</b> をクリックします。</li>
            </ol>
            <p>旧バージョンからアップグレードする場合は、ユーザー設定を含む <b>wxReader.cfg</b> と <b>pswd.txt</b> を新しいバージョンのフォルダーにコピーするだけで完了します。wxReader のリリースはすべてポータブルです。</p>
        """, []),
    ])
]


class ManualDialog(wx.Frame):
    def __init__(self, parent, lang=wx.LANGUAGE_ENGLISH):
        super().__init__(parent, title="wxReader Help", size=(1024, 768))

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

        if lang == wx.LANGUAGE_ENGLISH:
            self._populate_tree(self.root_id, MANUAL_TREE)
        elif lang == wx.LANGUAGE_CHINESE_SINGAPORE:
            self._populate_tree(self.root_id, MANUAL_TREE_ZHSG)
        elif lang == wx.LANGUAGE_JAPANESE:
            self._populate_tree(self.root_id, MANUAL_TREE_JAJP)


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
