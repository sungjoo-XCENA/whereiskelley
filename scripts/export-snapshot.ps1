$ErrorActionPreference = "Stop"
$project = Split-Path -Parent (Split-Path -Parent $MyInvocation.MyCommand.Path)
$python = Join-Path $env:USERPROFILE ".cache\codex-runtimes\codex-primary-runtime\dependencies\python\python.exe"
if (-not (Test-Path $python)) {
  $python = "python"
}
Push-Location $project
try {
  & $python .\scripts\export_snapshot.py
}
finally {
  Pop-Location
}
