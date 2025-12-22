# wxReader

**wxReader** is a lightweight, high-performance document reader built with wxWidgets (wxPython), MuPDF (PyMuPDF), OpenGL (PyOpenGL), and
Python.

> Happy to announce the release of **Version 1.1**!<br>What's new: OpenGL shaders with some built-in options, and you can add your own custom shaders.

---

## Features

<img height="300" src="https://github.com/puff-dayo/wxReader/blob/master/screenshot/1_1.png?raw=true"/>

| Feature                 | Description                                                                                              |
|-------------------------|----------------------------------------------------------------------------------------------------------|
| **File Format Support** | PDF, EPUB, MOBI, FB2, CBZ, and TXT files. Supported by `MuPDF`.                                          |
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

1. From sauce: Sync dependencies with `uv` and build with `cd ./src` and `../build.bat` on Windows x64. Run the build
   script inside /src folder.

2. Pre-compiled binary: portable `.exe` files is provided on the **Releases** page.

## TODO

- [ ] fix epub page margin/padding.
- [x] support custom filters (or even shaders?) woooooooah! we have shaders
- [ ] file panel support sort by date
