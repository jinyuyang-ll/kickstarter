param([string]$TaskName = "KickstarterCollectionControl")
$ErrorActionPreference = "Stop"
$ProjectRoot = Split-Path -Parent $MyInvocation.MyCommand.Path
$Launcher = Join-Path $ProjectRoot "start_control_panel.ps1"
if (-not (Test-Path -LiteralPath $Launcher)) { throw "缺少启动脚本: $Launcher" }
$PowerShell = "$env:SystemRoot\System32\WindowsPowerShell\v1.0\powershell.exe"
$Arguments = '-NoProfile -WindowStyle Hidden -ExecutionPolicy Bypass -File "' + $Launcher + '"'
$Action = New-ScheduledTaskAction -Execute $PowerShell -Argument $Arguments
$Trigger = New-ScheduledTaskTrigger -AtLogOn -User $env:USERNAME
$Settings = New-ScheduledTaskSettingsSet -StartWhenAvailable -RestartCount 3 -RestartInterval (New-TimeSpan -Minutes 5) -ExecutionTimeLimit (New-TimeSpan -Days 0)
Register-ScheduledTask -TaskName $TaskName -Action $Action -Trigger $Trigger -Settings $Settings -Description "Kickstarter本地工单队列控制台；登录后自动启动" -Force | Out-Null
Write-Host "已安装登录自启动任务: $TaskName"
Write-Host "控制台地址: http://127.0.0.1:8765"

\n