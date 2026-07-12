"""Application settings, loaded once from environment / .env."""
import os
from pathlib import Path

from dotenv import load_dotenv

# Repo root = two levels up from this file (backend/app/config.py)
ROOT_DIR = Path(__file__).resolve().parents[2]
load_dotenv(ROOT_DIR / ".env")


class Settings:
    gemini_api_key: str = os.getenv("GEMINI_API_KEY", "")
    gemini_model: str = os.getenv("GEMINI_MODEL", "gemini-2.5-flash")
    confidence_threshold: float = float(os.getenv("CONFIDENCE_THRESHOLD", "0.75"))
    upload_dir: Path = ROOT_DIR / "uploads"
    db_path: Path = ROOT_DIR / "documents.db"


settings = Settings()
settings.upload_dir.mkdir(parents=True, exist_ok=True)
