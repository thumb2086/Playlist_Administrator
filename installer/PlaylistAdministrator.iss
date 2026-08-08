; Inno Setup script for Playlist Administrator (Flutter)
#define MyAppName "playlist-admin"
#ifndef MyAppVersion
  #define MyAppVersion "2.0.2-beta.8"
#endif
#define MyAppPublisher "Playlist Administrator"
#define MyAppURL "https://github.com/thumb2086/playlist-admin"
#define MyAppExeName "playlist-admin.exe"

[Setup]
AppName={#MyAppName}
AppVersion={#MyAppVersion}
AppPublisher={#MyAppPublisher}
AppPublisherURL={#MyAppURL}
DefaultDirName={autopf}\{#MyAppName}
DefaultGroupName={#MyAppName}
DisableProgramGroupPage=yes
OutputDir=..\installer
OutputBaseFilename=playlist-admin-Setup-{#MyAppVersion}
Compression=lzma2
SolidCompression=yes
UninstallDisplayIcon={app}\{#MyAppExeName}
PrivilegesRequired=admin

[Tasks]
Name: "npmcli"; Description: "Install npm CLI package (playlist-admin)"; GroupDescription: "Additional tools:"; Flags: checkedonce

[Files]
Source: "..\build\windows\x64\runner\Release\*"; DestDir: "{app}"; Flags: ignoreversion recursesubdirs createallsubdirs

[Icons]
Name: "{autoprograms}\{#MyAppName}"; Filename: "{app}\{#MyAppExeName}"
Name: "{autodesktop}\{#MyAppName}"; Filename: "{app}\{#MyAppExeName}"

[Run]
Filename: "{cmd}"; Parameters: "/c npm install -g playlist-admin@{#MyAppVersion}"; StatusMsg: "Installing playlist-admin CLI (npm)..."; Tasks: npmcli; Flags: runhidden nowait
Filename: "{app}\{#MyAppExeName}"; Description: "{cm:LaunchProgram,{#MyAppName}}"; Flags: nowait postinstall skipifsilent

[UninstallRun]
Filename: "{cmd}"; Parameters: "/c npm uninstall -g playlist-admin"; Flags: runhidden
