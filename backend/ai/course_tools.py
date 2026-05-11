from langchain_core.tools import tool

from backend.ai.course_builders import build_pdf, build_powerpoint
from backend.ai.course_output import (
    GENERATED_COURSE_DIR,
    artifact_url,
    ensure_generated_dir,
    safe_stem,
)


def _parse_slides_text(slides_text: str) -> list[tuple[str, list[str]]]:
    slides: list[tuple[str, list[str]]] = []
    current_title: str | None = None
    current_bullets: list[str] = []

    def flush() -> None:
        nonlocal current_title, current_bullets
        if current_title is not None:
            slides.append((current_title, current_bullets))
        current_title = None
        current_bullets = []

    for raw_line in slides_text.splitlines():
        line = raw_line.strip()
        if not line:
            continue
        upper = line.upper()
        if upper.startswith("SLIDE:"):
            flush()
            current_title = line.split(":", 1)[1].strip() or "Slide"
            current_bullets = []
        elif line.startswith(("## ", "### ")):
            flush()
            current_title = line.lstrip("#").strip() or "Slide"
            current_bullets = []
        elif line.startswith(("- ", "* ", "• ")):
            if current_title is None:
                current_title = "Slide"
            current_bullets.append(line[2:].strip())
        elif current_title is None:
            current_title = line
        else:
            current_bullets.append(line)

    flush()

    if not slides and slides_text.strip():
        slides = [("Slides", [slides_text.strip()])]

    return slides


@tool(
    description=(
        "Create a real PowerPoint (.pptx) file from slide content you write. "
        "Use when the user wants lecture slides or a slide deck. "
        "Argument deck_title: short name for the file. "
        "Argument slides_text: one block per slide. Start each slide with a line "
        "'SLIDE: Title Here' then bullet lines starting with '- '. "
        "Example:\n"
        "SLIDE: Introduction\n"
        "- Goal of today\n"
        "- Outline\n\n"
        "SLIDE: Next topic\n"
        "- Point one\n"
        "Returns the download path for the user."
    )
)
def create_powerpoint_deck(deck_title: str, slides_text: str) -> str:
    ensure_generated_dir()
    slides = _parse_slides_text(slides_text)
    stem = safe_stem(deck_title)
    filename = f"{stem}.pptx"
    out_path = GENERATED_COURSE_DIR / filename
    build_powerpoint(slides, out_path)
    url = artifact_url(filename)
    return (
        f"PowerPoint saved as '{filename}'. "
        f"Download from: {url} (full URL: base URL of this API + {url})"
    )


@tool(
    description=(
        "Create a real PDF file for homework, quiz, midterm, final exam, or any written "
        "assessment or assignment. Use when the user wants homework, quizzes, exams, or "
        "problem sets as a PDF. "
        "Argument document_type: one of homework, quiz, midterm, final_exam, or other. "
        "Argument title: document title shown at the top. "
        "Argument body: full text of the assignment or exam (questions, instructions, "
        "space descriptions). Use plain text; separate major sections with a blank line. "
        "Returns the download path for the user."
    )
)
def create_course_pdf(document_type: str, title: str, body: str) -> str:
    ensure_generated_dir()
    stem = safe_stem(f"{document_type}_{title}")
    filename = f"{stem}.pdf"
    out_path = GENERATED_COURSE_DIR / filename
    subtitle = f"Type: {document_type.replace('_', ' ').title()}"
    build_pdf(title, body, out_path, subtitle=subtitle)
    url = artifact_url(filename)
    return (
        f"PDF saved as '{filename}'. "
        f"Download from: {url} (full URL: base URL of this API + {url})"
    )
