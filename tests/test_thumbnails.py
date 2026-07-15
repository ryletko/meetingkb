from meetingkb.ingest.thumbnails import has_thumbnails, thumbs_dir, vtt_path


def test_paths(tmp_path):
    assert thumbs_dir(tmp_path, "m1") == tmp_path / "thumbs" / "m1"
    assert vtt_path(tmp_path, "m1") == tmp_path / "thumbs" / "m1" / "storyboard.vtt"


def test_has_thumbnails_false_then_true(tmp_path):
    assert has_thumbnails(tmp_path, "m1") is False
    p = vtt_path(tmp_path, "m1")
    p.parent.mkdir(parents=True)
    p.write_text("WEBVTT\n", encoding="utf-8")
    assert has_thumbnails(tmp_path, "m1") is True
