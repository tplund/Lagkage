; Installer til Lagkage – byg med:
;   "%LOCALAPPDATA%\Programs\Inno Setup 6\ISCC.exe" installer\Lagkage.iss
; Kræver at dist\Lagkage er bygget med PyInstaller først (se README).

#define MyAppName "Lagkage"
#define MyAppVersion "1.0"
#define MyAppExe "Lagkage.exe"

[Setup]
AppId={{6C1E2B7A-4F3D-4E8B-9A51-2D7C0B9E4A17}
AppName={#MyAppName}
AppVersion={#MyAppVersion}
AppVerName={#MyAppName} {#MyAppVersion}
AppPublisher=Elearningspecialist
DefaultDirName={autopf}\{#MyAppName}
DefaultGroupName={#MyAppName}
DisableProgramGroupPage=yes
PrivilegesRequired=lowest
OutputDir=Output
OutputBaseFilename=Lagkage-Setup-{#MyAppVersion}
SetupIconFile=..\lagkage\lagkage.ico
UninstallDisplayIcon={app}\{#MyAppExe}
Compression=lzma2/max
SolidCompression=yes
WizardStyle=modern
ArchitecturesAllowed=x64compatible
ArchitecturesInstallIn64BitMode=x64compatible
CloseApplications=yes
ChangesAssociations=yes

[Languages]
Name: "danish"; MessagesFile: "compiler:Languages\Danish.isl"

[Tasks]
Name: "desktopicon"; Description: "Læg en genvej på skrivebordet"; GroupDescription: "Genveje:"
Name: "assocpsd"; Description: "Åbn PSD-filer med Lagkage"; GroupDescription: "Filtyper:"

[Files]
Source: "..\dist\Lagkage\*"; DestDir: "{app}"; Flags: ignoreversion recursesubdirs createallsubdirs

[Icons]
Name: "{autoprograms}\{#MyAppName}"; Filename: "{app}\{#MyAppExe}"
Name: "{autodesktop}\{#MyAppName}"; Filename: "{app}\{#MyAppExe}"; Tasks: desktopicon

[Registry]
; Lagkage som program, der kan åbne billeder ("Åbn med")
Root: HKA; Subkey: "Software\Classes\Lagkage.Image"; ValueType: string; ValueName: ""; ValueData: "Billede (Lagkage)"; Flags: uninsdeletekey
Root: HKA; Subkey: "Software\Classes\Lagkage.Image\DefaultIcon"; ValueType: string; ValueName: ""; ValueData: "{app}\{#MyAppExe},0"
Root: HKA; Subkey: "Software\Classes\Lagkage.Image\shell\open\command"; ValueType: string; ValueName: ""; ValueData: """{app}\{#MyAppExe}"" ""%1"""
Root: HKA; Subkey: "Software\Classes\Applications\{#MyAppExe}\shell\open\command"; ValueType: string; ValueName: ""; ValueData: """{app}\{#MyAppExe}"" ""%1"""; Flags: uninsdeletekey
Root: HKA; Subkey: "Software\Classes\.psd\OpenWithProgids"; ValueType: string; ValueName: "Lagkage.Image"; ValueData: ""; Flags: uninsdeletevalue
Root: HKA; Subkey: "Software\Classes\.png\OpenWithProgids"; ValueType: string; ValueName: "Lagkage.Image"; ValueData: ""; Flags: uninsdeletevalue
Root: HKA; Subkey: "Software\Classes\.jpg\OpenWithProgids"; ValueType: string; ValueName: "Lagkage.Image"; ValueData: ""; Flags: uninsdeletevalue
Root: HKA; Subkey: "Software\Classes\.jpeg\OpenWithProgids"; ValueType: string; ValueName: "Lagkage.Image"; ValueData: ""; Flags: uninsdeletevalue
Root: HKA; Subkey: "Software\Classes\.bmp\OpenWithProgids"; ValueType: string; ValueName: "Lagkage.Image"; ValueData: ""; Flags: uninsdeletevalue
Root: HKA; Subkey: "Software\Classes\.webp\OpenWithProgids"; ValueType: string; ValueName: "Lagkage.Image"; ValueData: ""; Flags: uninsdeletevalue
; PSD åbner som standard i Lagkage (hvis brugeren valgte det)
Root: HKA; Subkey: "Software\Classes\.psd"; ValueType: string; ValueName: ""; ValueData: "Lagkage.Image"; Flags: uninsdeletevalue; Tasks: assocpsd

[Run]
Filename: "{app}\{#MyAppExe}"; Description: "Start Lagkage nu"; Flags: nowait postinstall skipifsilent
