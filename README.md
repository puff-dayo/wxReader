# wxReader

**wxReader** is a **comic/manga/pdf** document reader built with wxWidgets (wxPython), MuPDF (PyMuPDF), OpenGL (PyOpenGL), libvips (pyvips), and
Python. Currently support Windows and Linux.

**wxReaderVoiceCtrl** is a hands-free external controller app for wxReader, recognizing **voice command** offline by vosk and pyaudio. GUI is built with wxPython.

**wxReaderEyeTrackCtrl** is a hands-free external controller app for wxReader, recognizing **eye movement and blinking gesture** offline by [EyeTrax](https://doi.org/10.5281/zenodo.17188537) through a webcam. GUI is also built with wxPython.

**-> Download link <-**
<br>wxReader for [Windows10+](https://github.com/puff-dayo/wxReader/releases/download/v1.3.9/wxReader_v1.3.9_msvc_x64.zip) (>1809)
<br>wxReader for [Debian13](https://github.com/puff-dayo/wxReader/releases/download/v1.3.9/wxReader_v1.3.9_debian13_amd64.zip)
<br>external controllers for [Windows10+_avx2](https://github.com/puff-dayo/wxReader/releases/tag/v1.3.6) (>1809)

Build/run from source: see below ↓

[//]: # ()
[//]: # (---)

[//]: # ()
[//]: # (## Features)

[//]: # ()
[//]: # (<div style="display: flex; justify-content: space-between;">)

[//]: # (  <img src="https://github.com/puff-dayo/wxReader/blob/goshujinsama/screenshot/1_1.png?raw=true" width="49%">)

[//]: # (  <img src="https://github.com/puff-dayo/wxReader/blob/goshujinsama/screenshot/1_2.png?raw=true" width="49%">)

[//]: # (</div>)

[//]: # ()
[//]: # (| Feature                 | Description                                                                                              |)

[//]: # (|-------------------------|----------------------------------------------------------------------------------------------------------|)

[//]: # (| **File Format Support** | PDF, EPUB, ePub, ZIP, CBZ &#40;manga or comics archive files&#41;.                                               |)

[//]: # (| **Paging Strategy**     | Single Page and Two-Page spreads &#40;with optional blank start page&#41;. Supports Right-to-Left &#40;RTL&#41; reading. |)

[//]: # (| **Content Extraction**  | Extract text and images directly from specific pages to the clipboard or disk.                           |)

[//]: # (| **Image Processing**    | Real-time built-in filters and enhancements. Support custom OpenGL frag shaders.                         |)

[//]: # (| **Zoom and View**       | Fit Width, Fit Page, Manual Zoom, Fullscreen Mode, and customizable background color.                    |)

[//]: # (| **Navigation**          | Sidebar with Outline &#40;TOC&#41; and File Browser tabs. Text search dialog, and a standalone TOC dialog.       |)

[//]: # (| **Gallery Mode**        | View all thumbnails or frontpages of all books inside a same folder like a gallery.                      |)

[//]: # (| **File History**        | Automatically saves recent files and reading progress on close.                                          |)

[//]: # (| **Interaction**         | Drag-and-drop file loading and full keyboard operation support.                                          |)

[//]: # (| **External control**    | &#40;Default off.&#41; Send command+token to a local UDP port to do page turning.                                |)

[//]: # ()
[//]: # (**Accessibility features**: The two independent external control programs, **wxReaderVoiceCtrl** and **wxReaderEyeTrackCtrl**, respectively provides offline voice-activated page turning commands and offline eye gesture based page-turning via computer camera recognition, triggered by “blinking twice while looking at a designated area of the screen.” &#40;The are fully offline and requires a not-potato CPU.&#41;)

[//]: # ()
[//]: # (<div style="display: flex; justify-content: space-between;">)

[//]: # (    <img src="https://github.com/puff-dayo/wxReader/blob/goshujinsama/screenshot/3.png?raw=true" width="32%">)

[//]: # (    <img src="https://github.com/puff-dayo/wxReader/blob/goshujinsama/screenshot/4.png?raw=true" width="65%">)

[//]: # (</div>)

---

## Installation

### Windows

1. From sauce (latest dev):
   1. Install Python 3.12 and uv, `uv --project . sync`.
   2. [Download](https://www.libvips.org/install.html) and put the libvips shared library *.dll files inside `.\src`.
   3. Sync dependencies with `uv`.
   4. Build with `.\build.bat` on Windows x64. (Run the build script inside root folder.)
   5. (Notes: upgrade pymupdf will fail the compilation.)
   6. Optional: `uv --project .\extctrl\voice sync`, `uv --project .\extctrl\eye_track sync`, then build with `.\build_*.bat`.

2. Pre-compiled binary (stable): portable `.exe` files are provided on the **Releases** page. Here are links to download (for win10+ x86_64):
   1. [wxReader](https://github.com/puff-dayo/wxReader/releases/)
   2. [wxReaderVoiceCtrl](https://github.com/puff-dayo/wxReader/releases/download/v1.3.6/wxReaderVoiceCtrl_msvc_avx2_x64.zip)
   3. [wxReaderEyeTrackCtrl](https://github.com/puff-dayo/wxReader/releases/download/v1.3.6/wxReaderEyeTrackCtrl_pyi_x64.zip)

3. Upgrade from older versions: simply copy the `wxReader.cfg` and `pswd.txt` files containing all user settings to the folder of a new version. You (probably) can also just unzip and overwrite existing files in the old folder.

### Linux

Tested on platform: Linux-6.12.73+deb13-amd64-x86_64-with-glibc2.41

1. Run from sauce (clone the linux-dev branch of the repo!):
   1. Install Python 3.13 and uv, `uv --project . sync`.
   2. `sudo apt install libvips42t64 python3-wxgtk4.0`.
   3. `uv venv --python /usr/bin/python3 --system-site-packages`, and then activate the venv.
   4. `cd src`
   5. ../.venv/bin/python wxReader.py

2. Build your own binary:
```
uv --project . run pyinstaller \
  --name wxReader \
  --distpath build \
  --workpath build/pyi-build \
  --specpath build/pyi-spec \
  --onedir \
  --icon "$(pwd)/src/icon.png" \
  --add-data "$(pwd)/src/icon.png:icon.png" \
  --add-data "$(pwd)/src/filters:filters" \
  --add-data "$(pwd)/src/locale:locale" \
  --exclude-module tkinter \
  --exclude-module pillow \
  --collect-submodules OpenGL \
  src/wxReader.py
```

3. Pre-compiled binary: portable files are provided on the **Releases** page.

## Edit translation

See [/tools.txt](https://github.com/puff-dayo/wxReader/blob/goshujinsama/tools.txt) in the repo.

**Language support currently:** en_US, ja_JP, zh_SG and zh_TW.

Message files are extracted with [pybabel](https://github.com/python-babel/babel) and translated with tool [Virtaal](https://github.com/translate/virtaal).

## How to ... in wxReader

Check the `Menubar -> Info -> Help Topic` manual of wxReader.
