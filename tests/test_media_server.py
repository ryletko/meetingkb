import requests

from meetingkb.web.media_server import start_media_server


def test_serves_file_with_range(tmp_path):
    # ``.mp4`` (a playable-media extension) rather than ``.txt``: the media
    # server only serves allowlisted extensions (see media_server.py /
    # test_media_server_allowlist.py), and this test is exercising Range
    # support, not the allowlist itself.
    (tmp_path / "a.mp4").write_bytes(b"0123456789")
    base = start_media_server(tmp_path, preferred_port=8650)
    r = requests.get(f"{base}/a.mp4", headers={"Range": "bytes=0-3"}, timeout=5)
    assert r.status_code == 206
    assert r.content == b"0123"
    assert r.headers["Content-Range"] == "bytes 0-3/10"
