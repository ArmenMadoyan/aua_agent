import re
import uuid
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent.parent.parent
GENERATED_COURSE_DIR = BASE_DIR / "generated_course"


def ensure_generated_dir() -> None:
    GENERATED_COURSE_DIR.mkdir(parents=True, exist_ok=True)


def safe_stem(name: str, max_len: int = 48) -> str:
    s = re.sub(r"[^\w\s-]", "", name, flags=re.UNICODE)
    s = re.sub(r"[-\s]+", "_", s.strip()).strip("_")
    return (s[:max_len] if s else "document") + f"_{uuid.uuid4().hex[:8]}"


def artifact_url(filename: str) -> str:
    return f"/course/artifacts/{filename}"
