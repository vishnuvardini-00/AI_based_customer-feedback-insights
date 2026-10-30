from __future__ import annotations

import hashlib
import io
import uuid
from collections import Counter

import pandas as pd

from .config import MAX_ROWS, MAX_UPLOAD_BYTES
from .privacy import duplicate_key, mask_pii, normalize_text

CANONICAL = [
    "feedback_id", "feedback_text", "date", "rating", "category",
    "source", "product", "customer_segment",
]
OPTIONAL = ["date", "rating", "category", "source", "product", "customer_segment"]


def read_upload(name: str, content: bytes) -> pd.DataFrame:
    if len(content) > MAX_UPLOAD_BYTES:
        raise ValueError("File exceeds the 10 MB upload limit.")
    suffix = name.casefold().rsplit(".", 1)[-1] if "." in name else ""
    try:
        if suffix == "csv":
            frame = pd.read_csv(io.BytesIO(content))
        elif suffix in {"xlsx", "xls"}:
            frame = pd.read_excel(io.BytesIO(content))
        else:
            raise ValueError("Unsupported file type. Upload CSV or Excel (.xlsx/.xls).")
    except ValueError:
        raise
    except Exception as exc:
        raise ValueError(f"Could not read the uploaded file: {exc}") from exc
    if len(frame) > MAX_ROWS:
        raise ValueError(f"File has {len(frame):,} rows; limit is {MAX_ROWS:,}.")
    if frame.empty:
        raise ValueError("The uploaded file contains no records.")
    return frame


def suggested_mapping(columns: list[str]) -> dict[str, str | None]:
    folded = {str(column).strip().casefold(): column for column in columns}
    aliases = {
        "feedback_id": ["feedback_id", "id", "review_id", "record_id"],
        "feedback_text": ["feedback_text", "text", "feedback", "comment", "review"],
        "date": ["date", "created_at", "timestamp", "feedback_date"],
        "rating": ["rating", "score", "stars"],
        "category": ["category", "type"],
        "source": ["source", "channel"],
        "product": ["product", "item"],
        "customer_segment": ["customer_segment", "segment"],
    }
    return {
        field: next((folded[a] for a in names if a in folded), None)
        for field, names in aliases.items()
    }


def validate_and_clean(
    frame: pd.DataFrame,
    mapping: dict[str, str | None],
    dataset_key: str,
    exclude_duplicates: bool = False,
) -> tuple[pd.DataFrame, pd.DataFrame, dict[str, int]]:
    source_text = mapping.get("feedback_text")
    if not source_text or source_text not in frame.columns:
        raise ValueError("Map a column to feedback_text before validating.")
    rows, rejected = [], []
    seen: Counter[str] = Counter()
    seen_ids: Counter[str] = Counter()
    duplicates = 0
    for row_number, (_, row) in enumerate(frame.iterrows(), start=2):
        raw_text = normalize_text(row.get(source_text))
        if not raw_text:
            rejected.append({"source_row": row_number, "reason": "Feedback text is empty"})
            continue
        key = duplicate_key(raw_text)
        duplicate = seen[key] > 0
        seen[key] += 1
        duplicates += int(duplicate)
        if duplicate and exclude_duplicates:
            rejected.append({"source_row": row_number, "reason": "Exact duplicate feedback"})
            continue
        values = {}
        for field in CANONICAL:
            column = mapping.get(field)
            values[field] = row.get(column) if column and column in frame.columns else None
        rating = None
        if values["rating"] is not None and not pd.isna(values["rating"]) and str(values["rating"]).strip():
            try:
                rating = float(values["rating"])
                if not 0 <= rating <= 5:
                    raise ValueError
            except (TypeError, ValueError):
                rejected.append({"source_row": row_number, "reason": "Rating must be numeric and between 0 and 5"})
                continue
        parsed_date = pd.to_datetime(values["date"], errors="coerce", utc=True)
        date_value = None if pd.isna(parsed_date) else parsed_date.isoformat()
        invalid_date = int(
            values["date"] is not None
            and not pd.isna(values["date"])
            and bool(str(values["date"]).strip())
            and date_value is None
        )
        original_id = None if values["feedback_id"] is None or pd.isna(values["feedback_id"]) else str(values["feedback_id"]).strip()
        if original_id:
            seen_ids[original_id] += 1
            identity = f"id:{original_id}:{seen_ids[original_id]}"
        else:
            identity = hashlib.sha256(
                f"{raw_text}|{date_value}|{seen[key]}".encode("utf-8")
            ).hexdigest()[:24]
        record_id = str(uuid.uuid5(uuid.NAMESPACE_URL, f"{dataset_key}:{identity}"))
        rows.append({
            "record_id": record_id,
            "original_id": original_id,
            "feedback_text": mask_pii(raw_text),
            "date": date_value,
            "rating": rating,
            "category": _optional(values["category"]),
            "source": _optional(values["source"]),
            "product": _optional(values["product"]),
            "customer_segment": _optional(values["customer_segment"]),
            "duplicate_candidate": duplicate,
            "invalid_date": invalid_date,
        })
    counts = {
        "imported": len(frame),
        "validated": len(rows),
        "rejected": len(rejected),
        "duplicates": duplicates,
        "masked": sum("[EMAIL]" in r["feedback_text"] or "[PHONE]" in r["feedback_text"] for r in rows),
        "invalid_dates": sum(r["invalid_date"] for r in rows),
    }
    return pd.DataFrame(rows), pd.DataFrame(rejected, columns=["source_row", "reason"]), counts


def _optional(value: object) -> str | None:
    if value is None or pd.isna(value) or not str(value).strip():
        return None
    return normalize_text(value)
