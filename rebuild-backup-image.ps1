$ErrorActionPreference = "Stop"
$root = Split-Path -Parent $MyInvocation.MyCommand.Path
$log = Join-Path $root "backup-build.log"
$err = Join-Path $root "backup-build.err"
$process = Start-Process -FilePath "podman" `
    -ArgumentList @("build", "--pull=always", "-f", "BackupDockerfile", "-t", "localhost/hamqtt-backup-pgbackrest:dev", ".") `
    -WorkingDirectory $root `
    -RedirectStandardOutput $log `
    -RedirectStandardError $err `
    -PassThru
Set-Content -Path (Join-Path $root "backup-build.pid") -Value $process.Id
Write-Output "Started backup image build PID $($process.Id)."