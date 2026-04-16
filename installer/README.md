# DelugeHub — Installer erstellen

## Voraussetzungen

1. **Python 3.11+** mit allen Abhängigkeiten installiert:
   ```bash
   pip install -r requirements.txt
   pip install pyinstaller
   ```

2. **Inno Setup 6** (kostenlos):  
   https://jrsoftware.org/isinfo.php

---

## Installer bauen

```bat
installer\build_installer.bat
```

Das Skript führt automatisch zwei Schritte aus:

**Schritt 1 — PyInstaller** bündelt die App zu einem eigenständigen Windows-Programm (kein Python nötig beim Endnutzer). Output: `dist\DelugeHub\`

**Schritt 2 — Inno Setup** verpackt den Build in einen klassischen Windows Setup-Wizard. Output: `installer\output\DelugeHub-2.0.1-Setup.exe`

---

## Manuell ausführen

```bat
:: Nur PyInstaller
pyinstaller installer\DelugeHub.spec --clean --noconfirm

:: Nur Inno Setup (nach PyInstaller)
"C:\Program Files (x86)\Inno Setup 6\ISCC.exe" installer\setup.iss
```

---

## Icon hinzufügen (optional)

1. `icon.ico` in diesen Ordner legen
2. In `DelugeHub.spec` die auskommentierte Zeile aktivieren:
   ```python
   icon='installer/icon.ico',
   ```
3. In `setup.iss` die auskommentierte Zeile aktivieren:
   ```ini
   SetupIconFile=icon.ico
   ```

---

## Hinweise

- Der Installer erfordert **Windows 10 64-bit** oder neuer
- Installiert nach `C:\Program Files\DelugeHub\` (änderbar im Wizard)
- Erstellt optional Desktop-Verknüpfung
- Enthält vollständigen Uninstaller
- `sounddevice` / `numpy` sind im Build **nicht** enthalten (optionale Audio-Vorschau) — bei Bedarf in `DelugeHub.spec` unter `excludes` entfernen
