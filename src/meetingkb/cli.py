"""MeetingKB command-line interface."""
from __future__ import annotations

import typer

app = typer.Typer(help="MeetingKB — transcribe, index, search meeting recordings.")


@app.callback()
def main() -> None:
    """MeetingKB — transcribe, index, search meeting recordings."""


@app.command()
def version() -> None:
    """Print the installed version."""
    from meetingkb import __version__

    typer.echo(__version__)


if __name__ == "__main__":
    app()
