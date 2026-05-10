"""
Turn a batch of user uploads (same drag-and-drop) into display text, model text, and vision specs.

Images and likely-scanned PDFs become vision attachments. Text-heavy PDFs / TXT / DOCX become
extracted text so the user can say e.g. "first PDF is rubric, second is homework" in chat.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

from ai.document_text import extract_text_from_bytes, trim_document_text
from ai.grading_media import homework_file_to_attachment_specs, pdf_bytes_to_png_base64_parts

# If a PDF yields less plain text than this, treat it as a scan and rasterize for vision.
SCANNED_PDF_CHAR_THRESHOLD = 220

# Max vision pages/images across one message (cost / context).
MAX_VISION_ITEMS_PER_MESSAGE = 24

_IMAGE_EXT = {".png", ".jpg", ".jpeg", ".webp", ".gif"}


def bundle_chat_uploads(*, prompt: str, uploads: list[Any]) -> dict[str, Any]:
    """
    Returns:
      ``display_content`` — short text for UI + DB (prompt + attached filenames).
      ``model_content`` — full text + extracted file bodies for the LLM.
      ``attachments`` — list of ``{mime_type, base64}`` for vision (may be empty).
      ``filenames`` — list of original names (for logging / persist).
    """
    prompt = (prompt or "").strip()
    if not uploads:
        return {
            "display_content": prompt,
            "model_content": prompt,
            "attachments": [],
            "filenames": [],
        }

    doc_sections: list[str] = []
    attachments: list[dict[str, str]] = []
    filenames: list[str] = []
    vision_budget = MAX_VISION_ITEMS_PER_MESSAGE

    for u in uploads:
        name = (getattr(u, "name", None) or "file").strip() or "file"
        filenames.append(name)
        raw = u.getvalue()
        ext = Path(name).suffix.lower()

        if ext in _IMAGE_EXT:
            try:
                specs = homework_file_to_attachment_specs(filename=name, data=raw)
            except ValueError:
                continue
            for spec in specs:
                if vision_budget <= 0:
                    doc_sections.append(
                        f"### {name}\n[Skipped extra image(s): vision page limit ({MAX_VISION_ITEMS_PER_MESSAGE}) reached.]"
                    )
                    break
                attachments.append(spec)
                vision_budget -= 1
            continue

        if ext == ".pdf":
            try:
                extracted = extract_text_from_bytes(filename=name, data=raw).strip()
            except ValueError:
                extracted = ""
            if len(extracted) >= SCANNED_PDF_CHAR_THRESHOLD:
                doc_sections.append(
                    f"### {name}\n{trim_document_text(extracted, 80_000)}"
                )
            else:
                try:
                    parts = pdf_bytes_to_png_base64_parts(
                        raw, max_pages=min(12, vision_budget)
                    )
                except Exception:
                    parts = []
                if not parts and extracted:
                    doc_sections.append(
                        f"### {name}\n{trim_document_text(extracted, 80_000)}"
                    )
                    continue
                for mime, b64 in parts:
                    if vision_budget <= 0:
                        break
                    attachments.append({"mime_type": mime, "base64": b64})
                    vision_budget -= 1
                if not parts and not extracted:
                    doc_sections.append(f"### {name}\n[No extractable text; could not rasterize PDF.]")
            continue

        if ext in {".txt", ".docx"}:
            try:
                extracted = extract_text_from_bytes(filename=name, data=raw).strip()
            except ValueError as e:
                doc_sections.append(f"### {name}\n[Could not read: {e}]")
                continue
            if extracted:
                doc_sections.append(f"### {name}\n{trim_document_text(extracted, 80_000)}")
            else:
                doc_sections.append(f"### {name}\n[Empty or no text extracted.]")
            continue

        doc_sections.append(
            f"### {name}\n[Unsupported type `{ext}` — skipped. Use images, PDF, TXT, or DOCX.]"
        )

    model_content = prompt
    if doc_sections:
        model_content = (
            f"{prompt}\n\n--- Attached files (extracted text) ---\n\n"
            + "\n\n".join(doc_sections)
        ).strip()

    names_line = ", ".join(filenames)
    display_content = f"{prompt}\n\n*Attached ({len(filenames)}): {names_line}*" if filenames else prompt

    return {
        "display_content": display_content,
        "model_content": model_content,
        "attachments": attachments,
        "filenames": filenames,
    }
