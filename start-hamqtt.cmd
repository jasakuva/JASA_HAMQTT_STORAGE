@echo off
setlocal EnableExtensions EnableDelayedExpansion
cd /d "%~dp0"

echo.
echo ============================================
echo   HAMQTT Store - Podman Start
echo ============================================
echo.

where podman-compose >nul 2>&1
if errorlevel 1 (
    echo ERROR: podman-compose was not found in PATH.
    exit /b 1
)

echo [1/5] Checking required local images...
call :require_image localhost/hamqtt-store:dev
if errorlevel 1 goto :missing_images
call :require_image localhost/hamqtt-postgres-pgbackrest:dev
if errorlevel 1 goto :missing_images
call :require_image localhost/hamqtt-backup-pgbackrest:dev
if errorlevel 1 goto :missing_images

echo [2/5] Starting PostgreSQL and Redis...
podman-compose up -d --no-deps postgres redis
if errorlevel 1 goto :failed

echo [3/5] Waiting for PostgreSQL and Redis...
call :wait_healthy hamqtt-postgres 90
if errorlevel 1 goto :failed
call :wait_healthy hamqtt-redis 60
if errorlevel 1 goto :failed

rem Safe on every start: Alembic applies only migrations that are missing.
echo [4/5] Checking database migrations...
podman-compose run --rm --no-deps migrate
if errorlevel 1 goto :failed

rem Avoid the podman-compose nested depends_on startup bug.
echo [5/5] Starting application services...
podman-compose up -d --no-deps web mqtt-ingestor ha-ingestor mcp cleanup backup recovery
if errorlevel 1 goto :failed

echo.
echo SUCCESS: HAMQTT Store startup finished.
podman ps --filter label=com.hamqtt.product=hamqtt-store
exit /b 0

:require_image
podman image exists "%~1" >nul 2>&1
if errorlevel 1 (
    echo   Missing: %~1
    exit /b 1
)
echo   Found: %~1
exit /b 0

:wait_healthy
set "SERVICE=%~1"
set /a "TRIES=%~2"
for /l %%I in (1,1,!TRIES!) do (
    set "HEALTH="
    for /f "delims=" %%H in ('podman inspect --format "{{.State.Health.Status}}" !SERVICE! 2^>nul') do set "HEALTH=%%H"
    if /i "!HEALTH!"=="healthy" (
        echo   !SERVICE!: healthy
        exit /b 0
    )
    timeout /t 2 /nobreak >nul
)
echo ERROR: !SERVICE! did not become healthy.
exit /b 1

:failed
echo.
echo ERROR: Startup stopped. Check output above.
echo No containers or volumes were deliberately removed.
exit /b 1

:missing_images
echo.
echo ERROR: One or more required HAMQTT images are missing.
echo Run update-hamqtt.cmd first to build the required images.
exit /b 1
