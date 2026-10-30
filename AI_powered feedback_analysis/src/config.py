from pathlib import Path
import os

ROOT = Path(__file__).resolve().parents[1]
DATA_DIR = Path(os.getenv("FEEDBACK_DATA_DIR", ROOT / "data"))
DATABASE_PATH = Path(os.getenv("FEEDBACK_DATABASE", DATA_DIR / "feedback.sqlite3"))
MAX_UPLOAD_BYTES = 10 * 1024 * 1024
MAX_ROWS = 10_000
MODEL_VERSION = "local-lexicon-1.0"
