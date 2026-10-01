import hashlib

import pytest

from sugar_core import updater as u


def rel(tag, *, pre=False, draft=False, assets=None):
    return {"tag_name": tag, "name": f"SUGAR {tag}", "prerelease": pre, "draft": draft, "body": "notes", "html_url": f"https://github.com/x/{tag}", "published_at": "2026-10-01T00:00:00Z",
            "assets": assets if assets is not None else [{"name": "SUGAR_1.8.0_x64.msi", "size": 5, "browser_download_url": "https://github.com/FL2744/SUGAR/releases/download/v1.8.0/SUGAR_1.8.0_x64.msi"},
                                                         {"name": "SUGAR-macOS.zip", "size": 5, "browser_download_url": "https://github.com/FL2744/SUGAR/releases/download/v1.8.0/SUGAR-macOS.zip"},
                                                         {"name": "SHA256SUMS", "size": 1, "browser_download_url": "https://github.com/FL2744/SUGAR/releases/download/v1.8.0/SHA256SUMS"}]}


RELEASES = [rel("v1.8.0-rc.1", pre=True), rel("v1.7.0"), rel("v1.9.0", draft=True), rel("v1.6.5-lts.2"), rel("v1.2.6-classroom.1")]


def test_version_order_puts_final_above_its_prereleases():
    assert u.is_newer("v1.8.0", "1.8.0-rc.2") and not u.is_newer("v1.8.0-rc.2", "1.8.0")
    assert u.is_newer("v1.7.1", "1.7.0") and not u.is_newer("v1.2.6-classroom.1", "1.7.0")


def test_channels_pick_the_right_release():
    assert u.choose_release(RELEASES, "stable")["tag_name"] == "v1.7.0"
    assert u.choose_release(RELEASES, "preview")["tag_name"] == "v1.8.0-rc.1"
    assert u.choose_release(RELEASES, "lts")["tag_name"] == "v1.6.5-lts.2"


def test_asset_is_chosen_per_platform():
    assets = RELEASES[0]["assets"]
    assert u.pick_asset(assets, "windows")["name"].endswith(".msi") and u.pick_asset(assets, "macos")["name"] == "SUGAR-macOS.zip"


class Resp:
    def __init__(self, data=None, body=b"", status=200, url="https://github.com/x"):
        self._data, self.body, self.status_code, self.url, self.text, self.headers = data, body, status, url, "", {"content-length": str(len(body))}

    def json(self):
        return self._data

    def raise_for_status(self):
        pass

    def iter_content(self, n):
        yield self.body

    def __enter__(self):
        return self

    def __exit__(self, *a):
        return False


class Http:
    def __init__(self, releases, body=b"hello", sums_of=b"hello"):
        self.releases, self.body, self.sums_of, self.calls = releases, body, sums_of, []

    def get(self, url, **kw):
        self.calls.append(url)
        if url.endswith("/releases"):
            return Resp(self.releases)
        if "/compare/" in url:
            return Resp({"ahead_by": 2, "commits": [{"commit": {"message": "one\nbody"}}, {"commit": {"message": "two"}}]})
        if url.endswith("SHA256SUMS"):
            r = Resp(); r.text = f"{hashlib.sha256(self.sums_of).hexdigest()}  SUGAR-macOS.zip\n{hashlib.sha256(self.sums_of).hexdigest()}  SUGAR_1.8.0_x64.msi\n"; return r
        return Resp(body=self.body, url=url)


def test_check_reports_update_caches_and_survives_failure(tmp_path, monkeypatch):
    monkeypatch.setenv("SUGAR_HOME", str(tmp_path))
    http = Http([rel("v1.8.0"), rel("v1.7.0")])
    info = u.check("stable", current="1.7.0", session=http)
    assert info["available"] and info["latest"] == "1.8.0" and info["ahead"]["commits"] == 2 and info["ahead"]["headlines"][0] == "two"
    n = len(http.calls)
    u.check("stable", current="1.7.0", session=http)
    assert len(http.calls) == n                               # served from the cache
    assert not u.check("stable", current="1.8.0", session=http, force=True)["available"]

    class Down:
        def get(self, *a, **k):
            import requests
            raise requests.ConnectionError("offline")
    assert "Could not check" in u.check("preview", current="1.7.0", session=Down())["error"]


def test_download_verifies_checksum_and_rejects_foreign_hosts(tmp_path, monkeypatch):
    monkeypatch.setenv("SUGAR_HOME", str(tmp_path))
    info = u.check("stable", current="1.7.0", session=Http([rel("v1.8.0")]), force=True)
    info["asset"] = u.pick_asset(rel("v1.8.0")["assets"], "macos") and {"name": "SUGAR-macOS.zip", "size": 5, "url": "https://github.com/FL2744/SUGAR/releases/download/v1.8.0/SUGAR-macOS.zip"}
    done = u.download(info, session=Http([], body=b"hello"), dest=tmp_path)
    assert done["state"] == "done" and done["verified"] and (tmp_path / "SUGAR-macOS.zip").read_bytes() == b"hello"
    with pytest.raises(ValueError, match="checksum"):
        u.download(info, session=Http([], body=b"tampered"), dest=tmp_path)
    assert not list(tmp_path.glob("*.part"))
    with pytest.raises(ValueError):
        u.download({**info, "asset": {"name": "x.zip", "url": "https://evil.example/x.zip"}}, session=Http([]), dest=tmp_path)
