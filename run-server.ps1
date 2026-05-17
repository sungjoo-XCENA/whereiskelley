$Public = $args -contains "-Public"
if ($Public) {
  $env:WHEREISKELLEY_HOST = "0.0.0.0"
} elseif (-not $env:WHEREISKELLEY_HOST) {
  $env:WHEREISKELLEY_HOST = "127.0.0.1"
}
$ErrorActionPreference = "Stop"
$python = Join-Path $env:USERPROFILE ".cache\codex-runtimes\codex-primary-runtime\dependencies\python\python.exe"
if (-not (Test-Path $python)) {
  $python = "python"
}
& $python .\app.py
