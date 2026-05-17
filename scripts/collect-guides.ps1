param(
  [switch]$Quick,
  [switch]$Discover,
  [switch]$NoSnapshot,
  [int]$MaxSourceItems = 200,
  [int]$MaxTargets = 100,
  [string]$Sources = "michelin,laliste,worlds50best"
)

$ErrorActionPreference = "Stop"
$project = Split-Path -Parent (Split-Path -Parent $MyInvocation.MyCommand.Path)
$python = Join-Path $env:USERPROFILE ".cache\codex-runtimes\codex-primary-runtime\dependencies\python\python.exe"
if (-not (Test-Path $python)) {
  $python = "python"
}

if ($Quick) {
  $MaxSourceItems = [Math]::Min($MaxSourceItems, 5)
  $MaxTargets = [Math]::Min($MaxTargets, 5)
}

Push-Location $project
try {
  $args = @(
    ".\scripts\guide_collect.py",
    "--sources", $Sources,
    "--max-source-items", "$MaxSourceItems",
    "--max-targets", "$MaxTargets"
  )
  if ($Discover) {
    $args += "--discover"
  } else {
    $args += "--no-discover"
  }
  & $python @args

  if (-not $NoSnapshot) {
    & $python .\scripts\export_snapshot.py
  }
}
finally {
  Pop-Location
}
