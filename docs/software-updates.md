# Software updates

## Desktop app

Open **Settings → Updates** and select **Stable** for signed desktop updates. The panel shows the installed app version, last successful check, release notes, download progress, and any actionable error. An available release also appears in a dismissible notice throughout the app. The default **Latest** channel retains the rolling main-branch build and its explicit installer download; Preview and Long-term retain their existing release selection.

Updater-enabled Windows x64 and macOS Apple Silicon releases check the stable channel shortly after startup, then every six hours while the window is open and visible. Checks resume when the window becomes visible or the network returns. Checks have a 30-second timeout; failed background attempts wait at least 15 minutes before retrying. Manual **Check for updates** bypasses the automatic-check cooldown. A failed check is shown as a failure, never as “up to date.”

- **Check for updates automatically** is enabled by default and can be disabled per device.
- **Download updates automatically** is optional and disabled by default. When enabled, a discovered update downloads in the background. Otherwise choose **Download update**.
- Downloads use HTTPS and must pass Tauri's signature and signed-version verification before **Install and restart** appears. Download failures can be retried.
- Installation always requires your action. Save form edits, choose **Install and restart**, and confirm. The interface blocks installation during known active research runs; the native host also blocks it during sidecar commands. An installer error leaves the verified download available for another attempt.
- Downloads are held in memory for the current app session. Quitting before installation requires another download. Project files stay in their existing folders, outside the application bundle.

Preferences and the last successful check persist locally. Release notes are displayed as plain text. Research operations and credentials are not sent to the update endpoint; it receives a normal request for the public release manifest.

Older releases that predate the updater need one manual installation of an updater-enabled release. Development builds without signing configuration display **Automatic updates aren’t enabled in this build**, with a link to release downloads. They do not poll an unconfigured endpoint. Building this code does not retroactively add an updater to an already installed release.

## Browser, service, and CLI

Browser deployments are upgraded by their host; reload to use the deployed interface. Upgrade the Python service and CLI explicitly in their original environment, then restart any running API process. The desktop updater replaces the packaged app and its bundled Python bridge together; it does not modify a separate Python environment.

For an installation made from GitHub source:

```bash
# Activate the environment that originally installed SUGAR first.
python -m pip install --upgrade "sugar-osint @ git+https://github.com/FL2744/SUGAR.git@vVERSION"
sugar --version
sugar-project --version
sugar-state --version
sugar-intel --version
sugar-api --version
```

Replace `VERSION` with the desired published tag version. For an editable checkout, check out the reviewed release commit and run `python -m pip install -e ".[dev]"`. See the [CLI quick start](cli-quick-start.md) for environment selection and troubleshooting.

## Configure signed releases

Signed updates require an organization-controlled updater key pair. Without keys, the release workflow still builds manual installers and the Python distributions. Generate a key pair once on a trusted machine, outside the repository, using the installed Tauri CLI:

```powershell
cd SUGAR-Desktop
npm ci
npm run tauri -- signer generate --write-keys "$env:USERPROFILE\.tauri\sugar.updater.key"
```

Create the `.tauri` directory first if necessary. Keep a secure backup of the private key and its password. On macOS, use a path such as `~/.tauri/sugar.updater.key` instead. Follow the [official Tauri updater documentation](https://v2.tauri.app/plugin/updater/) for key handling.

Configure the GitHub repository under **Settings → Secrets and variables → Actions**:

| Kind | Name | Value |
| --- | --- | --- |
| Variable | `SUGAR_UPDATER_PUBLIC_KEY` | Complete contents of the generated `.pub` file, not its path |
| Secret | `TAURI_SIGNING_PRIVATE_KEY` | Complete private key file contents |
| Secret | `TAURI_SIGNING_PRIVATE_KEY_PASSWORD` | Key password, if one was set |

For a signed local build, set the same environment variables in the build process. `TAURI_SIGNING_PRIVATE_KEY` also accepts a local key path. Optionally set `SUGAR_REQUIRE_UPDATER=1` to require signing configuration. Use `scripts/build-windows.ps1` or `scripts/build-macos.sh`; both generate an ignored `src-tauri/.updater-build.json` containing only public configuration. Unsigned local/branch-CI builds remain available when both keys are absent. Partial configuration is an error.

The workflow uses Tauri CLI 2.12+ and updater plugin 2.13+. `requireSignedVersion` is enabled: artifact signatures must include the same semantic version as the manifest. Never replace the public key in an existing update channel without a planned transition signed by the original key. Losing the private key prevents existing installations from trusting future updates; a manual reinstall is then required. Updater signatures are separate from Apple code signing/notarization and Windows Authenticode.

## Release feed and validation

Run `python tools/release_tools.py versions --tag vVERSION` before tagging. It checks Python, npm, Tauri, Cargo, and both lockfiles. Versions must match exactly, including prerelease suffixes; a tag such as `v1.7.0-rc.1` cannot package a desktop app still labeled `1.7.0`.

The tagged workflow requires a nonempty versioned changelog section before expensive builds. With signing configured, it retains the MSI and signature, macOS manual-install ZIP, macOS `.app.tar.gz` and signature, and Python wheel/source distribution. The publication job rejects missing/empty/duplicate updater artifacts, malformed signatures, signatures from a different key, and signatures bound to a different version. For signed formal releases it generates `latest.json` with version-specific changelog notes and only the supported `windows-x86_64` and `darwin-aarch64` targets. Every release includes checksums for the complete payload. The client performs cryptographic signature verification before installation.

Assets are uploaded to a draft before publication. Prereleases are marked as prereleases and never promoted to GitHub's latest stable release. Stable apps read:

```text
https://github.com/FL2744/SUGAR/releases/latest/download/latest.json
```

If an upload or validation fails, fix the failure before publishing the draft; do not publish a partial release. A rerun encountering an existing draft stops instead of overwriting it. Inspect/remove that failed draft in GitHub before rebuilding the same tag, or repair it and validate every asset before publication.

For a faulty release, publish a corrected **higher** version. Automatic downgrades are disabled. Users who explicitly need an older supported build can install it manually. Before a production rollout, exercise an upgrade between two disposable signed builds on both supported operating systems, including failed-network, corrupted-package, busy-research, and restart behavior. Local unit/browser tests do not run a real MSI replacement or a macOS app replacement.
