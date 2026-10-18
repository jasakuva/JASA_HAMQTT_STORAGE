@echo off
setlocal EnableExtensions EnableDelayedExpansion
cd /d "%~dp0"

echo.
echo ============================================
echo   HAMQTT Store - Full Rebuild
echo ============================================
echo.

where podman-compose >nul 2>&1
if errorlevel 1 (
    echo ERROR: podman-compose was not found in PATH.
    exit /b 1
)

echo [1/8] Rebuilding the application image without cache...
podman build --pull=always --no-cache -f build/Dockerfile -t localhost/hamqtt-store:dev .
if errorlevel 1 goto :failed

echo [2/8] Rebuilding the PostgreSQL image without cache...
podman build --pull=always --no-cache -f build/PostgresBackupDockerfile -t localhost/hamqtt-postgres-pgbackrest:dev .
if errorlevel 1 goto :failed

echo [3/8] Rebuilding the backup and recovery image without cache...
podman build --pull=always --no-cache -f build/BackupDockerfile -t localhost/hamqtt-backup-pgbackrest:dev .
if errorlevel 1 goto :failed

rem Never use -v: preserve PostgreSQL data, application data, and backups.
echo [4/8] Recreating containers while preserving named volumes...
podman-compose down
if errorlevel 1 goto :failed

echo [5/8] Starting PostgreSQL and Redis...
podman-compose up -d --no-deps postgres redis
if errorlevel 1 goto :failed

echo [6/8] Waiting for PostgreSQL and Redis...
call :wait_healthy hamqtt-postgres 90
if errorlevel 1 goto :failed
call :wait_healthy hamqtt-redis 60
if errorlevel 1 goto :failed

echo [7/8] Applying database migrations...
podman-compose run --rm --no-deps migrate
if errorlevel 1 goto :failed

echo [8/8] Starting application services...
podman-compose up -d --no-deps web mqtt-ingestor ha-ingestor mcp cleanup backup recovery
if errorlevel 1 goto :failed

echo.
echo SUCCESS: HAMQTT Store rebuild finished. Persistent volumes were preserved.
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
    timeout /t 2 /nobreak >nul
)
echo ERROR: !SERVICE! did not become healthy.
exit /b 1

:failed
echo.
echo ERROR: Rebuild stopped. Check the output above.
echo Persistent volumes were not deliberately removed.
exit /b 1