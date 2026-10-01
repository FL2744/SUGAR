import hashlib

import pytest

from sugar_core import updater as u
from test_research_api import api   # noqa: F401  (fixture reuse)


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


def test_cli_update_and_doctor(monkeypatch, capsys, tmp_path):
    from sugar_core import cli
    monkeypatch.setenv("SUGAR_HOME", str(tmp_path))
    monkeypatch.setattr(u, "check", lambda channel, **kw: {"current": "1.7.0", "available": True, "latest": "1.8.0", "url": "https://github.com/x", "error": ""})
    assert cli.main(["update", "--channel", "preview"]) == 0
    assert "1.8.0 is available on the preview channel" in capsys.readouterr().out
    monkeypatch.setattr(u, "check", lambda channel, **kw: {"current": "1.7.0", "available": False, "error": "Could not check for updates: offline"})
    assert cli.main(["update"]) == 1
    assert cli.main(["doctor"]) == 0 and "SUGAR " in capsys.readouterr().out


def test_latest_channel_follows_commits_not_versions(tmp_path, monkeypatch):
    monkeypatch.setenv("SUGAR_HOME", str(tmp_path))
    mine, theirs = "a" * 40, "b" * 40
    monkeypatch.setattr(u, "_platform_key", lambda: "macos")
    release = {**rel("latest-main"), "prerelease": True, "body": f"Automatic build.\ncommit: {theirs}"}

    class H(Http):
        def get(self, url, **kw):
            self.calls.append(url)
            if url.endswith("/releases/tags/latest-main"):
                return Resp(release)
            if f"/compare/{mine}...{theirs}" in url:
                return Resp({"status": "ahead", "ahead_by": 3, "commits": [{"commit": {"message": "one"}}, {"commit": {"message": "two"}}, {"commit": {"message": "three"}}]})
            return Resp({}, status=404)

    monkeypatch.setattr(u, "current_commit", lambda: mine)
    info = u.check("latest", current="1.7.0", session=H([]), force=True)
    assert info["available"] and info["ahead"]["commits"] == 3 and info["ahead"]["headlines"][0] == "three" and info["asset"]
    monkeypatch.setattr(u, "current_commit", lambda: theirs)
    assert not u.check("latest", current="1.7.0", session=H([]), force=True)["available"]
    monkeypatch.setattr(u, "current_commit", lambda: "")
    unknown = u.check("latest", current="1.7.0", session=H([]), force=True)
    assert not unknown["available"] and "cannot tell" in unknown["note"]

    class NoBuild(H):
        def get(self, url, **kw):
            return Resp({}, status=404)
    assert "No automatic build" in u.check("latest", current="1.7.0", session=NoBuild([]), force=True)["note"]


def test_host_check_rejects_lookalikes():
    assert u._allowed("https://github.com/x") and u._allowed("https://objects.githubusercontent.com/x") and u._allowed("https://release-assets.githubusercontent.com/x")
    assert not u._allowed("https://evilgithubusercontent.com/x") and not u._allowed("https://github.com.evil.example/x") and not u._allowed("http://github.com/x")


class Redirecting(Http):
    def __init__(self, hops, body=b"hello"):
        super().__init__([], body=body)
        self.hops = hops

    def get(self, url, **kw):
        self.calls.append(url)
        assert kw.get("allow_redirects") is False or "SHA256SUMS" in url
        if url in self.hops:
            r = Resp(status=302, url=url)
            r.headers = {"location": self.hops[url]}
            r.close = lambda: None
            return r
        return super().get(url, **kw)


def info_for(tmp_path, monkeypatch, url="https://github.com/FL2744/SUGAR/releases/download/v1/SUGAR-macOS.zip"):
    monkeypatch.setenv("SUGAR_HOME", str(tmp_path))
    return {"asset": {"name": "SUGAR-macOS.zip", "size": 5, "url": url}, "sums_url": "https://github.com/FL2744/SUGAR/releases/download/v1/SHA256SUMS"}


def test_download_follows_checked_redirects_and_refuses_foreign_ones(tmp_path, monkeypatch):
    info = info_for(tmp_path, monkeypatch)
    ok = Redirecting({info["asset"]["url"]: "https://release-assets.githubusercontent.com/abc"})
    assert u.download(info, session=ok, dest=tmp_path)["state"] == "done"
    assert ok.calls[-1] == "https://release-assets.githubusercontent.com/abc"
    evil = Redirecting({info["asset"]["url"]: "https://evil.example/payload"})
    with pytest.raises(ValueError, match="redirected somewhere unexpected"):
        u.download(info, session=evil, dest=tmp_path)
    assert not any("evil.example" in c for c in evil.calls)         # never even requested
    assert u.status()["state"] == "error"
    loop = Redirecting({info["asset"]["url"]: info["asset"]["url"]})
    with pytest.raises(ValueError, match="too many times"):
        u.download(info, session=loop, dest=tmp_path)


def test_download_without_a_published_checksum_is_refused(tmp_path, monkeypatch):
    info = info_for(tmp_path, monkeypatch)
    info["sums_url"] = ""
    with pytest.raises(ValueError, match="does not publish a checksum"):
        u.download(info, session=Http([]), dest=tmp_path)
    assert not (tmp_path / "SUGAR-macOS.zip").exists() and not list(tmp_path.glob("*.part"))


def test_open_download_only_opens_files_in_the_downloads_folder(tmp_path, monkeypatch):
    monkeypatch.setenv("SUGAR_HOME", str(tmp_path))
    monkeypatch.setattr(u, "downloads_dir", lambda: tmp_path / "dl")
    (tmp_path / "dl").mkdir()
    outside = tmp_path / "other.msi"
    outside.write_bytes(b"x")
    with pytest.raises(ValueError, match="no downloaded update"):
        u.open_download(str(outside))
    with pytest.raises(ValueError):
        u.open_download(str(tmp_path / "dl" / "missing.msi"))


def test_unstamped_packaged_build_is_offered_the_latest_build(tmp_path, monkeypatch):
    import sys
    monkeypatch.setenv("SUGAR_HOME", str(tmp_path))
    monkeypatch.setattr(u, "_platform_key", lambda: "macos")
    monkeypatch.setattr(u, "current_commit", lambda: "")
    release = {**rel("latest-main"), "prerelease": True, "body": "commit: " + "c" * 40}

    class H(Http):
        def get(self, url, **kw):
            return Resp(release)
    assert not u.check("latest", current="1.7.0", session=H([]), force=True)["available"]          # a dev checkout stays quiet
    monkeypatch.setattr(sys, "frozen", True, raising=False)
    info = u.check("latest", current="1.7.0", session=H([]), force=True)
    assert info["available"] and "predates automatic updates" in info["note"]


def test_repository_not_found_is_explained(tmp_path, monkeypatch):
    monkeypatch.setenv("SUGAR_HOME", str(tmp_path))

    class Missing:
        def get(self, url, **kw):
            return Resp({}, status=404)
    assert "could not be found" in u.check("stable", current="1.7.0", session=Missing(), force=True)["error"]


def test_update_routes_are_admin_only_and_local_only(api, monkeypatch, tmp_path):   # noqa: F811
    base, session, _wb = api
    monkeypatch.setenv("SUGAR_HOME", str(tmp_path / "h"))
    calls = []
    info = {"current": "1.7.0", "channel": "latest", "available": True, "error": "", "latest": "abc1234", "asset": {"name": "SUGAR-macOS.zip", "size": 5, "url": "https://github.com/x/SUGAR-macOS.zip"}, "sums_url": ""}
    monkeypatch.setattr(u, "check", lambda channel, **kw: calls.append(channel) or info)
    monkeypatch.setattr(u, "start_download", lambda i: {"state": "downloading", "name": i["asset"]["name"]})
    assert session.get(f"{base}/api/update/check?channel=stable").json()["latest"] == "abc1234" and calls == ["stable"]
    session.get(f"{base}/api/update/check")
    assert calls[-1] == "latest"                                                    # the default channel
    assert session.get(f"{base}/api/update/status").status_code == 200
    import requests
    anonymous = requests.get(f"{base}/api/update/check")
    assert anonymous.status_code in {401, 403}
    # downloading is only for the local desktop app (the server exposes paths only then)
    import sugar_api
    monkeypatch.setattr(sugar_api.SugarApiHandler, "expose_paths", False)
    blocked = session.post(f"{base}/api/update/download", json={"channel": "latest"})
    assert blocked.status_code == 403 and "desktop app" in blocked.json()["error"]
    monkeypatch.setattr(sugar_api.SugarApiHandler, "expose_paths", True)
    started = session.post(f"{base}/api/update/download", json={})
    assert started.status_code == 202 and started.json()["state"] == "downloading"
    info["available"] = False
    assert session.post(f"{base}/api/update/download", json={}).status_code == 409
    assert session.post(f"{base}/api/update/open", json={}).status_code == 409           # nothing downloaded
