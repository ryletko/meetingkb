from dataclasses import dataclass, field


@dataclass(frozen=True)
class Segment:
    """A segment of a meeting transcript."""
    id: str
    meeting_id: str
    segment_index: int
    start_sec: float
    end_sec: float
    text: str
    terms: list[str] = field(default_factory=list)


@dataclass(frozen=True)
class SearchHit:
    """A search result hit."""
    id: str
    meeting_id: str
    title: str
    meeting_date: str
    source_path: str
    segment_index: int
    start_sec: float
    end_sec: float
    start_label: str
    end_label: str
    text: str
    terms: list[str]
    score: float
    transcript_txt_path: str
    transcript_json_path: str
    # Optional presentation fields: highlighted markup and how the hit was matched.
    # Not every search path sets them (plain FTS has neither), so they default to "".
    highlighted_text: str = ""
    match_source: str = ""


@dataclass(frozen=True)
class Meeting:
    """Metadata for a meeting."""
    id: str
    title: str
    meeting_date: str | None
    source_path: str | None
    transcript_json_path: str
    transcript_txt_path: str | None
    duration_sec: float | None
    language: str
    model: str
    segment_count: int
    term_count: int


@dataclass(frozen=True)
class RagDocument:
    """A document for RAG (Retrieval-Augmented Generation)."""
    source_id: str
    meeting_id: str
    segment_index: int
    title: str
    meeting_date: str
    start_label: str
    end_label: str
    start_sec: float
    end_sec: float
    text: str
    source_path: str
    transcript_txt_path: str
    transcript_json_path: str


@dataclass(frozen=True)
class RagAnswer:
    """An answer from RAG with supporting documents."""
    answer: str
    documents: list[RagDocument]
