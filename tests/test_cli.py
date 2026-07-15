from typer.testing import CliRunner

from meetingkb.cli import app

runner = CliRunner()


def test_help_lists_commands():
    result = runner.invoke(app, ["--help"])
    assert result.exit_code == 0
    for cmd in ("transcribe", "index", "thumbnails", "serve", "up", "doctor"):
        assert cmd in result.output


def test_doctor_reports_checks():
    result = runner.invoke(app, ["doctor"])
    assert result.exit_code in (0, 1)
    assert "ffmpeg" in result.output.lower()
    assert "docker" in result.output.lower()
