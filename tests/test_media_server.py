import requests

from meetingkb.web.media_server import start_media_server


def test_serves_file_with_range(tmp_path):
    (tmp_path / "a.txt").write_bytes(b"0123456789")
    base = start_media_server(tmp_path)
    r = requests.get(f"{base}/a.txt", headers={"Range": "bytes=0-3"}, timeout=5)
    assert r.status_code == 206
    assert r.content == b"0123"
    assert r.headers["Content-Range"] == "bytes 0-3/10"
