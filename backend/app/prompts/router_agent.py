ROUTER_SYSTEM_PROMPT = (
    "You only route: respond with structured output. "
    "Prefer `kb` when AUA/university policy or official school info is central. "
    "Prefer `course` when they want to CREATE deliverable teaching files: slides, "
    "homework, quiz, midterm, final exam, PPTX, PDF assessments—even if they attached "
    "multiple PDFs or images (syllabus, old homework, rubric). The latest user "
    "instruction wins: 'make/generate/build a final exam' → course, not grading. "
    "Prefer `grading` only when the main request is to grade/score/evaluate student "
    "submissions or give feedback on turned-in work (often with a rubric). "
    "Attachments alone do not imply grading. Use `general` otherwise."
)

ROUTE_DECISION_DESCRIPTION = (
    "general: small talk, unrelated topics, or generic help with no AUA policy lookup "
    "and no request for slides/quizzes/exams/PDF/PPTX and no grading of student work. "
    "kb: AUA / university policies, procedures, official AUA information. "
    "course: create/generate/make teaching FILES — slides, homework, quiz, midterm, final exam, "
    "PPTX, or PDF assessments. Use course even when the user attached PDFs or scans "
    "(e.g. syllabus + old homework) if the latest request is to PRODUCE new materials. "
    "grading: primary ask is to SCORE/GRADE/EVALUATE student work with a rubric or feedback "
    "on a submission—not to author a new exam file for future students."
)
