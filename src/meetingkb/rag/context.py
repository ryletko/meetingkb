"""Context assembly and prompt building for RAG answers."""
from __future__ import annotations

from collections.abc import Callable

from meetingkb.models import RagDocument

DEFAULT_MAX_CONTEXT_CHARS = 18_000


def build_context_documents(
    hits: list[dict],
    segment_loader: Callable[[str, int, int, int], list[dict]],
    before: int = 1,
    after: int = 1,
    max_chars: int = DEFAULT_MAX_CONTEXT_CHARS,
) -> list[RagDocument]:
    documents: list[RagDocument] = []
    used: set[tuple[str, int]] = set()
    total_chars = 0

    for hit in hits:
        meeting_id = hit.get("meeting_id")
        segment_index = hit.get("segment_index")
        if meeting_id is None or segment_index is None:
            continue

        key = (str(meeting_id), int(segment_index))
        if key in used:
            continue
        used.add(key)

        segments = segment_loader(str(meeting_id), int(segment_index), before, after)
        if not segments:
            continue

        text = " ".join(str(segment.get("text", "")).strip() for segment in segments)
        text = " ".join(text.split())
        if not text:
            continue

        remaining = max_chars - total_chars
        if remaining <= 0:
            break
        if len(text) > remaining:
            text = text[: max(0, remaining - 20)].rstrip() + "..."

        first = segments[0]
        last = segments[-1]
        doc = RagDocument(
            source_id=f"S{len(documents) + 1}",
            meeting_id=str(meeting_id),
            segment_index=int(segment_index),
            title=hit.get("title") or first.get("title") or str(meeting_id),
            meeting_date=hit.get("meeting_date") or first.get("meeting_date") or "",
            start_label=first.get("start_label") or hit.get("start_label") or "",
            end_label=last.get("end_label") or hit.get("end_label") or "",
            start_sec=first.get("start_sec", hit.get("start_sec")),
            end_sec=last.get("end_sec", hit.get("end_sec")),
            text=text,
            source_path=hit.get("source_path") or first.get("source_path") or "",
            transcript_txt_path=(
                hit.get("transcript_txt_path") or first.get("transcript_txt_path") or ""
            ),
            transcript_json_path=(
                hit.get("transcript_json_path") or first.get("transcript_json_path") or ""
            ),
        )
        documents.append(doc)
        total_chars += len(text)

    return documents


def build_rag_messages(
    question: str, documents: list[RagDocument], system_prompt: str
) -> list[dict[str, str]]:
    context = "\n\n".join(
        (
            f"[{doc.source_id}] {doc.title} "
            f"({doc.meeting_date or 'no date'}, {doc.start_label} - {doc.end_label})\n"
            f"{doc.text}"
        )
        for doc in documents
    )
    user = (
        "Question:\n"
        f"{question.strip()}\n\n"
        "Transcript context:\n"
        f"{context if context else '(empty)'}"
    )
    return [{"role": "system", "content": system_prompt}, {"role": "user", "content": user}]
