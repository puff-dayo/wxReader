@echo off

python -m nuitka ^
  --mode=standalone ^
  --output-dir=build ^
  --remove-output ^
  --follow-imports ^
  --windows-console-mode=attach ^
  --windows-icon-from-ico=icon.png ^
  --include-data-file=icon.png=icon.png ^
  wxReader.py

echo.
echo ================================
echo              DONE
echo Remember to
echo delete unnecessary dlls manually.
echo ================================
pause
