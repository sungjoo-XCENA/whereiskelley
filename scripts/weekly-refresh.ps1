param(
  [switch]$SkipSync,
  [switch]$Quick,
  [switch]$NoPush,
  [int]$MaxPdfs = 999999,
  [int]$DelayMs = 800
)

$ErrorActionPreference = "Stop"
$project = Split-Path -Parent (Split-Path -Parent $MyInvocation.MyCommand.Path)
$python = Join-Path $env:USERPROFILE ".cache\codex-runtimes\codex-primary-runtime\dependencies\python\python.exe"
if (-not (Test-Path $python)) {
  $python = "python"
}

Push-Location $project
try {
  if (-not $SkipSync) {
    if ($Quick) {
      Write-Host "Running quick Star Wine collection sample..."
      & $python .\scripts\sync_search_api.py --pages=10 --download-pdfs --max-pdfs=20
    } else {
      Write-Host "Running resumable full Star Wine collection sweep..."
      & $python .\scripts\sync_search_sweep.py --download-pdfs --max-pdfs=$MaxPdfs --delay-ms=$DelayMs --state-file .\data\search-sweep-state.json
    }
  } else {
    Write-Host "Skipping collection. Exporting the current local DB snapshot only..."
  }

  Write-Host "Exporting web snapshot to public/data..."
  & $python .\scripts\export_snapshot.py

  if ($NoPush) {
    Write-Host "Snapshot created. Push skipped because -NoPush was set."
    exit 0
  }

  $git = Get-Command git -ErrorAction SilentlyContinue
  if (-not $git) {
    Write-Host "Snapshot created, but git was not found on this PC."
    Write-Host "Use GitHub Desktop or install Git, then commit and push public/data."
    exit 0
  }

  git add public/data
  git add README.md scripts/export_snapshot.py scripts/export-snapshot.ps1 scripts/weekly-refresh.ps1
  $changes = git status --porcelain
  if (-not $changes) {
    Write-Host "No snapshot changes to commit."
    exit 0
  }

  $stamp = Get-Date -Format "yyyy-MM-dd HH:mm"
  git commit -m "Update local collection snapshot $stamp"
  git push origin main
  Write-Host "Snapshot pushed. Vercel will redeploy from GitHub."
}
finally {
  Pop-Location
}
