#ifndef AppVersion
  #error AppVersion is required
#endif
[Setup]
AppId=FarazHussain.SereinVault
AppName=Serein Vault
AppVersion={#AppVersion}
AppPublisher=Faraz Hussain and contributors
AppPublisherURL=https://github.com/asteroidcrib729/serein-vault
DefaultDirName={localappdata}\Programs\SereinVault
DefaultGroupName=Serein Vault
PrivilegesRequired=lowest
ArchitecturesAllowed=x64compatible
ArchitecturesInstallIn64BitMode=x64compatible
OutputDir={#OutputPath}
OutputBaseFilename=SereinVault-{#AppVersion}-windows-x64-setup
SetupIconFile={#IconPath}
UninstallDisplayIcon={app}\SereinVault.exe
LicenseFile={#LicensePath}
Compression=lzma2
SolidCompression=yes
WizardStyle=modern
CloseApplications=yes
RestartApplications=no
[Files]
Source: "{#PayloadPath}\*"; DestDir: "{app}"; Flags: ignoreversion recursesubdirs createallsubdirs
[Icons]
Name: "{autoprograms}\Serein Vault"; Filename: "{app}\SereinVault.exe"
[Run]
Filename: "{app}\SereinVault.exe"; Description: "Open Serein Vault"; Flags: nowait postinstall skipifsilent
; No data-directory deletion: uninstall leaves vaults and user files intact.
