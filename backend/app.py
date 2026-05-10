from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles

from ai.course_output import GENERATED_COURSE_DIR, ensure_generated_dir
from ai.vector_store import load_existing_files
from backend.db import init_db
from backend.routers.chat import chat_router
from backend.routers.knowledge import knowledge_router

app = FastAPI(title="Q&A Agent API")

app.include_router(chat_router)
app.include_router(knowledge_router)

ensure_generated_dir()

app.mount(
    "/course/artifacts",
    StaticFiles(directory=str(GENERATED_COURSE_DIR)),
    name="course_artifacts",
)


@app.on_event("startup")
async def startup_event():
    init_db()
    ensure_generated_dir()
    load_existing_files()
