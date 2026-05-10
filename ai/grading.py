"""Vision-based homework grading: transcribe student work and apply an instructor rubric."""

from __future__ import annotations

from typing import Any

from langchain_core.messages import AIMessage, HumanMessage, SystemMessage

GRADING_SYSTEM = """You are an expert grader for university-level homework.

The instructor may paste a rubric, upload several files at once, and explain in plain language
which file is the rubric, which is the student submission, syllabus, etc. Extracted text appears
under '--- Attached files (extracted text) ---' when applicable; images/scans are separate inputs.
They may upload photos or scans of student work (often handwritten), or typed/printed pages.

Internally read the submission carefully, map it to the rubric, and assign fair points. Do not
invent content that is not visible. If image quality or handwriting limits certainty, reflect
that only inside the student-facing feedback (briefly), not as a separate extraction dump.

**Reply format (strict):** Output ONLY these two Markdown sections, in this order—nothing else
(no preamble, no transcription of the student work, no rubric walkthrough, no "## Student work",
no "## Rubric application"):

## Scores
- Per-criterion or per-row points as the rubric implies, plus **Total** / **Max** when you can infer max.
- Use a compact table or bullet list.

## Feedback to student
- Short, constructive comments the instructor can return to the student (strengths, what to improve).
- Optional one line if something was unclear or illegible in the scan."""


def build_grading_lc_messages(messages: list[dict[str, Any]]) -> list:
    """Turn chat dicts (optional ``attachments`` on user turns) into LangChain messages."""
    last_user_i: int | None = None
    for i in range(len(messages) - 1, -1, -1):
        if messages[i].get("role") == "user":
            last_user_i = i
            break

    lc: list = [SystemMessage(content=GRADING_SYSTEM)]
    for i, m in enumerate(messages):
        role = m.get("role")
        content = m.get("model_content")
        if content is None:
            content = m.get("content")
        if content is None:
            content = ""
        if not isinstance(content, str):
            content = str(content)

        if role == "user":
            attachments = list(m.get("attachments") or [])
            if last_user_i is not None and i != last_user_i:
                attachments = []
            if attachments:
                parts: list[dict[str, Any]] = []
                if content.strip():
                    parts.append({"type": "text", "text": content})
                for spec in attachments:
                    mt = spec.get("mime_type") or "image/png"
                    b64 = spec.get("base64") or ""
                    if not b64:
                        continue
                    parts.append(
                        {
                            "type": "image_url",
                            "image_url": {"url": f"data:{mt};base64,{b64}"},
                        }
                    )
                if len(parts) == 1 and parts[0].get("type") == "image_url":
                    parts.insert(
                        0,
                        {
                            "type": "text",
                            "text": "Grade this homework submission using the rubric and instructions in our conversation.",
                        },
                    )
                lc.append(HumanMessage(content=parts))
            else:
                lc.append(HumanMessage(content=content))
        elif role == "assistant":
            lc.append(AIMessage(content=content))
    return lc
