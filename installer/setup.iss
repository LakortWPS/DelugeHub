; Inno Setup Script — DelugeHub Installer
; https://jrsoftware.org/isinfo.php
; Version: 2.0.1

#define AppName      "DelugeHub"
#define AppVersion   "2.0.1"
#define AppPublisher "LakortWPS"
#define AppURL       "https://github.com/LakortWPS/DelugeHub"
#define AppExeName   "DelugeHub.exe"
#define BuildDir     "..\dist\DelugeHub"

[Setup]
AppId={{A3F2B8C1-4D7E-4F9A-B2C3-8E1D5F6A7B9C}
AppName={#AppName}
AppVersion={#AppVersion}
AppPublisherURL={#AppURL}
AppSupportURL={#AppURL}/issues
AppUpdatesURL={#AppURL}/releases
DefaultDirName={autopf}\{#AppName}
DefaultGroupName={#AppName}
AllowNoIcons=yes
LicenseFile=..\LICENSE
; OutputDir=installer\output        ; uncomment to set custom output dir
OutputBaseFilename=DelugeHub-{#AppVersion}-Setup
; SetupIconFile=icon.ico            ; uncomment when icon is available
Compression=lzma2/ultra64
SolidCompression=yes
WizardStyle=modern
PrivilegesRequiredOverridesAllowed=dialog
MinVersion=10.0
ArchitecturesAllowed=x64
ArchitecturesInstallIn64BitMode=x64

[Languages]
Name: "german";  MessagesFile: "compiler:Languages\German.isl"
Name: "english"; MessagesFile: "compiler:Default.isl"

[Tasks]
Name: "desktopicon";    Description: "{cm:CreateDesktopIcon}";    GroupDescription: "{cm:AdditionalIcons}"; Flags: unchecked
Name: "quicklaunchicon"; Description: "{cm:CreateQuickLaunchIcon}"; GroupDescription: "{cm:AdditionalIcons}"; Flags: unchecked; OnlyBelowVersion: 6.1

[Files]
Source: "{#BuildDir}\*"; DestDir: "{app}"; Flags: ignoreversion recursesubdirs createallsubdirs

[Icons]
Name: "{group}\{#AppName}";           FileName: "{app}\{#AppExeName}"
Name: "{group}\{cm:UninstallProgram,{#AppName}}"; FileName: "{uninstallexe}"
Name: "{autodesktop}\{#AppName}";     FileName: "{app}\{#AppExeName}"; Tasks: desktopicon

[Run]
Filename: "{app}\{#AppExeName}"; Description: "{cm:LaunchProgram,{#AppName}}"; Flags: nowait postinstall skipifsilent

[UninstallDelete]
Type: filesandordirs; Name: "{app}"

[Code]
// Zeige Hinweis wenn Python bereits installiert ist (optional)
function InitializeSetup(): Boolean;
begin
  Result := True;
end;
