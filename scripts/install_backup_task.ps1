# Registers (or replaces) the Windows scheduled task that runs scripts\backup.py.
#
#   powershell -ExecutionPolicy Bypass -File scripts\install_backup_task.ps1
#   powershell -ExecutionPolicy Bypass -File scripts\install_backup_task.ps1 -Times 12:00,17:30
#   powershell -ExecutionPolicy Bypass -File scripts\install_backup_task.ps1 -Remove
#
# The task runs as the signed-in user, so it needs no stored password. If the computer is off or
# nobody is signed in at a scheduled time, the run happens as soon as it can (StartWhenAvailable),
# instead of being skipped. Run this on the computer that hosts the database.

param(
    [string[]]$Times = @("12:00", "17:30"),
    [string]$TaskName = "SB Tolosa backup",
    [switch]$Remove
)

$ErrorActionPreference = "Stop"
$ProjectRoot = Split-Path -Parent $PSScriptRoot

if ($Remove) {
    Unregister-ScheduledTask -TaskName $TaskName -Confirm:$false
    Write-Host "Removed scheduled task '$TaskName'."
    return
}

# pythonw runs without opening a console window; the outcome is written to backup.log either way.
$Python = Join-Path $ProjectRoot ".venv\Scripts\pythonw.exe"
if (-not (Test-Path $Python)) { $Python = Join-Path $ProjectRoot ".venv\Scripts\python.exe" }
if (-not (Test-Path $Python)) { throw "No virtual environment found at $ProjectRoot\.venv" }
$Script = Join-Path $ProjectRoot "scripts\backup.py"

$Action = New-ScheduledTaskAction -Execute $Python -Argument "`"$Script`"" -WorkingDirectory $ProjectRoot
$Triggers = $Times | ForEach-Object { New-ScheduledTaskTrigger -Daily -At $_ }
$Settings = New-ScheduledTaskSettingsSet -StartWhenAvailable -AllowStartIfOnBatteries -DontStopIfGoingOnBatteries `
    -ExecutionTimeLimit (New-TimeSpan -Hours 1) -MultipleInstances IgnoreNew
$Principal = New-ScheduledTaskPrincipal -UserId "$env:USERDOMAIN\$env:USERNAME" -LogonType Interactive -RunLevel Limited

Register-ScheduledTask -TaskName $TaskName -Action $Action -Trigger $Triggers -Settings $Settings -Principal $Principal `
    -Description "Backs up the SB Tolosa database and document storage (scripts\backup.py)." -Force | Out-Null

Write-Host "Scheduled task '$TaskName' runs $($Python | Split-Path -Leaf) scripts\backup.py daily at $($Times -join ', ')."
Write-Host "Run it now:  Start-ScheduledTask -TaskName '$TaskName'"
Write-Host "Results go to backup.log in the backup folder (BACKUP_DIR, or sb_tolosa_backups next to the project)."
