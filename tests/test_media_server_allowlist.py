"""The media server root (data_dir) also holds knowledge.sqlite and raw
transcript files -- neither should be reachable over HTTP. Only assets/,
thumbs/, and playable media should be served.

All assertions share a single server (module-scoped fixture) started on a
port far from other media-server tests' default range: on Windows,
``HTTPServer``'s ``allow_reuse_address`` lets a second ``start_media_server``
call appear to bind successfully to a port an earlier (still-running, never
stopped) test server already holds -- silently misrouting requests instead
of raising. Each test module picking its own port band sidesteps that.
"""
import requests

from meetingkb.web.media_server import start_media_server

PORT = 8700


def _make_tree(tmp_path):
    (tmp_path / "knowledge.sqlite").write_bytes(b"sqlite-bytes")
    (tmp_path / "transcripts").mkdir()
    (tmp_path / "transcripts" / "x.json").write_text('{"segments": []}', encoding="utf-8")
    (tmp_path / "assets").mkdir()
    (tmp_path / "assets" / "player.html").write_text("<html>player</html>", encoding="utf-8")
    (tmp_path / "thumbs" / "m1").mkdir(parents=True)
    (tmp_path / "thumbs" / "m1" / "storyboard.vtt").write_text("WEBVTT", encoding="utf-8")
    (tmp_path / "clip.mp4").write_bytes(b"0123456789")
    return tmp_path


def test_media_server_allowlist(tmp_path):
    _make_tree(tmp_path)
    base = start_media_server(tmp_path, preferred_port=PORT)

    # Private files: blocked.
    r = requests.get(f"{base}/knowledge.sqlite", timeout=5)
    assert r.status_code == 403

    r = requests.get(f"{base}/transcripts/x.json", timeout=5)
    assert r.status_code == 403

    # Allowlisted paths: served.
    r = requests.get(f"{base}/assets/player.html", timeout=5)
    assert r.status_code == 200

    r = requests.get(f"{base}/thumbs/m1/storyboard.vtt", timeout=5)
    assert r.status_code == 200

    r = requests.get(f"{base}/clip.mp4", timeout=5)
    assert r.status_code == 200

    # Range support still works for allowlisted media.
    r = requests.get(f"{base}/clip.mp4", headers={"Range": "bytes=0-3"}, timeout=5)
    assert r.status_code == 206
    assert r.content == b"0123"
