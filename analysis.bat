@echo off
setlocal enabledelayedexpansion


set SRC_DIR=src
set OUT_DIR=analysis

echo [INFO] analysis for project: %SRC_DIR%

if not exist "%OUT_DIR%" (
    mkdir "%OUT_DIR%"
    echo [INFO] directory: %OUT_DIR%
)

uv run radon raw "%SRC_DIR%" -s > "%OUT_DIR%\metrics_raw.txt"

uv run radon cc "%SRC_DIR%" -a -s > "%OUT_DIR%\quality_complexity.txt"

uv run radon mi "%SRC_DIR%" -s > "%OUT_DIR%\quality_maintainability.txt"

uv run lizard "%SRC_DIR%" -o "%OUT_DIR%\report.html"

echo [SUCCESS] complete
echo.
pause
