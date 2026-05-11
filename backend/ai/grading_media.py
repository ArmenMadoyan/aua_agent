"""Convert homework uploads (images, PDF) into base64 image payloads for vision models."""

from __future__ import annotations

import base64
from pathlib import Path

# Reasonable cap for token/cost control (multi-page scans).
MAX_PDF_PAGES = 12


def _pymupdf_module():
    """
    Return the PyMuPDF API module.

    Prefer ``import pymupdf`` so we never pick up the unrelated PyPI package ``fitz``
    (which does not provide ``.open`` for PDFs).
    """
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
    """
    Rasterize PDF pages to PNG. Returns list of (mime_type, base64_str) per page.
    """
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
    """
    Build attachment dicts for orchestrator messages: ``{"mime_type", "base64"}``.

    Supports common image types and PDF (rendered to PNG per page).
    """
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
