"""
Turn a batch of user uploads (same drag-and-drop) into display text, model text, and vision specs.

Images and likely-scanned PDFs become vision attachments. Text-heavy PDFs / TXT / DOCX become
extracted text so the user can say e.g. "first PDF is rubric, second is homework" in chat.
"""

from __future__ import annotations

import base64
from pathlib import Path
from typing import Any

from backend.app.document_text import extract_text_from_bytes, trim_document_text

# ── API attachment normalizer ────────────────────────────────────────

def _sniff_image_mime(data: bytes, declared: str) -> str:
    if data[:3] == b"\xff\xd8\xff":
        return "image/jpeg"
    if data[:8] == b"\x89PNG\r\n\x1a\n":
        return "image/png"
    if data[:6] in (b"GIF87a", b"GIF89a"):
        return "image/gif"
    if data[:4] == b"RIFF" and data[8:12] == b"WEBP":
        return "image/webp"
    return declared


def normalize_attachments(
    question: str, attachments: list[dict]
) -> tuple[str, list[dict]]:
    """
    Convert raw API attachments into a (question, image_attachments) pair the LLM can consume.

    The frontend sends PDFs as ``mime_type: "application/pdf"`` base64 blobs.
    Claude's vision API only accepts image types, so we normalise here:
      - Text-heavy PDFs  → extracted text appended to the question.
      - Scanned PDFs     → rasterised to PNG image attachments.
      - Images           → passed through unchanged.
    """
    doc_sections: list[str] = []
    image_attachments: list[dict] = []

    for att in attachments:
        mime = att.get("mime_type", "")
        b64 = att.get("base64", "")

        if mime != "application/pdf":
            raw = base64.standard_b64decode(b64)
            actual_mime = _sniff_image_mime(raw, mime)
            image_attachments.append({"mime_type": actual_mime, "base64": b64})
            continue

        raw = base64.standard_b64decode(b64)

        try:
            extracted = extract_text_from_bytes(filename="upload.pdf", data=raw).strip()
        except Exception:
            extracted = ""

        if len(extracted) >= SCANNED_PDF_CHAR_THRESHOLD:
            doc_sections.append(trim_document_text(extracted, 80_000))
        else:
            try:
                parts = pdf_bytes_to_png_base64_parts(raw)
            except Exception:
                parts = []

            if parts:
                for mime_type, b64_png in parts:
                    image_attachments.append({"mime_type": mime_type, "base64": b64_png})
            elif extracted:
                doc_sections.append(trim_document_text(extracted, 80_000))

    if doc_sections:
        question = (
            question.rstrip()
            + "\n\n--- Attached files (extracted text) ---\n\n"
            + "\n\n".join(doc_sections)
        ).strip()

    return question, image_attachments

# ── media conversion (formerly grading_media.py) ────────────────────

MAX_PDF_PAGES = 12


def _pymupdf_module():
    try:
        import pymupdf as m
    except ImportError:
        import fitz as m  # type: ignore[no-redef]
    if not hasattr(m, "open"):
        raise RuntimeError(
            "PDF homework needs PyMuPDF. Run: pip install pymupdf\n"
            "If you installed the wrong package: pip uninstall fitz && pip install pymupdf"
        )
    return m


def pdf_bytes_to_png_base64_parts(
    data: bytes, *, max_pages: int = MAX_PDF_PAGES
) -> list[tuple[str, str]]:
    """Rasterize PDF pages to PNG. Returns list of (mime_type, base64_str) per page."""
    mu = _pymupdf_module()

    doc = mu.open(stream=data, filetype="pdf")
    try:
        n = min(doc.page_count, max_pages)
        out: list[tuple[str, str]] = []
        for i in range(n):
            page = doc.load_page(i)
            mat = mu.Matrix(2.0, 2.0)
            pix = page.get_pixmap(matrix=mat, alpha=False)
            png = pix.tobytes("png")
            out.append(("image/png", base64.standard_b64encode(png).decode("ascii")))
        return out
    finally:
        doc.close()


def homework_file_to_attachment_specs(
    *,
    filename: str,
    data: bytes,
    max_pdf_pages: int = MAX_PDF_PAGES,
) -> list[dict[str, str]]:
    """Build attachment dicts: ``{"mime_type", "base64"}``."""
    ext = Path(filename or "").suffix.lower()
    if ext == ".pdf":
        parts = pdf_bytes_to_png_base64_parts(data, max_pages=max_pdf_pages)
        return [{"mime_type": mime, "base64": b64} for mime, b64 in parts]

    mime_by_ext = {
        ".jpg": "image/jpeg",
        ".jpeg": "image/jpeg",
        ".png": "image/png",
        ".webp": "image/webp",
        ".gif": "image/gif",
    }
    mime = mime_by_ext.get(ext)
    if not mime:
        raise ValueError(
            f"Unsupported homework file type {ext or '(none)'}. "
            "Use PDF, JPEG, PNG, WebP, or GIF."
        )
    return [
        {"mime_type": mime, "base64": base64.standard_b64encode(data).decode("ascii")}
    ]


# ── upload bundling ─────────────────────────────────────────────────

SCANNED_PDF_CHAR_THRESHOLD = 220
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
                    doc_sections.append(
                        f"### {name}\n[No extractable text; could not rasterize PDF.]"
                    )
            continue

        if ext in {".txt", ".docx"}:
            try:
                extracted = extract_text_from_bytes(filename=name, data=raw).strip()
            except ValueError as e:
                doc_sections.append(f"### {name}\n[Could not read: {e}]")
                continue
            if extracted:
                doc_sections.append(
                    f"### {name}\n{trim_document_text(extracted, 80_000)}"
                )
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
    display_content = (
        f"{prompt}\n\n*Attached ({len(filenames)}): {names_line}*"
        if filenames
        else prompt
    )

    return {
        "display_content": display_content,
        "model_content": model_content,
        "attachments": attachments,
        "filenames": filenames,
    }
