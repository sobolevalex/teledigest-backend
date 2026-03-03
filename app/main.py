"""
TeleDigest FastAPI entry point.
Loads .env from project root, sets up SQLite, CORS, static media, and API routes.
"""

from pathlib import Path

from dotenv import load_dotenv
from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles

from app.api import router
from app.core.database import Base, engine
from app.models import Track  # noqa: F401 - ensure Track is registered with Base


def _ensure_media_dir() -> None:
    """Create media directory at project root if it does not exist."""
    root = Path(".").resolve()
    (root / "media").mkdir(parents=True, exist_ok=True)


load_dotenv()
Base.metadata.create_all(bind=engine)
_ensure_media_dir()

app = FastAPI(title="TeleDigest")

app.add_middleware(
    "fastapi.middleware.cors.CORSMiddleware",
    allow_origins=["http://localhost:3000"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Mount media so frontend can GET /media/{track_id}.mp3
app.mount("/media", StaticFiles(directory="media"), name="media")

app.include_router(router)
