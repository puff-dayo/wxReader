@echo off
set CCFLAGS=/arch:AVX2

uv --project .\extctrl\voice run python -m nuitka ^
  --mode=standalone ^
  --lto=yes ^
  --output-dir=build ^
  --remove-output ^
  --nofollow-import-to=tkinter ^
  --nofollow-import-to=pillow ^
  --nofollow-import-to=numpy ^
  --follow-imports ^
  --windows-console-mode=attach ^
  --windows-icon-from-ico=.\extctrl\voice\icon.png ^
  --include-data-file=.\extctrl\voice\icon.png=icon.png ^
  --include-data-dir=.\extctrl\voice\model=model ^
  .\extctrl\voice\wxReaderVoiceCtrl.py

echo.
echo DONE
pause
