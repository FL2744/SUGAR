from __future__ import annotations

import json
from pathlib import Path

from sugar_core.workspace_cli import main


def test_workspace_cli_init_status_register_and_list(tmp_path: Path, capsys) -> None:
    root = tmp_path / "workspace"
    assert main(["init", str(root), "--name", "CLI Project"]) == 0
    capsys.readouterr()

    artifact = root / "data" / "raw" / "sample.jsonl"
    artifact.write_text('{"ok": true}\n', encoding="utf-8")

    assert (
        main(
            [
                "register",
                str(root),
                "harvest",
                "data/raw/sample.jsonl",
                "--label",
                "Sample harvest",
                "--metadata",
                '{"source":"fixture"}',
            ]
        )
        == 0
    )
    registered = json.loads(capsys.readouterr().out)
    assert registered["kind"] == "harvest"
    assert registered["path"] == "data/raw/sample.jsonl"

    assert main(["status", str(root), "--json"]) == 0
    status = json.loads(capsys.readouterr().out)
    assert status["name"] == "CLI Project"
    assert status["artifact_counts"] == {"harvest": 1}

    assert main(["list", str(root), "--json"]) == 0
    rows = json.loads(capsys.readouterr().out)
    assert len(rows) == 1
    assert rows[0]["label"] == "Sample harvest"


def test_workspace_cli_path_prints_canonical_directory(tmp_path: Path, capsys) -> None:
    root = tmp_path / "workspace"
    main(["init", str(root), "--name", "Paths"])
    capsys.readouterr()

    assert main(["path", str(root), "reports"]) == 0
    output = capsys.readouterr().out.strip()
    assert Path(output) == (root / "outputs" / "reports").resolve()


def test_workspace_cli_archive_and_restore(tmp_path: Path, capsys) -> None:
    root = tmp_path / "workspace"
    restored = tmp_path / "restored"
    archive = tmp_path / "workspace.sugar.zip"
    main(["init", str(root), "--name", "Archive Project"])
    capsys.readouterr()

    assert main(["archive", str(root), str(archive)]) == 0
    assert Path(capsys.readouterr().out.strip()) == archive.resolve()
    assert main(["restore", str(archive), str(restored)]) == 0
    assert Path(capsys.readouterr().out.strip()) == restored.resolve() / "sugar-project.json"
