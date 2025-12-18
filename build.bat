@echo off

python -m nuitka ^
  --mode=standalone ^
  --output-dir=build ^
  --remove-output ^
  --follow-imports ^
  --windows-console-mode=attach ^
  --windows-icon-from-ico=icon.png ^
  wxReader.py

echo.
echo ================================
echo              DONE
echo Remember to copy icon.png and
echo delete unnecessary dlls.
echo ================================
pause
