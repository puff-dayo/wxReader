@echo off

uv --project . run python -m nuitka ^
  --mode=standalone ^
  --lto=yes ^
  --output-dir=build ^
  --remove-output ^
  --follow-imports ^
  --nofollow-import-to=tkinter ^
  --nofollow-import-to=pillow ^
  --windows-console-mode=attach ^
  --windows-icon-from-ico=.\src\icon.png ^
  --include-data-file=.\src\icon.png=icon.png ^
  --include-data-file=.\src\libglib-2.0-0.dll=libglib-2.0-0.dll ^
  --include-data-file=.\src\libgobject-2.0-0.dll=libgobject-2.0-0.dll ^
  --include-data-file=.\src\libvips-42.dll=libvips-42.dll ^
  --include-data-file=.\src\libvips-cpp-42.dll=libvips-cpp-42.dll ^
  --include-data-dir=.\src\filters=filters ^
  --include-data-dir=.\src\locale=locale ^
  .\src\wxReader.py

echo.
echo DONE
pause
