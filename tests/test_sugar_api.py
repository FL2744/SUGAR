import json
import threading
import urllib.error
import urllib.request
from http.server import ThreadingHTTPServer
from pathlib import Path
import uuid

import pytest

import sugar_api
from sugar_core.workspace import SugarWorkspace


def _workspace(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> tuple[str, Path]:
    identifier = str(uuid.uuid4())
    root = tmp_path / identifier
    SugarWorkspace.create(root, name="API boundary test")
    monkeypatch.setattr(sugar_api, "_workspace_root", tmp_path)
    return identifier, root


def test_browser_project_references_resolve_inside_the_workspace(tmp_path, monkeypatch):
    identifier, root = _workspace(tmp_path, monkeypatch)
    source = root / "data" / "raw" / "records.jsonl"
    source.write_text("{}\n", encoding="utf-8")

    config = sugar_api._rewrite_config(
        {
            "workspace": f"sugar-workspace://{identifier}",
            "records_file": f"sugar-file://{identifier}/data/raw/records.jsonl",
            "output_directory": f"sugar-workspace://{identifier}/outputs/exports",
        },
        workspace_id=identifier,
    )

    assert config["workspace"] == str(root.resolve())
    assert config["records_file"] == str(source.resolve())
    assert config["output_directory"] == str((root / "outputs" / "exports").resolve())


def test_browser_handoff_directory_reference_accepts_a_project_folder(tmp_path, monkeypatch):
    identifier, root = _workspace(tmp_path, monkeypatch)
    bundle = root / "outputs" / "exports" / "handoff"
    bundle.mkdir(parents=True)

    config = sugar_api._rewrite_config(
        {"bundle_directory": f"sugar-workspace://{identifier}/outputs/exports/handoff"},
        workspace_id=identifier,
    )

    assert config["bundle_directory"] == str(bundle.resolve())


def test_browser_handoff_directory_reference_rejects_a_file(tmp_path, monkeypatch):
    identifier, root = _workspace(tmp_path, monkeypatch)
    bundle_file = root / "outputs" / "exports" / "handoff.zip"
    bundle_file.parent.mkdir(parents=True, exist_ok=True)
    bundle_file.write_bytes(b"zip")

    with pytest.raises(sugar_api.ApiError, match="Project directory was not found"):
        sugar_api._rewrite_config(
            {"bundle_directory": f"sugar-workspace://{identifier}/outputs/exports/handoff.zip"},
            workspace_id=identifier,
        )


def test_browser_project_references_reject_traversal_and_cross_project_access(tmp_path, monkeypatch):
    identifier, _ = _workspace(tmp_path, monkeypatch)
    other_id = str(uuid.uuid4())

    with pytest.raises(sugar_api.ApiError, match="escapes"):
        sugar_api._rewrite_config(
            {"workspace": f"sugar-workspace://{identifier}/../../outside"},
            workspace_id=identifier,
        )
    with pytest.raises(sugar_api.ApiError, match="another project"):
        sugar_api._rewrite_config(
            {"workspace": f"sugar-workspace://{other_id}"},
            workspace_id=identifier,
        )
    with pytest.raises(sugar_api.ApiError, match="must reference a file"):
        sugar_api._rewrite_config({"source_file": "C:/private/records.csv"}, workspace_id=identifier)


def test_api_outputs_use_portable_forward_slash_project_references(tmp_path, monkeypatch):
    identifier, root = _workspace(tmp_path, monkeypatch)
    backend_path = str(root / "data" / "raw" / "records.jsonl")

    mapped = sugar_api._map_paths(
        {"outputs": [backend_path], "message": f"saved {backend_path}"},
        root=root,
        identifier=identifier,
    )

    expected = f"sugar-workspace://{identifier}/data/raw/records.jsonl"
    assert mapped["outputs"] == [expected]
    assert mapped["message"] == f"saved {expected}"


def test_project_member_tokens_are_scoped_and_roles_are_enforced(tmp_path, monkeypatch):
    identifier, root = _workspace(tmp_path, monkeypatch)
    profile = root / ".sugar" / "project-profile.json"
    profile.write_text(json.dumps({"notes": "", "members": [{"name": "Reviewer", "email": "reviewer@example.test", "role": "reviewer"}]}), encoding="utf-8")
    private_file = root / "outputs" / "exports" / "report.csv"
    private_file.parent.mkdir(parents=True, exist_ok=True)
    private_file.write_text("value\n1\n", encoding="utf-8")

    old_token, old_origins = sugar_api.SugarApiHandler.api_token, sugar_api.SugarApiHandler.allowed_origins
    sugar_api.SugarApiHandler.api_token = "test-admin-token"
    sugar_api.SugarApiHandler.allowed_origins = set()
    server = ThreadingHTTPServer(("127.0.0.1", 0), sugar_api.SugarApiHandler)
    worker = threading.Thread(target=server.serve_forever, daemon=True)
    worker.start()
    base = f"http://127.0.0.1:{server.server_address[1]}"

    def request(method, path, token, payload=None):
        data = json.dumps(payload).encode("utf-8") if payload is not None else None
        headers = {"Authorization": f"Bearer {token}"}
        if data is not None:
            headers["Content-Type"] = "application/json"
        req = urllib.request.Request(base + path, data=data, headers=headers, method=method)
        try:
            with urllib.request.urlopen(req, timeout=3) as response:
                return response.status, response.read()
        except urllib.error.HTTPError as response:
            status, body = response.code, response.read()
            response.close()
            return status, body

    try:
        status, body = request("POST", f"/api/workspaces/{identifier}/access", "test-admin-token", {"email": "reviewer@example.test"})
        assert status == 201
        access = json.loads(body)
        token = access["token"]
        assert access["role"] == "reviewer"
        store = (tmp_path / ".sugar-member-access.json").read_text(encoding="utf-8")
        assert token not in store

        status, body = request("GET", "/api/workspaces", token)
        assert status == 200
        assert [item["id"] for item in json.loads(body)["workspaces"]] == [identifier]

        status, body = request("GET", f"/api/workspaces/{identifier}/files/outputs/exports/report.csv", token)
        assert status == 200
        assert body.replace(b"\r\n", b"\n") == b"value\n1\n"

        status, body = request(
            "POST", "/api/run", token,
            {"operation": "workspace-hub", "config": {"action": "project-profile-update", "workspace": f"sugar-workspace://{identifier}", "members": []}},
        )
        assert status == 403
        assert "cannot perform" in json.loads(body)["error"]

        status, body = request("DELETE", f"/api/workspaces/{identifier}/access/reviewer%40example.test", "test-admin-token")
        assert status == 200
        assert json.loads(body)["revoked"] == 1
        status, _body = request("GET", "/api/workspaces", token)
        assert status == 401
    finally:
        server.shutdown()
        server.server_close()
        worker.join(timeout=3)
        sugar_api.SugarApiHandler.api_token = old_token
        sugar_api.SugarApiHandler.allowed_origins = old_origins
