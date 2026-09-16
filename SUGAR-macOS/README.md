# SUGAR for macOS

This directory contains the native SwiftUI distribution of SUGAR. The packaged app stores credentials in macOS Keychain and bundles the Python backend, so recipients do **not** install Python or use Terminal for ordinary desktop use.

## Classroom preview

The classroom build opens on a **Welcome** screen rather than dropping a new user directly into a developer-oriented search form. It includes:

- a credential-free sample spreadsheet, map, and PDF report;
- one-click sample map/report generation;
- keyword search for X, Bluesky, Mastodon, Bilibili, Weibo, and authorized Zhihu search;
- **Public URL Import** for known public WeChat Official Account, Zhihu, Douyin, Bilibili, and Weibo items;
- direct output opening plus Finder reveal;
- a classroom testing guide and GitHub usability-feedback link;
- build diagnostics containing the version and Git commit used to produce the app.

AI translation/location inference are off by default in the classroom search screen so users can perform supported public collection without first obtaining an LLM key. Source-specific credentials remain explicit rather than being silently substituted.

For the classroom preview, CI publishes an architecture-specific **`.app.zip`** containing the already validated `SUGAR.app`. Apple Silicon and Intel Macs receive separate artifacts. Extract the ZIP and open `SUGAR.app`; ordinary classroom users do not need Python or Terminal.

## Build an unsigned test release

Build the app locally with:

```bash
./scripts/build_app.sh
```

Outputs are written under `.build-native/`. For local convenience, a developer can also create an unsigned DMG with:

```bash
./scripts/package_dmg.sh
```

The classroom CI path intentionally publishes the tested `.app.zip` directly instead of making DMG creation a release gate. This avoids allowing a disk-image wrapper or hosted-runner disk-space problem to invalidate an app bundle that already passed architecture, backend, live-collection, analysis, and code-sign verification.

The classroom build is ad-hoc signed rather than a notarized public release. Gatekeeper may warn when the app is downloaded elsewhere; use only a build distributed by the project team and do not disable macOS security protections globally.

## Create a signed and notarized public release

Public distribution requires Apple Developer Program membership, full Xcode, a `Developer ID Application` certificate installed in Keychain, and a notarytool profile. After installing Xcode, select it and accept its license.

```bash
xcrun notarytool store-credentials SUGAR-notary \
  --apple-id "YOUR_APPLE_ID" \
  --team-id "YOUR_TEAM_ID" \
  --password "APP_SPECIFIC_PASSWORD"

export DEVELOPER_ID_APPLICATION="Developer ID Application: Your Name (TEAMID)"
export NOTARY_PROFILE="SUGAR-notary"
./scripts/release_notarized.sh
```

Never place Apple, X, OpenAI, ARC, Bluesky, Mastodon, Weibo, or Zhihu credentials in this repository. Runtime service credentials belong in Settings and are stored in macOS Keychain.

## macOS compatibility

The deployment baseline is macOS 13 Ventura. Build the backend with a Python 3.12 runtime/libraries compatible with macOS 13:

```bash
PYTHON=/path/to/python3.12 ./scripts/build_app.sh
```

The macOS-specific constraint keeps NumPy at a compatible build, and packaging inspects every Mach-O binary inside the frozen backend plus the Swift executable. The build rejects deployment targets newer than 13.0 or a missing host architecture. It always rebuilds the backend so an incompatible cached runtime cannot silently be reused.

Build on Apple Silicon for arm64, or on an Intel Mac with Intel Python for x86_64. These are separate builds, not a universal app. Classroom CI independently builds and exercises both architectures. Before broad release, also test launch, Keychain settings, keyword search, public URL import, map creation, and Word/PDF analysis on an actual macOS 13 installation of the corresponding architecture.

## Build identity

Every classroom app contains `Contents/Resources/build-info.json` with:

- SUGAR version;
- full Git commit SHA;
- build timestamp;
- architecture;
- bridge protocol;
- bundled-runtime marker.

The Welcome and Settings screens show the short build revision in diagnostics. Use this identifier in usability/bug reports so feedback cannot be confused with an older Drive copy or independently built executable.

## Live Activity log

Activity streams the backend's stdout/stderr as complete lines while a job runs, follows new messages automatically, reports completion/failure, and renders common backend events as researcher-readable progress. Generated output buttons open the file directly; a Finder button remains available for locating it on disk.

For multi-source collection, a single provider failure no longer erases successful work from the other selected sources. The Activity area reports the unavailable source, continues the remaining collectors, and labels a successful degraded run as **partial collection**. The saved metadata preserves the exact successful and failed source list.

Run the process-streaming regression check from this directory:

```bash
swiftc -swift-version 6 -parse-as-library Sources/BackendRunner.swift \
  Tests/ActivityStreaming.swift -o /tmp/sugar-activity-test
/tmp/sugar-activity-test
```

## Provider and source credentials

Settings keeps OpenAI, Virginia Tech ARC, custom endpoint, X, optional Bluesky/Mastodon, optional existing Weibo session, and Zhihu Open Platform credentials separate. Only credentials relevant to a selected operation are passed to the backend child process.

Zhihu's Access Secret is used only for official keyword search. Known public Zhihu URL import is a separate operation and does not require that credential. WeChat/Douyin classroom support is known-public-URL import; SUGAR does not label those adapters as general keyword search.

If an earlier version saved a shared LLM key, Settings offers a one-time menu to assign it to the correct provider. Save to Keychain to finish the move; the previous entry is removed only after the replacement saves successfully.

## Analysis packaging regression

The backend collects the complete `docx` package, including its Python source layout and templates. The backend build runs `scripts/check_word_templates.py` against the actual frozen archive and creates a test document using the packaged templates so development-environment success cannot hide a broken classroom binary.
