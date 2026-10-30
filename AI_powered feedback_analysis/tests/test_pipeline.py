import pandas as pd
import pytest

from src.database import (
    analyze, edit_insight, generate_insights, initialize, load_analysis, load_insights,
    save_correction, save_dataset, save_insight_review,
)
from src.exports import csv_bytes, excel_bytes
from src.ingestion import read_upload, suggested_mapping, validate_and_clean
from src.privacy import mask_pii
from src.sentiment import predict
from src.themes import discover_themes
from src.trends import trend_data


def sample_frame():
    return pd.DataFrame({
        "id": ["a", "b", "c", "d"],
        "comment": [
            "The delivery was terrible and late.",
            "The delivery was terrible and late.",
            "Thanks, alex@example.com. Call 555-123-4567.",
            "Great product and excellent support.",
        ],
        "date": ["2026-01-01", "2026-01-02", "bad-date", "2026-01-04"],
        "rating": [1, 1, 5, "invalid"],
    })


def test_upload_and_mapping():
    frame = pd.DataFrame({"review": ["Good service"]})
    result = read_upload("test.csv", frame.to_csv(index=False).encode())
    mapping = suggested_mapping(list(result.columns))
    assert mapping["feedback_text"] == "review"
    with pytest.raises(ValueError):
        read_upload("test.txt", b"review\nGood")


def test_validation_rejects_bad_ratings_and_masks_pii():
    frame = sample_frame()
    mapping = {"feedback_id": "id", "feedback_text": "comment", "date": "date", "rating": "rating"}
    records, rejected, counts = validate_and_clean(frame, mapping, "test")
    assert len(records) == 3
    assert len(rejected) == 1
    assert counts["duplicates"] == 1
    assert counts["masked"] == 1
    assert counts["invalid_dates"] == 1
    assert records.iloc[2].feedback_text.find("[EMAIL]") >= 0
    assert records.iloc[2].date is None
    missing, _, _ = validate_and_clean(
        pd.DataFrame({"comment": [None, float("nan")]}),
        {"feedback_text": "comment"}, "missing",
    )
    assert missing.empty


def test_pii_and_sentiment_uncertainty():
    masked = mask_pii("Email me alex@example.com or 555-123-4567")
    assert "[EMAIL]" in masked and "[PHONE]" in masked
    assert predict("Great")["sentiment"] == "uncertain"
    assert predict("This product is excellent and wonderful")["sentiment"] == "positive"
    assert predict("This product is terrible and broken")["sentiment"] == "negative"


def test_theme_discovery_and_trends():
    themes, labels = discover_themes(["late delivery was bad", "delivery arrived late", "excellent helpful support"])
    assert themes and len(labels) == 3
    frame = pd.DataFrame({
        "date": ["2026-01-01", "2026-01-08", "2026-01-15"],
        "sentiment": ["negative", "positive", "negative"],
    })
    trend = trend_data(frame)
    assert not trend.empty
    assert "feedback_count" in trend


def test_database_analysis_review_and_exports(tmp_path):
    database = tmp_path / "test.sqlite3"
    initialize(database)
    mapping = {"feedback_text": "comment", "date": "date", "rating": "rating", "feedback_id": "id"}
    records, _, _ = validate_and_clean(sample_frame(), mapping, "db-test")
    dataset_id = save_dataset("test data", records, path=database, source_fingerprint="same-file")
    repeated_id = save_dataset("test data", records, path=database, source_fingerprint="same-file")
    assert repeated_id == dataset_id
    run_id = analyze(dataset_id, path=database)
    loaded_run, analysed, themes = load_analysis(dataset_id, path=database)
    assert run_id == loaded_run and len(analysed) == len(records) and len(themes) > 0
    corrected_index = analysed.index[analysed.predicted_sentiment != "neutral"][0]
    corrected_id = analysed.loc[corrected_index, "record_id"]
    original_prediction = analysed.loc[corrected_index, "predicted_sentiment"]
    save_correction(corrected_id, "neutral", "tester", path=database)
    corrected = load_analysis(dataset_id, path=database)[1].set_index("record_id").loc[corrected_id]
    assert corrected.sentiment == "neutral"
    assert corrected.predicted_sentiment == original_prediction
    assert corrected.predicted_sentiment != corrected.sentiment
    generate_insights(run_id, path=database)
    insights = load_insights(run_id, path=database)
    if not insights.empty:
        item = insights.iloc[0]
        edit_insight(item.insight_id, "Edited title", "Edited body", "tester", path=database)
        save_insight_review(item.insight_id, "approved", "tester", path=database)
        assert load_insights(run_id, path=database).iloc[0].status == "approved"
    assert csv_bytes(analysed)
    assert excel_bytes(analysed)
    assert b"original_id" not in csv_bytes(analysed)
