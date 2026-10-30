from __future__ import annotations

import json
import sqlite3
import uuid
from contextlib import contextmanager
from datetime import datetime, timezone
from pathlib import Path

import pandas as pd

from .config import DATABASE_PATH, DATA_DIR, MODEL_VERSION
from .sentiment import predict
from .themes import discover_themes


def connect(path: Path | str | None = None) -> sqlite3.Connection:
    target = Path(path or DATABASE_PATH)
    target.parent.mkdir(parents=True, exist_ok=True)
    connection = sqlite3.connect(target, timeout=30)
    connection.row_factory = sqlite3.Row
    connection.execute("PRAGMA foreign_keys=ON")
    return connection


@contextmanager
def managed_connection(path: Path | str | None = None):
    db = connect(path)
    try:
        yield db
        db.commit()
    except Exception:
        db.rollback()
        raise
    finally:
        db.close()


def initialize(path: Path | str | None = None) -> None:
    with managed_connection(path) as db:
        db.executescript("""
        CREATE TABLE IF NOT EXISTS datasets (
            dataset_id TEXT PRIMARY KEY, name TEXT NOT NULL, synthetic INTEGER NOT NULL DEFAULT 0,
            created_at TEXT NOT NULL, imported_count INTEGER NOT NULL DEFAULT 0,
            source_fingerprint TEXT UNIQUE
        );
        CREATE TABLE IF NOT EXISTS feedback (
            record_id TEXT PRIMARY KEY, dataset_id TEXT NOT NULL REFERENCES datasets(dataset_id) ON DELETE CASCADE,
            original_id TEXT, feedback_text TEXT NOT NULL, date TEXT, rating REAL,
            category TEXT, source TEXT, product TEXT, customer_segment TEXT,
            duplicate_candidate INTEGER NOT NULL DEFAULT 0, invalid_date INTEGER NOT NULL DEFAULT 0
        );
        CREATE INDEX IF NOT EXISTS idx_feedback_dataset_date ON feedback(dataset_id, date);
        CREATE TABLE IF NOT EXISTS analysis_runs (
            run_id TEXT PRIMARY KEY, dataset_id TEXT NOT NULL REFERENCES datasets(dataset_id),
            model_version TEXT NOT NULL, created_at TEXT NOT NULL, record_count INTEGER NOT NULL
        );
        CREATE TABLE IF NOT EXISTS analyses (
            run_id TEXT NOT NULL REFERENCES analysis_runs(run_id) ON DELETE CASCADE,
            record_id TEXT NOT NULL REFERENCES feedback(record_id) ON DELETE CASCADE,
            sentiment TEXT NOT NULL, confidence REAL NOT NULL, theme_id TEXT,
            PRIMARY KEY(run_id, record_id)
        );
        CREATE TABLE IF NOT EXISTS themes (
            theme_id TEXT PRIMARY KEY, run_id TEXT NOT NULL REFERENCES analysis_runs(run_id) ON DELETE CASCADE,
            name TEXT NOT NULL, keywords TEXT NOT NULL, generated_name TEXT NOT NULL,
            excluded INTEGER NOT NULL DEFAULT 0, approved INTEGER NOT NULL DEFAULT 0
        );
        CREATE TABLE IF NOT EXISTS corrections (
            record_id TEXT PRIMARY KEY REFERENCES feedback(record_id) ON DELETE CASCADE,
            sentiment TEXT NOT NULL, reviewer TEXT NOT NULL, updated_at TEXT NOT NULL
        );
        CREATE TABLE IF NOT EXISTS insights (
            insight_id TEXT PRIMARY KEY, run_id TEXT NOT NULL REFERENCES analysis_runs(run_id) ON DELETE CASCADE,
            title TEXT NOT NULL, body TEXT NOT NULL, evidence_json TEXT NOT NULL,
            status TEXT NOT NULL DEFAULT 'pending', reviewer TEXT, updated_at TEXT
        );
        CREATE TABLE IF NOT EXISTS review_history (
            event_id TEXT PRIMARY KEY, entity_type TEXT NOT NULL, entity_id TEXT NOT NULL,
            action TEXT NOT NULL, reason TEXT, reviewer TEXT NOT NULL, created_at TEXT NOT NULL
        );
        """)
        dataset_columns = {row["name"] for row in db.execute("PRAGMA table_info(datasets)")}
        if "source_fingerprint" not in dataset_columns:
            db.execute("ALTER TABLE datasets ADD COLUMN source_fingerprint TEXT")
            db.execute("CREATE UNIQUE INDEX IF NOT EXISTS idx_dataset_fingerprint ON datasets(source_fingerprint)")
        feedback_columns = {row["name"] for row in db.execute("PRAGMA table_info(feedback)")}
        if "invalid_date" not in feedback_columns:
            db.execute("ALTER TABLE feedback ADD COLUMN invalid_date INTEGER NOT NULL DEFAULT 0")


@contextmanager
def transaction(path: Path | str | None = None):
    db = connect(path)
    try:
        db.execute("BEGIN")
        yield db
        db.commit()
    except Exception:
        db.rollback()
        raise
    finally:
        db.close()


def save_dataset(
    name: str, records: pd.DataFrame, synthetic: bool = False, path: Path | str | None = None,
    source_fingerprint: str | None = None,
) -> str:
    initialize(path)
    dataset_id = str(uuid.uuid4())
    with transaction(path) as db:
        if source_fingerprint:
            previous = db.execute(
                "SELECT dataset_id FROM datasets WHERE source_fingerprint=?", (source_fingerprint,)
            ).fetchone()
            if previous:
                return previous["dataset_id"]
        db.execute(
            "INSERT INTO datasets(dataset_id,name,synthetic,created_at,imported_count,source_fingerprint) VALUES(?,?,?,?,?,?)",
            (dataset_id, name, int(synthetic), _now(), len(records), source_fingerprint),
        )
        columns = [
            "record_id", "original_id", "feedback_text", "date", "rating",
            "category", "source", "product", "customer_segment", "duplicate_candidate", "invalid_date",
        ]
        db.executemany(
            f"INSERT INTO feedback(dataset_id,{','.join(columns)}) VALUES({','.join('?' for _ in range(len(columns)+1))})",
            [(dataset_id, *[_db_value(row.get(col)) for col in columns]) for row in records.to_dict("records")],
        )
    return dataset_id


def load_datasets(path: Path | str | None = None) -> pd.DataFrame:
    initialize(path)
    with managed_connection(path) as db:
        return pd.read_sql_query("SELECT * FROM datasets ORDER BY created_at DESC", db)


def load_feedback(dataset_id: str, path: Path | str | None = None) -> pd.DataFrame:
    with managed_connection(path) as db:
        return pd.read_sql_query("SELECT * FROM feedback WHERE dataset_id=? ORDER BY date, record_id", db, params=(dataset_id,))


def analyze(dataset_id: str, path: Path | str | None = None) -> str:
    records = load_feedback(dataset_id, path)
    if records.empty:
        raise ValueError("This dataset has no valid feedback to analyse.")
    predictions = [predict(text) for text in records.feedback_text]
    theme_rows, assignments = discover_themes(records.feedback_text.tolist())
    run_id = str(uuid.uuid4())
    with transaction(path) as db:
        db.execute(
            "INSERT INTO analysis_runs VALUES(?,?,?,?,?)",
            (run_id, dataset_id, MODEL_VERSION, _now(), len(records)),
        )
        for theme in theme_rows:
            db.execute(
                "INSERT INTO themes(theme_id,run_id,name,keywords,generated_name) VALUES(?,?,?,?,?)",
                (theme["theme_id"], run_id, theme["name"], json.dumps(theme["keywords"]), theme["name"]),
            )
        db.executemany(
            "INSERT INTO analyses(run_id,record_id,sentiment,confidence,theme_id) VALUES(?,?,?,?,?)",
            [
                (run_id, row.record_id, predictions[i]["sentiment"], predictions[i]["confidence"], assignments[i])
                for i, (_, row) in enumerate(records.iterrows())
            ],
        )
    return run_id


def load_analysis(dataset_id: str, path: Path | str | None = None) -> tuple[str | None, pd.DataFrame, pd.DataFrame]:
    with managed_connection(path) as db:
        run = db.execute(
            "SELECT run_id FROM analysis_runs WHERE dataset_id=? ORDER BY created_at DESC LIMIT 1", (dataset_id,)
        ).fetchone()
        if not run:
            return None, pd.DataFrame(), pd.DataFrame()
        run_id = run["run_id"]
        rows = pd.read_sql_query("""
            SELECT f.*, a.sentiment AS predicted_sentiment, a.confidence, a.theme_id,
                   COALESCE(c.sentiment,a.sentiment) AS sentiment
            FROM feedback f JOIN analyses a ON a.record_id=f.record_id
            LEFT JOIN corrections c ON c.record_id=f.record_id
            WHERE f.dataset_id=? AND a.run_id=?
        """, db, params=(dataset_id, run_id))
        themes = pd.read_sql_query(
            "SELECT * FROM themes WHERE run_id=? ORDER BY name", db, params=(run_id,)
        )
        return run_id, rows, themes


def save_correction(record_id: str, sentiment: str, reviewer: str, path: Path | str | None = None) -> None:
    if sentiment not in {"positive", "neutral", "negative", "uncertain"}:
        raise ValueError("Invalid sentiment label.")
    reviewer = reviewer.strip()
    if not reviewer:
        raise ValueError("Enter a reviewer name.")
    with transaction(path) as db:
        db.execute("""
            INSERT INTO corrections VALUES(?,?,?,?)
            ON CONFLICT(record_id) DO UPDATE SET sentiment=excluded.sentiment,
            reviewer=excluded.reviewer, updated_at=excluded.updated_at
        """, (record_id, sentiment, reviewer, _now()))
        _audit(db, "sentiment", record_id, f"corrected to {sentiment}", None, reviewer)


def save_insight_review(
    insight_id: str, action: str, reviewer: str, reason: str = "", path: Path | str | None = None
) -> None:
    if action not in {"approved", "dismissed", "investigate", "inconclusive"}:
        raise ValueError("Invalid review action.")
    reviewer = reviewer.strip()
    if not reviewer:
        raise ValueError("Enter a reviewer name.")
    with transaction(path) as db:
        cursor = db.execute(
            "UPDATE insights SET status=?,reviewer=?,updated_at=? WHERE insight_id=?",
            (action, reviewer, _now(), insight_id),
        )
        if cursor.rowcount == 0:
            raise ValueError("Insight was not found.")
        _audit(db, "insight", insight_id, action, reason.strip() or None, reviewer)


def edit_insight(insight_id: str, title: str, body: str, reviewer: str, path: Path | str | None = None) -> None:
    if not title.strip() or not body.strip() or not reviewer.strip():
        raise ValueError("Insight title, wording, and reviewer are required.")
    with transaction(path) as db:
        cursor = db.execute(
            "UPDATE insights SET title=?,body=?,reviewer=?,updated_at=? WHERE insight_id=?",
            (title.strip(), body.strip(), reviewer.strip(), _now(), insight_id),
        )
        if cursor.rowcount == 0:
            raise ValueError("Insight was not found.")
        _audit(db, "insight", insight_id, "edited", None, reviewer.strip())


def rename_theme(theme_id: str, name: str, reviewer: str, path: Path | str | None = None) -> None:
    if not name.strip() or not reviewer.strip():
        raise ValueError("Theme name and reviewer are required.")
    with transaction(path) as db:
        cursor = db.execute("UPDATE themes SET name=?,approved=1 WHERE theme_id=?", (name.strip(), theme_id))
        if cursor.rowcount == 0:
            raise ValueError("Theme was not found.")
        _audit(db, "theme", theme_id, "renamed", name.strip(), reviewer.strip())


def generate_insights(run_id: str, path: Path | str | None = None) -> int:
    with managed_connection(path) as db:
        result = pd.read_sql_query("""
            SELECT t.theme_id,t.name,a.sentiment,f.record_id,f.feedback_text
            FROM analyses a JOIN feedback f ON f.record_id=a.record_id
            LEFT JOIN themes t ON t.theme_id=a.theme_id WHERE a.run_id=?
        """, db, params=(run_id,))
    if result.empty:
        return 0
    created = 0
    for theme, group in result.groupby("name", dropna=False):
        neg = group[group.sentiment == "negative"]
        if len(neg) < 2:
            continue
        evidence = {
            "theme": theme or "Unassigned",
            "negative_count": len(neg),
            "theme_count": len(group),
            "sample_comments": neg.feedback_text.head(2).tolist(),
            "record_ids": neg.record_id.head(10).tolist(),
        }
        title = f"Negative feedback observed in {theme or 'unassigned feedback'}"
        body = (
            f"Observed evidence: {len(neg)} of {len(group)} records assigned to this theme "
            "were labelled negative by the local baseline model. This is a descriptive finding, "
            "not a verified cause. Hypothesis: an experience associated with this theme may merit "
            "investigation. Suggested next step: review the cited records and compare relevant "
            "products, dates, and categories. Limitations: small samples and model errors may affect this result."
        )
        with transaction(path) as db:
            if db.execute(
                "SELECT 1 FROM insights WHERE run_id=? AND title=?", (run_id, title)
            ).fetchone():
                continue
            db.execute(
                "INSERT INTO insights VALUES(?,?,?,?,?,'pending',NULL,NULL)",
                (str(uuid.uuid4()), run_id, title, body, json.dumps(evidence)),
            )
            created += 1
    return created


def load_insights(run_id: str, path: Path | str | None = None) -> pd.DataFrame:
    with managed_connection(path) as db:
        return pd.read_sql_query(
            "SELECT * FROM insights WHERE run_id=? ORDER BY rowid DESC", db, params=(run_id,)
        )


def _audit(db: sqlite3.Connection, kind: str, item_id: str, action: str, reason: str | None, reviewer: str):
    db.execute(
        "INSERT INTO review_history VALUES(?,?,?,?,?,?,?)",
        (str(uuid.uuid4()), kind, item_id, action, reason, reviewer, _now()),
    )


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _db_value(value):
    if value is None or (not isinstance(value, (str, bytes)) and pd.isna(value)):
        return None
    if isinstance(value, bool):
        return int(value)
    return value
