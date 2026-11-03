[CmdletBinding()]
param(
    [switch]$SkipRestorePoint,
    [switch]$Elevated
)

Set-StrictMode -Version Latest
$ErrorActionPreference = 'Stop'

$AppName = 'PlanetAltTab'
$TaskName = 'PlanetAltTab'
$RunKey = 'HKCU\Software\Microsoft\Windows\CurrentVersion\Run'
$RunValueName = 'PlanetAltTab'
$SourceDir = $PSScriptRoot
$InstallDir = Join-Path -Path $env:LOCALAPPDATA -ChildPath $AppName
$Timestamp = Get-Date -Format 'yyyyMMdd-HHmmss'
$BackupDir = Join-Path -Path $SourceDir -ChildPath "backup\$Timestamp"
$ManifestPath = Join-Path -Path $BackupDir -ChildPath 'manifest.json'
$UninstallScript = Join-Path -Path $SourceDir -ChildPath 'uninstall.ps1'
$PayloadItems = @('app', 'bin', 'assets', 'runtime', 'uninstall.ps1', 'panic-restore.ps1')
$TouchedRegistryKeys = @()
$WindowsPowerShell = Join-Path -Path $env:SystemRoot -ChildPath 'System32\WindowsPowerShell\v1.0\powershell.exe'

$Manifest = [ordered]@{
    app        = $AppName
    version    = 1
    createdAt  = (Get-Date).ToString('o')
    installDir = $InstallDir
    taskName   = $TaskName
    autostart  = $null
    reverted   = $false
    entries    = [System.Collections.ArrayList]::new()
}

function Save-Manifest {
    $Manifest | ConvertTo-Json -Depth 6 | Set-Content -LiteralPath $ManifestPath -Encoding UTF8
}

function Add-ManifestEntry {
    param([Parameter(Mandatory)][hashtable]$Entry)
    $Entry['at'] = (Get-Date).ToString('o')
    [void]$Manifest.entries.Add($Entry)
    Save-Manifest
}

function Test-Prerequisite {
    if ([Environment]::OSVersion.Platform -ne [PlatformID]::Win32NT) {
        throw 'This installer only runs on Windows.'
    }
    if (-not [Environment]::Is64BitOperatingSystem) {
        throw 'A 64-bit Windows is required.'
    }
    if ([Environment]::OSVersion.Version.Build -lt 22000) {
        Write-Warning 'This build targets Windows 11 (build 22000+). Continuing on an older build.'
    }
    foreach ($item in $PayloadItems) {
        if (-not (Test-Path -LiteralPath (Join-Path -Path $SourceDir -ChildPath $item))) {
            throw "Missing payload item '$item' next to install.ps1."
        }
    }
}

function Test-ExistingInstall {
    $activeManifests = @(Get-ChildItem -Path (Join-Path -Path $SourceDir -ChildPath 'backup\*\manifest.json') -ErrorAction SilentlyContinue |
        Where-Object { -not (Get-Content -LiteralPath $_.FullName -Raw | ConvertFrom-Json).reverted })
    $task = Get-ScheduledTask -TaskName $TaskName -ErrorAction SilentlyContinue
    $runValue = Get-ItemProperty -LiteralPath "Registry::$RunKey" -Name $RunValueName -ErrorAction SilentlyContinue
    return ($activeManifests.Count -gt 0) -or ($null -ne $task) -or ($null -ne $runValue) -or (Test-Path -LiteralPath $InstallDir)
}

function Test-AccessDenied {
    param([Parameter(Mandatory)][Management.Automation.ErrorRecord]$Record)
    if ($Record.CategoryInfo.Category -eq [Management.Automation.ErrorCategory]::PermissionDenied) {
        return $true
    }
    $exception = $Record.Exception
    while ($null -ne $exception) {
        if ($exception.HResult -eq -2147024891) {
            return $true
        }
        $nativeCode = $exception.PSObject.Properties['NativeErrorCode']
        if ($null -ne $nativeCode -and "$($nativeCode.Value)" -eq 'AccessDenied') {
            return $true
        }
        $exception = $exception.InnerException
    }
    return $false
}

function Test-AdministratorsMember {
    return [bool]((& whoami.exe /groups) -match 'S-1-5-32-544')
}

function Invoke-RestorePoint {
    $restoreScript = @'
$ErrorActionPreference = 'Stop'
try {
    $before = @(Get-ComputerRestorePoint -ErrorAction SilentlyContinue).Count
    Checkpoint-Computer -Description 'PlanetAltTab install' -RestorePointType APPLICATION_INSTALL
    $after = @(Get-ComputerRestorePoint -ErrorAction SilentlyContinue).Count
    if ($after -gt $before) { exit 0 }
    exit 4
} catch {
    exit 3
}
'@
    $encoded = [Convert]::ToBase64String([Text.Encoding]::Unicode.GetBytes($restoreScript))
    Write-Output 'Creating a System Restore point. Windows asks for administrator approval for this step only.'
    try {
        $process = Start-Process -FilePath $WindowsPowerShell -Verb RunAs -WindowStyle Hidden -Wait -PassThru `
            -ArgumentList @('-NoProfile', '-ExecutionPolicy', 'Bypass', '-EncodedCommand', $encoded)
        $exitCode = $process.ExitCode
    }
    catch {
        $exitCode = -1
    }
    switch ($exitCode) {
        0 { $status = 'created' }
        3 { $status = 'disabled'; Write-Warning 'System Restore is disabled or unavailable on this PC (System Protection off). No restore point was created.' }
        4 { $status = 'throttled'; Write-Warning 'Windows skipped the restore point (only one is allowed every 24 hours by default). No new restore point was created.' }
        -1 { $status = 'declined'; Write-Warning 'Administrator approval was declined. No restore point was created.' }
        default { $status = "failed($exitCode)"; Write-Warning "Restore point creation failed with exit code $exitCode." }
    }
    Add-ManifestEntry -Entry @{ type = 'restore-point'; status = $status; description = 'PlanetAltTab install' }
}

function Backup-RegistryKey {
    param(
        [Parameter(Mandatory)][string]$Key,
        [string]$EntryType = 'registry'
    )
    $file = Join-Path -Path $BackupDir -ChildPath ("registry-{0}.reg" -f ($Key -replace '[\\/:*?"<>| ]', '_'))
    $existed = Test-Path -LiteralPath ("Registry::{0}" -f $Key)
    if ($existed) {
        & reg.exe export $Key $file /y | Out-Null
        if ($LASTEXITCODE -ne 0) {
            throw "Backing up registry key '$Key' failed."
        }
    }
    Add-ManifestEntry -Entry @{ type = $EntryType; key = $Key; existed = $existed; file = $file }
}

function Copy-Payload {
    New-Item -ItemType Directory -Path $InstallDir -Force | Out-Null
    Add-ManifestEntry -Entry @{ type = 'directory'; path = $InstallDir }
    foreach ($item in $PayloadItems) {
        Copy-Item -LiteralPath (Join-Path -Path $SourceDir -ChildPath $item) -Destination $InstallDir -Recurse -Force
    }
    Get-ChildItem -LiteralPath $InstallDir -Recurse -File | Unblock-File
}

function Register-AppTaskCore {
    param(
        [Parameter(Mandatory)][string]$Name,
        [Parameter(Mandatory)][string]$UserId,
        [Parameter(Mandatory)][string]$Pythonw,
        [Parameter(Mandatory)][string]$EntryPoint,
        [Parameter(Mandatory)][string]$WorkingDirectory,
        [Parameter(Mandatory)][string]$RunLevel
    )
    $action = New-ScheduledTaskAction -Execute $Pythonw -Argument ('"{0}"' -f $EntryPoint) -WorkingDirectory $WorkingDirectory
    $trigger = New-ScheduledTaskTrigger -AtLogOn -User $UserId
    $principal = New-ScheduledTaskPrincipal -UserId $UserId -LogonType Interactive -RunLevel $RunLevel
    $settings = New-ScheduledTaskSettingsSet -AllowStartIfOnBatteries -DontStopIfGoingOnBatteries -StartWhenAvailable `
        -ExecutionTimeLimit ([TimeSpan]::Zero) -MultipleInstances IgnoreNew -Priority 4
    Register-ScheduledTask -TaskName $Name -Action $action -Trigger $trigger -Principal $principal -Settings $settings `
        -Description 'Planet Alt+Tab window switcher (per-user autostart).' | Out-Null
}

function Register-ElevatedAppTask {
    param([Parameter(Mandatory)][hashtable]$TaskArguments)
    if (-not (Test-AdministratorsMember)) {
        throw '-Elevated needs an account in the local Administrators group.'
    }
    $quotedArguments = ($TaskArguments.GetEnumerator() | ForEach-Object { "-{0} '{1}'" -f $_.Key, ($_.Value -replace "'", "''") }) -join ' '
    $elevatedScript = @(
        '$ErrorActionPreference = ''Stop'''
        "function Register-AppTaskCore {${function:Register-AppTaskCore}}"
        "try { Register-AppTaskCore $quotedArguments -RunLevel Highest; exit 0 } catch { exit 3 }"
    ) -join "`n"
    $encoded = [Convert]::ToBase64String([Text.Encoding]::Unicode.GetBytes($elevatedScript))
    Write-Output 'Registering the elevated autostart task. Windows asks for administrator approval for this step.'
    try {
        $process = Start-Process -FilePath $WindowsPowerShell -Verb RunAs -WindowStyle Hidden -Wait -PassThru `
            -ArgumentList @('-NoProfile', '-ExecutionPolicy', 'Bypass', '-EncodedCommand', $encoded)
        $exitCode = $process.ExitCode
    }
    catch {
        $exitCode = -1
    }
    if ($exitCode -eq -1) {
        throw 'Administrator approval was declined. The elevated task was not registered.'
    }
    if ($exitCode -ne 0) {
        throw "Registering the elevated task failed with exit code $exitCode."
    }
}

function Register-RunValue {
    param(
        [Parameter(Mandatory)][string]$Pythonw,
        [Parameter(Mandatory)][string]$EntryPoint
    )
    Backup-RegistryKey -Key $RunKey -EntryType 'registry-snapshot'
    $runPath = "Registry::$RunKey"
    if (-not (Test-Path -LiteralPath $runPath)) {
        New-Item -Path $runPath -Force | Out-Null
    }
    $command = '"{0}" "{1}"' -f $Pythonw, $EntryPoint
    New-ItemProperty -LiteralPath $runPath -Name $RunValueName -Value $command -PropertyType String -Force | Out-Null
    Add-ManifestEntry -Entry @{ type = 'run-value'; key = $RunKey; name = $RunValueName; command = $command }
}

function Register-AppAutostart {
    $userId = [Security.Principal.WindowsIdentity]::GetCurrent().Name
    $pythonw = Join-Path -Path $InstallDir -ChildPath 'runtime\pythonw.exe'
    $entryPoint = Join-Path -Path $InstallDir -ChildPath 'app\planet_alttab.py'
    $taskArguments = @{ Name = $TaskName; UserId = $userId; Pythonw = $pythonw; EntryPoint = $entryPoint; WorkingDirectory = $InstallDir }
    if ($Elevated) {
        Register-ElevatedAppTask -TaskArguments $taskArguments
        Add-ManifestEntry -Entry @{ type = 'scheduled-task'; name = $TaskName; user = $userId; runLevel = 'Highest' }
        $Manifest['autostart'] = 'scheduled-task'
        Save-Manifest
        return
    }
    try {
        Register-AppTaskCore @taskArguments -RunLevel 'Limited'
        Add-ManifestEntry -Entry @{ type = 'scheduled-task'; name = $TaskName; user = $userId; runLevel = 'Limited' }
        $Manifest['autostart'] = 'scheduled-task'
    }
    catch {
        if (-not (Test-AccessDenied -Record $_)) {
            throw
        }
        Write-Warning "Task Scheduler denied access. Falling back to the per-user Run key ($RunKey\$RunValueName)."
        Register-RunValue -Pythonw $pythonw -EntryPoint $entryPoint
        $Manifest['autostart'] = 'run-key'
    }
    Save-Manifest
}

function Start-App {
    [CmdletBinding(SupportsShouldProcess)]
    param()
    if (-not $PSCmdlet.ShouldProcess($AppName, 'Start switcher')) {
        return
    }
    $pythonw = Join-Path -Path $InstallDir -ChildPath 'runtime\pythonw.exe'
    Add-ManifestEntry -Entry @{ type = 'process'; path = $pythonw }
    if ($Manifest['autostart'] -eq 'run-key') {
        $entryPoint = Join-Path -Path $InstallDir -ChildPath 'app\planet_alttab.py'
        Start-Process -FilePath $pythonw -ArgumentList ('"{0}"' -f $entryPoint) -WorkingDirectory $InstallDir
        Start-Sleep -Seconds 3
        $running = @(Get-Process -Name 'pythonw' -ErrorAction SilentlyContinue | Where-Object { $_.Path -eq $pythonw }).Count -gt 0
    }
    else {
        Start-ScheduledTask -TaskName $TaskName
        Start-Sleep -Seconds 3
        $running = "$((Get-ScheduledTask -TaskName $TaskName).State)" -eq 'Running'
    }
    if (-not $running) {
        $log = Join-Path -Path $InstallDir -ChildPath 'planet-alttab.log'
        Write-Warning "The switcher is not running. Native Alt+Tab stays active. Check '$log' if it exists."
    }
}

Test-Prerequisite
if (Test-ExistingInstall) {
    Write-Output 'An existing installation was found. Removing it first.'
    & $UninstallScript
}

New-Item -ItemType Directory -Path $BackupDir -Force | Out-Null
Save-Manifest

try {
    if ($SkipRestorePoint) {
        Add-ManifestEntry -Entry @{ type = 'restore-point'; status = 'skipped'; description = 'PlanetAltTab install' }
    }
    else {
        Invoke-RestorePoint
    }
    foreach ($key in $TouchedRegistryKeys) {
        Backup-RegistryKey -Key $key
    }
    Copy-Payload
    Register-AppAutostart
    Start-App
}
catch {
    Write-Warning "Install failed: $($_.Exception.Message)"
    Write-Warning 'Rolling back every recorded change.'
    & $UninstallScript -ManifestPath $ManifestPath
    throw
}

Write-Output "Installed to $InstallDir"
Write-Output "Manifest: $ManifestPath"
Write-Output 'Uninstall: powershell -ExecutionPolicy Bypass -File .\uninstall.ps1'
Write-Output 'Panic:     powershell -ExecutionPolicy Bypass -File .\panic-restore.ps1'
