"""Ingestion, validation, cleaning, PII masking, deduplication."""
import re
import pandas as pd
from .config import MAX_ROWS

COLS = ["record_id", "date", "rating", "category", "source", "text"]
PII = [(re.compile(r"[\w.+-]+@[\w-]+\.[\w.-]+"), "[EMAIL]"),
       (re.compile(r"https?://\S+|www\.\S+"), "[URL]"),
       (re.compile(r"\+?\d[\d\s().-]{7,}\d"), "[PHONE]")]

def mask_pii(text):
    for rx, tag in PII:
        text = rx.sub(tag, text)
    return text

def normalize(text):
    return re.sub(r"\s+", " ", str(text)).strip()

def read_file(f):
    name = str(getattr(f, "name", f)).lower()
    try:
        if name.endswith(".csv"):
            df = pd.read_csv(f, dtype=str, keep_default_na=False)
        elif name.endswith(".xlsx"):
            df = pd.read_excel(f, dtype=str, keep_default_na=False)
        else:
            raise ValueError("Unsupported file type. Please upload .csv or .xlsx.")
    except ValueError:
        raise
    except Exception as e:
        raise ValueError(f"Could not read the file: {e}")
    if df.empty:
        raise ValueError("The file has no data rows.")
    if len(df) > MAX_ROWS:
        raise ValueError(f"File has {len(df)} rows; the limit is {MAX_ROWS}.")
    return df

def prepare(raw):
    """Returns (clean_df, issues_df, duplicate_ids). Raises ValueError for missing columns."""
    df = raw.copy()
    df.columns = [str(c).strip().lower() for c in df.columns]
    missing = [c for c in COLS[1:] if c not in df.columns]
    if missing:
        raise ValueError(f"Missing required column(s): {', '.join(missing)}. Expected: {', '.join(COLS)} (record_id optional).")
    if "record_id" not in df.columns:
        df["record_id"] = ""
    df = df.astype(str)
    df["record_id"] = [r.strip() or f"R{i:06d}" for i, r in enumerate(df.record_id, 1)]
    df["row"] = range(2, len(df) + 2)  # spreadsheet row number
    d = pd.to_datetime(df.date, errors="coerce")
    r = pd.to_numeric(df.rating, errors="coerce")
    checks = {"date is not a valid date": d.isna(),
              "rating must be a number from 1 to 5": ~r.between(1, 5),
              "text is empty": df.text.str.strip() == "",
              "source is empty": df.source.str.strip() == "",
              "category is empty": df.category.str.strip() == ""}
    ok, issues = pd.Series(True, index=df.index), []
    for msg, bad in checks.items():
        issues += [{"row": df.row[i], "record_id": df.record_id[i], "problem": msg} for i in df.index[bad]]
        ok &= ~bad
    df = df[ok].copy()
    df["date"], df["rating"] = d[ok].dt.strftime("%Y-%m-%d"), r[ok]
    df["text"] = df.text.map(lambda t: mask_pii(normalize(t)))
    for c in ("category", "source"):
        df[c] = df[c].map(normalize)
    key = df.text.str.lower().str.replace(r"\W+", " ", regex=True).str.strip() + "|" + df.date + "|" + df.source.str.lower()
    dup = key.duplicated() | df.record_id.duplicated()
    return df.loc[~dup, COLS].reset_index(drop=True), pd.DataFrame(issues, columns=["row", "record_id", "problem"]), df.record_id[dup].tolist()
