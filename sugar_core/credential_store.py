"""Local credential storage that keeps secrets out of Git, projects, logs, and bug reports.

Secrets are addressed by an opaque *reference* (``provider:<profile-id>`` or
``platform:<name>``). Projects, run records, and exports contain only references.

Operating-system credential vault integration is removed. SUGAR never reads,
writes, or deletes Keychain entries, including through legacy credential lookups.

``memory`` is the default: credentials last for this process only.
``file`` is an explicit opt-in through ``SUGAR_CREDENTIAL_BACKEND=file``: an
unencrypted per-user file with owner-only permissions (0600 in a 0700 directory).

Environment variables always take precedence at *resolution* time so local development builds
can use real credentials without persisting them (see :func:`load_env_file`).
"""
from __future__ import annotations

import json
import os
import re
import tempfile
import threading
from pathlib import Path
from typing import Iterable

from . import redaction

# platform secret key -> environment variable (mirrors the bridge's SECRET_ENV)
PLATFORM_SECRET_ENV = {
    "x_bearer_token": "SUGAR_X_BEARER_TOKEN",
    "bluesky_identifier": "SUGAR_BLUESKY_IDENTIFIER",
    "bluesky_app_password": "SUGAR_BLUESKY_APP_PASSWORD",
    "mastodon_token": "SUGAR_MASTODON_TOKEN",
    "weibo_cookie": "SUGAR_WEIBO_COOKIE",
    "openalex_api_key": "SUGAR_OPENALEX_API_KEY",
}
LEGACY_LLM_ENV = "SUGAR_LLM_API_KEY"


def sugar_home() -> Path:
    configured = os.environ.get("SUGAR_HOME", "").strip()
    return Path(configured).expanduser() if configured else Path.home() / ".sugar"


def _ref_env_name(ref: str) -> str:
    return "SUGAR_CRED_" + re.sub(r"[^A-Za-z0-9]+", "_", ref).strip("_").upper()


def parse_env_file(text: str) -> dict[str, str]:
    """Parse simple KEY=VALUE lines (optionally quoted, `export` prefix, # comments)."""
    values: dict[str, str] = {}
    for raw in text.splitlines():
        line = raw.strip()
        if not line or line.startswith("#"):
            continue
        if line.startswith("export "):
            line = line[7:].strip()
        if "=" not in line:
            continue
        key, _, value = line.partition("=")
        key = key.strip()
        value = value.strip()
        if len(value) >= 2 and value[0] == value[-1] and value[0] in "\"'":
            value = value[1:-1]
        elif " #" in value:
            value = value.split(" #", 1)[0].strip()
        if re.fullmatch(r"[A-Za-z_][A-Za-z0-9_]*", key):
            values[key] = value
    return values


def load_env_file(path: str | os.PathLike[str] | None = None, *, override: bool = False) -> list[str]:
    """Load ``SUGAR_*`` variables from a git-ignored env file into ``os.environ``.

    Returns the names loaded. Values are registered with the redactor immediately. Only
    variables that start with ``SUGAR_`` are honoured so an env file cannot alter unrelated
    process configuration.
    """
    candidates: list[Path] = []
    if path:
        candidates.append(Path(path).expanduser())
    elif os.environ.get("SUGAR_ENV_FILE"):
        candidates.append(Path(os.environ["SUGAR_ENV_FILE"]).expanduser())
    else:
        candidates.extend([Path.cwd() / ".env.local", sugar_home() / ".env"])
    loaded: list[str] = []
    for candidate in candidates:
        try:
            text = candidate.read_text(encoding="utf-8")
        except OSError:
            continue
        for key, value in parse_env_file(text).items():
            if not key.startswith("SUGAR_") or not value:
                continue
            if override or key not in os.environ:
                os.environ[key] = value
                loaded.append(key)
            redaction.register_secret(value)
        break
    return loaded


class CredentialError(RuntimeError):
    pass


class CredentialStore:
    def __init__(self, home: str | os.PathLike[str] | None = None, backend: str | None = None) -> None:
        self.home = Path(home).expanduser() if home else sugar_home()
        requested = (backend or os.environ.get("SUGAR_CREDENTIAL_BACKEND", "auto")).strip().casefold()
        self._lock = threading.RLock()
        self._memory: dict[str, str] = {}
        if requested in {"auto", "memory"}:
            self.backend = "memory"
        elif requested == "file":
            self.backend = "file"
        elif requested == "keyring":
            raise CredentialError("Keychain and OS credential vault access has been removed. Use memory or file storage.")
        else:
            raise CredentialError(f"Unknown credential backend {requested!r}.")

    @property
    def _file(self) -> Path:
        return self.home / "credentials.json"

    def _ensure_home(self) -> None:
        self.home.mkdir(parents=True, exist_ok=True)
        try:
            os.chmod(self.home, 0o700)
        except OSError:
            pass

    def _read_file(self, path: Path) -> dict[str, str]:
        try:
            payload = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            return {}
        return {str(k): str(v) for k, v in payload.items()} if isinstance(payload, dict) else {}

    def _write_file(self, path: Path, payload: dict[str, str]) -> None:
        self._ensure_home()
        handle, temporary = tempfile.mkstemp(dir=str(self.home), prefix=".cred-", suffix=".tmp")
        try:
            with os.fdopen(handle, "w", encoding="utf-8") as stream:
                json.dump(payload, stream, indent=2, sort_keys=True)
            try:
                os.chmod(temporary, 0o600)
            except OSError:
                pass
            os.replace(temporary, path)
        except BaseException:
            try:
                os.unlink(temporary)
            except OSError:
                pass
            raise

    # -- public API --------------------------------------------------------------------
    def set(self, ref: str, value: str) -> None:
        value = str(value or "")
        if not ref:
            raise CredentialError("A credential reference is required.")
        if not value.strip():
            raise CredentialError("Refusing to store an empty credential; use delete() to remove one.")
        redaction.register_secret(value)
        with self._lock:
            if self.backend == "memory":
                self._memory[ref] = value
            else:
                data = self._read_file(self._file)
                data[ref] = value
                self._write_file(self._file, data)

    def get(self, ref: str) -> str:
        """Return the secret for ``ref`` (environment override first), or '' if none."""
        env_value = os.environ.get(_ref_env_name(ref), "").strip()
        if env_value:
            redaction.register_secret(env_value)
            return env_value
        if ref.startswith("platform:"):
            key = ref.split(":", 1)[1]
            env_name = PLATFORM_SECRET_ENV.get(key)
            if env_name and os.environ.get(env_name, "").strip():
                value = os.environ[env_name].strip()
                redaction.register_secret(value)
                return value
        with self._lock:
            if self.backend == "memory":
                value = self._memory.get(ref, "")
            else:
                value = self._read_file(self._file).get(ref, "")
        if value:
            redaction.register_secret(value)
        return value

    def has(self, ref: str) -> bool:
        return bool(self.get(ref))

    def source_of(self, ref: str) -> str:
        """Where a credential would come from: 'environment', the backend name, or ''."""
        if os.environ.get(_ref_env_name(ref), "").strip():
            return "environment"
        if ref.startswith("platform:"):
            env_name = PLATFORM_SECRET_ENV.get(ref.split(":", 1)[1])
            if env_name and os.environ.get(env_name, "").strip():
                return "environment"
        with self._lock:
            if self.backend == "memory":
                return self.backend if ref in self._memory else ""
            return self.backend if ref in self._read_file(self._file) else ""

    def delete(self, ref: str) -> None:
        with self._lock:
            if self.backend == "memory":
                self._memory.pop(ref, None)
            else:
                data = self._read_file(self._file)
                if data.pop(ref, None) is not None:
                    self._write_file(self._file, data)

    def refs(self, prefix: str = "") -> list[str]:
        with self._lock:
            if self.backend == "memory":
                found: Iterable[str] = self._memory
            else:
                found = self._read_file(self._file)
            return sorted(r for r in found if r.startswith(prefix))

    # -- convenience -------------------------------------------------------------------
    def platform_secrets(self) -> dict[str, str]:
        """Secrets dict in the shape collectors expect (`x_bearer_token`, ...)."""
        return {key: self.get(f"platform:{key}") for key in PLATFORM_SECRET_ENV}


_default_store: CredentialStore | None = None
_default_lock = threading.Lock()


def default_store() -> CredentialStore:
    global _default_store
    with _default_lock:
        if _default_store is None:
            _default_store = CredentialStore()
        return _default_store


def set_default_store(store: CredentialStore | None) -> None:
    global _default_store
    with _default_lock:
        _default_store = store
