@echo off
:: ============================================================
:: DelugeHub — Installer Build Script
:: Voraussetzungen:
::   pip install pyinstaller
::   Inno Setup 6 installiert (https://jrsoftware.org/isinfo.php)
:: ============================================================

setlocal
set SCRIPT_DIR=%~dp0
set PROJECT_DIR=%SCRIPT_DIR%..
set ISCC="C:\Program Files (x86)\Inno Setup 6\ISCC.exe"

echo.
echo ============================================================
echo  DelugeHub Installer Builder
echo ============================================================
echo.

:: --- Schritt 1: PyInstaller ---
echo [1/2] PyInstaller — App bundeln...
cd /d "%PROJECT_DIR%"
pyinstaller installer\DelugeHub.spec --clean --noconfirm

if %ERRORLEVEL% neq 0 (
    echo.
    echo FEHLER: PyInstaller fehlgeschlagen. Abbruch.
    pause
    exit /b 1
)

echo PyInstaller fertig.
echo.

:: --- Schritt 2: Inno Setup ---
echo [2/2] Inno Setup — Installer erstellen...

if not exist %ISCC% (
    echo FEHLER: Inno Setup nicht gefunden unter %ISCC%
    echo Bitte Inno Setup 6 installieren: https://jrsoftware.org/isinfo.php
    echo Oder ISCC-Pfad in diesem Skript anpassen.
    pause
    exit /b 1
)

%ISCC% "%SCRIPT_DIR%setup.iss"

if %ERRORLEVEL% neq 0 (
    echo.
    echo FEHLER: Inno Setup fehlgeschlagen.
    pause
    exit /b 1
)

echo.
echo ============================================================
echo  Fertig! Installer liegt in: installer\output\
echo ============================================================
echo.
pause
