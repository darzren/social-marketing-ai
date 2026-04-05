# Social Marketing AI — Windows Task Scheduler Setup
# Run this once in PowerShell as Administrator to register the 9am daily task
# Usage: .\setup_task_scheduler.ps1
# To add more industries: .\setup_task_scheduler.ps1 -Industry real_estate

param(
    [string]$Industry = "generic",
    [string]$TimeAt   = "09:00"
)

$taskName   = "SocialMarketingAI_$Industry"
$scriptPath = "C:\social-marketing-ai\venv\Scripts\python.exe"
$args       = "C:\social-marketing-ai\main.py --industry $Industry"
$workDir    = "C:\social-marketing-ai"
$logPath    = "C:\social-marketing-ai\logs\task_scheduler_$Industry.log"

# Remove existing task with this name if present
Unregister-ScheduledTask -TaskName $taskName -Confirm:$false -ErrorAction SilentlyContinue

$action  = New-ScheduledTaskAction `
    -Execute $scriptPath `
    -Argument $args `
    -WorkingDirectory $workDir

$trigger = New-ScheduledTaskTrigger -Daily -At $TimeAt

$settings = New-ScheduledTaskSettingsSet `
    -ExecutionTimeLimit (New-TimeSpan -Hours 1) `
    -StartWhenAvailable `
    -RunOnlyIfNetworkAvailable

Register-ScheduledTask `
    -TaskName $taskName `
    -Action $action `
    -Trigger $trigger `
    -Settings $settings `
    -Description "Daily social media post for industry: $Industry" `
    -RunLevel Highest `
    -Force

Write-Host ""
Write-Host "Task '$taskName' registered — fires daily at $TimeAt" -ForegroundColor Green
Write-Host "To add another industry, run:"
Write-Host "  .\setup_task_scheduler.ps1 -Industry real_estate -TimeAt 09:00" -ForegroundColor Cyan
Write-Host "  .\setup_task_scheduler.ps1 -Industry swimwear -TimeAt 10:00" -ForegroundColor Cyan
Write-Host ""
Write-Host "To view all tasks: Get-ScheduledTask | Where-Object { `$_.TaskName -like 'SocialMarketingAI*' }"
Write-Host "To remove a task:  Unregister-ScheduledTask -TaskName '$taskName' -Confirm:`$false"
