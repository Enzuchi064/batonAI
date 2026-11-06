#define MyAppName "batonAI"
#define MyAppVersion "0.3.1"
#define MyAppPublisher "batonAI"
#define MyAppExeName "batonAI-control.exe"

[Setup]
AppId={{84F3BA32-A780-4ECC-A332-1EA48D686DDD}
AppName={#MyAppName}
AppVersion={#MyAppVersion}
AppPublisher={#MyAppPublisher}
DefaultDirName={autopf}\batonAI
DefaultGroupName=batonAI
DisableProgramGroupPage=yes
PrivilegesRequired=admin
OutputDir=..\release
OutputBaseFilename=batonAI-control-setup-{#MyAppVersion}
SetupIconFile=..\desktop\baton_desktop\ui\favicon.ico
Compression=lzma2/ultra64
SolidCompression=yes
WizardStyle=modern
CloseApplications=yes
UninstallDisplayIcon={app}\control\{#MyAppExeName}

[Languages]
Name: "spanish"; MessagesFile: "compiler:Languages\Spanish.isl"

[Tasks]
Name: "desktopicon"; Description: "Crear un acceso directo en el escritorio"; GroupDescription: "Accesos directos:"; Flags: unchecked
Name: "autostart"; Description: "Arrancar el gateway al iniciar sesión"; GroupDescription: "Inicio automático:"; Flags: unchecked

[Files]
Source: "..\release\dist\batonAI-control\*"; DestDir: "{app}\control"; Flags: recursesubdirs createallsubdirs ignoreversion
Source: "..\release\dist\batonAI-gateway\*"; DestDir: "{app}\gateway"; Flags: recursesubdirs createallsubdirs ignoreversion
Source: "..\README.md"; DestDir: "{app}"; Flags: ignoreversion

[Icons]
Name: "{group}\batonAI control"; Filename: "{app}\control\{#MyAppExeName}"; WorkingDir: "{app}\control"
Name: "{group}\batonAI gateway"; Filename: "{app}\gateway\batonAI-gateway.exe"; WorkingDir: "{app}\gateway"
Name: "{commonstartup}\batonAI gateway"; Filename: "{app}\gateway\batonAI-gateway.exe"; WorkingDir: "{app}\gateway"; Tasks: autostart
Name: "{autodesktop}\batonAI control"; Filename: "{app}\control\{#MyAppExeName}"; WorkingDir: "{app}\control"; Tasks: desktopicon

[Run]
Filename: "powershell.exe"; Parameters: "-NoProfile -ExecutionPolicy Bypass -Command ""New-NetFirewallRule -DisplayName 'batonAI gateway' -Direction Inbound -Program '{app}\gateway\batonAI-gateway.exe' -Action Allow -Profile Any -ErrorAction SilentlyContinue"""; Flags: runhidden; StatusMsg: "Permitiendo el gateway en la red local..."
Filename: "{app}\control\{#MyAppExeName}"; Description: "Abrir batonAI control"; Flags: nowait postinstall skipifsilent

[UninstallRun]
Filename: "powershell.exe"; Parameters: "-NoProfile -ExecutionPolicy Bypass -Command ""Remove-NetFirewallRule -DisplayName 'batonAI gateway' -ErrorAction SilentlyContinue"""; Flags: runhidden; RunOnceId: "RemoveBatonFirewall"
