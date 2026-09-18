# SUGAR for macOS

SUGAR itself is licensed under Apache License 2.0. The packaged application includes `LICENSE`, `NOTICE`, `THIRD_PARTY_NOTICES.md`, and a generated third-party license inventory in its Resources directory.

This directory contains the native SwiftUI distribution of SUGAR. The app stores
credentials in macOS Keychain and bundles the Python search, map, and analysis
engine so recipients do not install Python or use Terminal.

## Recommended workflow

The app now opens on **Research Project** rather than raw keyword search. This is
the supported question-first path for a substantive research task:

1. create or open a portable SUGAR project folder;
2. save the research question, geography, timeframe, target audiences, languages,
   known entities, preferred sources, and collection depth;
3. build an inspectable bounded search plan;
4. execute that plan or import an existing authorized CSV/JSONL dataset;
5. triage evidence into ResearchObservation records and apply evidence feedback;
6. export or verify a portable hash-checked handoff bundle.

**Expert Search**, **Public URL**, **Map**, and **Analysis** remain available for
one-off operations. They are deliberately secondary to the project workflow so a
new user does not have to design a keyword matrix before defining the question.

## Build an unsigned test release

```bash
./scripts/build_app.sh
./scripts/package_dmg.sh
```

Outputs are written under `.build-native/`. The unsigned DMG is suitable for
local testing but Gatekeeper will warn other users.

## Create a signed and notarized public release

Public distribution requires Apple Developer Program membership, full Xcode,
a `Developer ID Application` certificate installed in Keychain, and a notarytool
profile. After installing Xcode, select it with `sudo xcode-select -s
/Applications/Xcode.app/Contents/Developer` and accept its license.

Store notarization credentials once:

```bash
xcrun notarytool store-credentials SUGAR-notary \
  --apple-id "YOUR_APPLE_ID" \
  --team-id "YOUR_TEAM_ID" \
  --password "APP_SPECIFIC_PASSWORD"
```

Then build, sign, notarize, staple, and verify the release:

```bash
export DEVELOPER_ID_APPLICATION="Developer ID Application: Your Name (TEAMID)"
export NOTARY_PROFILE="SUGAR-notary"
./scripts/release_notarized.sh
```

Never place Apple, X, OpenAI, ARC, Bluesky, or Mastodon credentials in this
repository. Runtime service credentials belong in the app's Settings screen and
are stored in macOS Keychain.

## macOS compatibility

The deployment baseline is macOS 13 Ventura. SUGAR itself supports Python
3.11–3.14, but the packaged macOS application deliberately embeds Python 3.12
whose runtime and libraries also support macOS 13 (for example, a compatible
python.org distribution). Select it explicitly if necessary:

```bash
PYTHON=/path/to/python3.12 ./scripts/build_app.sh
```

The macOS-specific constraint keeps NumPy at 2.2.6, and the build explicitly
selects its macOS 13-compatible wheel instead of the macOS 14 variant. Merely setting
`MACOSX_DEPLOYMENT_TARGET` does not lower the requirements of precompiled Python
libraries. The build now inspects every Mach-O binary inside the frozen backend,
as well as the Swift executable, and rejects deployment targets newer than 13.0
or a missing host architecture before assembling the app. It always rebuilds
the backend so a previous incompatible runtime cannot silently be reused.

An earlier distributed backend contained Python 3.14 and supporting libraries
with a macOS 26.0 minimum, plus NumPy libraries with a 14.0 minimum, despite the
app's 13.0 Info.plist. Rebuild the backend; editing the plist cannot fix this.

The supported packaged desktop target is Apple Silicon (`arm64`). Intel Mac
desktop builds are not distributed or supported. Before release, test
launch, Keychain settings, search, map creation, and Word/PDF analysis on an
actual supported arm64 macOS 13 installation. The binary
check verifies declared requirements, not all runtime behavior.

## Live Activity log

Activity streams the backend's stdout and stderr as complete lines while a job
runs, follows new messages automatically, and reports completion or the exit
code on failure. The Python bridge uses line-buffered output, including when
frozen with PyInstaller. Output file buttons remain available after completion.

Run the process-streaming regression check from this directory:

```bash
swiftc -swift-version 6 -parse-as-library Sources/BackendRunner.swift \
  Tests/ActivityStreaming.swift -o /tmp/sugar-activity-test
/tmp/sugar-activity-test
```

This checks delivery before exit, stderr, split UTF-8 characters, a final line
without a newline, nonzero exit codes, large output, and process launch failure.

## Provider credentials and model menus

Settings stores OpenAI, Virginia Tech ARC, and custom endpoint keys separately.
Search has provider and model dropdowns for OpenAI and ARC, with independent
model selections retained while switching providers. The custom endpoint keeps
its own model-ID and base-URL fields. Only the selected provider's key is passed
to the backend operation that requested it; a missing key never falls back to
another provider. Research Project triage uses the same provider/key boundary.

If an earlier version saved a shared LLM key, Settings offers a one-time menu to
assign that key to the correct provider. Save to Keychain to finish the move.
The original key is removed only after the separate entries save successfully.
Keychain save failures are reported in Activity.

The bundled model choices were checked on 2026-09-10 against:
- OpenAI: https://developers.openai.com/api/docs/models
- ARC: https://docs.arc.vt.edu/ai/011_llm_api_arc_vt_edu.html

These are bundled choices, not a live account-specific availability query.
Run the provider selection regression check from this directory:

```bash
swiftc -swift-version 6 -parse-as-library Sources/LLMProvider.swift \
  Tests/LLMProviderSelection.swift -o /tmp/sugar-provider-test
/tmp/sugar-provider-test
```

## Analysis packaging regression

The backend collects the complete `docx` package, including its Python source
layout and templates. `python-docx` opens headers and footers via paths such as
`docx/parts/../templates/default-footer.xml`; the intermediate `parts` directory
must exist even when imports otherwise come from PyInstaller's module archive.
The backend build runs `scripts/check_word_templates.py` against the actual
frozen archive. It extracts the packaged Word layout and creates a document
with a header and footer using only those template paths. This reproduces and
catches the missing-directory failure that development-environment tests miss.
