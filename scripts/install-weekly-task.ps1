$ErrorActionPreference = "Stop"

$project = Split-Path -Parent $PSScriptRoot
$taskName = "Where Is Kelley Guide Collection"
$script = Join-Path $project "scripts\collect-guides.ps1"
$action = New-ScheduledTaskAction -Execute "powershell.exe" -Argument "-ExecutionPolicy Bypass -File `"$script`" -Discover -MaxSourceItems 1000 -MaxTargets 1000" -WorkingDirectory $project
$trigger = New-ScheduledTaskTrigger -Weekly -DaysOfWeek Monday -At 3am
$settings = New-ScheduledTaskSettingsSet -AllowStartIfOnBatteries -DontStopIfGoingOnBatteries -StartWhenAvailable

Register-ScheduledTask -TaskName $taskName -Action $action -Trigger $trigger -Settings $settings -Description "Collect Michelin, La Liste, and World's 50 Best restaurant targets, discover wine lists, update the local DB snapshot." -Force
Write-Host "Installed weekly task: $taskName"
