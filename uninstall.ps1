[CmdletBinding()]
param(
    [string]$ManifestPath
)

Set-StrictMode -Version Latest
$ErrorActionPreference = 'Stop'

$AppName = 'PlanetAltTab'
$TaskName = 'PlanetAltTab'
$RunKey = 'HKCU\Software\Microsoft\Windows\CurrentVersion\Run'
$RunValueName = 'PlanetAltTab'
$WindowsPowerShell = Join-Path -Path $env:SystemRoot -ChildPath 'System32\WindowsPowerShell\v1.0\powershell.exe'
$InstallDir = Join-Path -Path $env:LOCALAPPDATA -ChildPath $AppName
$ScriptDir = $PSScriptRoot

function Test-InsideInstallDir {
    param([Parameter(Mandatory)][string]$Path)
    $root = [IO.Path]::GetFullPath($InstallDir).TrimEnd('\') + '\'
    $full = [IO.Path]::GetFullPath($Path).TrimEnd('\') + '\'
    return $full.StartsWith($root, [StringComparison]::OrdinalIgnoreCase)
}

function Clear-AppProcess {
    $processes = @(Get-Process -Name 'pythonw', 'python' -ErrorAction SilentlyContinue |
        Where-Object { $_.Path -and (Test-InsideInstallDir -Path $_.Path) })
    foreach ($process in $processes) {
        Stop-Process -Id $process.Id -Force -ErrorAction SilentlyContinue
        Write-Output "Stopped process $($process.Id) (keyboard hook released)."
    }
    if ($processes.Count -gt 0) {
        Start-Sleep -Milliseconds 500
    }
}

function Unregister-AppTask {
    param([Parameter(Mandatory)][string]$Name)
    $task = Get-ScheduledTask -TaskName $Name -ErrorAction SilentlyContinue
    if ($null -eq $task) {
        return
    }
    Stop-ScheduledTask -TaskName $Name -ErrorAction SilentlyContinue
    Unregister-ScheduledTask -TaskName $Name -Confirm:$false
    Write-Output "Removed scheduled task '$Name'."
}

function Remove-RunValue {
    $runPath = "Registry::$RunKey"
    if ($null -eq (Get-ItemProperty -LiteralPath $runPath -Name $RunValueName -ErrorAction SilentlyContinue)) {
        return
    }
    Remove-ItemProperty -LiteralPath $runPath -Name $RunValueName -Force
    Write-Output "Removed autostart value '$RunValueName' from $RunKey."
}

function Test-Elevated {
    $principal = [Security.Principal.WindowsPrincipal][Security.Principal.WindowsIdentity]::GetCurrent()
    return $principal.IsInRole([Security.Principal.WindowsBuiltInRole]::Administrator)
}

function Test-ElevatedInstall {
    $task = Get-ScheduledTask -TaskName $TaskName -ErrorAction SilentlyContinue
    if ($null -ne $task -and "$($task.Principal.RunLevel)" -eq 'Highest') {
        return $true
    }
    foreach ($file in @(Get-ChildItem -Path (Join-Path -Path $ScriptDir -ChildPath 'backup\*\manifest.json') -ErrorAction SilentlyContinue)) {
        $manifest = Get-Content -LiteralPath $file.FullName -Raw | ConvertFrom-Json
        if ($manifest.reverted) {
            continue
        }
        foreach ($entry in @($manifest.entries)) {
            if ($entry.type -eq 'scheduled-task' -and $entry.PSObject.Properties['runLevel'] -and $entry.runLevel -eq 'Highest') {
                return $true
            }
        }
    }
    return $false
}

function Clear-InstallDirectory {
    param([Parameter(Mandatory)][string]$Path)
    if (-not (Test-InsideInstallDir -Path $Path)) {
        Write-Warning "Refusing to delete '$Path': it is outside $InstallDir."
        return
    }
    if (-not (Test-Path -LiteralPath $Path)) {
        return
    }
    if ((Get-Location).Path -and (Test-InsideInstallDir -Path (Get-Location).Path)) {
        Set-Location -LiteralPath $env:USERPROFILE
    }
    Remove-Item -LiteralPath $Path -Recurse -Force
    Write-Output "Deleted $Path."
}

function Restore-RegistryBackup {
    param([Parameter(Mandatory)]$Entry)
    $registryPath = "Registry::{0}" -f $Entry.key
    if ($Entry.existed) {
        if (-not (Test-Path -LiteralPath $Entry.file)) {
            Write-Warning "Registry backup '$($Entry.file)' is missing. '$($Entry.key)' was left as is."
            return
        }
        & reg.exe import $Entry.file 2>&1 | Out-Null
        if ($LASTEXITCODE -ne 0) {
            Write-Warning "Restoring '$($Entry.key)' from '$($Entry.file)' failed."
            return
        }
        Write-Output "Restored registry key '$($Entry.key)'."
    }
    elseif (Test-Path -LiteralPath $registryPath) {
        Remove-Item -LiteralPath $registryPath -Recurse -Force
        Write-Output "Removed registry key '$($Entry.key)' that the install created."
    }
}

function Undo-ManifestEntry {
    param([Parameter(Mandatory)]$Entry)
    switch ($Entry.type) {
        'process' { Clear-AppProcess }
        'scheduled-task' { Unregister-AppTask -Name $Entry.name }
        'directory' { Clear-AppProcess; Clear-InstallDirectory -Path $Entry.path }
        'registry' { Restore-RegistryBackup -Entry $Entry }
        'run-value' { Remove-RunValue }
        'registry-snapshot' {
            if ($Entry.existed) {
                Write-Output "Snapshot of '$($Entry.key)' from before install is kept at '$($Entry.file)'."
            }
        }
        'restore-point' {
            if ($Entry.status -eq 'created') {
                Write-Output 'The System Restore point from install is kept as an extra safety net.'
            }
        }
        default { Write-Warning "Unknown manifest entry type '$($Entry.type)', skipped." }
    }
}

function Undo-Manifest {
    param([Parameter(Mandatory)][string]$Path)
    $manifest = Get-Content -LiteralPath $Path -Raw | ConvertFrom-Json
    if ($manifest.reverted) {
        return
    }
    Write-Output "Reverting $Path"
    $entries = @($manifest.entries)
    [array]::Reverse($entries)
    foreach ($entry in $entries) {
        try {
            Undo-ManifestEntry -Entry $entry
        }
        catch {
            Write-Warning "Could not revert '$($entry.type)': $($_.Exception.Message)"
            throw
        }
    }
    $manifest.reverted = $true
    $manifest | Add-Member -NotePropertyName 'revertedAt' -NotePropertyValue (Get-Date).ToString('o') -Force
    $manifest | ConvertTo-Json -Depth 6 | Set-Content -LiteralPath $Path -Encoding UTF8
}

if (-not (Test-Elevated) -and (Test-ElevatedInstall)) {
    Write-Output 'The switcher was installed elevated. Windows asks for administrator approval to remove it.'
    $arguments = @('-NoProfile', '-ExecutionPolicy', 'Bypass', '-File', ('"{0}"' -f $PSCommandPath))
    if ($ManifestPath) {
        $arguments += @('-ManifestPath', ('"{0}"' -f $ManifestPath))
    }
    try {
        $process = Start-Process -FilePath $WindowsPowerShell -Verb RunAs -Wait -PassThru -ArgumentList $arguments
        exit $process.ExitCode
    }
    catch {
        Write-Warning 'Administrator approval was declined. Removing what this account can; the elevated task may remain.'
    }
}

if ($ManifestPath) {
    if (Test-Path -LiteralPath $ManifestPath) {
        Undo-Manifest -Path $ManifestPath
    }
}
else {
    $manifests = @(Get-ChildItem -Path (Join-Path -Path $ScriptDir -ChildPath 'backup\*\manifest.json') -ErrorAction SilentlyContinue |
        Sort-Object -Property FullName -Descending)
    foreach ($manifest in $manifests) {
        Undo-Manifest -Path $manifest.FullName
    }
}

Clear-AppProcess
Unregister-AppTask -Name $TaskName
Remove-RunValue
Clear-InstallDirectory -Path $InstallDir
Write-Output 'Uninstall complete. Native Alt+Tab is active.'
