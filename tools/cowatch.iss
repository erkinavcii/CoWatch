; The Windows installer, built by tools\build_windows.ps1 (which passes the defines below).
; Installs for the current user only (no administrator), with a Start menu shortcut and an
; uninstaller. The settings stay in %APPDATA%\CoWatch: a new version installs over the old one
; without touching them, and removing the app leaves them too.

#ifndef AppVersion
  #define AppVersion "0.1.0"
#endif
#ifndef SourceDir
  #define SourceDir "..\dist\CoWatch"
#endif
#ifndef OutputDir
  #define OutputDir "..\dist"
#endif
#ifndef IconFile
  #define IconFile "..\build\cowatch.ico"
#endif

[Setup]
AppId={{6E0C2B1A-5C7D-4F0E-9A3B-2D8C4F1E7A90}
AppName=Co-Watch
AppVersion={#AppVersion}
AppPublisher=erkinavcii
AppPublisherURL=https://github.com/erkinavcii/CoWatch
AppSupportURL=https://github.com/erkinavcii/CoWatch/issues
DefaultDirName={localappdata}\Programs\CoWatch
DefaultGroupName=Co-Watch
DisableProgramGroupPage=yes
PrivilegesRequired=lowest
OutputDir={#OutputDir}
OutputBaseFilename=CoWatch-Setup-{#AppVersion}
SetupIconFile={#IconFile}
UninstallDisplayIcon={app}\CoWatch.exe
UninstallDisplayName=Co-Watch
Compression=lzma2/ultra64
SolidCompression=yes
ArchitecturesAllowed=x64compatible
ArchitecturesInstallIn64BitMode=x64compatible
WizardStyle=modern

[Languages]
Name: "turkish"; MessagesFile: "compiler:Languages\Turkish.isl"
Name: "english"; MessagesFile: "compiler:Default.isl"
Name: "russian"; MessagesFile: "compiler:Languages\Russian.isl"

[Tasks]
Name: "desktopicon"; Description: "{cm:CreateDesktopIcon}"; GroupDescription: "{cm:AdditionalIcons}"

[Files]
Source: "{#SourceDir}\*"; DestDir: "{app}"; Flags: recursesubdirs createallsubdirs ignoreversion

[InstallDelete]
; files of an older version that this one no longer has
Type: filesandordirs; Name: "{app}\_internal"

[Icons]
Name: "{autoprograms}\Co-Watch"; Filename: "{app}\CoWatch.exe"
Name: "{autodesktop}\Co-Watch"; Filename: "{app}\CoWatch.exe"; Tasks: desktopicon

[Run]
Filename: "{app}\CoWatch.exe"; Description: "{cm:LaunchProgram,Co-Watch}"; Flags: nowait postinstall skipifsilent

[UninstallRun]
; with its children: the torrent helper, ffmpeg and the Tailscale link it started
Filename: "{sys}\taskkill.exe"; Parameters: "/IM CoWatch.exe /T /F"; Flags: runhidden; RunOnceId: "StopCoWatch"

[Code]
function PrepareToInstall(var NeedsRestart: Boolean): String;
var
  Code: Integer;
begin
  { A running Co-Watch holds its files: stop it (and what it started) before replacing them. }
  Exec(ExpandConstant('{sys}\taskkill.exe'), '/IM CoWatch.exe /T /F', '', SW_HIDE, ewWaitUntilTerminated, Code);
  Result := '';
end;
