import pandas as pd


def trend_data(frame: pd.DataFrame, frequency: str = "W") -> pd.DataFrame:
    if frame.empty or "date" not in frame or frame["date"].notna().sum() < 2:
        return pd.DataFrame()
    data = frame.copy()
    data["date"] = pd.to_datetime(data["date"], errors="coerce", utc=True)
    data = data.dropna(subset=["date"]).set_index("date")
    if data.empty:
        return pd.DataFrame()
    counts = data.groupby([pd.Grouper(freq=frequency), "sentiment"], dropna=False).size().unstack(fill_value=0)
    counts["feedback_count"] = counts.sum(axis=1)
    counts["small_sample"] = counts["feedback_count"] < 10
    return counts.reset_index(names="period")


def rating_comparison(frame: pd.DataFrame) -> pd.DataFrame:
    rated = frame.dropna(subset=["rating"])
    if rated.empty:
        return pd.DataFrame(columns=["sentiment", "average_rating", "records"])
    return rated.groupby("sentiment").rating.agg(average_rating="mean", records="count").reset_index()
