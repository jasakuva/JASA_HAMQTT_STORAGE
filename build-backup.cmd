@echo off
setlocal
cd /d "%~dp0"

echo Building the dedicated HAMQTT backup image...
podman build --pull=always -f BackupDockerfile -t localhost/hamqtt-backup-pgbackrest:dev .
if errorlevel 1 exit /b 1

echo Recreating only hamqtt-backup without removing volumes...
podman rm -f hamqtt-backup >nul 2>&1
podman-compose up -d --no-deps backup
if errorlevel 1 exit /b 1

echo Verifying pgBackRest...
podman run --rm --entrypoint pgbackrest localhost/hamqtt-backup-pgbackrest:dev version
if errorlevel 1 exit /b 1
podman logs --tail 50 hamqtt-backup