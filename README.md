# wxReader

**wxReader** is a lightweight, high-performance document reader built with wxWidgets (wxPython), MuPDF (PyMuPDF), OpenGL (PyOpenGL), and
Python.

> **Version 1.1** Supports OpenGL shaders with some built-in options, and you can add your own custom shaders. (22-12-2025)
>
> **Version 1.2.1** Bug fix and UI/UX enhancements. New Gallery mode, built-in help manual.  More built-in shader to simulate reading papers. (31-12-2025)
> 
> **Version 1.3** Refactor to add support for zip and cbz files. Add passwordbook support. (WIP)

---

## Features

<div style="display: flex; justify-content: space-between;">
  <img src="https://github.com/puff-dayo/wxReader/blob/goshujinsama/screenshot/1_1.png?raw=true" width="49%">
  <img src="https://github.com/puff-dayo/wxReader/blob/goshujinsama/screenshot/1_2.png?raw=true" width="49%">
</div>

| Feature                 | Description                                                                                              |
|-------------------------|----------------------------------------------------------------------------------------------------------|
| **File Format Support** | PDF, EPUB... Supported by `MuPDF`.                                                                       |
| **Paging Strategy**     | Single Page and Two-Page spreads (with optional blank start page). Supports Right-to-Left (RTL) reading. |
| **Content Extraction**  | Extract text and images directly from specific pages to the clipboard or disk.                           |
| **Image Processing**    | Real-time built-in filters and enhancements. Support custom OpenGL frag shaders.                         |
| **Zoom & View**         | Fit Width, Fit Page, Fullscreen Mode (F11), and customizable background color.                           |
| **Navigation**          | Sidebar with Outline (TOC) and File Browser tabs. Text search dialog, and a standalone TOC dialog.       |
| **Reflowable Text**     | Adjustable font sizes for EPUB and other reflowable formats.                                             |
| **File History**        | Automatically saves recent files and reading progress on close.                                          |
| **Interaction**         | Drag-and-drop file loading and full keyboard operation support.                                          |

---

## Installation

1. From sauce: Sync dependencies with `uv` and build with `cd ./src` and `../build.bat` on Windows x64. (Run the build
   script inside /src folder.)

2. Pre-compiled binary: portable `.exe` files is provided on the **Releases** page.

## TODO

- [x] add support for zip and cbz format manga/comic files <- that's a hard refactor
- [x] add support for encrypted zip and cbz files...
- [x] fix page/width fit not auto updating when a book is made of pages of different sizes
- [x] handle two pages of different size in Two-page view
- [ ] add manual detect new version and open browser in the menu