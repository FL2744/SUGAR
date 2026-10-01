"""Update checks against this project's GitHub Releases, with a verified download and an install hand-off.

Channels
* ``latest``: every change that lands on ``main`` and passes the tests. A rolling build is published automatically for each one
  (tag ``latest-main``), so nobody has to cut a release. Whether it is newer is decided by commit, not version number.
* ``stable``: the newest published release that is not marked pre-release (what classmates should run).
* ``preview``: the newest release including pre-releases (tags such as ``v1.8.0-rc.1``).
* ``lts``: the newest release whose tag carries ``-lts`` (a long-term line that only gets fixes).

A check reads release metadata only. A download is streamed from GitHub's release hosts over https, compared with the
release's ``SHA256SUMS`` file when it has one, and saved to the user's Downloads folder; nothing is installed until the
person opens it. Windows opens the installer (an in-place upgrade); on a Mac the zip is revealed so the app can be replaced.
Results are cached so launching the app never hits GitHub's rate limit, and every failure is reported, never raised into the app.
"""
from __future__ import annotations

import hashlib
import json
import os
import platform
import re
import subprocess
import sys
import threading
import time
from pathlib import Path
from typing import Any
from urllib.parse import urlparse

import requests

from . import __version__
from .credential_store import sugar_home

REPO = "FL2744/SUGAR"
API = f"https://api.github.com/repos/{REPO}"
CHANNELS = ("latest", "stable", "preview", "lts")
ROLLING_TAG = "latest-main"
CACHE_SECONDS = 6 * 3600
_HOSTS = ("github.com", "githubusercontent.com")      # exact host or any subdomain of these
MAX_REDIRECTS = 5
_TAG = re.compile(r"^v?(\d+)\.(\d+)\.(\d+)(?:[-.](.+))?$")
_LOCK = threading.Lock()
_JOB: dict[str, Any] = {"state": "idle"}


def parse_version(tag: str) -> tuple[int, int, int, int, tuple[int, ...]] | None:
    """Sortable form of a tag. A plain release outranks its own pre-releases (1.8.0 > 1.8.0-rc.2)."""
    match = _TAG.match(tag.strip())
    if not match:
        return None
    major, minor, patch, suffix = int(match.group(1)), int(match.group(2)), int(match.group(3)), match.group(4)
    nums = tuple(int(n) for n in re.findall(r"\d+", suffix or ""))
    plain = 1 if not suffix or suffix.startswith("lts") or suffix.startswith("classroom") else 0
    return major, minor, patch, plain, nums


def is_newer(candidate: str, current: str) -> bool:
    a, b = parse_version(candidate), parse_version(current)
    return bool(a and b and a > b)


def current_commit() -> str:
    """The commit this installation was built from: stamped at build time, or read from git when running from a checkout."""
    try:
        from ._build_info import BUILD  # type: ignore[import-not-found]
        return str(BUILD.get("commit", ""))
    except ImportError:
        pass
    try:
        return subprocess.run(["git", "rev-parse", "HEAD"], cwd=Path(__file__).resolve().parents[1], capture_output=True, text=True, timeout=5, check=True).stdout.strip()
    except (OSError, subprocess.SubprocessError):
        return ""


def _release_commit(release: dict[str, Any]) -> str:
    match = re.search(r"commit:\s*([0-9a-f]{7,40})", str(release.get("body") or ""), re.I)
    return match.group(1).lower() if match else ""


def _platform_key() -> str:
    system = platform.system().lower()
    return "windows" if system == "windows" else "macos" if system == "darwin" else "other"


def pick_asset(assets: list[dict[str, Any]], system: str | None = None) -> dict[str, Any] | None:
    system = system or _platform_key()
    names = {a.get("name", ""): a for a in assets}
    if system == "windows":
        for name, asset in names.items():
            if name.lower().endswith(".msi") or (name.lower().endswith(".zip") and "windows" in name.lower()):
                return asset
    if system == "macos":
        for name, asset in names.items():
            if name.lower().endswith(".zip") and "macos" in name.lower():
                return asset
    return next((a for n, a in names.items() if n.endswith(".whl")), None)


def choose_release(releases: list[dict[str, Any]], channel: str) -> dict[str, Any] | None:
    best: tuple[Any, dict[str, Any]] | None = None
    for release in releases:
        if release.get("draft"):
            continue
        tag = str(release.get("tag_name", ""))
        key = parse_version(tag)
        if key is None:
            continue
        if channel == "stable" and (release.get("prerelease") or "-lts" in tag):
            continue
        if channel == "lts" and "-lts" not in tag:
            continue
        if best is None or key > best[0]:
            best = (key, release)
    return best[1] if best else None


def _cache_path() -> Path:
    return sugar_home() / "update-cache.json"


def _read_cache() -> dict[str, Any]:
    try:
        return json.loads(_cache_path().read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {}


def _write_cache(data: dict[str, Any]) -> None:
    try:
        _cache_path().parent.mkdir(parents=True, exist_ok=True)
        _cache_path().write_text(json.dumps(data), encoding="utf-8")
    except OSError:
        pass


def _headers() -> dict[str, str]:
    return {"Accept": "application/vnd.github+json", "User-Agent": f"SUGAR/{__version__} update-check"}


def check(channel: str = "stable", *, current: str = __version__, session: requests.Session | None = None, force: bool = False, now: float | None = None) -> dict[str, Any]:
    """Is a newer release available on this channel? Never raises; ``error`` explains a failed check."""
    channel = channel if channel in CHANNELS else "latest"
    clock = now if now is not None else time.time()
    result: dict[str, Any] = {"current": current, "channel": channel, "available": False, "checked_at": clock, "error": "", "platform": _platform_key()}
    cache = _read_cache()
    cached = cache.get(channel) if isinstance(cache.get(channel), dict) else None
    if cached and not force and clock - float(cached.get("checked_at", 0)) < CACHE_SECONDS and cached.get("current") == current and cached.get("build", "") == (current_commit()[:7] if channel == "latest" else ""):
        return cached
    try:
        http = session or requests.Session()
        if channel == "latest":
            return _check_latest(http, result, cache, clock)
        response = http.get(f"{API}/releases", params={"per_page": 20}, headers=_headers(), timeout=12)
        if response.status_code == 403 and "rate limit" in response.text.lower():
            raise RuntimeError("GitHub is limiting requests from this network right now. Try again in a while.")
        if response.status_code == 404:
            raise RuntimeError("The release list could not be found. Check that the repository is public and the network allows github.com.")
        response.raise_for_status()
        release = choose_release(response.json(), channel)
        if release is None:
            result["note"] = f"No {channel} release has been published yet."
        else:
            tag = str(release["tag_name"])
            asset = pick_asset(release.get("assets") or [])
            result.update({
                "latest": tag.lstrip("v"), "tag": tag, "name": release.get("name") or tag, "published_at": release.get("published_at", ""), "url": release.get("html_url", ""),
                "notes": str(release.get("body") or "")[:4000], "prerelease": bool(release.get("prerelease")),
                "asset": {"name": asset["name"], "size": asset.get("size", 0), "url": asset.get("browser_download_url", "")} if asset else None,
                "sums_url": next((a.get("browser_download_url", "") for a in release.get("assets") or [] if a.get("name") == "SHA256SUMS"), ""),
                "available": is_newer(tag, current),
            })
            result["ahead"] = _ahead(http, tag)
        if not result["available"]:
            result.setdefault("note", "You are up to date.")
    except (requests.RequestException, RuntimeError, ValueError, KeyError) as exc:
        result["error"] = f"Could not check for updates: {exc}"
        return result
    cache[channel] = result
    _write_cache(cache)
    return result


def _check_latest(http: requests.Session, result: dict[str, Any], cache: dict[str, Any], clock: float) -> dict[str, Any]:
    """Compare this build's commit with the newest rolling build. Newer means main has moved on from the commit we were built from."""
    response = http.get(f"{API}/releases/tags/{ROLLING_TAG}", headers=_headers(), timeout=12)
    if response.status_code == 404:
        result["note"] = "No automatic build has been published yet."
    else:
        if response.status_code == 403 and "rate limit" in response.text.lower():
            raise RuntimeError("GitHub is limiting requests from this network right now. Try again in a while.")
        response.raise_for_status()
        release = response.json()
        latest, mine = _release_commit(release), current_commit()
        asset = pick_asset(release.get("assets") or [])
        moved: dict[str, Any] = {"commits": 0, "headlines": []}
        if latest and mine and latest != mine and not (latest.startswith(mine) or mine.startswith(latest)):
            moved = _compare(http, mine, latest)
        migrating = bool(latest and not mine and getattr(sys, "frozen", False))    # a packaged build made before builds were stamped
        available = bool(latest and mine and moved["commits"] > 0) or migrating
        result.update({
            "latest": latest[:7], "tag": ROLLING_TAG, "name": f"Latest build ({latest[:7]})", "published_at": release.get("published_at", ""), "url": release.get("html_url", ""),
            "prerelease": True, "notes": "", "asset": {"name": asset["name"], "size": asset.get("size", 0), "url": asset.get("browser_download_url", "")} if asset else None,
            "sums_url": next((a.get("browser_download_url", "") for a in release.get("assets") or [] if a.get("name") == "SHA256SUMS"), ""),
            "available": available, "ahead": moved, "build": mine[:7],
        })
        if not mine and not migrating:
            result["note"] = "This copy of SUGAR does not know which commit it was built from, so it cannot tell whether a newer build exists."
        elif migrating:
            result["note"] = "This build predates automatic updates. Installing the latest build enables them."
        elif not available:
            result["note"] = "You have the newest build."
    cache[result["channel"]] = result
    _write_cache(cache)
    return result


def _compare(http: requests.Session, base: str, head: str) -> dict[str, Any]:
    try:
        response = http.get(f"{API}/compare/{base}...{head}", headers=_headers(), timeout=12)
        response.raise_for_status()
        data = response.json()
        commits = data.get("commits") or []
        ahead = int(data.get("ahead_by", len(commits))) if data.get("status") in {"ahead", "diverged"} else 0
        return {"commits": ahead, "headlines": [str(c.get("commit", {}).get("message", "")).split("\n")[0][:140] for c in commits[-10:]][::-1]}
    except (requests.RequestException, ValueError):
        return {"commits": 0, "headlines": []}


def _ahead(http: requests.Session, tag: str) -> dict[str, Any]:
    """How far main has moved since a release, as a plain list of commit headlines (for people who want the detail)."""
    try:
        response = http.get(f"{API}/compare/{tag}...main", headers=_headers(), timeout=12)
        response.raise_for_status()
        data = response.json()
        commits = data.get("commits") or []
        return {"commits": int(data.get("ahead_by", len(commits))), "headlines": [str(c.get("commit", {}).get("message", "")).split("\n")[0][:140] for c in commits[-10:]][::-1]}
    except (requests.RequestException, ValueError):
        return {"commits": 0, "headlines": []}


# ------------------------------------------------------------------------------------------------ download
def _allowed(url: str) -> bool:
    parts = urlparse(url)
    host = (parts.hostname or "").lower()
    return parts.scheme == "https" and any(host == h or host.endswith("." + h) for h in _HOSTS)


def _open_checked(http: requests.Session, url: str):
    """GET ``url`` following redirects by hand, so every hop is checked against the allowed hosts before anything is read."""
    for _ in range(MAX_REDIRECTS + 1):
        if not _allowed(url):
            raise ValueError("The download was redirected somewhere unexpected.")
        response = http.get(url, headers=_headers(), stream=True, timeout=30, allow_redirects=False)
        if response.status_code in {301, 302, 303, 307, 308}:
            location = response.headers.get("location", "")
            response.close()
            url = requests.compat.urljoin(url, location)
            continue
        response.raise_for_status()
        return response
    raise ValueError("The download was redirected too many times.")


def downloads_dir() -> Path:
    for candidate in (Path.home() / "Downloads", sugar_home() / "downloads"):
        try:
            candidate.mkdir(parents=True, exist_ok=True)
            return candidate
        except OSError:
            continue
    return Path.cwd()


def _expected_hash(http: requests.Session, sums_url: str, name: str) -> str:
    if not sums_url or not _allowed(sums_url):
        return ""
    try:
        text = http.get(sums_url, headers=_headers(), timeout=15).text
    except requests.RequestException:
        return ""
    for line in text.splitlines():
        parts = line.split()
        if len(parts) >= 2 and parts[-1].lstrip("*") == name:
            return parts[0].lower()
    return ""


def status() -> dict[str, Any]:
    with _LOCK:
        return dict(_JOB)


def _set(**values: Any) -> None:
    with _LOCK:
        _JOB.update(values)


def download(info: dict[str, Any], *, session: requests.Session | None = None, dest: Path | None = None) -> dict[str, Any]:
    """Download and verify the release asset named in ``info`` (a result of ``check``). Blocking; ``status()`` reports progress."""
    asset = info.get("asset") or {}
    url, name = str(asset.get("url", "")), os.path.basename(str(asset.get("name", "")))
    if not url or not name or not _allowed(url):
        raise ValueError("This release has no download for your system.")
    http = session or requests.Session()
    target_dir = dest or downloads_dir()
    target = target_dir / name
    partial = target.with_suffix(target.suffix + ".part")
    _set(state="downloading", name=name, received=0, total=int(asset.get("size") or 0), error="", path="")
    digest = hashlib.sha256()
    expected = ""
    try:
        expected = _expected_hash(http, str(info.get("sums_url", "")), name)
        if not expected:
            raise ValueError("This release does not publish a checksum for its download, so SUGAR will not install it automatically. Open the release page to download it yourself.")
        with _open_checked(http, url) as response:
            total = int(response.headers.get("content-length") or asset.get("size") or 0)
            received = 0
            with partial.open("wb") as stream:
                for chunk in response.iter_content(1 << 16):
                    stream.write(chunk)
                    digest.update(chunk)
                    received += len(chunk)
                    _set(received=received, total=total)
        if expected != digest.hexdigest():
            partial.unlink(missing_ok=True)
            raise ValueError("The downloaded file did not match its published checksum, so it was discarded.")
        os.replace(partial, target)
    except (requests.RequestException, OSError, ValueError) as exc:
        partial.unlink(missing_ok=True)
        _set(state="error", error=str(exc) or exc.__class__.__name__)
        raise
    _set(state="done", path=str(target), verified=bool(expected), sha256=digest.hexdigest())
    return status()


def start_download(info: dict[str, Any]) -> dict[str, Any]:
    if status().get("state") == "downloading":
        return status()
    _set(state="downloading", name=str((info.get("asset") or {}).get("name", "")), received=0, total=0, error="", path="")

    def run() -> None:
        try:
            download(info)
        except Exception:      # noqa: BLE001  (recorded in status for the UI)
            pass

    threading.Thread(target=run, name="sugar-update-download", daemon=True).start()
    return status()


def open_download(path: str | None = None) -> dict[str, Any]:
    """Hand the verified download to the operating system: run the installer on Windows, reveal the zip on a Mac."""
    target = Path(path or status().get("path", ""))
    root = downloads_dir().resolve()
    if not target.is_file() or root not in target.resolve().parents:
        raise ValueError("There is no downloaded update to open.")
    if sys.platform.startswith("win"):
        os.startfile(str(target))  # type: ignore[attr-defined]  # noqa: S606
        return {"opened": str(target), "how": "The installer is open. Follow it to finish; SUGAR will close if it needs to."}
    if sys.platform == "darwin":
        subprocess.Popen(["open", "-R", str(target)])  # noqa: S603,S607
        return {"opened": str(target), "how": "Unzip it, then drag SUGAR into Applications and choose Replace."}
    return {"opened": str(target), "how": f"Saved to {target}."}
