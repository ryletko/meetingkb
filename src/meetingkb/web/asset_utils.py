"""Locate and materialize packaged web assets (e.g. the video player page)."""
from __future__ import annotations

import shutil
from importlib.resources import files
from pathlib import Path

_ASSET_FILENAMES = ("player.html", "plyr.css", "plyr.min.js", "plyr.svg")


def ensure_player_asset(data_dir: Path) -> Path:
    """Copy the packaged player assets into ``<data_dir>/assets/`` (idempotent).

    The media server is rooted at ``data_dir`` and cannot serve files that
    live inside the installed package, so the player page and its Plyr
    library assets (CSS, JS, SVG icon sprite) are copied out to a location
    the server can reach. Returns the destination path of ``player.html``
    (callers rely on this return value).
    """
    dest_dir = data_dir / "assets"
    dest_dir.mkdir(parents=True, exist_ok=True)
    # Anchor on the ``meetingkb.web`` package: this module (``assets.py``) shadows
    # the sibling ``assets/`` data directory, so ``files("meetingkb.web.assets")``
    # would resolve to this file's parent, not the data dir. Join from ``web``.
    src_dir = files("meetingkb.web").joinpath("assets")
    dest = dest_dir / "player.html"
    for filename in _ASSET_FILENAMES:
        shutil.copyfile(str(src_dir.joinpath(filename)), dest_dir / filename)
    return dest
