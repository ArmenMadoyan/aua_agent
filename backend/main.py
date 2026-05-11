import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles

from backend.app.main_init import init_checkpointer
from backend.app.orchestrator import init_agents
from backend.app.agents.course_agent import GENERATED_COURSE_DIR, ensure_generated_dir
from backend.app.kb_rag import load_existing_files
from backend.config import DATABASE_URL
from backend.db import close_db, init_db, run_migrations
from backend.routes import router

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(name)s] %(levelname)s %(message)s",
)


@asynccontextmanager
async def lifespan(app: FastAPI):
    await init_db(DATABASE_URL)
    run_migrations()
    ensure_generated_dir()
    checkpointer = init_checkpointer()
    init_agents(checkpointer=checkpointer)
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
