#define AppName "Sakura"
#define AppVersion "0.1.0-beta"
[Setup]
AppId={{E40B318B-7567-44D6-BBC3-36B4C23F527F}
AppName={#AppName}
AppVersion={#AppVersion}
DefaultDirName={localappdata}\Programs\Sakura
DefaultGroupName=Sakura
PrivilegesRequired=lowest
OutputDir=installer
OutputBaseFilename=Sakura-Windows-Beta
Compression=lzma2
SolidCompression=yes
WizardStyle=modern
CloseApplications=yes
[Files]
Source: "dist\Sakura\*"; DestDir: "{app}"; Flags: ignoreversion recursesubdirs createallsubdirs
[Tasks]
Name: "desktopicon"; Description: "Create a desktop shortcut"
[Icons]
Name: "{group}\Sakura"; Filename: "{app}\Sakura.exe"
Name: "{autodesktop}\Sakura"; Filename: "{app}\Sakura.exe"; Tasks: desktopicon
[Run]
Filename: "{app}\Sakura.exe"; Description: "Launch Sakura"; Flags: nowait postinstall skipifsilent
