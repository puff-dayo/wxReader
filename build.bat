@echo off
setlocal
cd /d "%~dp0"

uv --project . run python -m PyInstaller ^
  --onedir ^
  --contents-directory . ^
  --name wxReader ^
  --distpath build ^
  --workpath build\pyinstaller-temp ^
  --console ^
  --icon ".\src\icon.png" ^
  --hidden-import wx._xml ^
  --collect-data pymupdf ^
  --hide-console hide-early ^
  --exclude-module onnxruntime ^
  --add-data ".\src\icon.png:." ^
  --add-data ".\src\filters:filters" ^
  --add-data ".\src\locale:locale" ^
  --add-binary ".\src\libglib-2.0-0.dll:." ^
  --add-binary ".\src\libgobject-2.0-0.dll:." ^
  --add-binary ".\src\libvips-42.dll:." ^
  --add-binary ".\src\libvips-cpp-42.dll:." ^
  ".\src\wxReader.py"

if errorlevel 1 (
    echo BUILD FAILED
    pause
    exit /b 1
)

echo.
echo DONE: build\wxReader\wxReader.exe
pause
