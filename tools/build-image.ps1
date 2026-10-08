$ErrorActionPreference = "Stop"
$root = Split-Path -Parent $PSScriptRoot
$log = Join-Path $root "build-image.log"
$err = Join-Path $root "build-image.err"
Remove-Item $log, $err -Force -ErrorAction SilentlyContinue
$process = Start-Process -FilePath "podman" `
  -ArgumentList @("build", "-t", "localhost/hamqtt-store:dev", ".") `
  -WorkingDirectory $root `
  -RedirectStandardOutput $log `
  -RedirectStandardError $err `
  -PassThru
Write-Output "Build process started: $($process.Id)"
Write-Output "Log: $log"