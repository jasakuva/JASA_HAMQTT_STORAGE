@echo off
setlocal EnableExtensions EnableDelayedExpansion
cd /d "%~dp0"

 echo.
echo ============================================
echo   HAMQTT Store - Podman Update
echo ============================================
echo.

where podman-compose >nul 2>&1
if errorlevel 1 (
    echo ERROR: podman-compose was not found in PATH.
    exit /b 1
)

rem Build while existing containers still run, so a build failure does not stop them.
echo [1/6] Building application image...
podman-compose build --pull
if errorlevel 1 goto :failed

rem Never use -v here: preserve existing PostgreSQL and application volumes.
echo [2/6] Removing old containers (preserving named volumes)...
podman-compose down
if errorlevel 1 goto :failed

rem --no-deps prevents Podman from constructing the nested startup dependency graph.
echo [3/6] Starting PostgreSQL and Redis...
podman-compose up -d --no-deps postgres redis
if errorlevel 1 goto :failed

 echo [4/6] Waiting for services to become healthy...
call :wait_healthy hamqtt-postgres 90
if errorlevel 1 goto :failed
call :wait_healthy hamqtt-redis 60
if errorlevel 1 goto :failed

rem Alembic upgrade head is safe to run repeatedly: it applies only pending migrations.
echo [5/6] Running database migrations...
podman-compose run --rm --no-deps migrate
if errorlevel 1 goto :failed

 echo [6/6] Starting application services...
podman-compose up -d --no-deps web mqtt-ingestor ha-ingestor mcp cleanup
if errorlevel 1 goto :failed

 echo.
echo SUCCESS: HAMQTT Store update finished.
podman ps --filter label=com.hamqtt.product=hamqtt-store
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
    if /i "!HEALTH!"=="unhealthy" (
        echo   !SERVICE!: currently unhealthy, retrying...
    )
    timeout /t 2 /nobreak >nul
)
echo ERROR: !SERVICE! did not become healthy.
exit /b 1

:failed
echo.
echo ERROR: Update stopped. Check the output above.
echo Your named volumes were not removed.
exit /b 1
