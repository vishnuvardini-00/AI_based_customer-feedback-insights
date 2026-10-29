"""Configuration from environment variables (no secrets needed; none are hardcoded)."""
import os

def _int(name, default):
    try:
        return max(1, int(os.environ.get(name, default)))
    except ValueError:
        return default

MAX_ROWS = _int("FBI_MAX_ROWS", 50_000)
BATCH_SIZE = _int("FBI_BATCH_SIZE", 500)
TIMEOUT_S = _int("FBI_TIMEOUT_S", 120)
MIN_N = _int("FBI_MIN_N", 10)
# DB path: FEEDBACK_DB (read at call time in db.py). No API keys are used; analysis is fully local.
