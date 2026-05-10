from __future__ import annotations

MAX_ATTACHMENTS = 20
MAX_REFERENCE_DOCS = 40
MAX_REFERENCE_CHARS = 480_000


def validate_attachment_count(
    attachments: list | None, *, max_count: int = MAX_ATTACHMENTS
) -> list | None:
    if attachments is None:
        return None
    if len(attachments) > max_count:
        raise ValueError(f"At most {max_count} attachment images/pages per request.")
    return attachments


def validate_reference_documents(
    docs: list | None,
    *,
    max_count: int = MAX_REFERENCE_DOCS,
    max_chars: int = MAX_REFERENCE_CHARS,
) -> list | None:
    if not docs:
        return docs
    if len(docs) > max_count:
        raise ValueError(f"At most {max_count} reference documents per request.")
    total = sum(len(d.text) for d in docs)
    if total > max_chars:
        raise ValueError(
            f"Combined reference document text exceeds limit ({max_chars // 1000}k characters)."
        )
    return docs
