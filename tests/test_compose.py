import shutil
import subprocess

import pytest


@pytest.mark.skipif(not shutil.which("docker"), reason="docker not installed")
def test_compose_config_is_valid():
    r = subprocess.run(
        ["docker", "compose", "-f", "deploy/docker-compose.yml", "config"],
        capture_output=True,
        text=True,
    )
    assert r.returncode == 0, r.stderr
    assert "meetingkb-opensearch" in r.stdout
