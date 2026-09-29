from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


def test_release_workflow_publishes_all_supported_desktop_artifacts() -> None:
    workflow = (ROOT / ".github" / "workflows" / "release.yml").read_text(encoding="utf-8")
    assert "runs-on: macos-15" in workflow
    assert "SUGAR-macOS.zip" in workflow
    assert "SUGAR-macOS-Apple-Silicon.zip" not in workflow
    assert "SUGAR-macOS-Intel.zip" not in workflow
    assert "macos-15-intel" not in workflow
    assert "bundle/msi/*.msi" in workflow
    assert "SUGAR-Windows-x64.zip" not in workflow
    assert 'tag_version="${tag_version%%-*}"' in workflow


def test_ci_retains_a_validated_mac_bundle() -> None:
    workflow = (ROOT / ".github" / "workflows" / "ci.yml").read_text(encoding="utf-8")
    assert "Archive validated macOS bundle" in workflow
    assert "runs-on: macos-15" in workflow
    assert "SUGAR-Desktop/src-tauri/target/release/bundle/macos/SUGAR.app" in workflow
    assert "SUGAR-macOS.zip" in workflow
    assert "SUGAR-macOS-Apple-Silicon.zip" not in workflow
    assert "SUGAR-macOS-Intel.zip" not in workflow
    assert "actions/upload-artifact@v7" in workflow


def test_branch_ci_uses_fast_gate_and_reserves_expensive_jobs() -> None:
    workflow = (ROOT / ".github" / "workflows" / "ci.yml").read_text(encoding="utf-8")
    live_workflow = (ROOT / ".github" / "workflows" / "authorized-live-smoke.yml").read_text(encoding="utf-8")
    assert "fast-test:" in workflow
    assert 'python-version: "3.14"' in workflow
    assert "compatibility-test:" in workflow
    expensive_gate = "github.ref == 'refs/heads/main' || github.event_name == 'workflow_dispatch'"
    # Packaged desktop jobs should not run on every fix-branch push. Public live
    # API checks run only through a separately confirmed manual workflow.
    assert workflow.count(expensive_gate) >= 2
    assert "weibo-live-smoke:" not in workflow
    assert "offline-stress-smoke:" in workflow
    assert "workflow_dispatch:" in live_workflow
    assert "confirm_bounded_public_reads:" in live_workflow
    assert "type: boolean" in live_workflow
    assert "push:" not in live_workflow
    assert "pull_request:" not in live_workflow
    # The compatibility matrix is intentionally non-Cartesian: supported Python
    # versions are covered cheaply on Linux while native OS checks use one runtime.
    assert "os: [ubuntu-latest, macos-latest, windows-latest]" not in workflow
    assert 'python-version: ["3.11", "3.12", "3.13", "3.14"]' not in workflow


def test_windows_build_info_matches_current_bridge_protocol() -> None:
    build = (ROOT / "SUGAR-Desktop" / "scripts" / "build-windows.ps1").read_text(encoding="utf-8")
    shell = (ROOT / "SUGAR-Desktop" / "src-tauri" / "src" / "main.rs").read_text(encoding="utf-8")
    bridge = (ROOT / "sugar_bridge.py").read_text(encoding="utf-8")
    assert "build --bundles msi" in build
    assert "sugar-bridge-x86_64-pc-windows-msvc.exe" not in build  # target name is derived from Rust
    assert "BRIDGE_PROTOCOL_VERSION = 3" in bridge
    assert "run_backend" in shell
