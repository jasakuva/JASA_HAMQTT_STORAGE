$ErrorActionPreference = "Stop"
$root = Split-Path -Parent $PSScriptRoot
$logDirectory = Join-Path $root "artifacts\logs"
New-Item -ItemType Directory -Force -Path $logDirectory | Out-Null
$log = Join-Path $logDirectory "backup-build.log"
$err = Join-Path $logDirectory "backup-build.err"
$process = Start-Process -FilePath "podman" `
    -ArgumentList @("build", "--pull=always", "-f", "build/BackupDockerfile", "-t", "localhost/hamqtt-backup-pgbackrest:dev", ".") `
    -WorkingDirectory $root `
    -RedirectStandardOutput $log `
    -RedirectStandardError $err `
    -PassThru
Set-Content -Path (Join-Path $logDirectory "backup-build.pid") -Value $process.Id
Write-Output "Started backup image build PID $($process.Id)."