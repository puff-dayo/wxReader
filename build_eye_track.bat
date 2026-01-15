@echo off
setlocal

set ROOT=%~dp0

set PYINSTALLER_CONFIG_DIR=%ROOT%build\_pyi_cache
set TEMP=%ROOT%build\_tmp
set TMP=%ROOT%build\_tmp

if not exist "%PYINSTALLER_CONFIG_DIR%" mkdir "%PYINSTALLER_CONFIG_DIR%"
if not exist "%TEMP%" mkdir "%TEMP%"

uv --project "%ROOT%extctrl\eye_track" run pyinstaller ^
  --noconfirm ^
  --onedir ^
  --console ^
  --name wxReaderEyeTrackCtrl ^
  --distpath "%ROOT%build" ^
  --workpath "%ROOT%build\_pyi_work" ^
  --specpath "%ROOT%build\_pyi_spec" ^
  --icon "%ROOT%extctrl\eye_track\icon.ico" ^
  --add-data "%ROOT%extctrl\eye_track\icon.png;." ^
  --collect-all eyetrax ^
  "%ROOT%extctrl\eye_track\wxReaderEyeTrackCtrl.py"

IF ERRORLEVEL 1 (
  echo.
  echo [ERROR] PyInstaller build failed.
  pause
  exit /b 1
)

set SRC_MP=%ROOT%extctrl\eye_track\.venv\Lib\site-packages\mediapipe\modules
set DST_MP=%ROOT%build\wxReaderEyeTrackCtrl\_internal\mediapipe\modules

if not exist "%SRC_MP%" (
  echo.
  echo [ERROR] Source mediapipe\modules not found:
  echo %SRC_MP%
  pause
  exit /b 1
)

if not exist "%DST_MP%" mkdir "%DST_MP%"

echo.
echo [INFO] Copying mediapipe\modules ...
robocopy "%SRC_MP%" "%DST_MP%" /E /NFL /NDL /NJH /NJS /NP

IF %ERRORLEVEL% GEQ 8 (
  echo.
  echo [ERROR] robocopy failed with code %ERRORLEVEL%.
  pause
  exit /b 1
)

echo.
echo DONE
echo Output: %ROOT%build\wxReaderEyeTrackCtrl\
pause
