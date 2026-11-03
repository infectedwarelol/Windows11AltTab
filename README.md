# Windows11AltTab

A Windows 11 port of my Hyprland "planet" Alt+Tab switcher. Open windows sit as app icons on a rendered globe; Alt+Tab spins the globe to the next one, releasing Alt switches to it.

The folder is portable. It ships a Python 3.13 embeddable runtime with pycairo, one native DLL that holds the globe renderer and the keyboard hook, and pre-baked globe textures. Nothing is installed system-wide and nothing is written to HKLM.

## Requirements

- Windows 11 (build 22000 or newer), 64-bit
- A normal, non-elevated PowerShell window

If the folder came from a zip or download, unblock it first:

```powershell
Get-ChildItem -Recurse | Unblock-File
```

## Install

```powershell
powershell -ExecutionPolicy Bypass -File .\install.ps1
```

The installer copies the app to `%LOCALAPPDATA%\PlanetAltTab`, registers the per-user scheduled task `PlanetAltTab` to start it at logon, and records every change in `.\backup\<timestamp>\manifest.json`.

If Task Scheduler denies access, the installer backs up `HKCU\Software\Microsoft\Windows\CurrentVersion\Run` to a `.reg` file and adds a `PlanetAltTab` value there instead. The manifest records which mechanism was used.

UAC asks for admin approval once, to create a System Restore point. To skip it:

```powershell
powershell -ExecutionPolicy Bypass -File .\install.ps1 -SkipRestorePoint
```

### Elevated windows

A non-elevated hook gets no input while an elevated window (admin console, installer) has focus, so Alt+Tab over those windows stays native. `-Elevated` registers the task with highest privileges so the switcher works there too, at the cost of running a keyboard hook with admin rights. It needs an account in the Administrators group and asks for UAC approval once.

```powershell
powershell -ExecutionPolicy Bypass -File .\install.ps1 -Elevated
```

## Uninstall

```powershell
powershell -ExecutionPolicy Bypass -File .\uninstall.ps1
```

It replays the manifests in reverse, removes the scheduled task and the Run value, and deletes the install folder. Running it twice is safe.

## Panic

```powershell
powershell -ExecutionPolicy Bypass -File .\panic-restore.ps1
```

Kills the switcher, which drops its keyboard hook, removes both autostart entries, and brings native Alt+Tab back. Files stay in place. A copy also lives in `%LOCALAPPDATA%\PlanetAltTab\panic-restore.ps1`.

## How it stays safe

- The hook runs on its own native thread. If the Python side stops sending its heartbeat for 3 seconds, every key passes through untouched.
- When the process dies, Windows removes the hook with it. Native Alt+Tab comes back with nothing left behind.
- While idle, the hook re-installs itself every 5 seconds, because Windows silently drops low-level hooks that time out.
- The mouse hook exists only while the switcher is open. It forwards the wheel to the overlay and is removed on close.

## Limits

- Defender and SmartScreen may flag the unsigned hook DLL. The DLLs carry version info and a manifest, but only code signing fully fixes this.
- Edge tabs in Alt+Tab (`MultiTaskingAltTabFilter`) are not shown. Windows has no public API to enumerate them.
- The fast DLL loads only on CPUs that report AVX2, FMA, and OS-enabled AVX state. Everything else uses the generic build.

## Build

The native DLLs cross-compile on Linux with mingw-w64:

```bash
./native/build-native.sh
```

`app/selfcheck.py` renders 3840×2160 frames at 1.0, 1.25, 1.5, and 2.0 scale with a fake native library, checks the layout math, and prints per-frame timings. It runs on Linux with only Python and pycairo:

```bash
PYTHONDONTWRITEBYTECODE=1 python3 app/selfcheck.py
```

`./inspect.sh` runs the build, export checks, the selfcheck, and source lint in one go. It must report 0 errors and 0 warnings.

## License

MIT, see [LICENSE](LICENSE). Bundled third-party components keep their own licenses.

## Third-party components

- `runtime/` bundles the Python 3.13 embeddable package, licensed under the PSF License (`runtime/LICENSE.txt`).
- `runtime/Lib/site-packages/cairo` bundles [pycairo](https://github.com/pygobject/pycairo) 1.29.2, licensed under LGPL-2.1-only or MPL-1.1, with the cairo library linked into its extension module under the same licenses. License texts are in `runtime/Lib/site-packages/pycairo-1.29.2.dist-info/licenses/`.

Windows, Windows 11, and Microsoft Edge are trademarks of Microsoft Corporation. This project is not affiliated with or endorsed by Microsoft.

## Disclaimer

This project is provided for educational purposes only. It is intended for users who want to change the Alt+Tab switcher on their own Windows 11 PC. Use these scripts at your own risk. The author is not responsible for any damage, data loss, system malfunction, or other issues resulting from their use. Make sure you understand what the scripts do before running them: they install a per-user keyboard and mouse hook, register an autostart entry, and write to `HKCU`. By using this project, you acknowledge that you are responsible for any consequences of running it.
