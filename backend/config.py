import os

from dotenv import load_dotenv

load_dotenv()

DATABASE_URL: str = os.getenv("DATABASE_URL", "")
OPENAI_API_KEY: str = os.getenv("OPENAI_API_KEY", "")
EMBEDDING_DIMENSION: int = int(os.getenv("EMBEDDING_DIMENSION", "1536"))
DEFAULT_USER_ID: int = int(os.getenv("DEFAULT_USER_ID", "1"))
GRADING_VISION_MODEL: str = os.getenv("GRADING_VISION_MODEL", "gpt-4o")
