from __future__ import annotations

import io
import json

import pandas as pd


def csv_bytes(frame: pd.DataFrame) -> bytes:
    safe = frame.drop(columns=["original_id", "dataset_id"], errors="ignore")
    return safe.to_csv(index=False).encode("utf-8-sig")


def excel_bytes(frame: pd.DataFrame) -> bytes:
    safe = frame.drop(columns=["original_id", "dataset_id"], errors="ignore")
    buffer = io.BytesIO()
    with pd.ExcelWriter(buffer, engine="openpyxl") as writer:
        safe.to_excel(writer, index=False, sheet_name="Feedback analysis")
    return buffer.getvalue()


def insight_json_bytes(insights: pd.DataFrame, metadata: dict) -> bytes:
    safe_insights = insights.drop(columns=["insight_id"], errors="ignore").to_dict("records")
    return json.dumps({"metadata": metadata, "insights": safe_insights}, indent=2, default=str).encode("utf-8")
