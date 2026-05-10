import os

from dotenv import load_dotenv

load_dotenv()

API_KEY = os.getenv("OPENAI_API_KEY")

# Vision-capable model for handwritten / scanned homework grading (override in .env if needed).
GRADING_VISION_MODEL = os.getenv("GRADING_VISION_MODEL", "gpt-4o")
