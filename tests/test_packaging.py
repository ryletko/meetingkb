import subprocess
import sys

import meetingkb


def test_version_string():
    assert isinstance(meetingkb.__version__, str)
    assert meetingkb.__version__.count(".") >= 2


def test_cli_version_command():
    out = subprocess.run(
        [sys.executable, "-m", "meetingkb.cli", "version"],
        capture_output=True, text=True, check=True,
    )
    assert meetingkb.__version__ in out.stdout
