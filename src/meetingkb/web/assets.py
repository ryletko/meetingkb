"""Locate and materialize packaged web assets (e.g. the video player page)."""
from __future__ import annotations

import shutil
from importlib.resources import files
from pathlib import Path


def ensure_player_asset(data_dir: Path) -> Path:
    """Copy the packaged ``player.html`` into ``<data_dir>/assets/`` (idempotent).

    The media server is rooted at ``data_dir`` and cannot serve a file that
    lives inside the installed package, so the player page is copied out to a
    location the server can reach. Returns the destination path.
    """
    dest = data_dir / "assets" / "player.html"
    dest.parent.mkdir(parents=True, exist_ok=True)
    # Anchor on the ``meetingkb.web`` package: this module (``assets.py``) shadows
    # the sibling ``assets/`` data directory, so ``files("meetingkb.web.assets")``
    # would resolve to this file's parent, not the data dir. Join from ``web``.
    src = files("meetingkb.web").joinpath("assets").joinpath("player.html")
    shutil.copyfile(str(src), dest)
    return dest
