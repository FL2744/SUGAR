from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


def test_release_workflow_publishes_all_supported_desktop_artifacts() -> None:
    workflow = (ROOT / ".github" / "workflows" / "release.yml").read_text(encoding="utf-8")
    assert "runs-on: macos-15" in workflow
    assert "SUGAR-macOS.zip" in workflow
    assert "SUGAR-macOS-Apple-Silicon.zip" not in workflow
    assert "SUGAR-macOS-Intel.zip" not in workflow
    assert "macos-15-intel" not in workflow
    assert "SUGAR-Windows-x64.zip" in workflow
    assert 'tag_version="${tag_version%%-*}"' in workflow


def test_ci_retains_a_validated_mac_bundle() -> None:
    workflow = (ROOT / ".github" / "workflows" / "ci.yml").read_text(encoding="utf-8")
    assert "Archive validated macOS bundle" in workflow
    assert "runs-on: macos-15" in workflow
    assert "SUGAR-macOS.zip" in workflow
    assert "SUGAR-macOS-Apple-Silicon.zip" not in workflow
    assert "SUGAR-macOS-Intel.zip" not in workflow
    assert "actions/upload-artifact@v7" in workflow


def test_branch_ci_uses_fast_gate_and_reserves_expensive_jobs() -> None:
    workflow = (ROOT / ".github" / "workflows" / "ci.yml").read_text(encoding="utf-8")
    assert "fast-test:" in workflow
    assert 'python-version: "3.14"' in workflow
    assert "compatibility-test:" in workflow
    expensive_gate = "github.ref == 'refs/heads/main' || github.event_name == 'workflow_dispatch'"
    # Live-network and packaged desktop jobs should not run on every fix-branch push.
    assert workflow.count(expensive_gate) >= 3
    # The compatibility matrix is intentionally non-Cartesian: supported Python
    # versions are covered cheaply on Linux while native OS checks use one runtime.
    assert "os: [ubuntu-latest, macos-latest, windows-latest]" not in workflow
    assert 'python-version: ["3.11", "3.12", "3.13", "3.14"]' not in workflow


def test_windows_build_info_matches_current_bridge_protocol() -> None:
    build = (ROOT / "SUGAR-Windows" / "scripts" / "build.ps1").read_text(encoding="utf-8")
    assert "bridge_protocol = 3" in build
    assert "bridge_protocol = 2" not in build
