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

Set the frontend API address to the reverse-proxied HTTPS endpoint using `VITE_SUGAR_API_URL` at build time or **Settings → Research API** at runtime. The browser keeps the API token in session memory. Remote connections require HTTPS. The operator token grants administrator access; administrators can issue and revoke project-scoped member tokens, and each request enforces the member's current project role. This does not provide institutional sign-in or simultaneous conflict-resolved editing. Put hosted research data behind approved institutional identity and access controls. See the [root README](../README.md#browser-and-desktop-use) for roles and token storage.

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

Opening a project restores its saved question, evidence, registry, and history. Changing projects clears project-specific drafts, previews, imports, and filters. Save requirement and project-profile edits before switching. After reconnecting the Research API in Settings, the selected project reloads automatically.

Evidence results are paged for bulk runs. The Institutions page and Map page provide their own filters and record inspectors.

## Find your way around

Use **Research** to prepare a request, review its plan, run collection, inspect evidence, and export results. **Institutions**, **Map**, **Timeline**, and **Monitoring** open the corresponding project views. The advanced workspace provides additional import and review tools. Save form edits before changing projects or reloading.

The evidence desk supports activity verification, rubric coding, public feed seeds, analyst captures, country snapshots, and packages for an approved AI tool. Imported evidence stays linked to its source and human review state.

Use **Ctrl K** on Windows/Linux or **⌘ K** on macOS to open quick actions. Type a destination, use the arrow keys to select it, and press Enter. Escape closes the dialog. Dialogs keep keyboard focus inside and return it when closed.

Choose a color theme under **Settings → Interface**, or use the theme quick action. The preference persists locally. Responsive navigation keeps the main destinations available on small screens.

## Software updates

**Settings → Updates → Stable** shows the desktop version, update status, release notes, and verified download progress. Signed release builds check automatically; automatic downloads are optional. Installation requires confirmation and waits for known active research work to finish. The default Latest channel keeps the rolling build and explicit installer download. Browser deployments are updated by their host. Older desktop releases need one manual installation to gain the updater.

Local builds without release keys display a manual-download link. To enable signed update builds and configure release CI, follow [Software updates](../docs/software-updates.md). Private signing keys never belong in this repository.

## Map source

MapLibre renders the primary interactive map. The basemap uses OpenFreeMap vector tiles and needs a network connection. Project records remain in SUGAR workspaces. Folium/Leaflet remains available for portable HTML exports.

## Archived native clients

The retired PySide6 and SwiftUI implementations are preserved under `archive/legacy-native-ui/` for historical reference. They are not build fallbacks or supported application entry points.
