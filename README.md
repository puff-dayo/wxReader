# wxReader

**wxReader** is a ~lightweight, high-performance~ document reader built with wxWidgets (wxPython), MuPDF (PyMuPDF), OpenGL (PyOpenGL), libvips (pyvips), and
Python.

**wxReaderVoiceCtrl** is a hands-free external controller app for wxReader, recognizing **voice command** offline by vosk and pyaudio. GUI is  built with wxPython.

**wxReaderEyeTrackCtrl** is a hands-free external controller app for wxReader, recognizing **eye movement and blinking gesture** offline by EyeTrax(https://doi.org/10.5281/zenodo.17188537) through a webcam. GUI is also built with wxPython.

> **Version 1.3.4** Add customizable keyboard shortcuts. Add GUI control on uStrength of shaders. Add a folder tab in the sidebar. Gallery and cache performance optimized.
> 
> **Version 1.3.6** Add support for external controlled page tuning, and add example apps of voice and eye gesture command. UI/UX enhancements. Bugs fixed.

---

## Features

<div style="display: flex; justify-content: space-between;">
  <img src="https://github.com/puff-dayo/wxReader/blob/goshujinsama/screenshot/1_1.png?raw=true" width="49%">
  <img src="https://github.com/puff-dayo/wxReader/blob/goshujinsama/screenshot/1_2.png?raw=true" width="49%">
</div>

| Feature                 | Description                                                                                              |
|-------------------------|----------------------------------------------------------------------------------------------------------|
| **File Format Support** | PDF, EPUB, ePub, ZIP, CBZ (manga or comics archive files).                                               |
| **Paging Strategy**     | Single Page and Two-Page spreads (with optional blank start page). Supports Right-to-Left (RTL) reading. |
| **Content Extraction**  | Extract text and images directly from specific pages to the clipboard or disk.                           |
| **Image Processing**    | Real-time built-in filters and enhancements. Support custom OpenGL frag shaders.                         |
| **Zoom and View**       | Fit Width, Fit Page, Manual Zoom, Fullscreen Mode, and customizable background color.                    |
| **Navigation**          | Sidebar with Outline (TOC) and File Browser tabs. Text search dialog, and a standalone TOC dialog.       |
| **Gallery Mode**        | View all thumbnails or frontpages of all books inside a same folder like a gallery.                      |
| **File History**        | Automatically saves recent files and reading progress on close.                                          |
| **Interaction**         | Drag-and-drop file loading and full keyboard operation support.                                          |
| **External control**    | (Default off.) Send command+token to a local UDP port to do page turning.                                |

**Accessibility features**: The two independent external control programs, **wxReaderVoiceCtrl** and **wxReaderEyeTrackCtrl**, respectively provides offline voice-activated page turning commands and offline eye gesture based page-turning via computer camera recognition, triggered by “blinking twice while looking at a designated area of the screen.” (The are fully offline and requires a not-potato CPU.)

<div style="display: flex; justify-content: space-between;">
    <img src="https://github.com/puff-dayo/wxReader/blob/goshujinsama/screenshot/3.png?raw=true" width="49%">
    <img src="https://github.com/puff-dayo/wxReader/blob/goshujinsama/screenshot/4.png?raw=true" width="49%">
</div>

---

## Installation

1. From sauce (latest dev):
   1. Install Python 3.12 and uv, `uv --project . sync`.
   2. [Download](https://www.libvips.org/install.html) and put the libvips shared library *.dll files inside `.\src`.
   3. Sync dependencies with `uv`.
   4. Build with `.\build.bat` on Windows x64. (Run the build
      script inside /src folder.)
   5. (Notes: upgrade pymupdf will fail the compilation, and this is a Nuitka issue.)
   6. Optional: `uv --project .\extctrl\voice sync`, `uv --project .\extctrl\eye_track sync`, then build with `.\build_*.bat`.

2. Pre-compiled binary (stable): portable `.exe` files are provided on the **Releases** page. Here are links to download (for win10+ x86_64):
   1. [wxReader](https://github.com/puff-dayo/wxReader/releases/download/v1.3.6/wxReader_v1.3.6_msvc_avx2_x64.zip)
   2. [wxReaderVoiceCtrl](https://github.com/puff-dayo/wxReader/releases/download/v1.3.6/wxReaderVoiceCtrl_msvc_avx2_x64.zip)
   3. [wxReaderEyeTrackCtrl](https://github.com/puff-dayo/wxReader/releases/download/v1.3.6/wxReaderEyeTrackCtrl_pyi_x64.zip)

3. Upgrade from older versions: simply copy the `wxReader.cfg` and `pswd.txt` files containing all user settings to the folder of a new version. You (probably) can also just unzip and overwrite existing files in the old folder. 

## TODO

- [ ] keys for navigation can conflict with input fields
