# DelugeHub — Building the Windows Installer

## Prerequisites

1. **Python 3.11+** with all dependencies installed:
   ```bash
   pip install -r requirements.txt
   pip install pyinstaller
   ```

2. **Inno Setup 6** (free):  
   https://jrsoftware.org/isinfo.php

---

## Build

```bat
installer\build_installer.bat
```

The script runs two steps automatically:

**Step 1 — PyInstaller** bundles the app into a standalone Windows executable (no Python required on the end user's machine). Output: `dist\DelugeHub\`

**Step 2 — Inno Setup** packages the build into a classic Windows setup wizard. Output: `installer\output\DelugeHub-2.0.4-Setup.exe`

---

## Running steps manually

```bat
:: PyInstaller only
pyinstaller installer\DelugeHub.spec --clean --noconfirm

:: Inno Setup only (after PyInstaller)
"C:\Program Files (x86)\Inno Setup 6\ISCC.exe" installer\setup.iss
```

---

## Adding an icon (optional)

1. Place `icon.ico` in this folder
2. Uncomment the line in `DelugeHub.spec`:
   ```python
   icon='installer/icon.ico',
   ```
3. Uncomment the line in `setup.iss`:
   ```ini
   SetupIconFile=icon.ico
   ```

---

## Notes

- Requires **Windows 10 64-bit** or later
- Installs to `C:\Program Files\DelugeHub\` (configurable during setup)
- Optionally creates a desktop shortcut
- Includes a full uninstaller
- `sounddevice` / `numpy` are **not** included in the build (optional audio preview) — remove them from `excludes` in `DelugeHub.spec` if needed
