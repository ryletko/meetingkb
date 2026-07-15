import subprocess

import pytest

from meetingkb.ingest.thumbnails import generate, thumbs_dir, vtt_path


@pytest.mark.integration
def test_generate_produces_jpegs_and_vtt(tmp_path):
    video = tmp_path / "clip.mp4"
    subprocess.run(
        [
            "ffmpeg", "-hide_banner", "-loglevel", "error", "-y",
            "-f", "lavfi", "-i", "testsrc=duration=6:size=320x240:rate=10",
            str(video),
        ],
        check=True,
        capture_output=True,
    )

    out = generate(tmp_path, "m1", video, gpu=False)

    assert out == vtt_path(tmp_path, "m1")
    frames = sorted(thumbs_dir(tmp_path, "m1").glob("thumb-*.jpg"))
    assert frames
    vtt_text = vtt_path(tmp_path, "m1").read_text(encoding="utf-8")
    assert vtt_text.startswith("WEBVTT")
    assert vtt_text.strip() != "WEBVTT"
