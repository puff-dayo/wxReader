# wxReader

**wxReader** is a lightweight, high-performance document reader built with wxWidgets (wxPython), MuPDF (PyMuPDF), OpenGL (PyOpenGL), libvips (pyvips), and
Python.

> **Version ~1.2** Supports OpenGL shaders with some built-in options, and you can add your own custom shaders. New Gallery mode, built-in help manual.
> 
> **Version 1.3.3** Add support for zip and cbz files. Add passwordbook support. Switch image backend to libvips. Fix image cache. Refactor code for maintainability. New UI decorations. MANY bugs fixed. 

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

---

## Installation

1. From sauce (latest dev):
   1. Install Python 3.12 and uv.
   2. [Download](https://www.libvips.org/install.html) and put the libvips shared library *.dll files inside `./src`.
   3. Sync dependencies with `uv`.
   4. Build with `cd ./src` and `../build.bat` on Windows x64. (Run the build
      script inside /src folder.)
   5. (Notes: upgrade pymupdf will fail the compilation, and this is a Nuitka issue.)

2. Pre-compiled binary (stable): portable `.exe` files is provided on the **Releases** page.

3. Upgrade from older versions: simply copy the `wxReader.cfg` file containing all user settings to the folder of a new version.

## TODO

- [x] add support for zip and cbz format manga/comic files <- that's a hard refactor
- [x] add support for encrypted zip and cbz files...
- [x] fix page/width fit not auto updating when a book is made of pages of different sizes
- [x] handle two pages of different size in Two-page view
- [x] add manual detect new version and open browser in the menu
- [ ] scale UI (add to `get_app_font(size)`)
- [ ] keys for navigation can conflict with input fields
