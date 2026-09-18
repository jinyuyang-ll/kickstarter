param([string]$TaskName = "KickstarterCollectionControl")
$ErrorActionPreference = "Stop"
$ProjectRoot = Split-Path -Parent $MyInvocation.MyCommand.Path
$Launcher = Join-Path $ProjectRoot "start_control_panel.ps1"
if (-not (Test-Path -LiteralPath $Launcher)) { throw "Missing launcher: $Launcher" }
$PowerShell = "$env:SystemRoot\System32\WindowsPowerShell\v1.0\powershell.exe"
$Arguments = '-NoProfile -WindowStyle Hidden -ExecutionPolicy Bypass -File "' + $Launcher + '"'
$Action = New-ScheduledTaskAction -Execute $PowerShell -Argument $Arguments
$Trigger = New-ScheduledTaskTrigger -AtLogOn -User $env:USERNAME
$Settings = New-ScheduledTaskSettingsSet -StartWhenAvailable -RestartCount 3 -RestartInterval (New-TimeSpan -Minutes 5) -ExecutionTimeLimit (New-TimeSpan -Days 0)
Register-ScheduledTask -TaskName $TaskName -Action $Action -Trigger $Trigger -Settings $Settings -Description "Local Kickstarter work-order queue; starts after sign-in." -Force | Out-Null
Write-Host "Installed sign-in task: $TaskName"
Write-Host "Control panel: http://127.0.0.1:8765"
