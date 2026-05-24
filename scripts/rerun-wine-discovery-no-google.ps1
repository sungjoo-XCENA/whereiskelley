$ErrorActionPreference = "Stop"

$Root = Resolve-Path (Join-Path $PSScriptRoot "..")
$Python = Join-Path $env:USERPROFILE ".cache\codex-runtimes\codex-primary-runtime\dependencies\python\python.exe"
if (-not (Test-Path $Python)) {
  $Python = "python"
}

Push-Location $Root
try {
  & $Python .\scripts\guide_discover_wine_lists.py --skip-google --only-with-website --recheck-all --replace-existing
  & $Python .\scripts\export_snapshot.py
}
finally {
  Pop-Location
}
