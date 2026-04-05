# Social Marketing AI — Windows Task Scheduler Setup
# Run once in PowerShell as Administrator
# Usage: .\setup_task_scheduler.ps1
#        .\setup_task_scheduler.ps1 -Industry real_estate -TimeAt 09:15

param(
    [string]$Industry = "velocx_nz",
    [string]$TimeAt   = "09:15"
)

$taskName   = "SocialMarketingAI_Post_$Industry"
$scriptPath = "C:\social-marketing-ai\post_pending.bat"
$workDir    = "C:\social-marketing-ai"

Unregister-ScheduledTask -TaskName $taskName -Confirm:$false -ErrorAction SilentlyContinue

$action  = New-ScheduledTaskAction `
    -Execute $scriptPath `
    -Argument $Industry `
    -WorkingDirectory $workDir

$trigger  = New-ScheduledTaskTrigger -Daily -At $TimeAt

$settings = New-ScheduledTaskSettingsSet `
    -ExecutionTimeLimit (New-TimeSpan -Hours 1) `
    -StartWhenAvailable `
    -RunOnlyIfNetworkAvailable

Register-ScheduledTask `
    -TaskName $taskName `
    -Action $action `
    -Trigger $trigger `
    -Settings $settings `
    -Description "Daily social media poster for: $Industry" `
    -RunLevel Highest `
    -Force

Write-Host ""
Write-Host "Task '$taskName' registered — fires daily at $TimeAt" -ForegroundColor Green
Write-Host ""
Write-Host "Flow: Remote agent generates at 9:00am → this posts at 9:15am"
Write-Host ""
Write-Host "To add another brand:"
Write-Host "  .\setup_task_scheduler.ps1 -Industry real_estate -TimeAt 09:15" -ForegroundColor Cyan
