; Inno Setup script for AI-Bench.
;
; Produces a single wizard installer (AI-Bench-Setup.exe) with the standard
; Welcome -> License -> Destination -> Tasks -> Ready -> Installing -> Finish
; flow, Start Menu + optional Desktop shortcuts, and a full uninstaller that
; appears in "Apps & features" / "Add or remove programs".
;
; Expects the PyInstaller onedir output at ..\dist\AI-Bench\ (built by
; build_installer.ps1). Compile with:  ISCC.exe installer\ai-bench.iss

#define MyAppName "AI-Bench"
#ifndef MyAppVersion
  #define MyAppVersion "0.1.0"
#endif
#define MyAppPublisher "AI-Bench"
#define MyAppURL "https://github.com/eachan/AI-Bench"
#define MyAppExeName "AI-Bench.exe"

[Setup]
; A stable AppId keeps upgrades/uninstall associated across versions.
AppId={{7F3B9C2E-4A1D-4E7A-9C2B-AIB0BENCH0001}
AppName={#MyAppName}
AppVersion={#MyAppVersion}
AppVerName={#MyAppName} {#MyAppVersion}
AppPublisher={#MyAppPublisher}
AppPublisherURL={#MyAppURL}
AppSupportURL={#MyAppURL}
AppUpdatesURL={#MyAppURL}
DefaultDirName={autopf}\{#MyAppName}
DefaultGroupName={#MyAppName}
DisableProgramGroupPage=yes
LicenseFile=license.txt
OutputDir=Output
OutputBaseFilename=AI-Bench-Setup
; SetupIconFile is intentionally omitted (uses Inno's default wizard icon).
; Drop an installer\aibench.ico and re-add SetupIconFile=aibench.ico to brand it.
UninstallDisplayIcon={app}\{#MyAppExeName}
UninstallDisplayName={#MyAppName}
Compression=lzma2
SolidCompression=yes
WizardStyle=modern
ArchitecturesInstallIn64BitMode=x64compatible
ArchitecturesAllowed=x64compatible
; Allow install without admin (per-user) or with admin (all users).
PrivilegesRequired=lowest
PrivilegesRequiredOverridesAllowed=dialog commandline

[Languages]
Name: "english"; MessagesFile: "compiler:Default.isl"

[Tasks]
Name: "desktopicon"; Description: "{cm:CreateDesktopIcon}"; GroupDescription: "{cm:AdditionalIcons}"; Flags: unchecked

[Files]
; The entire PyInstaller onedir bundle.
Source: "..\dist\{#MyAppName}\*"; DestDir: "{app}"; Flags: ignoreversion recursesubdirs createallsubdirs

[Icons]
Name: "{group}\{#MyAppName}"; Filename: "{app}\{#MyAppExeName}"
Name: "{group}\{cm:UninstallProgram,{#MyAppName}}"; Filename: "{uninstallexe}"
Name: "{autodesktop}\{#MyAppName}"; Filename: "{app}\{#MyAppExeName}"; Tasks: desktopicon

[Run]
Filename: "{app}\{#MyAppExeName}"; Description: "{cm:LaunchProgram,{#MyAppName}}"; Flags: nowait postinstall skipifsilent

[Code]
// On uninstall, offer to remove the user's benchmark results and downloaded
// models (stored under %LOCALAPPDATA%\AI-Bench), leaving it opt-in.
procedure CurUninstallStepChanged(CurUninstallStep: TUninstallStep);
var
  DataDir: String;
begin
  if CurUninstallStep = usUninstall then
  begin
    DataDir := ExpandConstant('{localappdata}\AI-Bench');
    if DirExists(DataDir) then
    begin
      if MsgBox('Also delete your saved benchmark results and downloaded models?'
        + #13#10 + DataDir, mbConfirmation, MB_YESNO) = IDYES then
      begin
        DelTree(DataDir, True, True, True);
      end;
    end;
  end;
end;
