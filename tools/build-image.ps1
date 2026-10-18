$ErrorActionPreference = "Stop"
$root = Split-Path -Parent $PSScriptRoot
$logDirectory = Join-Path $root "artifacts\logs"
New-Item -ItemType Directory -Force -Path $logDirectory | Out-Null
$log = Join-Path $logDirectory "build-image.log"
$err = Join-Path $logDirectory "build-image.err"
Remove-Item $log, $err -Force -ErrorAction SilentlyContinue
$process = Start-Process -FilePath "podman" `
  -ArgumentList @("build", "-f", "build/Dockerfile", "-t", "localhost/hamqtt-store:dev", ".") `
  -WorkingDirectory $root `
  -RedirectStandardOutput $log `
  -RedirectStandardError $err `
  -PassThru
Write-Output "Build process started: $($process.Id)"
Write-Output "Log: $log"