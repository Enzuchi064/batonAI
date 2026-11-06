# batonAI

Centro de control local para agentes de IA: una app de escritorio, un gateway
en loopback y un panel de 480×320 que también se puede probar en el navegador.

El panel muestra el estado de los agentes y, en la columna lateral, los límites
reales de las IAs instaladas: **OpenCode**, **Codex** y **Claude Code**.

**[Descargar el instalador](https://github.com/Enzuchi064/batonAI/releases/latest)**

## Descargar e instalar

1. Entra en **[Releases](https://github.com/Enzuchi064/batonAI/releases/latest)**.
2. Descarga `batonAI-control-setup-0.1.0.exe`.
3. Ejecútalo. Se instala en tu carpeta de usuario, sin pedir administrador.
4. Abre **batonAI control** desde el menú Inicio.

La app arranca el gateway automáticamente si no está corriendo. El panel queda
disponible en:

```
http://127.0.0.1:8770/
```

En la pestaña **Hardware** de la app tienes el QR del dispositivo virtual y el
botón **Abrir panel**.

> El instalador no está firmado digitalmente. Windows puede mostrar SmartScreen:
> pulsa **Más información → Ejecutar de todas formas**.

## Qué incluye

- **Agentes:** sesiones de OpenCode, Claude Code, Codex, Gemini, Antigravity,
  Cursor y GitHub Copilot.
- **Límites reales:** ventanas Rolling, Semanal y Mensual de OpenCode, Codex y
  Claude Code, con porcentaje restante/gastado, barra y renovación.
- **Ojos por ventana:** eliges qué límites aparecen en el dispositivo.
- **Modo Restante / Gastado:** el dispositivo puede mostrar lo que queda o lo
  consumido.
- **Panel 480×320:** cabecera, rejilla de agentes y columna lateral dividida
  entre límites y estados de agentes.
- **Radar de peligro:** nivel 1/4–4/4, motivos y confirmación mantenida en el
  dispositivo.
- **Modo reposo:** resumen de lo ocurrido mientras no estabas.
- **Aprobaciones solo desde el dispositivo:** la app no aprueba permisos.

## Requisitos

- Windows 10/11.
- WebView2 (incluido en Windows modernos).
- Para leer límites:
  - **OpenCode** abierto con su servidor local.
  - **Codex** instalado y con sesión iniciada.
  - **Claude Code** instalado y con sesión iniciada (`~/.claude`).
- No hace falta hardware: el panel web simula la pantalla de 480×320.

## Desarrollo

Gateway:

```powershell
cd gateway
python -m venv .venv
.\.venv\Scripts\python.exe -m pip install -e ".[dev]"
.\.venv\Scripts\python.exe -m baton serve --port 8770
.\.venv\Scripts\python.exe -m pytest -q
```

App de escritorio:

```powershell
cd desktop
python -m venv .venv
.\.venv\Scripts\python.exe -m pip install -e .
.\.venv\Scripts\python.exe -m baton_desktop
```

## Crear el instalador

```powershell
# 1. PyInstaller en ambos entornos
cd gateway
.\.venv\Scripts\python.exe -m pip install pyinstaller
cd ..\desktop
.\.venv\Scripts\python.exe -m pip install pyinstaller
cd ..

# 2. Ejecutables
.\gateway\.venv\Scripts\pyinstaller.exe --noconfirm --clean --onedir --windowed `
  --name batonAI-gateway --icon "desktop\baton_desktop\ui\favicon.ico" `
  --distpath "release\dist" --workpath "release\build" --specpath "release\spec" `
  --paths "gateway" --add-data "$PWD\gateway\baton\static;baton\static" `
  --collect-submodules uvicorn --collect-submodules websockets "packaging\gateway_entry.py"

.\desktop\.venv\Scripts\pyinstaller.exe --noconfirm --clean --onedir --windowed `
  --name batonAI-control --icon "desktop\baton_desktop\ui\favicon.ico" `
  --distpath "release\dist" --workpath "release\build" --specpath "release\spec" `
  --paths "desktop" --add-data "$PWD\desktop\baton_desktop\ui;baton_desktop/ui" `
  --collect-all webview --collect-submodules clr_loader "packaging\desktop_entry.py"

# 3. Instalador (Inno Setup 6)
& "C:\Program Files (x86)\Inno Setup 6\ISCC.exe" "packaging\batonAI.iss"
```

El resultado queda en `release\batonAI-control-setup-0.1.0.exe`.

## Datos y privacidad

- El gateway escucha solo en `127.0.0.1`.
- La base de datos empaquetada vive en
  `%LOCALAPPDATA%\batonAI\baton.db`.
- Los registros del gateway empaquetado se escriben en
  `%LOCALAPPDATA%\batonAI\gateway.log`.
- No se suben datos a ningún servidor de batonAI: las lecturas de límites se
  hacen contra los servicios locales o contra las APIs oficiales usando las
  sesiones que ya tienes iniciadas.
