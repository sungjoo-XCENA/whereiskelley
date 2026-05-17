param(
  [switch]$Quick,
  [switch]$Discover,
  [switch]$SkipGoogle,
  [switch]$RefreshWebsites,
  [switch]$NoSnapshot,
  [switch]$Snapshot,
  [int]$MaxSourceItems = 0,
  [int]$MaxTargets = 0,
  [string]$Sources = "michelin,laliste,worlds50best"
)

$ErrorActionPreference = "Stop"
$project = Split-Path -Parent (Split-Path -Parent $MyInvocation.MyCommand.Path)
$python = Join-Path $env:USERPROFILE ".cache\codex-runtimes\codex-primary-runtime\dependencies\python\python.exe"
if (-not (Test-Path $python)) {
  $python = "python"
}

if ($Quick) {
  if ($MaxSourceItems -le 0) {
    $MaxSourceItems = 5
  } else {
    $MaxSourceItems = [Math]::Min($MaxSourceItems, 5)
  }
  if ($MaxTargets -le 0) {
    $MaxTargets = 5
  } else {
    $MaxTargets = [Math]::Min($MaxTargets, 5)
  }
  if (-not $Snapshot) {
    $NoSnapshot = $true
  }
}

Push-Location $project
try {
  if ($Discover) {
    $args = @(
      ".\scripts\guide_discover_wine_lists.py",
      "--max-targets", "$MaxTargets"
    )
    if ($SkipGoogle) {
      $args += "--skip-google"
    }
    if ($RefreshWebsites) {
      $args += "--refresh-websites"
    }
  } else {
    $args = @(
      ".\scripts\guide_collect_targets.py",
      "--sources", $Sources,
      "--max-source-items", "$MaxSourceItems"
    )
  }
  & $python @args

  if (-not $NoSnapshot) {
    & $python .\scripts\export_snapshot.py
  }
}
finally {
  Pop-Location
}
