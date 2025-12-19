# wxReader

**wxReader** is a lightweight, high-performance document reader built with wxWidgets(wxPython), MuPDF(PyMuPDF) and Python. It provides a better viewing experience for PDFs (and various e-book formats WIP).

---

## Features

<img height="300" src="https://github.com/puff-dayo/wxReader/blob/master/scrnsht/1_1.png?raw=true"/>

| Feature                 | Description                                                                                                        |
|-------------------------|--------------------------------------------------------------------------------------------------------------------|
| **File format support** | PDF, EPUB, MOBI, FB2, CBZ, and TXT files. Same as `MuPDF`.                                                         |
| **Paging strategy**     | Single Page and Two-Page spreads (option add a blank page at start), support for Right-to-Left (RTL) page turning. |
| **Image processing**    | Sharpen, Soften, Color Inversion, Green/Brown filters.                                                             |
| **Zoom**                | Fit Width, Fit Page and auto/manual modes.                                                                         |
| **Navigation & TOC**    | Integrated sidebar and search bar for document outlines.                                                           |
| **File history**        | Automatically saved in `wxReader.cfg`.                                                                             |
| **Interaction**         | Drag-and-drop file loading and FULL keyboard operation.                                                            |

---

## Getting Started

Sync dependencies with uv and build with `build.bat` on Windows x64. 

## TODO

- [x] add full screen mode.
- [ ] fix epub page margin/padding.
- [ ] fix recent files display
- [ ] saved font size should load on first time