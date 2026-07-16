"""Optional end-to-end browser smoke test against a live `kb serve` instance.

Not run by default (module is marked ``integration``; the default addopts
exclude that marker). To run it manually:

    playwright install chromium
    KB_DATA_DIR=./sample_data KB_TERMS_FILE=./sample_data/terms.txt kb index --no-opensearch
    KB_DATA_DIR=./sample_data KB_TERMS_FILE=./sample_data/terms.txt kb serve &
    uv run pytest -m integration tests/playwright_smoke_test.py -v

Drives a real browser (Playwright's bundled Chromium) against the running
Streamlit app and exercises search, context paging/formatting, and the
embedded video player using the bundled sample data (terms Alpha/Beta/Gamma).

The bundled sample_data has no committed media (transcript-only fixture), so
the test itself generates a tiny video for one sample meeting via ffmpeg (if
ffmpeg is on PATH) and reindexes sample_data in place before driving the
browser, so the embedded-player assertion is genuinely exercised rather than
a guaranteed no-op. If ffmpeg is unavailable, that assertion is skipped
gracefully instead of failing on a fixture property this suite doesn't
control -- see `_ensure_sample_video()` / `open_video()`.
"""
from __future__ import annotations

import os
import re
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

import pytest
from playwright.sync_api import Page, sync_playwright
from playwright.sync_api import TimeoutError as PlaywrightTimeoutError

from meetingkb.config import Settings
from meetingkb.ingest.indexer import build_index

pytestmark = pytest.mark.integration

try:  # keep debug output readable on a cp1251 Windows console
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    sys.stderr.reconfigure(encoding="utf-8", errors="replace")
except Exception:  # noqa: BLE001
    pass


REPO_ROOT = Path(__file__).resolve().parent.parent
SAMPLE_DATA_DIR = REPO_ROOT / "sample_data"

BASE_URL = os.environ.get("KB_URL", "http://127.0.0.1:8502")
_TMP_DIR = Path(tempfile.gettempdir())
SCREENSHOT_PATH = Path(
    os.environ.get("KB_PLAYWRIGHT_SCREENSHOT", str(_TMP_DIR / "kb-playwright-smoke.png"))
)
DEBUG_SCREENSHOT_PATH = Path(
    os.environ.get("KB_PLAYWRIGHT_DEBUG_SCREENSHOT", str(_TMP_DIR / "kb-playwright-debug.png"))
)
SEARCH_PLACEHOLDER = "Search across your meeting transcripts…"

# First stCode block in a result card is the transcript context (Files paths come after).
CONTEXT_SELECTOR = '[data-testid="stCode"]'


def body_text(page: Page) -> str:
    return page.locator("body").inner_text(timeout=15_000)


def search(page: Page, query: str, expected_terms: list[str]) -> None:
    field = page.get_by_placeholder(SEARCH_PLACEHOLDER)
    field.fill(query)
    if field.input_value() != query:
        raise AssertionError(f"search field did not accept query: {query}")
    field.press("Enter")
    # Results render as "<n> match" / "<n> matches"; wait for the count to appear.
    page.wait_for_function(
        "() => /\\b\\d+ match(es)?\\b/.test(document.body.innerText)",
        timeout=60_000,
    )
    if expected_terms:
        page.wait_for_function(
            "(term) => document.body.innerText.includes(term)",
            arg=expected_terms[0],
            timeout=60_000,
        )
    text = body_text(page)
    if "No matches" in text or re.search(r"\b0 matches\b", text):
        raise AssertionError(f"query returned no results: {query}")
    missing = [term for term in expected_terms if term not in text]
    if missing:
        print(text[:4_000])
        raise AssertionError(f"query {query!r} did not show expected terms: {missing}")


def _ensure_sample_video() -> bool:
    """Generate a tiny real video for one sample meeting and reindex
    ``sample_data`` in place, so ``open_video()``'s player-iframe assertion is
    genuinely exercised instead of being a guaranteed no-op.

    The bundled ``sample_data`` fixture is transcript-only by design (no
    committed binary media), so without this ``has_video`` is always False in
    ``web/app.py`` and no player ``<iframe>`` ever renders. This generates a
    1-second ``testsrc`` clip via ffmpeg for the alphabetically-first sample
    meeting (both bundled meetings mention "Alpha", so the "Alpha" search
    used below still matches) and rebuilds the SQLite index so ``source_path``
    picks it up. The already-running ``kb serve`` instance (started per this
    module's docstring, before pytest runs) shares the same sqlite file and
    will see the new ``source_path`` on its next query -- no restart needed.

    Generated files (``*.mp4``, ``knowledge.sqlite``) are git-ignored.

    Returns True if a video fixture is present (freshly generated here, or
    left over from a prior run) so ``open_video()`` should assert on it;
    False if ffmpeg is unavailable, in which case ``open_video()`` skips its
    assertion rather than failing on a fixture property this test suite
    doesn't control.
    """
    if shutil.which("ffmpeg") is None:
        return False
    transcripts_dir = SAMPLE_DATA_DIR / "transcripts"
    json_paths = sorted(transcripts_dir.glob("*.json"))
    if not json_paths:
        return False
    stem = json_paths[0].stem
    video_path = SAMPLE_DATA_DIR / f"{stem}.mp4"
    if not video_path.exists():
        try:
            subprocess.run(
                [
                    "ffmpeg", "-y", "-loglevel", "error",
                    "-f", "lavfi", "-i", "testsrc=size=320x240:rate=1",
                    "-t", "1",
                    str(video_path),
                ],
                check=True,
                timeout=30,
            )
        except (subprocess.SubprocessError, OSError):
            return False
    settings = Settings(data_dir=SAMPLE_DATA_DIR, terms_file=SAMPLE_DATA_DIR / "terms.txt")
    build_index(settings, use_opensearch=False)
    return True


def open_video(page: Page, *, expect_video: bool) -> None:
    # The video is an embedded Plyr player served via the local media server as an
    # <iframe> next to the transcript (no tab, no Play button).
    #
    # Guarded: the bundled sample_data is transcript-only, so unless
    # `_ensure_sample_video()` generated a fixture video (needs ffmpeg on
    # PATH), no result has `has_video` and no player iframe ever renders --
    # skip rather than fail on that fixture property. When a video fixture
    # *is* present (expect_video=True), a missing iframe is a real failure.
    iframe = page.locator('iframe[src*="player.html"]').first
    try:
        iframe.wait_for(state="attached", timeout=30_000 if expect_video else 5_000)
    except PlaywrightTimeoutError:
        if expect_video:
            raise
        print("no video result present (sample_data is transcript-only, ffmpeg unavailable "
              "or not run) -- skipping video assertion")
        return
    src = iframe.get_attribute("src") or ""
    if "video=" not in src:
        raise AssertionError("player iframe is missing its video source")


def verify_context_controls(page: Page) -> None:
    # The Context tab is active by default; its code block holds the transcript.
    output = page.locator(CONTEXT_SELECTOR).first
    output.wait_for(timeout=30_000)
    before_text = output.inner_text(timeout=30_000)
    if not before_text.strip():
        raise AssertionError("context output is empty")

    page.get_by_role("button", name=re.compile(r"Later")).first.click()
    page.wait_for_function(
        "([sel, previous]) => document.querySelector(sel)?.innerText !== previous",
        arg=[CONTEXT_SELECTOR, before_text],
        timeout=30_000,
    )
    loaded_text = output.inner_text(timeout=30_000)
    if len(loaded_text) <= len(before_text):
        raise AssertionError("loading later context did not extend the output")

    page.get_by_text("Plain text").first.click()
    page.get_by_text("Markdown list").click()
    page.wait_for_function(
        "(sel) => document.querySelector(sel)?.innerText.includes('- `')",
        arg=CONTEXT_SELECTOR,
        timeout=30_000,
    )
    formatted_text = output.inner_text(timeout=30_000)
    shared_token = next((token for token in re.findall(r"[^\s`>\-\[\]]{6,}", before_text)), "")
    if shared_token and shared_token not in formatted_text:
        raise AssertionError("format change lost previously loaded context")


def test_playwright_smoke() -> None:
    video_ready = _ensure_sample_video()
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        page = browser.new_page(viewport={"width": 1440, "height": 1000})
        page.goto(BASE_URL, wait_until="domcontentloaded", timeout=30_000)

        try:
            page.get_by_role("heading", name="Meeting Knowledge Base").wait_for(timeout=30_000)
        except Exception:
            DEBUG_SCREENSHOT_PATH.parent.mkdir(parents=True, exist_ok=True)
            page.screenshot(path=str(DEBUG_SCREENSHOT_PATH), full_page=True)
            print(f"debug screenshot {DEBUG_SCREENSHOT_PATH}")
            print(body_text(page)[:4_000])
            raise
        page.get_by_placeholder(SEARCH_PLACEHOLDER).wait_for(timeout=30_000)

        search(page, "Alpha", ["Alpha"])
        verify_context_controls(page)
        open_video(page, expect_video=video_ready)
        search(page, "Beta", ["Beta"])
        search(page, "Alha", ["Alpha"])

        SCREENSHOT_PATH.parent.mkdir(parents=True, exist_ok=True)
        page.screenshot(path=str(SCREENSHOT_PATH), full_page=True)
        browser.close()

    print(f"ok playwright {BASE_URL}")
    print(f"screenshot {SCREENSHOT_PATH}")
