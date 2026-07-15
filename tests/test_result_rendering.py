"""`result_block` must not render raw transcript text as unescaped HTML.

Before this fix, `text = hit.highlighted_text or hit.text or ""` was rendered
via `st.markdown(..., unsafe_allow_html=True)` without escaping -- safe only
when `highlighted_text` is set (fuzzy search already HTML-escapes via
`highlight_fuzzy`, and OpenSearch highlighting now uses `encoder: "html"`).
The raw `hit.text` fallback (e.g. the SQLite FTS path, where
`highlighted_text` is empty) was not escaped, so hostile transcript text
would be interpreted as markup by the browser.

`snippet_html()` is the extracted helper `result_block` uses to compute what
gets rendered; testing it directly avoids needing a full Streamlit render.
"""
from meetingkb.models import SearchHit


def _hit(text="", highlighted_text=""):
    return SearchHit(
        id="m1_00001",
        meeting_id="m1",
        title="T",
        meeting_date="2026-01-01",
        source_path="",
        segment_index=1,
        start_sec=0.0,
        end_sec=5.0,
        start_label="00:00:00",
        end_label="00:00:05",
        text=text,
        terms=[],
        score=1.0,
        transcript_txt_path="",
        transcript_json_path="",
        highlighted_text=highlighted_text,
        match_source="",
    )


def test_raw_text_fallback_is_escaped():
    from meetingkb.web import app as kb_app

    hostile = "<img src=x onerror=alert(1)>hello"
    hit = _hit(text=hostile, highlighted_text="")

    rendered = kb_app.snippet_html(hit)

    assert "&lt;img" in rendered
    assert "<img" not in rendered
    assert "hello" in rendered


def test_highlighted_text_is_not_double_escaped():
    from meetingkb.web import app as kb_app

    # Already-safe HTML, as produced by `highlight_fuzzy` (escaped text with
    # literal <mark> tags around the matches) -- must pass through unchanged.
    safe_html = "safe &amp; sound <mark>hello</mark>"
    hit = _hit(text="hello", highlighted_text=safe_html)

    rendered = kb_app.snippet_html(hit)

    assert rendered == safe_html
    assert "&amp;amp;" not in rendered
