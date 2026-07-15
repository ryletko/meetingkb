"""MeetingKB command-line interface.

Cross-platform replacement for the old ``.bat``/``.ps1`` scripts: every
subcommand wraps the already-built service layer (``ingest.transcriber``,
``ingest.indexer``, ``ingest.gen_thumbnails``, ``web.media_server``) so the
CLI stays a thin dispatcher.
"""
from __future__ import annotations

import importlib.resources
import importlib.util
import json
import shutil
import subprocess
import sys
from pathlib import Path

import typer

from meetingkb.config import get_settings
from meetingkb.ingest.gen_thumbnails import generate_all
from meetingkb.ingest.indexer import build_index
from meetingkb.ingest.transcriber import FasterWhisperTranscriber, transcribe_dir
from meetingkb.search.opensearch_backend import OpenSearchClient

app = typer.Typer(help="MeetingKB — transcribe, index, search meeting recordings.")


@app.callback()
def main() -> None:
    """MeetingKB — transcribe, index, search meeting recordings."""
    # Also guards against Typer collapsing to a single command: with this
    # callback present, `kb <subcommand>` keeps working even if the app ever
    # has only one @app.command() registered.


@app.command()
def version() -> None:
    """Print the installed version."""
    from meetingkb import __version__

    typer.echo(__version__)


@app.command()
def index(
    no_opensearch: bool = typer.Option(
        False, "--no-opensearch", help="Skip OpenSearch indexing; SQLite only."
    ),
) -> None:
    """Build the SQLite (and, by default, OpenSearch) meeting index."""
    result = build_index(get_settings(), use_opensearch=not no_opensearch)
    typer.echo(json.dumps(result))


@app.command()
def transcribe(
    input: Path | None = typer.Argument(  # noqa: B008 - Typer idiom; evaluated once, fine here
        None, help="Directory of media files to transcribe (default: settings.data_dir)."
    ),
) -> None:
    """Transcribe media files that don't have a transcript yet."""
    settings = get_settings()
    input_dir = input if input is not None else settings.data_dir
    transcriber = FasterWhisperTranscriber(settings)
    produced = transcribe_dir(settings, transcriber, input_dir)
    typer.echo(f"produced {len(produced)} transcript(s)")


@app.command()
def thumbnails() -> None:
    """Generate seek-bar hover-preview thumbnails for meetings missing them."""
    n = generate_all(get_settings())
    typer.echo(f"generated {n}")


def _web_app_path() -> Path:
    """Resolve the packaged Streamlit entrypoint (``meetingkb/web/app.py``)."""
    return Path(str(importlib.resources.files("meetingkb.web").joinpath("app.py")))


@app.command()
def serve(
    port: int | None = typer.Option(
        None, "--port", help="Port for the Streamlit UI (default: settings.ui_port)."
    ),
) -> None:
    """Launch the Streamlit UI."""
    settings = get_settings()
    resolved_port = port if port is not None else settings.ui_port
    app_path = _web_app_path()
    subprocess.run(
        [
            sys.executable,
            "-m",
            "streamlit",
            "run",
            str(app_path),
            "--server.port",
            str(resolved_port),
            "--server.address",
            "127.0.0.1",
        ],
        check=True,
    )


@app.command()
def up() -> None:
    """Start OpenSearch (Docker Compose), index, generate thumbnails, then serve.

    Mirrors the old ``start_kb.bat`` end-to-end bootstrap, cross-platform.
    """
    settings = get_settings()
    subprocess.run(
        ["docker", "compose", "-f", "deploy/docker-compose.yml", "up", "-d"],
        check=True,
    )

    client = OpenSearchClient(settings.opensearch_url)
    if not client.wait_available():
        typer.echo("OpenSearch did not become available in time.", err=True)
        raise typer.Exit(1)

    typer.echo(json.dumps(build_index(settings)))
    typer.echo(f"generated {generate_all(settings)}")
    serve(port=settings.ui_port)


@app.command()
def doctor() -> None:
    """Check the local environment for required and optional tooling."""
    ffmpeg_path = shutil.which("ffmpeg")
    docker_path = shutil.which("docker")
    python_ok = sys.version_info >= (3, 11)
    faster_whisper_ok = importlib.util.find_spec("faster_whisper") is not None

    gpu_ok = False
    if ffmpeg_path:
        try:
            result = subprocess.run(
                [ffmpeg_path, "-hide_banner", "-hwaccels"],
                capture_output=True,
                text=True,
                timeout=5,
            )
            gpu_ok = "cuda" in result.stdout.lower()
        except (OSError, subprocess.SubprocessError):
            gpu_ok = False

    def marker(ok: bool) -> str:
        return "OK" if ok else "missing"

    typer.echo(f"ffmpeg        : {marker(bool(ffmpeg_path))} ({ffmpeg_path or 'not found'})")
    typer.echo(f"docker        : {marker(bool(docker_path))} ({docker_path or 'not found'})")
    typer.echo(f"python >= 3.11: {marker(python_ok)} ({sys.version.split()[0]})")
    typer.echo(f"faster-whisper: {marker(faster_whisper_ok)}")
    typer.echo(f"GPU (CUDA)    : {marker(gpu_ok)}")

    if not ffmpeg_path or not docker_path:
        raise typer.Exit(1)


if __name__ == "__main__":
    app()
