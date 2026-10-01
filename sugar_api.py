"""Small HTTP boundary for the browser based SUGAR interface.

The API keeps projects under one configured workspace root. The operator token
is an administrator credential; project-scoped member tokens are issued to named
roster members and checked against their current role on every request. Bind to
loopback for local use. Remote use requires the administrator token and HTTPS.
"""
from __future__ import annotations

import argparse
import hashlib
import hmac
import json
import mimetypes
import os
import re
import secrets
import subprocess
import sys
import threading
import tempfile
import uuid
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Any
from urllib.parse import parse_qs, unquote, urlsplit

import sugar_bridge
from sugar_core.credential_store import load_env_file
from sugar_core.research_api import ApiError, Stream, dispatch as research_dispatch
from sugar_core.research_runs import ResearchProject
from sugar_core.workbench import ResearchWorkbench
from sugar_core.workspace import SugarWorkspace


MAX_JSON_BYTES = 2 * 1024 * 1024
MAX_UPLOAD_BYTES = 50 * 1024 * 1024
UPLOAD_SUFFIXES = {".csv", ".tsv", ".xlsx", ".xls", ".json", ".jsonl", ".ndjson"}
VIRTUAL_SCHEMES = {"sugar-workspace", "sugar-file"}
PATH_KEYS = {
    "workspace", "path", "source_file", "records_file", "bundle_directory",
    "output_directory", "artifact", "artifact_path", "input_file", "output_file",
    "file_path", "csv_path", "jsonl_path", "image_path", "comparison_file",
}
OPTIONAL_PATH_KEYS = {"output_directory", "artifact", "artifact_path", "output_file"}
DIRECTORY_PATH_KEYS = {"workspace", "bundle_directory"}
ROLE_LEVELS = {"viewer": 0, "reviewer": 1, "analyst": 2, "owner": 3}
_member_token_lock = threading.Lock()
VIEWER_ACTIONS = {
    "dashboard", "project-history", "project-profile", "registry-list", "registry-profile",
    "dataset-browse", "dataset-geography-summary", "monitor-list", "monitor-feed",
    "project-comment-list", "research-template-list", "dataset-region-compare",
}
REVIEWER_ACTIONS = {"monitor-review", "research-triage", "dataset-export", "registry-export", "project-bundle-export"}
OWNER_ACTIONS = {"project-profile-update", "project-create-subproject", "project-bundle-import"}
SECRET_ENV = {
    "llm_api_key": "SUGAR_LLM_API_KEY",
    "x_bearer_token": "SUGAR_X_BEARER_TOKEN",
    "bluesky_identifier": "SUGAR_BLUESKY_IDENTIFIER",
    "bluesky_app_password": "SUGAR_BLUESKY_APP_PASSWORD",
    "mastodon_token": "SUGAR_MASTODON_TOKEN",
    "weibo_cookie": "SUGAR_WEIBO_COOKIE",
}


_workbench: ResearchWorkbench | None = None


def get_workbench() -> ResearchWorkbench:
    """The process-wide research workbench (providers, credentials, live runs)."""
    global _workbench
    if _workbench is None:
        _workbench = ResearchWorkbench()
    return _workbench


def _linked_path() -> Path:
    return get_workspace_root() / "linked-projects.json"


def _linked_index() -> dict[str, str]:
    """Folders a local desktop user opened from elsewhere on disk: stable id -> absolute folder."""
    try:
        payload = json.loads(_linked_path().read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {}
    return {str(k): str(v) for k, v in payload.items()} if isinstance(payload, dict) else {}


def link_local_project(folder: str, *, name: str = "", create: bool = False) -> dict[str, Any]:
    """Register an existing (or new) SUGAR project folder so the workbench can use it. Desktop/loopback only."""
    target = Path(folder).expanduser().resolve()
    if not (target / "sugar-project.json").is_file():
        if not create:
            raise ApiError(404, "That folder is not a SUGAR project. Create a new project or choose a folder that contains sugar-project.json.")
        workspace = SugarWorkspace.create(target, name=name or target.name)
    else:
        workspace = SugarWorkspace.open(target)
    identifier = str(uuid.uuid5(uuid.NAMESPACE_URL, target.as_uri()))
    index = _linked_index()
    index[identifier] = str(target)
    _linked_path().write_text(json.dumps(index, indent=2, sort_keys=True), encoding="utf-8")
    return {"id": identifier, "workspace": f"sugar-workspace://{identifier}", "name": workspace.manifest.name, "path": str(target)}


def resolve_project(raw_identifier: str) -> ResearchProject:
    identifier = _workspace_id(raw_identifier)
    linked = _linked_index().get(identifier)
    if linked and (Path(linked) / "sugar-project.json").is_file():
        return ResearchProject(SugarWorkspace.open(linked))
    root = (get_workspace_root() / identifier).resolve()
    if not _within(get_workspace_root(), root) or not (root / "sugar-project.json").is_file():
        raise ApiError(404, "Project was not found on this SUGAR server.")
    return ResearchProject(SugarWorkspace.open(root))


def list_research_projects() -> list[ResearchProject]:
    projects = []
    for candidate in sorted(get_workspace_root().iterdir()):
        if candidate.is_dir() and re.fullmatch(r"[0-9a-fA-F-]{36}", candidate.name) and (candidate / "sugar-project.json").is_file():
            try:
                projects.append(ResearchProject(SugarWorkspace.open(candidate)))
            except (OSError, ValueError):
                continue
    for identifier, folder in _linked_index().items():
        if (Path(folder) / "sugar-project.json").is_file():
            try:
                projects.append(ResearchProject(SugarWorkspace.open(folder)))
            except (OSError, ValueError):
                continue
    return projects


def _role_name(value: Any) -> str:
    normalized = re.sub(r"[^a-z]+", " ", str(value or "").casefold()).strip()
    aliases = {
        "owner": "owner", "project owner": "owner", "lead": "owner", "lead analyst": "analyst",
        "administrator": "owner", "admin": "owner", "analyst": "analyst", "editor": "analyst",
        "contributor": "analyst", "reviewer": "reviewer", "review": "reviewer",
        "viewer": "viewer", "observer": "viewer", "read only": "viewer",
    }
    return aliases.get(normalized, "viewer")


def _member_token_store() -> Path:
    return get_workspace_root() / ".sugar-member-access.json"


def _read_member_tokens() -> dict[str, dict[str, str]]:
    try:
        payload = json.loads(_member_token_store().read_text(encoding="utf-8"))
    except FileNotFoundError:
        return {}
    except (OSError, json.JSONDecodeError) as exc:
        raise ApiError(500, "The SUGAR member access registry could not be read.") from exc
    if not isinstance(payload, dict):
        raise ApiError(500, "The SUGAR member access registry has an invalid format.")
    return {str(key): value for key, value in payload.items() if isinstance(value, dict)}


def _write_member_tokens(payload: dict[str, dict[str, str]]) -> None:
    target = _member_token_store()
    target.parent.mkdir(parents=True, exist_ok=True)
    descriptor, temporary = tempfile.mkstemp(prefix=".sugar-member-access-", suffix=".tmp", dir=target.parent)
    try:
        with os.fdopen(descriptor, "w", encoding="utf-8") as stream:
            json.dump(payload, stream, ensure_ascii=False, indent=2)
            stream.write("\n")
        try:
            os.chmod(temporary, 0o600)
        except OSError:
            pass
        os.replace(temporary, target)
    finally:
        Path(temporary).unlink(missing_ok=True)


def _project_member(root: Path, email: str) -> dict[str, Any] | None:
    try:
        payload = json.loads((root / ".sugar" / "project-profile.json").read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return None
    members = payload.get("members", []) if isinstance(payload, dict) else []
    if not isinstance(members, list):
        return None
    return next((row for row in members if isinstance(row, dict) and str(row.get("email", "")).casefold() == email.casefold()), None)


def _workspace_id(value: str) -> str:
    try:
        return str(uuid.UUID(value))
    except (ValueError, AttributeError) as exc:
        raise ApiError(400, "Invalid project identifier.") from exc


def _within(root: Path, candidate: Path) -> bool:
    try:
        candidate.resolve().relative_to(root.resolve())
        return True
    except ValueError:
        return False


def _virtual_path(
    value: str,
    *,
    workspace_id: str | None = None,
    allow_missing: bool = False,
    must_be_directory: bool = False,
) -> Path:
    parsed = urlsplit(value)
    if parsed.scheme not in VIRTUAL_SCHEMES or not parsed.netloc:
        raise ApiError(400, "Browser requests must use a SUGAR project file reference.")
    identifier = _workspace_id(parsed.netloc)
    if workspace_id and identifier != workspace_id:
        raise ApiError(403, "A request cannot use files from another project.")
    root = (get_workspace_root() / identifier).resolve()
    if not root.is_dir() or not (root / "sugar-project.json").is_file():
        raise ApiError(404, "Project was not found on this SUGAR server.")
    relative = unquote(parsed.path).lstrip("/")
    candidate = (root / relative).resolve() if relative else root
    if not _within(root, candidate):
        raise ApiError(403, "Project file reference escapes its project folder.")
    if not relative and not candidate.is_dir():
        raise ApiError(404, "Project was not found on this SUGAR server.")
    if relative and not allow_missing:
        exists = candidate.is_dir() if must_be_directory else candidate.is_file()
        if not exists:
            message = "Project directory was not found." if must_be_directory else "Project file was not found."
            raise ApiError(404, message)
    return candidate


_workspace_root: Path | None = None


def get_workspace_root() -> Path:
    global _workspace_root
    if _workspace_root is None:
        configured = os.environ.get("SUGAR_API_WORKSPACE_ROOT", "").strip()
        _workspace_root = Path(configured).expanduser().resolve() if configured else (Path.home() / ".sugar" / "workspaces").resolve()
    _workspace_root.mkdir(parents=True, exist_ok=True)
    return _workspace_root


def _rewrite_config(value: Any, *, workspace_id: str | None = None, key: str = "") -> Any:
    if isinstance(value, dict):
        return {str(child_key): _rewrite_config(child, workspace_id=workspace_id, key=str(child_key)) for child_key, child in value.items()}
    if isinstance(value, list):
        return [_rewrite_config(child, workspace_id=workspace_id, key=key) for child in value]
    if not isinstance(value, str) or key not in PATH_KEYS or not value:
        return value
    parsed = urlsplit(value)
    if parsed.scheme in VIRTUAL_SCHEMES:
        return str(_virtual_path(
            value,
            workspace_id=workspace_id,
            allow_missing=key in OPTIONAL_PATH_KEYS,
            must_be_directory=key in DIRECTORY_PATH_KEYS,
        ))
    raise ApiError(400, f"The {key} field must reference a file in the selected SUGAR project.")


def _find_workspace_id(value: Any, key: str = "") -> str | None:
    if isinstance(value, dict):
        for child_key, child in value.items():
            found = _find_workspace_id(child, str(child_key))
            if found:
                return found
    elif isinstance(value, list):
        for child in value:
            found = _find_workspace_id(child, key)
            if found:
                return found
    elif isinstance(value, str) and key in PATH_KEYS:
        parsed = urlsplit(value)
        if parsed.scheme in VIRTUAL_SCHEMES:
            return _workspace_id(parsed.netloc)
    return None


def _map_paths(value: Any, *, root: Path, identifier: str) -> Any:
    root_text = str(root.resolve())
    root_slash = root_text.replace("\\", "/")
    virtual = f"sugar-workspace://{identifier}"
    if isinstance(value, dict):
        return {key: _map_paths(child, root=root, identifier=identifier) for key, child in value.items()}
    if isinstance(value, list):
        return [_map_paths(child, root=root, identifier=identifier) for child in value]
    if isinstance(value, str):
        result = value.replace(root_text + os.sep, virtual + "/").replace(root_text, virtual)
        if root_slash != root_text:
            result = result.replace(root_slash + "/", virtual + "/").replace(root_slash, virtual)
        if virtual in result:
            result = result.replace("\\", "/")
        return result
    return value


def _read_manifest(path: Path) -> dict[str, Any] | None:
    try:
        payload = json.loads((path / "sugar-project.json").read_text(encoding="utf-8"))
        return payload if isinstance(payload, dict) else None
    except (OSError, ValueError):
        return None


class SugarApiHandler(BaseHTTPRequestHandler):
    server_version = "SUGAR-API/2.0"
    api_token = ""
    allowed_origins: set[str] = set()
    expose_paths = False    # desktop sidecar only: lets the local app reach a project's folder for file dialogs

    def log_message(self, fmt: str, *args: Any) -> None:
        # Log only "METHOD /path -> status": never request bodies, query strings, or authorization headers.
        try:
            request, code = str(args[0]), str(args[1])
            method, _, rest = request.partition(" ")
            super().log_message("%s %s -> %s", method, rest.split(" ")[0].split("?")[0], code)
        except (IndexError, ValueError):
            super().log_message("%s", "request")

    def _send(self, status: int, payload: Any, content_type: str = "application/json; charset=utf-8", headers: dict[str, str] | None = None) -> None:
        body = payload if isinstance(payload, bytes) else json.dumps(payload, ensure_ascii=False).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", content_type)
        self.send_header("Content-Length", str(len(body)))
        self.send_header("X-Content-Type-Options", "nosniff")
        origin = self.headers.get("Origin", "")
        if origin and origin in self.allowed_origins:
            self.send_header("Access-Control-Allow-Origin", origin)
            self.send_header("Vary", "Origin")
            self.send_header("Access-Control-Allow-Headers", "Authorization, Content-Type")
            self.send_header("Access-Control-Allow-Methods", "GET, POST, DELETE, OPTIONS")
        if headers:
            for key, value in headers.items():
                self.send_header(key, value)
        self.end_headers()
        self.wfile.write(body)

    def _authorized(self) -> bool:
        origin = self.headers.get("Origin", "")
        if origin and self.allowed_origins and origin not in self.allowed_origins:
            self._send(403, {"error": "This browser origin is not allowed by the SUGAR API."})
            return False
        supplied = self.headers.get("Authorization", "")
        prefix = "Bearer "
        token = supplied[len(prefix):] if supplied.startswith(prefix) else ""
        self.principal: dict[str, str] | None = None
        if self.api_token and token and hmac.compare_digest(token, self.api_token):
            self.principal = {"email": "", "role": "owner", "project_id": ""}
        elif token:
            digest = hashlib.sha256(token.encode("utf-8")).hexdigest()
            member = _read_member_tokens().get(digest)
            if member:
                self.principal = {key: str(value) for key, value in member.items()}
        elif not self.api_token:
            # No token is configured only for loopback development; treat that
            # local operator as the administrator, matching the bind policy.
            self.principal = {"email": "", "role": "owner", "project_id": ""}
        if self.principal is None:
            self._send(401, {"error": "A valid SUGAR API token is required."})
            return False
        return True

    def _require_admin(self) -> bool:
        if self.principal and self.principal.get("role") == "owner" and not self.principal.get("email"):
            return True
        self._send(403, {"error": "Only the SUGAR API administrator can manage project access."})
        return False

    def _require_project(self, identifier: str, minimum_role: str = "viewer") -> bool:
        if not self.principal:
            self._send(401, {"error": "A valid SUGAR API token is required."})
            return False
        if self.principal.get("role") == "owner" and not self.principal.get("email"):
            return True
        if self.principal.get("project_id") != identifier:
            self._send(403, {"error": "This member token is scoped to a different project."})
            return False
        root = _virtual_path(f"sugar-workspace://{identifier}", workspace_id=identifier)
        member = _project_member(root, self.principal.get("email", ""))
        if member is None:
            self._send(403, {"error": "This account is not listed as a member of the project."})
            return False
        actual_level = ROLE_LEVELS[_role_name(member.get("role"))]
        required_level = ROLE_LEVELS[minimum_role]
        if actual_level < required_level:
            self._send(403, {"error": f"The project role '{_role_name(member.get('role'))}' cannot perform this operation."})
            return False
        return True

    def _required_role(self, operation: str, config: dict[str, Any]) -> str:
        action = str(config.get("action") or "") if operation == "workspace-hub" else ""
        if action in OWNER_ACTIONS:
            return "owner"
        if action in REVIEWER_ACTIONS or operation in {"research-strategy-approve", "research-review-apply"}:
            return "reviewer"
        if operation in {"research-strategy-update", "research-workbook-apply"} and str(config.get("review_state") or "").casefold() in {"approved", "rejected", "needs_followup"}:
            return "reviewer"
        if action in VIEWER_ACTIONS or operation in {"diagnostics", "research-status"}:
            return "viewer"
        return "analyst"

    def _json_body(self, maximum: int = MAX_JSON_BYTES) -> dict[str, Any]:
        try:
            length = int(self.headers.get("Content-Length", "0"))
        except ValueError as exc:
            raise ApiError(400, "Invalid Content-Length header.") from exc
        if length < 0 or length > maximum:
            raise ApiError(413, "Request body is too large.")
        if length == 0:
            return {}
        try:
            payload = json.loads(self.rfile.read(length))
        except (ValueError, UnicodeDecodeError) as exc:
            raise ApiError(400, "Request body must be valid JSON.") from exc
        if not isinstance(payload, dict):
            raise ApiError(400, "Request body must be a JSON object.")
        return payload

    def do_OPTIONS(self) -> None:
        origin = self.headers.get("Origin", "")
        if self.allowed_origins and origin not in self.allowed_origins:
            self._send(403, {"error": "This browser origin is not allowed by the SUGAR API."})
            return
        self._send(204, b"")

    def do_GET(self) -> None:
        if not self._authorized():
            return
        route = urlsplit(self.path)
        try:
            self._get(route)
        except ApiError as exc:
            self._send(exc.status, {"error": str(exc)})
        except Exception as exc:  # Keep internal paths and tracebacks out of browser responses.
            self._send(500, {"error": f"SUGAR API operation failed ({type(exc).__name__})."})

    def _get(self, route) -> None:
        if route.path == "/api/health":
            self._send(200, {"status": "ready", "api_version": 2, "bridge_protocol": sugar_bridge.BRIDGE_PROTOCOL_VERSION,
                             "features": ["research_workbench", "activity_stream", "providers", "debug_report"]})
            return
        if route.path == "/api/workspaces":
            rows = []
            scoped_project_id = self.principal.get("project_id", "") if self.principal else ""
            linked_ids = {str(Path(v).resolve()): k for k, v in _linked_index().items()}
            for project in list_research_projects():
                manifest = _read_manifest(project.workspace.root)
                if not manifest:
                    continue
                identifier = linked_ids.get(str(project.workspace.root)) or _workspace_id(project.workspace.root.name)
                if scoped_project_id and identifier.casefold() != scoped_project_id.casefold():
                    continue
                if not self._require_project(identifier, "viewer"):
                    if scoped_project_id:
                        return
                    continue
                summary = project.summary()
                rows.append({"id": identifier, "workspace": f"sugar-workspace://{identifier}", "name": manifest.get("name") or project.workspace.root.name,
                             "description": manifest.get("description", ""), "research_question": summary["research_question"],
                             "status": summary["status"], "last_activity": summary["last_activity"], "updated_at": summary["updated_at"],
                             "run_count": summary["run_count"],
                             **({"path": str(project.workspace.root)} if self.expose_paths else {})})
            rows.sort(key=lambda row: str(row["last_activity"]), reverse=True)
            self._send(200, {"workspaces": rows})
            return
        match = re.fullmatch(r"/api/workspaces/([0-9a-fA-F-]+)/files/(.+)", route.path)
        if match:
            identifier = _workspace_id(match.group(1))
            if not self._require_project(identifier, "viewer"):
                return
            reference = f"sugar-file://{identifier}/{match.group(2)}"
            path = _virtual_path(reference, workspace_id=identifier)
            filename = path.name.replace('"', "")
            self._send(200, path.read_bytes(), mimetypes.guess_type(filename)[0] or "application/octet-stream", {"Content-Disposition": f'attachment; filename="{filename}"'})
            return
        self._research("GET", route, None)

    @staticmethod
    def _research_role(method: str, area: str, rest: str) -> str:
        """Minimum project role for a workbench route (reads: viewer; changing plans/runs: analyst; settings: owner)."""
        if method == "GET":
            return "viewer"
        if area == "research" and rest == "settings":
            return "owner"
        if area == "research" and rest == "review":
            return "reviewer"          # reviewers may judge, tag and comment; viewers can only read
        return "analyst"

    def _authorize_research(self, method: str, path: str, body: dict[str, Any] | None) -> bool:
        """Project routes follow project roles. Providers, credentials, diagnostics and folder access are administrator-only,
        because they spend money, expose configuration, or reach outside the project."""
        match = re.fullmatch(r"/api/workspaces/([0-9a-fA-F-]+)/(research|runs|timeline)(?:/(.*))?", path)
        if match:
            return self._require_project(_workspace_id(match.group(1)), self._research_role(method, match.group(2), match.group(3) or ""))
        if path == "/api/platforms" and method == "GET":
            return True
        if path == "/api/interpret" and body and body.get("workspace_id"):
            return self._require_project(_workspace_id(str(body["workspace_id"])), "analyst")
        return self._require_admin()

    def _research(self, method: str, route, body: dict[str, Any] | None) -> None:
        if not self._authorize_research(method, route.path, body):
            return
        query = {key: values[-1] for key, values in parse_qs(route.query).items()}
        if isinstance(body, dict):
            body.pop("_author", None)      # the author of a review action is the authenticated member, never client input
            if method == "POST" and self.principal:
                body["_author"] = self.principal.get("email") or str(body.get("author") or "").strip()[:80] or "Researcher"
        result = research_dispatch(method, route.path, query, body, wb=get_workbench(), resolve_project=resolve_project,
                                   list_projects=list_research_projects)
        if result is None:
            self._send(404, {"error": "API route not found."})
        elif isinstance(result, Stream):
            self._stream(result)
        else:
            self._send(result[0], result[1])

    def _stream(self, stream: Stream) -> None:
        self.send_response(200)
        self.send_header("Content-Type", "text/event-stream; charset=utf-8")
        self.send_header("Cache-Control", "no-cache")
        self.send_header("X-Accel-Buffering", "no")
        self.send_header("X-Content-Type-Options", "nosniff")
        origin = self.headers.get("Origin", "")
        if origin and origin in self.allowed_origins:
            self.send_header("Access-Control-Allow-Origin", origin)
            self.send_header("Vary", "Origin")
        self.end_headers()
        try:
            for frame in stream.frames():
                self.wfile.write(frame)
                self.wfile.flush()
        except (BrokenPipeError, ConnectionResetError, OSError):
            pass

    def do_POST(self) -> None:
        if not self._authorized():
            return
        route = urlsplit(self.path)
        try:
            if route.path == "/api/workspaces":
                self._create_workspace()
                return
            if route.path == "/api/workspaces/open":
                if not self.expose_paths:
                    raise ApiError(403, "Opening folders is only available in the local desktop app.")
                payload = self._json_body()
                self._send(200, link_local_project(str(payload.get("path") or ""), name=str(payload.get("name") or ""), create=bool(payload.get("create"))))
                return
            access_match = re.fullmatch(r"/api/workspaces/([0-9a-fA-F-]+)/access", route.path)
            if access_match:
                self._issue_member_access(access_match.group(1))
                return
            upload_match = re.fullmatch(r"/api/workspaces/([0-9a-fA-F-]+)/uploads/(.+)", route.path)
            if upload_match:
                if not self._require_project(_workspace_id(upload_match.group(1)), "analyst"):
                    return
                self._upload(upload_match.group(1), upload_match.group(2))
                return
            if route.path == "/api/run":
                self._run_operation()
                return
            self._research("POST", route, self._json_body())
        except ApiError as exc:
            self._send(exc.status, {"error": str(exc)})
        except Exception as exc:  # Keep internal paths and tracebacks out of browser responses.
            self._send(500, {"error": f"SUGAR API operation failed ({type(exc).__name__})."})

    def do_DELETE(self) -> None:
        if not self._authorized():
            return
        match = re.fullmatch(r"/api/workspaces/([0-9a-fA-F-]+)/access/(.+)", urlsplit(self.path).path)
        if not match:
            try:
                self._research("DELETE", urlsplit(self.path), None)
            except ApiError as exc:
                self._send(exc.status, {"error": str(exc)})
            except Exception as exc:
                self._send(500, {"error": f"SUGAR API operation failed ({type(exc).__name__})."})
            return
        identifier = _workspace_id(match.group(1))
        if not self._require_project(identifier, "owner"):
            return
        email = unquote(match.group(2)).strip().casefold()
        with _member_token_lock:
            tokens = _read_member_tokens()
            updated = {key: row for key, row in tokens.items()
                       if not (str(row.get("project_id", "")).casefold() == identifier.casefold()
                               and str(row.get("email", "")).casefold() == email)}
            _write_member_tokens(updated)
        self._send(200, {"revoked": len(tokens) - len(updated), "email": email})

    def _issue_member_access(self, raw_identifier: str) -> None:
        identifier = _workspace_id(raw_identifier)
        if not self._require_project(identifier, "owner"):
            return
        root = _virtual_path(f"sugar-workspace://{identifier}", workspace_id=identifier)
        payload = self._json_body()
        email = str(payload.get("email") or "").strip().casefold()
        if len(email) > 254 or "@" not in email or any(ch.isspace() for ch in email):
            raise ApiError(400, "A valid project-member email address is required.")
        member = _project_member(root, email)
        if member is None:
            raise ApiError(404, "Add this person to the project roster before issuing access.")
        role = _role_name(member.get("role"))
        if role not in ROLE_LEVELS:
            raise ApiError(400, "The project member role is not supported.")
        token = "sugar_member_" + secrets.token_urlsafe(32)
        digest = hashlib.sha256(token.encode("utf-8")).hexdigest()
        with _member_token_lock:
            tokens = _read_member_tokens()
            tokens = {key: row for key, row in tokens.items()
                      if not (str(row.get("project_id", "")).casefold() == identifier.casefold()
                              and str(row.get("email", "")).casefold() == email)}
            tokens[digest] = {"project_id": identifier, "email": email, "role": "member"}
            _write_member_tokens(tokens)
        self._send(201, {"token": token, "email": email, "role": role, "project_id": identifier,
                         "message": "This token is shown once. Share it with the member through your approved secure channel."})

    def _create_workspace(self) -> None:
        if not self._require_admin():
            return
        payload = self._json_body()
        name = str(payload.get("name") or "").strip()
        if not name:
            raise ApiError(400, "A project name is required.")
        if len(name) > 120:
            raise ApiError(400, "Project name must be 120 characters or fewer.")
        identifier = str(uuid.uuid4())
        path = (get_workspace_root() / identifier).resolve()
        if not _within(get_workspace_root(), path):
            raise ApiError(500, "Could not create a project inside the configured workspace root.")
        workspace = SugarWorkspace.create(path, name=name, description=str(payload.get("description") or ""))
        self._send(201, {"id": identifier, "workspace": f"sugar-workspace://{identifier}", "name": workspace.manifest.name, "description": workspace.manifest.description})

    def _upload(self, raw_identifier: str, raw_name: str) -> None:
        identifier = _workspace_id(raw_identifier)
        name = unquote(raw_name).replace("\\", "/").split("/")[-1].strip(" .")
        suffix = Path(name).suffix.lower()
        if not name or suffix not in UPLOAD_SUFFIXES:
            raise ApiError(415, "Upload a CSV, TSV, Excel, JSON, or JSONL dataset.")
        try:
            length = int(self.headers.get("Content-Length", "0"))
        except ValueError as exc:
            raise ApiError(400, "Invalid Content-Length header.") from exc
        if length <= 0 or length > MAX_UPLOAD_BYTES:
            raise ApiError(413, "Dataset uploads must be between 1 byte and 50 MB.")
        root = _virtual_path(f"sugar-workspace://{identifier}", workspace_id=identifier)
        uploads = root / "data" / "raw" / "browser-imports"
        uploads.mkdir(parents=True, exist_ok=True)
        safe_stem = re.sub(r"[^A-Za-z0-9_.-]+", "_", Path(name).stem).strip("._") or "dataset"
        target = uploads / f"{safe_stem}-{secrets.token_hex(5)}{suffix}"
        if not _within(root, target):
            raise ApiError(403, "Upload target escapes the selected project.")
        remaining = length
        with target.open("wb") as stream:
            while remaining:
                chunk = self.rfile.read(min(1024 * 1024, remaining))
                if not chunk:
                    target.unlink(missing_ok=True)
                    raise ApiError(400, "Upload ended before the declared content length.")
                stream.write(chunk)
                remaining -= len(chunk)
        relative = target.relative_to(root).as_posix()
        self._send(201, {"path": f"sugar-file://{identifier}/{relative}", "name": name, "size": length})

    def _run_operation(self) -> None:
        payload = self._json_body()
        operation = str(payload.get("operation") or "")
        if operation not in sugar_bridge.ALL_OPERATIONS:
            raise ApiError(400, "Unsupported SUGAR operation.")
        config = payload.get("config") or {}
        credentials = payload.get("secrets") or {}
        if not isinstance(config, dict) or not isinstance(credentials, dict):
            raise ApiError(400, "Configuration and credentials must be JSON objects.")
        identifier = _find_workspace_id(config)
        if identifier:
            if not self._require_project(identifier, self._required_role(operation, config)):
                return
        elif self.principal and self.principal.get("email"):
            self._send(403, {"error": "Member tokens require an explicit project scope."})
            return
        prepared = _rewrite_config(config, workspace_id=identifier)
        if self.principal and self.principal.get("email"):
            prepared["actor"] = self.principal["email"]
        with tempfile.NamedTemporaryFile("w", encoding="utf-8", suffix=".json", delete=False) as stream:
            json.dump(prepared, stream, ensure_ascii=False)
            config_path = Path(stream.name)
        environment = os.environ.copy()
        for name, variable in SECRET_ENV.items():
            supplied = str(credentials.get(name) or "")
            if supplied:                      # otherwise the bridge falls back to the environment, then to saved Settings
                environment[variable] = supplied
        command = [sys.executable, str(Path(sugar_bridge.__file__).resolve()), operation]
        if operation != "diagnostics":
            command.extend(["--config", str(config_path)])
        try:
            result = subprocess.run(command, cwd=str(Path(sugar_bridge.__file__).resolve().parent), env=environment, capture_output=True, text=True, timeout=600, check=False)
        except subprocess.TimeoutExpired as exc:
            raise ApiError(504, "SUGAR operation exceeded the 10 minute server limit.") from exc
        finally:
            config_path.unlink(missing_ok=True)
        events = []
        for line in result.stdout.splitlines():
            try:
                event = json.loads(line)
                if isinstance(event, dict):
                    events.append(event)
            except ValueError:
                continue
        if result.stderr.strip():
            events.append({"event": "backend-stderr", "message": result.stderr.strip()})
        if result.returncode and not any(event.get("event") == "error" for event in events):
            events.append({"event": "error", "message": result.stderr.strip() or f"SUGAR exited with code {result.returncode}."})
        if identifier:
            root = get_workspace_root() / identifier
            events = _map_paths(events, root=root, identifier=identifier)
            stdout = result.stdout.replace(str(root.resolve()), f"sugar-workspace://{identifier}")
            stderr = result.stderr.replace(str(root.resolve()), f"sugar-workspace://{identifier}")
        else:
            stdout, stderr = result.stdout, result.stderr
        stdout = stdout.replace(str(config_path), "[request-config]")
        stderr = stderr.replace(str(config_path), "[request-config]")
        self._send(200, {"code": result.returncode, "events": events, "stdout": stdout, "stderr": stderr})


TAURI_ORIGINS = {"tauri://localhost", "http://tauri.localhost", "https://tauri.localhost"}
DEFAULT_DEV_ORIGINS = {"http://localhost:1420", "http://127.0.0.1:1420", "http://localhost:4173", "http://127.0.0.1:4173",
                       "http://localhost:5173", "http://127.0.0.1:5173"}


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Run the SUGAR HTTP API for its browser interface.")
    parser.add_argument("--host", default=os.environ.get("SUGAR_API_HOST", "127.0.0.1"))
    parser.add_argument("--port", type=int, default=int(os.environ.get("SUGAR_API_PORT", "8765")), help="0 selects a free port.")
    parser.add_argument("--workspace-root", default=os.environ.get("SUGAR_API_WORKSPACE_ROOT", str(Path.home() / ".sugar" / "workspaces")))
    parser.add_argument("--allow-origin", action="append", default=[])
    parser.add_argument("--env-file", default="", help="Git-ignored file of SUGAR_* variables (default: ./.env.local or ~/.sugar/.env).")
    parser.add_argument("--generate-token", action="store_true", help="Create a random API token for this process (desktop sidecar).")
    parser.add_argument("--ready-json", action="store_true", help="Print one machine-readable JSON line when ready (desktop sidecar).")
    parser.add_argument("--expose-paths", action="store_true", help="Include project folder paths in listings (loopback desktop use only).")
    args = parser.parse_args(argv)
    loaded = load_env_file(args.env_file or None)
    if loaded and not args.ready_json:
        print(f"Loaded {len(loaded)} SUGAR_* variable(s) from the environment file (values are never printed).")
    global _workspace_root
    _workspace_root = Path(args.workspace_root).expanduser().resolve()
    _workspace_root.mkdir(parents=True, exist_ok=True)
    token = os.environ.get("SUGAR_API_TOKEN", "").strip()
    if args.generate_token and not token:
        token = secrets.token_urlsafe(32)
    local_hosts = {"localhost", "127.0.0.1", "::1"}
    if args.host not in local_hosts and not token:
        parser.error("SUGAR_API_TOKEN is required when binding beyond loopback.")
    if args.expose_paths and args.host not in local_hosts:
        parser.error("--expose-paths is only allowed when binding to loopback.")
    allowed_origins = set(args.allow_origin)
    allowed_origins.update(origin.strip() for origin in os.environ.get("SUGAR_API_ALLOWED_ORIGINS", "").split(",") if origin.strip())
    if not allowed_origins:
        allowed_origins = set(DEFAULT_DEV_ORIGINS)
    if args.ready_json:
        allowed_origins |= TAURI_ORIGINS
    SugarApiHandler.api_token = token
    SugarApiHandler.allowed_origins = allowed_origins
    SugarApiHandler.expose_paths = bool(args.expose_paths)
    server = ThreadingHTTPServer((args.host, args.port), SugarApiHandler)
    server.daemon_threads = True
    url = f"http://{args.host}:{server.server_address[1]}"
    if args.ready_json:
        print(json.dumps({"event": "api_ready", "url": url, "token": token, "workspace_root": str(_workspace_root)}), flush=True)
    else:
        print(f"SUGAR API ready at {url}/api/health", flush=True)
        print(f"Project root: {_workspace_root}", flush=True)
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        server.server_close()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
