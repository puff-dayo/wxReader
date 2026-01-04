@echo off
echo Remember to run this inside the ./src folder

set CCFLAGS=/arch:AVX2

python -m nuitka ^
  --mode=standalone ^
  --lto=yes ^
  --output-dir=build ^
  --remove-output ^
  --follow-imports ^
  --windows-console-mode=attach ^
  --windows-icon-from-ico=icon.png ^
  --include-data-file=icon.png=icon.png ^
  --include-data-file=libglib-2.0-0.dll=libglib-2.0-0.dll ^
  --include-data-file=libgobject-2.0-0.dll=libgobject-2.0-0.dll ^
  --include-data-file=libvips-42.dll=libvips-42.dll ^
  --include-data-file=libvips-cpp-42.dll=libvips-cpp-42.dll ^
  --include-data-dir=filters=filters ^
  wxReader.py

echo.
echo ================================
echo              DONE
echo delete unnecessary tkinter dlls and pil folder manually.
echo ================================
pause
