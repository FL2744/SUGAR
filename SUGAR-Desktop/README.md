# SUGAR Desktop and Web

SUGAR has one active research interface: a React/TypeScript web application with a MapLibre map. The browser is the canonical surface. The optional Tauri 2 shell wraps the same frontend on Windows and macOS and starts the existing Python bridge as a local sidecar.

```text
Browser or optional Tauri shell
              ↓
       React + MapLibre
              ↓ HTTP            ↓ Tauri sidecar
         sugar_api.py              sugar_bridge.py
                 \                 /
                    sugar_core
```

The browser and desktop use the same project format and Python research logic. The browser can connect to a local API or to a hosted API endpoint. Tauri is useful when analysts need a locally packaged app and native file pickers.

## Run the browser workflow locally

From the repository root, install the Python package and start its API:

```powershell
python -m pip install -e .
python sugar_api.py
```

In another terminal, build dependencies and launch the frontend:

```powershell
cd SUGAR-Desktop
npm install
npm run dev
```

Open the displayed Vite URL. The default API address is `http://127.0.0.1:8765`; it can be changed in **Settings → Research API**. Browser projects are stored under `~/.sugar/workspaces` (or `%USERPROFILE%\.sugar\workspaces`). Set `SUGAR_API_WORKSPACE_ROOT` to choose another root.

The API accepts project files through browser uploads, stores them in that project, and provides exported handoff bundles as downloads. Uploads are limited to 50 MB and supported data formats. Project file references are scoped to the selected workspace.

## Host the frontend and API

Build the static browser frontend with `npm run build`. Serve `dist/` using the approved web host. Run `sugar_api.py` behind an HTTPS reverse proxy and configure the exact frontend origin:

```sh
export SUGAR_API_TOKEN="a-long-random-secret"
export SUGAR_API_WORKSPACE_ROOT="/srv/sugar/workspaces"
export SUGAR_API_ALLOWED_ORIGINS="https://research.vt.domains"
python sugar_api.py --host 127.0.0.1 --port 8765
```

Set the frontend API address to the reverse-proxied HTTPS endpoint using `VITE_SUGAR_API_URL` at build time or **Settings → Research API** at runtime. The browser keeps the API token in session memory. Remote connections require HTTPS. The current API is a single-operator boundary: it scopes files to a workspace and supports a bearer token, but does not provide per-user identity, tenant isolation, or institutional authorization. Put it behind approved identity and access controls before hosting real research data.

## Optional desktop packages

The same UI can be packaged in the Tauri shell.

Windows, from PowerShell at the repository root:

```powershell
.\SUGAR-Desktop\scripts\build-windows.ps1
```

On macOS with Xcode command line tools, Rust, and Python 3.12:

```sh
./SUGAR-Desktop/scripts/build-macos.sh
```

The packaged sidecar runs locally, so a desktop user does not need to start `sugar_api.py`. The app bundles the Python research bridge, not the full Python development environment.

## Shared workflows

- Create or open a local or API-managed research project.
- Record a research requirement, generate a deterministic plan, and review it before collection.
- Upload authorized evidence or reference data and inspect fields before import.
- Filter institution records, view clustered locations, and inspect evidence sources.
- Prepare a human-review draft and export a verified handoff bundle.
- Keep provider credentials in session memory and pass them only with the requested operation.

## Map source

MapLibre renders the primary interactive map. The basemap uses OpenFreeMap vector tiles and needs a network connection. Project records remain in SUGAR workspaces. Folium/Leaflet remains available for portable HTML exports.

## Archived native clients

The retired PySide6 and SwiftUI implementations are preserved under `archive/legacy-native-ui/` for historical reference. They are not build fallbacks or supported application entry points.
