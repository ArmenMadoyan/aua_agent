from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles

from backend.ai.agents import init_checkpointer
from backend.ai.course_output import GENERATED_COURSE_DIR, ensure_generated_dir
from backend.ai.vector_store import load_existing_files
from backend.config import DATABASE_URL
from backend.db import close_db, init_db, run_migrations
from backend.routes import router


@asynccontextmanager
async def lifespan(app: FastAPI):
    await init_db(DATABASE_URL)
    run_migrations()
    ensure_generated_dir()
    init_checkpointer()
    load_existing_files()
    yield
    await close_db()


app = FastAPI(title="Q&A Agent API", lifespan=lifespan)
app.include_router(router)

ensure_generated_dir()
app.mount(
    "/course/artifacts",
    StaticFiles(directory=str(GENERATED_COURSE_DIR)),
    name="course_artifacts",
)
