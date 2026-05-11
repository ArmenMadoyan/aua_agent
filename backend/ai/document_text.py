"""Extract plain text from common document uploads (rubric / reference materials)."""

from __future__ import annotations

from io import BytesIO
from pathlib import Path

from pypdf import PdfReader

REFERENCE_HEADER = "--- Reference documents (rubric / materials) ---"

# Total cap for merged reference block sent to the model (per request).
MAX_REFERENCE_BLOCK_CHARS = 120_000


def extract_text_from_bytes(*, filename: str, data: bytes) -> str:
    """
    Return best-effort plain text. Supports .txt, .pdf, .docx.

    Legacy Word ``.doc`` is not supported (convert to PDF or DOCX).
    """
    ext = Path(filename or "").suffix.lower()
    if ext == ".txt":
        return data.decode("utf-8", errors="replace")

    if ext == ".pdf":
        reader = PdfReader(BytesIO(data))
        parts: list[str] = []
        for page in reader.pages:
            parts.append(page.extract_text() or "")
        return "\n\n".join(parts)

    if ext == ".docx":
        import docx

        doc = docx.Document(BytesIO(data))
        return "\n".join(p.text for p in doc.paragraphs if p.text.strip())

    raise ValueError(
        f"Unsupported document type {ext or '(no extension)'}. "
        "Use .txt, .pdf, or .docx."
    )


def trim_document_text(text: str, max_chars: int) -> str:
    t = (text or "").strip()
    if len(t) <= max_chars:
        return t
    return t[:max_chars] + "\n\n[… document truncated …]"


def merge_reference_block_into_last_user(
    messages: list[dict],
    *,
    reference_parts: list[tuple[str, str]],
) -> list[dict]:
    """
    Append extracted reference text to the **last** user message only (copy of list).

    ``reference_parts`` is (display_name, text) per document.
    """
    if not reference_parts:
        return messages

    sections: list[str] = [REFERENCE_HEADER]
    used = len(sections[0])

    for name, body in reference_parts:
        header = f"### {name}\n"
        text = (body or "").strip()
        overhead = used + len(header) + 4
        remaining = MAX_REFERENCE_BLOCK_CHARS - overhead
        if remaining <= 80:
            sections.append("[… additional documents omitted (size limit) …]")
            break
        if len(text) > remaining:
            text = text[:remaining].rstrip() + "\n[… truncated …]"
        block = header + text
        sections.append(block)
        used += len(block) + 2
        if used >= MAX_REFERENCE_BLOCK_CHARS:
            break

    block = "\n\n".join(sections)
    if len(block) > MAX_REFERENCE_BLOCK_CHARS:
        block = (
            block[:MAX_REFERENCE_BLOCK_CHARS].rstrip()
            + "\n\n[… reference block truncated …]"
        )

    out = [dict(m) for m in messages]
    for i in range(len(out) - 1, -1, -1):
        if out[i].get("role") != "user":
            continue
        base = out[i].get("content") or ""
        if not isinstance(base, str):
            base = str(base)
        out[i] = {
            **out[i],
            "content": f"{base.rstrip()}\n\n{block}".strip(),
        }
        break
    return out
