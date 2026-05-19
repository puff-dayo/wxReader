# wxReader

**wxReader** is a document reader for **ZIP comics, ZIP manga, PDF**, and more. Built with wxPython, PyMuPDF, OpenGL, libvips, Nuitka, and Python. It is distributed as a compiled portable Windows app (Linux version is unmaintained).

Fora a comfortable reading experience, it provides a mouse shortcut wheel, multi-tab reading, blank-page padding for proper two-page spreads, dark mode, password book for zip files with a password, and a custom page effect renderer with user-defined and preloaded GLSL fragment shaders.

**wxReaderVoiceCtrl** is a hands-free external controller app for wxReader, recognizing voice command offline by vosk and pyaudio. GUI is built with wxPython. **wxReaderEyeTrackCtrl** is a hands-free external controller app for wxReader, recognizing eye movement and blinking gesture offline by [EyeTrax](https://doi.org/10.5281/zenodo.17188537) through a webcam.

**-> Download link <-**
<br>wxReader v1.6.0 for [Windows10+](https://github.com/puff-dayo/wxReader/releases) (>1809)
<br>wxReader v1.3.9 for [Debian13](https://github.com/puff-dayo/wxReader/releases/download/v1.3.9/wxReader_v1.3.9_debian13_amd64.zip)
<br>external controllers for [Windows10+_avx2](https://github.com/puff-dayo/wxReader/releases/tag/v1.3.6) (>1809)

Build/run from source: see below.

| Light mode                                                                                                 | Dark mode                                                                                                  |
|------------------------------------------------------------------------------------------------------------|------------------------------------------------------------------------------------------------------------|
| <img src="https://github.com/puff-dayo/wxReader/blob/goshujinsama/screenshot/1.png?raw=true" width="100%"> | <img src="https://github.com/puff-dayo/wxReader/blob/goshujinsama/screenshot/2.png?raw=true" width="100%"> |

---

## Minimum GPU Requirements

Any GPU with OpenGL 2.1 support is compatible. This typically includes:

Intel Graphics: GMA 950 and later<br>
NVIDIA: GeForce 6000 series and later<br>
AMD/ATI: Radeon X1000 series and later<br>
All-in-Wonder: ATI X600 series and later

## Installation

### Windows

1. From sauce (latest dev):
   1. Install Python 3.12 and uv, `uv --project . sync`.
   2. [Download](https://www.libvips.org/install.html) and put the libvips shared library *.dll files inside `.\src`.
   3. Sync dependencies with `uv`.
   4. Build with `.\build.bat` on Windows x64. (Run the build script inside root folder.)
   5. (Notes: upgrade pymupdf will fail the compilation.)
   6. Optional example controller apps: `uv --project .\extctrl\voice sync`, `uv --project .\extctrl\eye_track sync`, then build with `.\build_*.bat`.

2. Pre-compiled binary (stable): portable `.exe` files are provided on the **Releases** page. Here are links to download (for win10+ x86_64):
   1. [wxReader](https://github.com/puff-dayo/wxReader/releases/)
   2. [wxReaderVoiceCtrl](https://github.com/puff-dayo/wxReader/releases/download/v1.3.6/wxReaderVoiceCtrl_msvc_avx2_x64.zip)
   3. [wxReaderEyeTrackCtrl](https://github.com/puff-dayo/wxReader/releases/download/v1.3.6/wxReaderEyeTrackCtrl_pyi_x64.zip)

3. Upgrade from older versions: simply copy the `wxReader.cfg` and `pswd.txt` files containing all user settings to the folder of a new version. You (probably) can also just unzip and overwrite existing files in the old folder.

### Linux (unmaintained)

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
