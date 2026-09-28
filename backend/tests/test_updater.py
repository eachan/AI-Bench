"""Tests for the self-update logic (pure functions + check flow)."""

from aibench import updater


def test_compare_versions():
    assert updater.compare_versions("1.0.0", "1.0.1") < 0
    assert updater.compare_versions("1.2.0", "1.1.9") > 0
    assert updater.compare_versions("v2.0.0", "2.0.0") == 0
    assert updater.compare_versions("1.0", "1.0.0") == 0
    assert updater.compare_versions("1.0.0", "1.0.0-beta") == 0  # tolerant of suffixes


def test_parse_release_picks_assets():
    rel = updater.parse_release(
        {
            "tag_name": "v2.3.0",
            "name": "AI-Bench 2.3.0",
            "body": "- Faster benchmarks",
            "html_url": "https://github.com/eachan/AI-Bench/releases/tag/v2.3.0",
            "published_at": "2026-10-01T00:00:00Z",
            "assets": [
                {"name": "AI-Bench-Setup.exe", "browser_download_url": "https://x/setup.exe", "size": 123},
                {"name": "AI-Bench-2.3.0-windows-x64.zip", "browser_download_url": "https://x/dist.zip", "size": 456},
            ],
        }
    )
    assert rel["version"] == "2.3.0"
    assert rel["installer_url"] == "https://x/setup.exe"
    assert rel["installer_size"] == 123
    assert rel["zip_url"] == "https://x/dist.zip"


def test_build_windows_installer_cmd():
    cmd = updater.build_windows_installer_cmd(r"C:\Temp\AI-Bench-Setup.exe")
    assert cmd[0].endswith("AI-Bench-Setup.exe")
    for flag in ("/SILENT", "/CLOSEAPPLICATIONS", "/RESTARTAPPLICATIONS"):
        assert flag in cmd


def test_bundled_components_lists_app_and_frameworks():
    comps = {c["name"]: c["version"] for c in updater.bundled_components()}
    assert "AI-Bench" in comps
    assert "fastapi" in comps and "numpy" in comps
    assert any("llama.cpp" in n for n in comps)


class _FakeResp:
    def __init__(self, status_code, payload=None):
        self.status_code = status_code
        self._payload = payload or {}

    def raise_for_status(self):
        if self.status_code >= 400:
            raise RuntimeError(f"HTTP {self.status_code}")

    def json(self):
        return self._payload


def _release(tag):
    return {
        "tag_name": tag,
        "body": "notes",
        "html_url": "https://x",
        "assets": [{"name": "AI-Bench-Setup.exe", "browser_download_url": "https://x/s.exe", "size": 1}],
    }


def test_check_update_available(monkeypatch):
    monkeypatch.setattr(updater, "current_version", lambda: "1.0.0")
    monkeypatch.setattr(updater.httpx, "get", lambda *a, **k: _FakeResp(200, _release("v2.0.0")))
    res = updater.check_for_update()
    assert res["update_available"] is True
    assert res["latest_version"] == "2.0.0"
    assert res["status"] == "update_available"
    assert res["release"]["installer_url"] == "https://x/s.exe"


def test_check_up_to_date(monkeypatch):
    monkeypatch.setattr(updater, "current_version", lambda: "2.0.0")
    monkeypatch.setattr(updater.httpx, "get", lambda *a, **k: _FakeResp(200, _release("v2.0.0")))
    res = updater.check_for_update()
    assert res["update_available"] is False
    assert res["status"] == "up_to_date"


def test_check_no_releases(monkeypatch):
    monkeypatch.setattr(updater.httpx, "get", lambda *a, **k: _FakeResp(404))
    res = updater.check_for_update()
    assert res["status"] == "no_releases"
    assert res["update_available"] is False


def test_check_network_error(monkeypatch):
    def boom(*a, **k):
        raise RuntimeError("dns fail")

    monkeypatch.setattr(updater.httpx, "get", boom)
    res = updater.check_for_update()
    assert res["status"] == "error"
    assert "dns fail" in res["message"]
