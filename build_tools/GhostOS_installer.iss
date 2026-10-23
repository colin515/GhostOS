#ifndef AppVersion
  #define AppVersion "1.2.3"
#endif
[Setup]
AppId={{5EEDCD48-2F6C-46E7-9C19-7B39E8AC5B22}
AppName=GhostOS
AppVersion={#AppVersion}
AppPublisher=GhostOS Contributors
DefaultDirName={localappdata}\Programs\GhostOS
DefaultGroupName=GhostOS
UsePreviousAppDir=yes
UsePreviousGroup=yes
UsePreviousTasks=yes
UninstallDisplayName=GhostOS
SetupLogging=yes
PrivilegesRequired=lowest
ArchitecturesAllowed=x64compatible
ArchitecturesInstallIn64BitMode=x64compatible
MinVersion=10.0
OutputDir=..\dist
OutputBaseFilename=GhostOS_Installer_v{#AppVersion}
Compression=lzma2
SolidCompression=yes
WizardStyle=modern
SetupIconFile=..\assets\GhostOS.ico
UninstallDisplayIcon={app}\GhostOS.exe
CloseApplications=force
RestartApplications=no
CloseApplicationsFilter=*.exe,*.dll,*.pyd
LicenseFile=..\LICENSE
[Tasks]
Name: "repairsettings"; Description: "Reset settings to repair startup (backs up settings; keeps models, recipes and logs)"; Flags: unchecked checkedonce
Name: "desktopicon"; Description: "Create a desktop shortcut"; Flags: unchecked
[Files]
Source: "..\dist\GhostOS\*"; DestDir: "{app}"; Flags: ignoreversion recursesubdirs createallsubdirs
[Icons]
Name: "{group}\GhostOS"; Filename: "{app}\GhostOS.exe"; Parameters: "--desktop"; AppUserModelID: "GhostOS.Desktop"
Name: "{group}\Documentation"; Filename: "{app}\_internal\docs\installation.md"
Name: "{group}\Uninstall GhostOS"; Filename: "{uninstallexe}"
Name: "{autodesktop}\GhostOS"; Filename: "{app}\GhostOS.exe"; Parameters: "--desktop"; AppUserModelID: "GhostOS.Desktop"; Tasks: desktopicon
[Run]
Filename: "{app}\GhostOS.exe"; Parameters: "--repair-settings"; Tasks: repairsettings; Flags: runhidden waituntilterminated
Filename: "{app}\GhostOS.exe"; Parameters: "--desktop"; Description: "Launch GhostOS"; Flags: nowait postinstall skipifsilent
; Only installer-owned files and shortcuts are removed. User recipes, logs,
; configuration, browser profiles and separately installed Ollama are preserved.
