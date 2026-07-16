from __future__ import annotations

import html
import json
import re
import sqlite3
import threading
import urllib.parse
from dataclasses import asdict
from pathlib import Path

import streamlit as st

from meetingkb.config import get_settings
from meetingkb.context import AppContext, build_context
from meetingkb.ingest import thumbnails
from meetingkb.ingest.watcher import AutoIngestWorker
from meetingkb.models import RagDocument, SearchHit
from meetingkb.rag.client import (
    LLMConfig,
    LLMError,
    list_ollama_models,
)
from meetingkb.rag.context import build_context_documents, build_rag_messages
from meetingkb.web.asset_utils import ensure_player_asset
from meetingkb.web.media_server import start_media_server

# All runtime configuration comes from Settings; shadow the former module-level
# constant so the rest of this file reads it unchanged.
_settings = get_settings()
ROOT_DIR = _settings.data_dir


@st.cache_resource
def _ctx() -> AppContext:
    return build_context()


@st.cache_resource
def _auto_ingest_worker() -> AutoIngestWorker | None:
    """Start the background auto-ingest worker (once per server process).

    Returns `None` when `KB_AUTO_INGEST` is off, so callers can skip
    rendering anything -- zero UX change for the (default) opt-out case.
    `st.cache_resource` guarantees a single worker/thread per server even
    across reruns and sessions.
    """
    if not _settings.auto_ingest:
        return None
    worker = AutoIngestWorker(_ctx().settings, _ctx().transcriber())
    thread = threading.Thread(target=worker.run_forever, daemon=True)
    thread.start()
    return worker


st.set_page_config(page_title="Meeting Knowledge Base", page_icon="◈", layout="wide")

KB_CSS = """
<style>
:root {
    --kb-bg: #0F1115;
    --kb-surface: #171A21;
    --kb-surface-2: #1E222B;
    --kb-border: rgba(255, 255, 255, 0.08);
    --kb-border-strong: rgba(255, 255, 255, 0.16);
    --kb-text: #E6E9EF;
    --kb-muted: #8B93A7;
    --kb-accent: #2DD4BF;
    --kb-accent-dim: rgba(45, 212, 191, 0.13);
    --kb-amber: #E8B84B;
    --kb-amber-dim: rgba(232, 184, 75, 0.20);
    --kb-mono: ui-monospace, SFMono-Regular, Menlo, Consolas, "Liberation Mono", monospace;
}

/* --- strip dev chrome, keep the menu --- */
[data-testid="stAppDeployButton"] { display: none !important; }
[data-testid="stStatusWidget"] { display: none !important; }
[data-testid="stDecoration"] { display: none !important; }
[data-testid="stHeader"] { background: transparent; }

/* --- wide working area; text line-length is capped per block for readability --- */
[data-testid="stMainBlockContainer"], .block-container {
    max-width: min(1440px, 96vw);
    padding-top: 2rem;
    padding-bottom: 5rem;
}

/* --- hero --- */
.kb-hero { margin: 0 0 1.5rem; }
.kb-eyebrow {
    font-family: var(--kb-mono);
    font-size: 0.72rem;
    letter-spacing: 0.18em;
    color: var(--kb-accent);
    text-transform: uppercase;
    margin-bottom: 0.35rem;
}
.kb-title {
    font-size: 2rem;
    font-weight: 700;
    letter-spacing: -0.02em;
    line-height: 1.1;
    margin: 0;
    color: var(--kb-text);
}
.kb-sub { color: var(--kb-muted); font-size: 0.95rem; margin: 0.4rem 0 0; }

/* --- sidebar identity --- */
.kb-brand {
    display: flex; align-items: center; gap: 0.5rem;
    font-weight: 700; font-size: 1.15rem; letter-spacing: -0.01em;
    margin: 0.2rem 0 1.25rem;
}
.kb-brand-mark { color: var(--kb-accent); font-size: 1.25rem; }
.kb-stats { display: flex; flex-direction: column; gap: 0.85rem; margin-bottom: 1.25rem; }
.kb-stat { display: flex; align-items: baseline; gap: 0.55rem; }
.kb-stat-num {
    font-family: var(--kb-mono); font-size: 1.5rem; font-weight: 600;
    color: var(--kb-text); line-height: 1;
}
.kb-stat-label {
    font-size: 0.72rem; letter-spacing: 0.08em; text-transform: uppercase;
    color: var(--kb-muted);
}
.kb-engine {
    display: inline-flex; align-items: center; gap: 0.5rem;
    font-family: var(--kb-mono); font-size: 0.8rem; color: var(--kb-muted);
    padding: 0.4rem 0.7rem; border: 1px solid var(--kb-border);
    border-radius: 999px; background: var(--kb-surface);
}
.kb-dot { width: 8px; height: 8px; border-radius: 50%; display: inline-block; }
.kb-engine--ok .kb-dot { background: var(--kb-accent); box-shadow: 0 0 8px var(--kb-accent); }
.kb-engine--fallback .kb-dot { background: var(--kb-amber); box-shadow: 0 0 8px var(--kb-amber); }

/* --- result card head --- */
.kb-card-head {
    display: flex; justify-content: space-between; align-items: flex-start;
    gap: 1rem; margin-bottom: 0.5rem;
}
.kb-card-title { font-weight: 650; font-size: 1.02rem; color: var(--kb-text); line-height: 1.35; }
.kb-card-meta { display: flex; align-items: center; gap: 0.6rem; flex-shrink: 0; }
.kb-date { font-family: var(--kb-mono); font-size: 0.72rem; color: var(--kb-muted); white-space: nowrap; }
.kb-pill {
    font-family: var(--kb-mono); font-size: 0.78rem; font-weight: 600;
    color: var(--kb-accent); letter-spacing: 0.02em;
    padding: 0.15rem 0.55rem; border-radius: 6px;
    background: var(--kb-accent-dim); border: 1px solid rgba(45, 212, 191, 0.28);
    white-space: nowrap;
}
.kb-chips { display: flex; flex-wrap: wrap; gap: 0.35rem; margin: 0.1rem 0 0.6rem; }
.kb-chip {
    font-family: var(--kb-mono); font-size: 0.72rem; color: var(--kb-muted);
    padding: 0.12rem 0.5rem; border-radius: 999px;
    border: 1px solid var(--kb-border-strong); background: var(--kb-surface-2);
}
.kb-snippet { font-size: 0.98rem; line-height: 1.6; color: var(--kb-text); margin: 0.2rem 0 0.3rem; max-width: 80ch; }
.kb-snippet mark {
    background: var(--kb-amber-dim); color: var(--kb-text);
    padding: 0.02em 0.2em; border-radius: 3px; font-weight: 600;
}
.kb-note { font-family: var(--kb-mono); font-size: 0.72rem; color: var(--kb-muted); margin-top: 0.2rem; }

/* --- embedded video; caps at viewport height so theater mode fits the page --- */
[data-testid="stVideo"] { border-radius: 8px; overflow: hidden; }
[data-testid="stVideo"] video {
    border-radius: 8px; display: block; width: 100%;
    max-height: 82vh; object-fit: contain; background: #000;
}

/* --- soften every bordered container into a card --- */
[data-testid="stVerticalBlockBorderWrapper"] {
    background: var(--kb-surface);
    border: 1px solid var(--kb-border) !important;
    border-radius: 12px;
    transition: border-color 0.15s ease;
}
[data-testid="stVerticalBlockBorderWrapper"]:hover { border-color: var(--kb-border-strong) !important; }

/* --- filter chips + empty states --- */
.kb-active { display: flex; flex-wrap: wrap; align-items: center; gap: 0.4rem; margin: 0.2rem 0 0.4rem; }
.kb-active-chip {
    font-family: var(--kb-mono); font-size: 0.74rem; color: var(--kb-text);
    padding: 0.15rem 0.55rem; border-radius: 999px;
    background: var(--kb-accent-dim); border: 1px solid rgba(45, 212, 191, 0.28);
}
.kb-active-chip b { color: var(--kb-accent); font-weight: 600; }
.kb-result-count {
    font-family: var(--kb-mono); font-size: 0.85rem; color: var(--kb-muted);
    margin: 0.6rem 0 0.9rem;
}
.kb-result-count b { color: var(--kb-text); }
.kb-empty {
    text-align: center; padding: 2.5rem 1rem; color: var(--kb-muted);
    border: 1px dashed var(--kb-border-strong); border-radius: 12px; background: var(--kb-surface);
}
.kb-empty-title { color: var(--kb-text); font-weight: 600; font-size: 1.05rem; margin-bottom: 0.4rem; }
.kb-section-label {
    font-family: var(--kb-mono); font-size: 0.75rem; letter-spacing: 0.12em;
    text-transform: uppercase; color: var(--kb-muted); margin: 0.5rem 0 0.75rem;
}
</style>
"""

st.markdown(KB_CSS, unsafe_allow_html=True)

CONTEXT_DEFAULT_BEFORE = 2
CONTEXT_DEFAULT_AFTER = 2
CONTEXT_STEP = 10
CONTEXT_FORMATS = ("Plain text", "Timestamps", "Markdown quote", "Markdown list")


def seconds_label(seconds: float | int | None) -> str:
    if seconds is None:
        return "00:00:00"
    seconds = max(0, int(seconds))
    h, rem = divmod(seconds, 3600)
    m, s = divmod(rem, 60)
    return f"{h:02d}:{m:02d}:{s:02d}"


def human_duration(seconds: float | int | None) -> str:
    seconds = max(0, int(seconds or 0))
    hours, rem = divmod(seconds, 3600)
    minutes, _ = divmod(rem, 60)
    if hours:
        return f"{hours}h {minutes:02d}m"
    return f"{minutes}m"


def video_format(path: str | Path) -> str:
    suffix = Path(path).suffix.lower()
    return {
        ".webm": "video/webm",
        ".mp4": "video/mp4",
        ".mkv": "video/x-matroska",
        ".mov": "video/quicktime",
        ".avi": "video/x-msvideo",
    }.get(suffix, "video/mp4")


@st.cache_resource
def db_conn() -> sqlite3.Connection:
    return _ctx().sqlite()


@st.cache_data(ttl=10)
def opensearch_available() -> bool:
    return _ctx().opensearch_available()


@st.cache_data(ttl=10)
def load_meetings() -> list[dict]:
    conn = db_conn()
    rows = conn.execute(
        """
        SELECT id, title, meeting_date, source_path, duration_sec, segment_count, term_count
        FROM meetings
        ORDER BY meeting_date, title
        """
    ).fetchall()
    return [dict(row) for row in rows]


@st.cache_data(ttl=10)
def load_terms() -> list[str]:
    conn = db_conn()
    rows = conn.execute("SELECT DISTINCT term FROM terms ORDER BY term").fetchall()
    terms = [row["term"] for row in rows]
    return terms or _settings.terms


@st.cache_data(ttl=10)
def load_ollama_models() -> list[str]:
    return list_ollama_models()


@st.cache_data(ttl=10)
def load_context_bounds(meeting_id: str) -> dict[str, int]:
    conn = db_conn()
    row = conn.execute(
        """
        SELECT min(segment_index) AS min_index, max(segment_index) AS max_index, count(*) AS total
        FROM segments
        WHERE meeting_id = ?
        """,
        (meeting_id,),
    ).fetchone()
    return {
        "min_index": int(row["min_index"] or 0),
        "max_index": int(row["max_index"] or 0),
        "total": int(row["total"] or 0),
    }


@st.cache_data(ttl=10)
def load_context_segments(meeting_id: str, center_index: int, before: int, after: int) -> list[dict]:
    bounds = load_context_bounds(meeting_id)
    start_index = max(bounds["min_index"], center_index - before)
    end_index = min(bounds["max_index"], center_index + after)
    conn = db_conn()
    rows = conn.execute(
        """
        SELECT
            s.id, s.meeting_id, s.segment_index, s.start_sec, s.end_sec, s.text, s.terms,
            m.title, m.meeting_date, m.source_path, m.transcript_txt_path, m.transcript_json_path
        FROM segments s
        JOIN meetings m ON m.id = s.meeting_id
        WHERE s.meeting_id = ? AND s.segment_index BETWEEN ? AND ?
        ORDER BY s.segment_index
        """,
        (meeting_id, start_index, end_index),
    ).fetchall()
    segments = []
    for row in rows:
        segment = dict(row)
        try:
            segment["terms"] = json.loads(segment.get("terms") or "[]")
        except json.JSONDecodeError:
            segment["terms"] = []
        segment["start_label"] = seconds_label(segment["start_sec"])
        segment["end_label"] = seconds_label(segment["end_sec"])
        segments.append(segment)
    return segments


def stable_key(value: object) -> str:
    return re.sub(r"[^0-9A-Za-z_]+", "_", str(value or "unknown")).strip("_") or "unknown"


def format_context_text(segments: list[dict], format_name: str) -> str:
    if format_name == "Timestamps":
        return "\n".join(
            f"[{segment['start_label']} - {segment['end_label']}] {segment['text']}" for segment in segments
        )
    if format_name == "Markdown quote":
        return "\n".join(f"> [{segment['start_label']}] {segment['text']}" for segment in segments)
    if format_name == "Markdown list":
        return "\n".join(f"- `{segment['start_label']}` {segment['text']}" for segment in segments)
    return " ".join(segment["text"].strip() for segment in segments if segment["text"].strip())


def context_block(hit: SearchHit, key: str) -> None:
    meeting_id = hit.meeting_id
    segment_index = hit.segment_index
    if meeting_id is None or segment_index is None:
        st.caption("No transcript context for this segment.")
        return

    center_index = int(segment_index)
    before_key = f"context_before_{key}"
    after_key = f"context_after_{key}"
    format_key = f"context_format_{key}"

    st.session_state.setdefault(before_key, CONTEXT_DEFAULT_BEFORE)
    st.session_state.setdefault(after_key, CONTEXT_DEFAULT_AFTER)

    bounds = load_context_bounds(str(meeting_id))
    before_limit = max(0, center_index - bounds["min_index"])
    after_limit = max(0, bounds["max_index"] - center_index)
    before = min(int(st.session_state[before_key]), before_limit)
    after = min(int(st.session_state[after_key]), after_limit)
    st.session_state[before_key] = before
    st.session_state[after_key] = after

    controls = st.columns([1.1, 1.1, 2])
    if controls[0].button("↑ Earlier", key=f"context_prev_{key}", disabled=before >= before_limit,
                          use_container_width=True):
        before = min(before + CONTEXT_STEP, before_limit)
        st.session_state[before_key] = before
    if controls[1].button("↓ Later", key=f"context_next_{key}", disabled=after >= after_limit,
                          use_container_width=True):
        after = min(after + CONTEXT_STEP, after_limit)
        st.session_state[after_key] = after
    format_name = controls[2].selectbox("Format", CONTEXT_FORMATS, key=format_key,
                                        label_visibility="collapsed")

    segments = load_context_segments(str(meeting_id), center_index, before, after)
    if not segments:
        st.warning("No transcript context for this segment.")
        return

    start = segments[0]["start_label"]
    end = segments[-1]["end_label"]
    first_idx = segments[0]["segment_index"] + 1
    last_idx = segments[-1]["segment_index"] + 1
    st.caption(f"{start}–{end} · segments {first_idx}–{last_idx} of {bounds['total']} · hover to copy")
    st.code(format_context_text(segments, str(format_name)), language=None, wrap_lines=True)


def _card_head_html(title: str, start_label: str, end_label: str, date: str) -> str:
    return (
        '<div class="kb-card-head">'
        f'<div class="kb-card-title">{html.escape(str(title))}</div>'
        '<div class="kb-card-meta">'
        f'<span class="kb-pill">{start_label}–{end_label}</span>'
        f'<span class="kb-date">{html.escape(str(date))}</span>'
        '</div></div>'
    )


def _render_terms(terms: list) -> None:
    if not terms:
        return
    chips = "".join(f'<span class="kb-chip">{html.escape(str(t))}</span>' for t in terms)
    st.markdown(f'<div class="kb-chips">{chips}</div>', unsafe_allow_html=True)


@st.cache_resource
def media_base_url() -> str:
    # The media server is rooted at data_dir; copy the packaged player page there
    # so it can be served over HTTP alongside the videos and thumbnails.
    ensure_player_asset(_settings.data_dir)
    return start_media_server(Path(ROOT_DIR))


def _root_relative_url(base: str, path: str) -> str | None:
    try:
        rel = Path(path).resolve().relative_to(Path(ROOT_DIR).resolve()).as_posix()
    except (ValueError, OSError):
        return None
    return base + "/" + urllib.parse.quote(rel)


def render_video(hit: SearchHit, height: int = 360) -> None:
    """Embed the Plyr player (via the local media server) with a hover scrub preview."""
    source_path = str(hit.source_path or "")
    start = int(float(hit.start_sec or 0))
    base = media_base_url()
    video_url = _root_relative_url(base, source_path)
    if not video_url:
        # Video lives outside the served root; fall back to the native player.
        st.video(source_path, format=video_format(Path(source_path)), start_time=start)
        return
    params = {"video": video_url, "start": str(start)}
    meeting_id = str(hit.meeting_id or "")
    if meeting_id and thumbnails.has_thumbnails(Path(ROOT_DIR), meeting_id):
        params["vtt"] = base + "/" + urllib.parse.quote(f"thumbs/{meeting_id}/storyboard.vtt")
    player_url = base + "/assets/player.html?" + urllib.parse.urlencode(params)
    st.components.v1.iframe(player_url, height=height, scrolling=False)


def theater_button(hit: SearchHit, key: str, where: str) -> None:
    hit_id = hit.id or key
    st.button(
        "⛶ Theater",
        key=f"theater_{where}_{key}",
        help="Show this recording large, filling the page (Esc / Back to return)",
        on_click=lambda k=hit_id: st.session_state.update(focus=k),
    )


def snippet_html(hit: SearchHit) -> str:
    """Return the safe-to-render HTML for a hit's transcript snippet.

    `highlighted_text` is already safe HTML (fuzzy matches are escaped by
    `highlight_fuzzy`; OpenSearch escapes via the `encoder: html` highlight
    option) -- do not double-escape it. The raw `hit.text` fallback (used
    when there is no highlight, e.g. the SQLite FTS path) is not HTML-safe
    and must be escaped here.
    """
    return hit.highlighted_text or html.escape(str(hit.text or ""))


def result_block(hit: SearchHit, layout: str) -> None:
    title = hit.title or hit.meeting_id or ""
    start_label = hit.start_label or seconds_label(hit.start_sec)
    end_label = hit.end_label or seconds_label(hit.end_sec)
    text = snippet_html(hit)
    date = hit.meeting_date or ""
    key = stable_key(hit.id or f"{hit.meeting_id}_{hit.segment_index}")

    source_path = hit.source_path
    has_video = bool(source_path and Path(source_path).exists())

    with st.container(border=True):
        st.markdown(_card_head_html(title, start_label, end_label, date), unsafe_allow_html=True)
        _render_terms(hit.terms or [])
        st.markdown(f'<div class="kb-snippet">{text}</div>', unsafe_allow_html=True)

        match_source = hit.match_source
        if match_source:
            st.markdown(f'<div class="kb-note">matched via {html.escape(str(match_source))}</div>',
                        unsafe_allow_html=True)

        if has_video and layout == "Stacked":
            # Default: a large video on top (full card width), transcript centred below.
            theater_button(hit, key, "stack")
            render_video(hit, height=680)
            _, mid, _ = st.columns([1, 8, 1])
            with mid:
                context_block(hit, key)
        elif has_video:
            # Split: video beside the transcript so you can watch while reading.
            ctx_col, vid_col = st.columns([1.1, 1], gap="large")
            with vid_col:
                theater_button(hit, key, "split")
                render_video(hit, height=360)
            with ctx_col:
                context_block(hit, key)
        else:
            context_block(hit, key)
            if source_path:
                st.caption(f"Video file is missing: {source_path}")

        with st.expander("Files"):
            render_files(hit)


def render_theater(hit: SearchHit) -> None:
    title = hit.title or hit.meeting_id or ""
    start_label = hit.start_label or seconds_label(hit.start_sec)
    end_label = hit.end_label or seconds_label(hit.end_sec)
    date = hit.meeting_date or ""
    key = stable_key(hit.id or f"{hit.meeting_id}_{hit.segment_index}")
    source_path = hit.source_path
    has_video = bool(source_path and Path(source_path).exists())

    st.button("← Back to results", key="theater_back",
              on_click=lambda: st.session_state.update(focus=None))
    st.markdown(_card_head_html(title, start_label, end_label, date), unsafe_allow_html=True)
    _render_terms(hit.terms or [])

    if has_video:
        render_video(hit, height=800)  # fills the page in theater mode
    elif source_path:
        st.warning(f"Video file is missing: {source_path}")

    _, mid, _ = st.columns([1, 5, 1])
    with mid:
        context_block(hit, key)


def render_files(hit: SearchHit) -> None:
    rows = [
        ("Video", "source_path"),
        ("Transcript TXT", "transcript_txt_path"),
        ("Transcript JSON", "transcript_json_path"),
    ]
    shown = False
    for label, field in rows:
        path = getattr(hit, field)
        if path:
            shown = True
            st.caption(label)
            st.code(str(path), language=None, wrap_lines=True)
    if not shown:
        st.caption("No files linked to this segment.")


def render_auto_ingest_status() -> None:
    """Sidebar status block for the background auto-ingest worker.

    Renders nothing when `KB_AUTO_INGEST` is off (the default) -- zero UX
    change for the opt-out case.
    """
    worker = _auto_ingest_worker()
    if worker is None:
        return

    status = worker.status
    state_labels = {
        "idle": "Idle",
        "transcribing": f"Transcribing {status.current_file or ''}".strip(),
        "indexing": "Indexing",
        "error": f"Error: {status.last_error or ''}".strip(),
        "disabled": f"Disabled: {status.last_error or ''}".strip(),
    }
    state_label = state_labels.get(status.state, status.state)

    st.markdown('<div class="kb-section-label" style="margin-top:1.5rem">Auto-ingest</div>',
                unsafe_allow_html=True)
    st.caption(f"Watching {status.watching_dir}")
    st.caption(f"Status: {state_label}")
    st.caption(f"Last scan: {status.last_scan_at or 'never'}")
    st.caption(f"Transcribed: {status.transcribed_count}")
    if status.state not in ("error", "disabled") and status.last_error:
        st.caption(f"Last error: {status.last_error}")
    st.button("Scan now", key="auto_ingest_scan_now", on_click=worker.run_once)


def render_sidebar(meetings: list[dict], available: bool) -> str:
    total_duration = sum(int(m.get("duration_sec") or 0) for m in meetings)
    total_segments = sum(int(m.get("segment_count") or 0) for m in meetings)
    engine_class = "kb-engine--ok" if available else "kb-engine--fallback"
    engine_label = "OpenSearch" if available else "SQLite FTS · fallback"

    with st.sidebar:
        st.markdown(
            '<div class="kb-brand"><span class="kb-brand-mark">◈</span> Meeting KB</div>',
            unsafe_allow_html=True,
        )
        st.markdown(
            '<div class="kb-stats">'
            f'<div class="kb-stat"><span class="kb-stat-num">{len(meetings)}</span>'
            '<span class="kb-stat-label">meetings</span></div>'
            f'<div class="kb-stat"><span class="kb-stat-num">{human_duration(total_duration)}</span>'
            '<span class="kb-stat-label">recorded</span></div>'
            f'<div class="kb-stat"><span class="kb-stat-num">{total_segments:,}</span>'
            '<span class="kb-stat-label">segments</span></div>'
            '</div>',
            unsafe_allow_html=True,
        )
        st.markdown(
            f'<div class="kb-engine {engine_class}"><span class="kb-dot"></span>{engine_label}</div>',
            unsafe_allow_html=True,
        )
        render_auto_ingest_status()
        st.markdown('<div class="kb-section-label" style="margin-top:1.5rem">Result layout</div>',
                    unsafe_allow_html=True)
        layout = st.segmented_control(
            "Result layout",
            options=["Stacked", "Split"],
            default="Stacked",
            key="kb_layout",
            label_visibility="collapsed",
        )
    return layout or "Stacked"


def render_rag_sources(documents: list[RagDocument]) -> None:
    st.markdown('<div class="kb-section-label">Sources</div>', unsafe_allow_html=True)
    for doc in documents:
        label = (
            f"[{doc.source_id}] {doc.title} "
            f"{doc.start_label or ''}-{doc.end_label or ''}"
        )
        with st.expander(label):
            if doc.meeting_date:
                st.caption(str(doc.meeting_date))
            st.code(str(doc.text or ""), language=None, wrap_lines=True)
            if doc.source_path:
                st.caption("Video")
                st.code(str(doc.source_path), language=None, wrap_lines=True)


def render_rag_answer(answer: str, documents: list[RagDocument]) -> None:
    st.markdown('<div class="kb-section-label">Answer</div>', unsafe_allow_html=True)
    st.markdown(answer)
    render_rag_sources(documents)


def render_rag_mode(
    query: str,
    meeting_id: str | None,
    selected_meeting: str,
    selected_term: str | None,
    limit: int,
    available: bool,
) -> None:
    st.markdown('<div class="kb-section-label">Ask with RAG</div>', unsafe_allow_html=True)
    st.caption(
        "The assistant retrieves transcript fragments first, then sends only those fragments to the configured LLM."
    )

    local_models = load_ollama_models()
    env_model = _settings.llm_model
    default_model = env_model or (local_models[0] if local_models else "llama3.1")

    with st.expander("LLM settings", expanded=not bool(env_model or local_models)):
        llm_base_url = st.text_input(
            "LLM base URL",
            value=_settings.llm_base_url,
            key="llm_base_url",
            help="OpenAI-compatible base URL. Ollama default: http://127.0.0.1:11434/v1",
        )
        if local_models:
            options = list(dict.fromkeys([default_model, *local_models]))
            llm_model = st.selectbox("Model", options, index=options.index(default_model), key="llm_model_select")
        else:
            llm_model = st.text_input("Model", value=default_model, key="llm_model_text")
        llm_api_key = st.text_input(
            "API key",
            value=_settings.llm_api_key,
            type="password",
            key="llm_api_key",
            help="Leave empty for local Ollama. Set KB_LLM_API_KEY for hosted providers.",
        )
        c1, c2, c3, c4 = st.columns([1, 1, 1, 1])
        rag_limit = c1.number_input("Context hits", min_value=3, max_value=30, value=min(max(limit, 8), 12), step=1)
        rag_before = c2.number_input("Before", min_value=0, max_value=5, value=1, step=1)
        rag_after = c3.number_input("After", min_value=0, max_value=5, value=1, step=1)
        max_tokens = c4.number_input("Max tokens", min_value=256, max_value=4096, value=1200, step=128)

    if not (query or "").strip():
        st.markdown(
            '<div class="kb-empty"><div class="kb-empty-title">Ask a question</div>'
            'Type a question above, then run the RAG answer.</div>',
            unsafe_allow_html=True,
        )
        return

    active_chips = [f'<span class="kb-active-chip"><b>question</b> {html.escape(query)}</span>']
    if meeting_id:
        active_chips.append(f'<span class="kb-active-chip"><b>meeting</b> {html.escape(selected_meeting)}</span>')
    if selected_term:
        active_chips.append(f'<span class="kb-active-chip"><b>term</b> {html.escape(selected_term)}</span>')
    st.markdown(f'<div class="kb-active">{"".join(active_chips)}</div>', unsafe_allow_html=True)

    disabled = not bool(str(llm_model).strip())
    if disabled:
        st.warning("Configure an LLM model before asking.")

    if st.button("Ask LLM", type="primary", disabled=disabled):
        with st.spinner("Retrieving transcript context..."):
            hits = _ctx().search_service().search(
                query, meeting_id, selected_term, int(rag_limit), opensearch_available=available
            )
            # `build_context_documents` (the RAG segment_loader flow) consumes plain
            # dict hits, so adapt the typed SearchHit results back to dicts here.
            documents = build_context_documents(
                [asdict(hit) for hit in hits],
                load_context_segments,
                before=int(rag_before),
                after=int(rag_after),
            )

        if not documents:
            st.warning("No transcript context was found for this question.")
            return

        config = LLMConfig(
            base_url=str(llm_base_url).strip(),
            model=str(llm_model).strip(),
            api_key=str(llm_api_key or "").strip(),
            max_tokens=int(max_tokens),
        )
        try:
            with st.spinner("Asking LLM..."):
                answer = _ctx().llm_client(config).chat(
                    build_rag_messages(query, documents, _settings.rag_system_prompt)
                )
        except LLMError as exc:
            st.error(str(exc))
            render_rag_sources(documents)
            return

        st.session_state["rag_last"] = {
            "question": query,
            "answer": answer,
            "documents": documents,
        }

    last = st.session_state.get("rag_last")
    if last and last.get("question") == query:
        render_rag_answer(str(last["answer"]), list(last["documents"]))


def render_start_screen(meetings: list[dict]) -> None:
    st.markdown('<div class="kb-section-label">All meetings</div>', unsafe_allow_html=True)
    if not meetings:
        st.markdown(
            '<div class="kb-empty"><div class="kb-empty-title">No meetings indexed yet</div>'
            'Run the indexer to populate the knowledge base.</div>',
            unsafe_allow_html=True,
        )
        return
    for meeting in meetings:
        with st.container(border=True):
            st.markdown(
                f'<div class="kb-card-head">'
                f'<div class="kb-card-title">{html.escape(str(meeting["title"]))}</div>'
                f'<div class="kb-card-meta">'
                f'<span class="kb-pill">{human_duration(meeting.get("duration_sec"))}</span>'
                f'<span class="kb-date">{html.escape(str(meeting.get("meeting_date") or ""))}</span>'
                f'</div></div>',
                unsafe_allow_html=True,
            )
            st.markdown(
                '<div class="kb-chips">'
                f'<span class="kb-chip">{int(meeting.get("segment_count") or 0):,} segments</span>'
                f'<span class="kb-chip">{int(meeting.get("term_count") or 0)} terms</span>'
                '</div>',
                unsafe_allow_html=True,
            )
            st.button(
                "Search in this meeting",
                key=f"open_meeting_{meeting['id']}",
                on_click=lambda title=meeting["title"]: st.session_state.update(flt_meeting=title),
            )


def main() -> None:
    meetings = load_meetings()
    terms = load_terms()
    available = opensearch_available()

    layout = render_sidebar(meetings, available)

    st.markdown(
        '<div class="kb-hero">'
        '<div class="kb-eyebrow">transcript search</div>'
        '<h1 class="kb-title">Meeting Knowledge Base</h1>'
        '<p class="kb-sub">Search across your meeting transcripts by phrase, meeting, or term.</p>'
        '</div>',
        unsafe_allow_html=True,
    )

    meeting_options = {"All meetings": None}
    meeting_options.update({m["title"]: m["id"] for m in meetings})

    st.session_state.setdefault("flt_meeting", "All meetings")
    st.session_state.setdefault("flt_term", "All terms")

    mode = st.radio("Mode", ["Search", "Ask"], horizontal=True, label_visibility="collapsed", key="kb_mode")

    query = st.text_input(
        "Search",
        key="q",
        placeholder="Search across your meeting transcripts…",
    )
    col1, col2, col3, col4 = st.columns([3, 3, 1.4, 1.4])
    selected_meeting = col1.selectbox("Meeting", list(meeting_options.keys()), key="flt_meeting")
    selected_term_label = col2.selectbox("Term", ["All terms", *terms], key="flt_term")
    limit = col3.number_input("Limit", min_value=5, max_value=100, value=10, step=5)
    col4.markdown('<div style="height: 1.75rem"></div>', unsafe_allow_html=True)
    col4.button("Reset", on_click=_reset_filters, use_container_width=True)

    meeting_id = meeting_options.get(selected_meeting)
    selected_term = None if selected_term_label == "All terms" else selected_term_label

    if mode == "Ask":
        render_rag_mode(query, meeting_id, selected_meeting, selected_term, int(limit), available)
        return

    has_query = bool((query or "").strip() or meeting_id or selected_term)

    if not has_query:
        render_start_screen(meetings)
        return

    with st.spinner("Searching transcripts…"):
        hits = _ctx().search_service().search(
            query, meeting_id, selected_term, int(limit), opensearch_available=available
        )

    focus = st.session_state.get("focus")
    if focus:
        focused = next((h for h in hits if str(h.id) == str(focus)), None)
        if focused is not None:
            render_theater(focused)
            return
        st.session_state["focus"] = None  # focused hit is no longer in the results

    active_chips = []
    if (query or "").strip():
        active_chips.append(f'<span class="kb-active-chip"><b>query</b> {html.escape(query)}</span>')
    if meeting_id:
        active_chips.append(f'<span class="kb-active-chip"><b>meeting</b> {html.escape(selected_meeting)}</span>')
    if selected_term:
        active_chips.append(f'<span class="kb-active-chip"><b>term</b> {html.escape(selected_term)}</span>')
    if active_chips:
        st.markdown(f'<div class="kb-active">{"".join(active_chips)}</div>', unsafe_allow_html=True)

    st.markdown(
        f'<div class="kb-result-count"><b>{len(hits)}</b> '
        f'{"match" if len(hits) == 1 else "matches"}</div>',
        unsafe_allow_html=True,
    )

    if not hits:
        st.markdown(
            '<div class="kb-empty"><div class="kb-empty-title">No matches</div>'
            'Try a shorter phrase, check spelling, or clear the filters above.</div>',
            unsafe_allow_html=True,
        )
        return

    for hit in hits:
        result_block(hit, layout)


def _reset_filters() -> None:
    st.session_state["q"] = ""
    st.session_state["flt_meeting"] = "All meetings"
    st.session_state["flt_term"] = "All terms"


if __name__ == "__main__":
    main()
