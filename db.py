"""SQLite persistence. DB path comes from env var FEEDBACK_DB (default feedback.db)."""
import os, sqlite3
import pandas as pd

def conn():
    return sqlite3.connect(os.environ.get("FEEDBACK_DB", "feedback.db"))

def init():
    with conn() as c:
        c.executescript("""
CREATE TABLE IF NOT EXISTS feedback(record_id TEXT PRIMARY KEY, date TEXT, rating REAL,
 category TEXT, source TEXT, text TEXT, sentiment TEXT, score REAL, conf REAL,
 agreement TEXT, theme TEXT, dist REAL, review TEXT);
CREATE TABLE IF NOT EXISTS insights(id INTEGER PRIMARY KEY AUTOINCREMENT, kind TEXT, theme TEXT,
 summary TEXT, hypothesis TEXT, evidence TEXT, status TEXT DEFAULT 'draft');""")

def load():
    with conn() as c:
        return pd.read_sql("SELECT * FROM feedback ORDER BY date, record_id", c)

def add(df, batch_size=500):
    """Insert in batches (each its own transaction). Existing record_ids are ignored.
    Returns (inserted, errors); a failed batch is reported and the others still save."""
    rows = df[["record_id", "date", "rating", "category", "source", "text"]].values.tolist()
    inserted, errors = 0, []
    for i in range(0, len(rows), batch_size):
        try:
            with conn() as c:
                before = c.total_changes
                c.executemany("INSERT OR IGNORE INTO feedback(record_id,date,rating,category,source,text) VALUES(?,?,?,?,?,?)",
                              rows[i:i + batch_size])
                inserted += c.total_changes - before
        except Exception as e:
            errors.append(f"rows {i + 1}-{i + len(rows[i:i + batch_size])}: {e}")
    return inserted, errors

def save_analysis(df):
    rows = [(r.sentiment, r.score, r.conf, r.agreement, r.theme, r.dist, r.record_id) for r in df.itertuples()]
    with conn() as c:  # single transaction: all-or-nothing
        c.executemany("UPDATE feedback SET sentiment=?,score=?,conf=?,agreement=?,theme=?,dist=? WHERE record_id=?", rows)

def merge_themes(olds, new):
    """Rename one theme or merge several into `new` (feedback and insights)."""
    q = ",".join("?" * len(olds))
    with conn() as c:
        c.execute(f"UPDATE feedback SET theme=? WHERE theme IN ({q})", [new, *olds])
        c.execute(f"UPDATE insights SET theme=? WHERE theme IN ({q})", [new, *olds])

def set_review(record_id, verdict):
    with conn() as c:
        c.execute("UPDATE feedback SET review=? WHERE record_id=?", (verdict, record_id))

def replace_drafts(items):
    """Replace untouched draft insights; edited/dismissed ones are kept."""
    with conn() as c:
        c.execute("DELETE FROM insights WHERE status='draft'")
        c.executemany("INSERT INTO insights(kind,theme,summary,hypothesis,evidence) VALUES(?,?,?,?,?)",
                      [(i["kind"], i["theme"], i["summary"], i["hypothesis"], i["evidence"]) for i in items])

def insights():
    with conn() as c:
        return pd.read_sql("SELECT * FROM insights ORDER BY id", c)

def update_insight(iid, summary=None, status=None):
    with conn() as c:
        if summary is not None:
            c.execute("UPDATE insights SET summary=?, status='edited' WHERE id=?", (summary, iid))
        if status:
            c.execute("UPDATE insights SET status=? WHERE id=?", (status, iid))

def clear_all():
    with conn() as c:
        c.executescript("DELETE FROM feedback; DELETE FROM insights;")
