[CmdletBinding()]
param()

Set-StrictMode -Version Latest
$ErrorActionPreference = 'Continue'

$AppName = 'PlanetAltTab'
$TaskName = 'PlanetAltTab'
$RunKey = 'HKCU\Software\Microsoft\Windows\CurrentVersion\Run'
$RunValueName = 'PlanetAltTab'
$WindowsPowerShell = Join-Path -Path $env:SystemRoot -ChildPath 'System32\WindowsPowerShell\v1.0\powershell.exe'
$Roots = @(
    (Join-Path -Path $env:LOCALAPPDATA -ChildPath $AppName),
    $PSScriptRoot
) | Where-Object { $_ } | ForEach-Object { [IO.Path]::GetFullPath($_).TrimEnd('\') + '\' } | Select-Object -Unique

function Test-AppPath {
    param([string]$Path)
    if (-not $Path) {
        return $false
    }
    foreach ($root in $Roots) {
        if ($Path.StartsWith($root, [StringComparison]::OrdinalIgnoreCase)) {
            return $true
        }
    }
    return $false
}

function Get-AppProcess {
    @(Get-Process -Name 'pythonw', 'python' -ErrorAction SilentlyContinue | Where-Object { Test-AppPath -Path $_.Path })
}

function Test-Elevated {
    $principal = [Security.Principal.WindowsPrincipal][Security.Principal.WindowsIdentity]::GetCurrent()
    return $principal.IsInRole([Security.Principal.WindowsBuiltInRole]::Administrator)
}

function Test-NeedsElevation {
    $elevatedTask = Get-ScheduledTask -TaskName $TaskName -ErrorAction SilentlyContinue
    if ($null -ne $elevatedTask -and "$($elevatedTask.Principal.RunLevel)" -eq 'Highest') {
        return $true
    }
    $sessionId = (Get-Process -Id $PID).SessionId
    $hidden = @(Get-Process -Name 'pythonw', 'python' -ErrorAction SilentlyContinue |
        Where-Object { $_.SessionId -eq $sessionId -and -not $_.Path })
    return $hidden.Count -gt 0
}

if (-not (Test-Elevated) -and (Test-NeedsElevation)) {
    Write-Output 'An elevated switcher may be running. Windows asks for administrator approval to stop it.'
    try {
        $process = Start-Process -FilePath $WindowsPowerShell -Verb RunAs -Wait -PassThru `
            -ArgumentList @('-NoProfile', '-ExecutionPolicy', 'Bypass', '-File', ('"{0}"' -f $PSCommandPath))
        exit $process.ExitCode
    }
    catch {
        Write-Warning 'Administrator approval was declined. Continuing without elevation.'
    }
}

$task = Get-ScheduledTask -TaskName $TaskName -ErrorAction SilentlyContinue
if ($null -ne $task) {
    Stop-ScheduledTask -TaskName $TaskName -ErrorAction SilentlyContinue
    Unregister-ScheduledTask -TaskName $TaskName -Confirm:$false -ErrorAction SilentlyContinue
    Write-Output "Autostart removed (scheduled task '$TaskName')."
}
else {
    Write-Output 'No autostart task found.'
}

if ($null -ne (Get-ItemProperty -LiteralPath "Registry::$RunKey" -Name $RunValueName -ErrorAction SilentlyContinue)) {
    Remove-ItemProperty -LiteralPath "Registry::$RunKey" -Name $RunValueName -Force -ErrorAction SilentlyContinue
    Write-Output "Autostart removed (Run value '$RunValueName')."
}

foreach ($process in @(Get-AppProcess)) {
    Stop-Process -Id $process.Id -Force -ErrorAction SilentlyContinue
    Write-Output "Killed switcher process $($process.Id). Its keyboard hook is gone with it."
}

Start-Sleep -Milliseconds 500
$survivors = @(Get-AppProcess)
if ($survivors.Count -gt 0) {
    Write-Warning ("Still running: {0}. Close them in Task Manager or sign out to restore native Alt+Tab." -f (($survivors | ForEach-Object { $_.Id }) -join ', '))
    exit 1
}

Write-Output 'Native Windows Alt+Tab is active again. Files were left in place; run uninstall.ps1 to remove them.'
