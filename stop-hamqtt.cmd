@echo off
setlocal EnableExtensions
cd /d "%~dp0"

echo.
echo ============================================
echo   HAMQTT Store - Safe Stop
echo ============================================
echo.

where podman-compose >nul 2>&1
if errorlevel 1 (
    echo ERROR: podman-compose was not found in PATH.
    exit /b 1
)

echo Stopping HAMQTT containers without removing containers or volumes...
podman-compose stop
if errorlevel 1 (
    echo ERROR: One or more containers could not be stopped.
    exit /b 1
)

echo.
echo SUCCESS: HAMQTT Store is stopped. Persistent volumes were preserved.
podman-compose ps -a
exit /b 0