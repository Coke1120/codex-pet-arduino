[CmdletBinding()]
param(
    [string]$Port = "auto",
    [switch]$SkipStartupTask
)

$ErrorActionPreference = "Stop"
$RepoRoot = Split-Path -Parent $PSScriptRoot
$AppRoot = Join-Path $env:LOCALAPPDATA "CodexPet"
$Runtime = Join-Path $AppRoot "runtime"
$Venv = Join-Path $Runtime ".venv"
$Python = Join-Path $Venv "Scripts\python.exe"
$Pythonw = Join-Path $Venv "Scripts\pythonw.exe"
$HooksPath = Join-Path $HOME ".codex\hooks.json"
$TaskName = "CodexPet"

function Find-PythonLauncher {
    $py = Get-Command py -ErrorAction SilentlyContinue
    if ($py) { return @($py.Source, "-3") }
    $python = Get-Command python -ErrorAction SilentlyContinue
    if ($python) { return @($python.Source) }
    throw "Python 3 was not found. Install it from https://www.python.org/downloads/windows/ and rerun this installer."
}

Write-Host "Installing Codex Pet for Windows..."
New-Item -ItemType Directory -Force -Path $Runtime | Out-Null
Copy-Item (Join-Path $RepoRoot "mac\codex_pet_bridge.py") $Runtime -Force
Copy-Item (Join-Path $RepoRoot "mac\codex_pet_daemon.py") $Runtime -Force
Copy-Item (Join-Path $RepoRoot "mac\codex_pet_hook.py") $Runtime -Force
Copy-Item (Join-Path $RepoRoot "mac\codex_pet_usage.py") $Runtime -Force
Copy-Item (Join-Path $RepoRoot "mac\requirements.txt") $Runtime -Force
Copy-Item (Join-Path $RepoRoot "tools\install_codex_hooks.py") $Runtime -Force

if (-not (Test-Path $Python)) {
    $launcher = Find-PythonLauncher
    $exe = $launcher[0]
    $prefix = @()
    if ($launcher.Count -gt 1) { $prefix = $launcher[1..($launcher.Count - 1)] }
    & $exe @prefix -m venv $Venv
}

& $Python -m pip install --disable-pip-version-check -r (Join-Path $Runtime "requirements.txt")
& $Python (Join-Path $Runtime "install_codex_hooks.py") `
    --hooks $HooksPath `
    --python $Python `
    --hook-script (Join-Path $Runtime "codex_pet_hook.py")

& $Python (Join-Path $Runtime "codex_pet_daemon.py") --dry-run --once

if (-not $SkipStartupTask) {
    $action = New-ScheduledTaskAction `
        -Execute $Pythonw `
        -Argument ('"{0}" --port "{1}"' -f (Join-Path $Runtime "codex_pet_daemon.py"), $Port)
    $trigger = New-ScheduledTaskTrigger -AtLogOn -User $env:USERNAME
    $settings = New-ScheduledTaskSettingsSet -ExecutionTimeLimit ([TimeSpan]::Zero) -RestartCount 3 -RestartInterval (New-TimeSpan -Minutes 1)
    Register-ScheduledTask -TaskName $TaskName -Action $action -Trigger $trigger -Settings $settings -Description "Mirror Codex lifecycle states to Arduino Codex Pet" -Force | Out-Null
    Start-ScheduledTask -TaskName $TaskName
    Write-Host "Installed and started Windows startup task: $TaskName"
}

Write-Host "Runtime: $Runtime"
Write-Host "Hooks:   $HooksPath"
Write-Host "Connect the Uno, restart Codex, review /hooks, and trust only the commands under $Runtime."
Write-Host "To verify the board manually:"
Write-Host ('  & "{0}" "{1}" --list' -f $Python, (Join-Path $Runtime "codex_pet_bridge.py"))
