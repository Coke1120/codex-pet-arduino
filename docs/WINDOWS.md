# Windows installation

The Arduino firmware is portable and remains stored on the Uno. Windows only needs the small host runtime that receives Codex lifecycle hooks and sends `idle`, `running`, `waiting`, or `review` over the board's `COM` port.

## Requirements

- Windows 10 or 11
- Python 3 available as `py -3` or `python`
- Codex Desktop or CLI with lifecycle-hook support
- The Arduino Uno already flashed with `arduino/CodexPet/CodexPet.ino`

An official Uno normally uses Windows' built-in USB support. Some compatible boards use a CH340 USB-serial chip and may need the board vendor's driver.

## Install

Open PowerShell in the repository and run:

```powershell
Set-ExecutionPolicy -Scope Process Bypass
.\windows\install.ps1
```

The installer:

1. Copies a privacy-minimal runtime to `%LOCALAPPDATA%\CodexPet\runtime`.
2. Creates an isolated Python virtual environment and installs `pyserial`.
3. Merges Codex Pet commands into `%USERPROFILE%\.codex\hooks.json` without deleting unrelated hooks.
4. Creates and starts a per-user `CodexPet` Scheduled Task at logon.
5. Uses conservative Arduino metadata to auto-select one unambiguous `COM` port.

Restart Codex after installation. Open `/hooks`, inspect the commands, and trust them only when they point to `%LOCALAPPDATA%\CodexPet\runtime`.

## Verify

List detected serial ports:

```powershell
$runtime = "$env:LOCALAPPDATA\CodexPet\runtime"
& "$runtime\.venv\Scripts\python.exe" "$runtime\codex_pet_bridge.py" --list
```

Send a state through one verified board port:

```powershell
& "$runtime\.venv\Scripts\python.exe" "$runtime\codex_pet_bridge.py" --port auto --state running
```

Inspect the startup task:

```powershell
Get-ScheduledTask -TaskName CodexPet
Get-ScheduledTaskInfo -TaskName CodexPet
```

If more than one Arduino is attached, reinstall with the verified port:

```powershell
.\windows\install.ps1 -Port COM7
```

## Remove

```powershell
Unregister-ScheduledTask -TaskName CodexPet -Confirm:$false
Remove-Item -Recurse -Force "$env:LOCALAPPDATA\CodexPet"
```

The installer deliberately leaves `%USERPROFILE%\.codex\hooks.json` in place because it may contain unrelated user hooks. Remove only the Codex Pet command groups after reviewing that file.

## Notes

- Do not connect the same Uno to two computers simultaneously.
- Reconnecting the board does not require reflashing; the daemon retries and performs an exact `ping` → `pong` handshake.
- A USB charger can power the Uno and display its default state, but it cannot provide Codex lifecycle updates.
- The Uno cannot inject or install this runtime into Windows: it enumerates as a Serial/programming device, not a trusted storage drive or installer.
