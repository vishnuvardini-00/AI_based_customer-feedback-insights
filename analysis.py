"""Trend analysis and evidence-backed insight generation."""
import pandas as pd

def trend(df, freq="M", min_n=10):
    d = df.copy()
    d["period"] = pd.to_datetime(d.date).dt.to_period(freq).astype(str)
    vol = d.groupby("period").size().rename("total").reset_index()
    t = d.groupby(["period", "theme"]).size().rename("n").reset_index().merge(vol, on="period")
    t["share"] = t.n / t.total
    t["low_sample"] = t.total < min_n
    return t, vol

def generate(df, min_n=10):
    """Rule-based insights; themes with fewer than min_n responses are skipped."""
    out, d = [], df.copy()
    d["month"] = pd.to_datetime(d.date).dt.to_period("M").astype(str)
    months = sorted(d.month.unique())
    for th, g in d.groupby("theme"):
        if len(g) < min_n:
            continue
        s = g.sentiment.value_counts(normalize=True)
        pos, neg = s.get("positive", 0), s.get("negative", 0)
        kind = "positive" if pos >= .5 and pos > neg else "pain point" if neg >= .4 else None
        if not kind:
            continue
        ev = " | ".join(f"[{r.record_id}] {r.text[:140]}" for r in g.sort_values("dist").head(3).itertuples())
        summary = (f"{kind.title()}: theme '{th}' ({len(g)} responses, avg rating {g.rating.mean():.2f}); "
                   f"{pos:.0%} positive, {neg:.0%} negative text sentiment.")
        hyp = "Hypothesis (unverified): "
        if len(months) >= 4:
            h = len(months) // 2
            def share(ms):
                sel = d.month.isin(ms)
                return ((sel) & (d.theme == th)).sum() / max(1, sel.sum())
            hyp += f"this theme's share of feedback moved from {share(months[:h]):.0%} to {share(months[h:]):.0%} between the first and second half of the period; "
        hyp += "the cause is not established by this data. Check product, support or operations records."
        out.append({"kind": kind, "theme": th, "summary": summary, "hypothesis": hyp, "evidence": ev})
    return out
