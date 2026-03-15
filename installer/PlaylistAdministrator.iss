[Setup]
AppName=Playlist Administrator
AppVersion={#MyAppVersion}
AppPublisher=thumb2086
DefaultDirName={autopf}\Playlist Administrator
DefaultGroupName=Playlist Administrator
DisableProgramGroupPage=yes
OutputDir=dist_installer
OutputBaseFilename=PlaylistAdministrator-Setup
Compression=lzma
SolidCompression=yes

[Tasks]
Name: "desktopicon"; Description: "Create a desktop icon"; GroupDescription: "Additional icons:"

[Files]
Source: "..\dist\PlaylistAdministrator.exe"; DestDir: "{app}"; Flags: ignoreversion

[Icons]
Name: "{group}\Playlist Administrator"; Filename: "{app}\PlaylistAdministrator.exe"
Name: "{commondesktop}\Playlist Administrator"; Filename: "{app}\PlaylistAdministrator.exe"; Tasks: desktopicon
