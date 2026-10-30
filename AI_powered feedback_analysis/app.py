from __future__ import annotations

import json
import hashlib
import logging
from pathlib import Path

import plotly.io as pio
import plotly.graph_objects as go

import pandas as pd
import plotly.express as px
import streamlit as st

from src.config import DATABASE_PATH, MODEL_VERSION
from src.database import (
    analyze, edit_insight, generate_insights, initialize, load_analysis, load_datasets,
    load_feedback, load_insights, rename_theme, save_correction, save_dataset,
    save_insight_review,
)
from src.exports import csv_bytes, excel_bytes, insight_json_bytes
from src.ingestion import CANONICAL, OPTIONAL, read_upload, suggested_mapping, validate_and_clean
from src.trends import rating_comparison, trend_data

logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")
st.set_page_config(page_title="Feedback Insights", page_icon="📊", layout="wide")
st.markdown("""
<style>
:root { color-scheme: light; --app-bg:#f5f7fb; --surface:#fff; --text:#172338; --muted:#526174; --border:#d9e1ec; }
.stApp,[data-testid="stAppViewContainer"],[data-testid="stMain"],[data-testid="stMainBlockContainer"],.main {background:var(--app-bg)!important;color:var(--text)!important}
.stApp,.stApp p,.stApp li,.stApp label,.stApp small,.stApp [data-testid="stMarkdownContainer"],.stApp [data-testid="stMarkdownContainer"] p,.stApp [data-testid="stMarkdownContainer"] li,.stApp [data-testid="stWidgetLabel"] p {color:var(--text)!important;line-height:1.55}
h1,h2,h3,h4,h5,h6,[data-testid="stHeading"],[data-testid="stHeading"] * {color:#14243b!important;line-height:1.3!important;overflow-wrap:anywhere}
[data-testid="stCaptionContainer"],.stCaption,.stApp [data-testid="stCaptionContainer"] * {color:var(--muted)!important}
.stApp a {color:#174ea6!important}
[data-testid="stSidebar"] {background:#132238!important;border-right:1px solid #263c58}
[data-testid="stSidebar"] * {color:#f3f6fb!important}
[data-testid="stSidebar"] [data-testid="stMarkdownContainer"] p,[data-testid="stSidebar"] [data-testid="stWidgetLabel"] p,[data-testid="stSidebar"] [data-testid="stCaptionContainer"] {color:#e6edf7!important}
[data-testid="stSidebar"] input,[data-testid="stSidebar"] textarea,[data-testid="stSidebar"] [data-baseweb="select"] *,[data-testid="stSidebar"] [data-baseweb="tag"] {color:#172338!important;-webkit-text-fill-color:#172338!important}
[data-testid="stSidebar"] [data-baseweb="select"] > div,[data-testid="stSidebar"] input,[data-testid="stSidebar"] textarea {background:#fff!important}
[data-testid="stSidebar"] [data-testid="stRadio"] label {padding:.35rem .45rem;border-radius:7px}
[data-testid="stSidebar"] [data-testid="stRadio"] label:hover {background:#203752!important}
[data-testid="stSidebar"] [data-testid="stExpander"] {background:#192d45!important;border:1px solid #49617d;border-radius:10px}
.stApp input,.stApp textarea,.stApp [data-baseweb="input"] input,.stApp [data-baseweb="select"] input,.stApp [data-baseweb="select"] > div,.stApp [data-baseweb="select"] span {color:#172338!important;-webkit-text-fill-color:#172338!important}
.stApp input,.stApp textarea,.stApp [data-baseweb="select"] > div,.stApp [data-baseweb="input"] > div {background:#fff!important;border-color:#aebdce!important}
.stApp input::placeholder,.stApp textarea::placeholder {color:#68788d!important;-webkit-text-fill-color:#68788d!important;opacity:1!important}
.stApp [data-baseweb="tag"] {background:#e8efff!important;border:1px solid #c6d6fa!important}
.stApp [data-baseweb="tag"] * {color:#183b79!important}
[data-baseweb="popover"],[data-baseweb="menu"],[data-baseweb="popover"] *,[data-baseweb="menu"] * {color:#172338!important;background-color:#fff}
[data-baseweb="menu"] li:hover,[data-baseweb="option"]:hover {background:#eaf0fa!important}
.stApp [data-testid="stWidgetLabel"] p {color:#26364c!important;font-weight:650}
.stApp button[kind],[data-testid="stDownloadButton"] button {font-weight:600}
.stApp button:focus,.stApp input:focus,.stApp textarea:focus {outline-color:#2457c5!important}
[data-testid="stMetric"],[data-testid="stExpander"],[data-testid="stVerticalBlockBorderWrapper"] {background:#fff!important;color:#172338!important;border:1px solid var(--border);border-radius:12px}
[data-testid="stMetric"] {padding:14px;min-width:0}
[data-testid="stMetric"] label,[data-testid="stMetric"] [data-testid="stMetricLabel"] {color:#526174!important;white-space:normal!important;overflow-wrap:anywhere}
[data-testid="stMetricValue"],[data-testid="stMetricDelta"],[data-testid="stMetricValue"] * {color:#14243b!important;overflow-wrap:anywhere}
[data-testid="stExpander"] summary,[data-testid="stExpander"] summary p,[data-testid="stExpander"] summary svg {color:#172338!important}
div[data-testid="stAlert"] {border-radius:10px}
[data-testid="stAlert"] p,[data-testid="stAlert"] li {color:#172338!important}
[data-testid="stDataFrame"],[data-testid="stTable"] {max-width:100%;border:1px solid var(--border);border-radius:8px;overflow:hidden}
[data-testid="stDataFrame"] *,[data-testid="stTable"] * {font-size:.92rem}
[data-testid="stHorizontalBlock"] {flex-wrap:wrap;gap:.8rem}
[data-testid="stHorizontalBlock"] > [data-testid="column"] {min-width:min(100%,220px)}
.stApp p,.stApp li,.stApp code,.stApp a {overflow-wrap:anywhere}
@media(max-width:768px){.block-container{padding-left:1rem;padding-right:1rem}h1{font-size:1.65rem!important}h2{font-size:1.35rem!important}h3{font-size:1.15rem!important}[data-testid="stMetric"]{padding:10px}}
</style>""", unsafe_allow_html=True)

# Global Plotly styling
# PxDefaults does not support title_font; set title styling in the template instead.
custom_template = go.layout.Template(
    layout=dict(
        font=dict(
            family="Arial, sans-serif",
            size=13,
            color="#172338"
        ),
        title=dict(
            font=dict(
                family="Arial, sans-serif",
                size=18,
                color="#14243b"
            )
        ),
        paper_bgcolor="#FFFFFF",
        plot_bgcolor="#FFFFFF",
        xaxis=dict(
            color="#172338",
            gridcolor="#E5E7EB"
        ),
        yaxis=dict(
            color="#172338",
            gridcolor="#E5E7EB"
        )
    )
)

# Register and apply the same named template everywhere.
pio.templates["custom_white"] = custom_template
pio.templates.default = "custom_white"
px.defaults.template = "custom_white"
px.defaults.color_discrete_sequence = [
    "#2563eb", "#0f766e", "#d97706", "#dc2626", "#7c3aed"
]
initialize()

PAGES = [
    "Overview Dashboard", "Import Feedback", "Data Cleaning and Privacy",
    "Sentiment Analysis", "Theme Discovery", "Trend Analysis", "AI Insights",
    "Insight Review and Validation", "Export Center", "Settings and Model Information",
]

with st.sidebar:
    st.title("Feedback Insights")
    page = st.radio("Navigate", PAGES, label_visibility="collapsed")
    st.caption("Local analytics · SQLite persistence")

datasets = load_datasets()
if datasets.empty:
    active_dataset = None
else:
    labels = {
        row.dataset_id: f"{row.name}{' · SYNTHETIC' if row.synthetic else ''}"
        for row in datasets.itertuples()
    }
    preferred = st.session_state.get("dataset_id")
    if preferred not in labels:
        preferred = datasets.iloc[0].dataset_id
    active_id = st.sidebar.selectbox(
        "Active dataset", list(labels), format_func=lambda key: labels[key],
        index=list(labels).index(preferred),
    )
    st.session_state.dataset_id = active_id
    active_dataset = datasets[datasets.dataset_id == active_id].iloc[0]

run_id, records, themes = (None, pd.DataFrame(), pd.DataFrame())
if active_dataset is not None:
    run_id, records, themes = load_analysis(active_dataset.dataset_id)
    if not run_id:
        records = load_feedback(active_dataset.dataset_id)


def notice_empty(message: str = "Import a dataset or load the synthetic example to get started.") -> None:
    st.info(message)


def filter_records(frame: pd.DataFrame) -> pd.DataFrame:
    """Apply shared filters while keeping each filter's options stable."""
    if frame.empty:
        return frame.copy()

    base = frame.copy()
    if "theme_id" in base and not themes.empty:
        theme_names = themes.set_index("theme_id")["name"].to_dict()
        base["theme_name"] = base["theme_id"].map(theme_names).fillna("Unassigned")
    filtered = base.copy()

    with st.sidebar.expander("Shared filters", expanded=False):
        if "date" in base:
            dates = pd.to_datetime(base["date"], errors="coerce", utc=True)
            valid_dates = dates.dropna()
            if not valid_dates.empty:
                first_date, last_date = valid_dates.min().date(), valid_dates.max().date()
                selected_dates = st.date_input(
                    "Date range", value=(first_date, last_date),
                    min_value=first_date, max_value=last_date,
                    key="shared_filter_dates",
                )
                if isinstance(selected_dates, (tuple, list)) and len(selected_dates) == 2:
                    date_values = dates.dt.date
                    filtered = filtered[
                        date_values.notna()
                        & date_values.between(selected_dates[0], selected_dates[1])
                    ]

        if "sentiment" in base:
            options = sorted(base["sentiment"].dropna().astype(str).unique())
            selected = st.multiselect("Sentiment", options, default=options, key="shared_filter_sentiment")
            filtered = filtered[filtered["sentiment"].astype(str).isin(selected)]

        if "theme_name" in base:
            options = sorted(base["theme_name"].dropna().astype(str).unique())
            selected = st.multiselect("Theme", options, default=options, key="shared_filter_theme")
            filtered = filtered[filtered["theme_name"].astype(str).isin(selected)]

        for col, label in [
            ("category", "Category"), ("product", "Product"),
            ("source", "Source"), ("customer_segment", "Segment"),
        ]:
            if col not in base:
                continue
            options = sorted(base[col].dropna().astype(str).unique())
            selected = st.multiselect(label, options, default=options, key=f"filter_{col}")
            # Clearing a filter means no values are selected, so show no matching rows.
            filtered = filtered[filtered[col].astype(str).isin(selected)]

        if "rating" in base and base["rating"].notna().any():
            low, high = st.slider(
                "Rating range", 0.0, 5.0, (0.0, 5.0), 0.5,
                key="shared_filter_rating",
            )
            filtered = filtered[filtered["rating"].isna() | filtered["rating"].between(low, high)]

        query = st.text_input("Search anonymized text", key="shared_filter_search").strip()
        if query:
            searchable = [c for c in ("feedback_text", "theme_name", "category", "product", "source") if c in filtered]
            if searchable:
                matches = pd.Series(False, index=filtered.index)
                for col in searchable:
                    matches |= filtered[col].astype(str).str.contains(query, case=False, na=False, regex=False)
                filtered = filtered[matches]

        st.caption(f"Showing {len(filtered):,} of {len(base):,} records.")

    return filtered


if page == "Import Feedback":
    st.title("Import Feedback")
    st.write("Upload approved CSV or Excel files. Files are limited to 10 MB and 10,000 rows.")
    demo_col, note_col = st.columns([1, 2])
    with demo_col:
        if st.button("Load synthetic demo dataset", type="primary"):
            existing = datasets[datasets.name == "Synthetic demonstration feedback"] if not datasets.empty else pd.DataFrame()
            if existing.empty:
                demo_path = Path(__file__).parent / "data" / "demo_feedback.csv"
                raw = pd.read_csv(demo_path)
                mapping = suggested_mapping(list(raw.columns))
                cleaned, rejected, counts = validate_and_clean(raw, mapping, "synthetic-demo", False)
                fingerprint = hashlib.sha256(demo_path.read_bytes()).hexdigest()
                dataset_id = save_dataset("Synthetic demonstration feedback", cleaned, synthetic=True,
                                          source_fingerprint=f"demo:{fingerprint}")
                st.session_state.dataset_id = dataset_id
                st.session_state.import_counts = counts
                st.success(f"Loaded {len(cleaned)} fictional synthetic records.")
            else:
                st.session_state.dataset_id = existing.iloc[0].dataset_id
                st.info("The synthetic demo is already saved; selected it.")
            st.rerun()
    with note_col:
        st.caption("Demo comments are fictional and clearly labelled. Uploaded original text is not retained; supported email and phone patterns are masked before storage.")

    upload = st.file_uploader("Choose CSV or Excel file", type=["csv", "xlsx", "xls"])
    if upload:
        try:
            frame = read_upload(upload.name, upload.getvalue())
            st.write(f"Preview: {len(frame):,} rows × {len(frame.columns)} columns")
            st.dataframe(frame.head(8), width="stretch", config={"displaylogo": False, "responsive": True})
            defaults = suggested_mapping(list(frame.columns))
            st.subheader("Map your columns")
            mapping = {}
            options = ["(not provided)", *list(frame.columns)]
            for index, field in enumerate(CANONICAL):
                default = defaults[field]
                chosen_index = options.index(default) if default in options else 0
                with st.container():
                    mapping[field] = st.selectbox(
                        f"{field}{' (required)' if field == 'feedback_text' else ''}",
                        options, index=chosen_index, key=f"map_{field}",
                    )
                    mapping[field] = None if mapping[field] == "(not provided)" else mapping[field]
            st.caption("Optional fields: " + ", ".join(OPTIONAL))
            if st.button("Validate, mask and save dataset"):
                mapped = {key: value for key, value in mapping.items()}
                raw_upload = upload.getvalue()
                fingerprint_payload = raw_upload + json.dumps(mapped, sort_keys=True).encode("utf-8")
                fingerprint = hashlib.sha256(fingerprint_payload).hexdigest()
                dataset_key = fingerprint
                cleaned, rejected, counts = validate_and_clean(frame, mapped, dataset_key)
                if cleaned.empty:
                    st.error("No valid records were found. Review the validation errors below.")
                else:
                    dataset_id = save_dataset(upload.name, cleaned, source_fingerprint=fingerprint)
                    st.session_state.dataset_id = dataset_id
                    st.session_state.import_counts = counts
                    st.session_state.rejected_csv = rejected.to_csv(index=False).encode("utf-8")
                    st.success(f"Saved {counts['validated']} anonymized records.")
                    st.rerun()
            if "rejected_csv" in st.session_state:
                st.download_button("Download rejected row report", st.session_state.rejected_csv, "rejected_rows.csv", "text/csv")
        except ValueError as exc:
            st.error(str(exc))
        except Exception as exc:
            logging.error("Unexpected import error (%s)", type(exc).__name__)
            st.error(f"Import failed safely ({type(exc).__name__}). Check the file format and column mapping, then retry.")

elif page == "Settings and Model Information":
    st.title("Settings and Model Information")
    st.subheader("Local baseline")
    st.write(f"Sentiment model identifier: `{MODEL_VERSION}`")
    st.write("A transparent, rule-based local lexicon baseline; it is not trained on your data. Confidence describes the rule-score strength, not the probability that a label is correct.")
    st.write("Theme discovery uses TF-IDF terms and reproducible K-means clustering (random seed 42). Clusters can be unstable for small, sparse, multilingual, or specialized datasets.")
    st.warning("Automatic language detection is not implemented. Predictions may be uncertain or wrong for unsupported languages, irony, negation, and domain-specific wording. Review before acting.")
    st.subheader("Persistence and privacy")
    st.code(str(DATABASE_PATH))
    st.write("Raw uploaded feedback is not persisted. Email addresses and phone-like sequences are masked before saving; automatic detection is incomplete and is not a guarantee of anonymity. This local app has no authentication and is not a secure multi-user production service.")
    st.write("Back up the SQLite file after stopping the app. Keep the database, exports, and uploaded data private.")
    st.subheader("Synthetic sample")
    st.write("`data/demo_feedback.csv` contains fictional examples only; its results are not customer findings.")

elif page == "Overview Dashboard":
    st.title("Overview Dashboard")
    if active_dataset is None:
        notice_empty()
    else:
        st.caption(f"Dataset: **{active_dataset['name']}**" + (" · Synthetic data" if active_dataset.synthetic else ""))
        if not run_id:
            st.warning("This dataset has not been analysed yet.")
            if st.button("Run sentiment and theme analysis", type="primary"):
                with st.spinner("Analysing stored anonymized records…"):
                    new_run = analyze(active_dataset.dataset_id)
                    generate_insights(new_run)
                st.rerun()
        else:
            filtered = filter_records(records)
            total = len(filtered)
            counts = filtered.sentiment.value_counts() if "sentiment" in filtered else pd.Series(dtype=int)
            avg_rating = filtered.rating.mean() if "rating" in filtered and filtered.rating.notna().any() else None
            cols = st.columns(5)
            cols[0].metric("Feedback records", f"{total:,}")
            cols[1].metric("Positive", f"{100 * counts.get('positive', 0) / total:.1f}%" if total else "—")
            cols[2].metric("Neutral", f"{100 * counts.get('neutral', 0) / total:.1f}%" if total else "—")
            cols[3].metric("Negative", f"{100 * counts.get('negative', 0) / total:.1f}%" if total else "—")
            cols[4].metric("Average rating", f"{avg_rating:.2f}/5" if avg_rating is not None else "—")
            cols2 = st.columns(3)
            cols2[0].metric("Uncertain", int(counts.get("uncertain", 0)))
            cols2[1].metric("Discovered themes", len(themes))
            cols2[2].metric("Pending insights", int((load_insights(run_id).status == "pending").sum()))
            if not total:
                notice_empty("No records match the selected filters.")
            else:
                c1, c2 = st.columns(2)
                with c1:
                    st.plotly_chart(px.pie(filtered, names="sentiment", title="Sentiment distribution", color="sentiment",
                        color_discrete_map={"positive": "#2b8a5a", "negative": "#d64b4b", "uncertain": "#d89b21", "neutral": "#718096"}),
                        width="stretch", config={"displaylogo": False, "responsive": True})
                with c2:
                    if "theme_id" in filtered and not themes.empty:
                        names = themes.set_index("theme_id").name.to_dict()
                        frequencies = filtered.theme_id.map(names).fillna("Unassigned").value_counts().rename_axis("theme").reset_index(name="records")
                        st.plotly_chart(px.bar(frequencies, x="theme", y="records", title="Most frequent themes", labels={"theme": "Feedback theme", "records": "Number of records"}).update_layout(xaxis_tickangle=-30, margin=dict(b=100), font=dict(color="#263445", size=13)), width="stretch", config={"displaylogo": False, "responsive": True})
                trend = trend_data(filtered, "W")
                if not trend.empty:
                    st.plotly_chart(px.line(trend, x="period", y=[c for c in ["positive", "neutral", "negative", "uncertain"] if c in trend],
                                            title="Weekly sentiment counts", markers=True), width="stretch", config={"displaylogo": False, "responsive": True})
                    if trend.small_sample.any():
                        st.warning("Some weeks have fewer than 10 records; percentages and apparent trends may be unreliable.")
                rating = rating_comparison(filtered)
                if not rating.empty:
                    st.plotly_chart(px.bar(rating, x="sentiment", y="average_rating", hover_data=["records"], title="Ratings by text sentiment"),
                                    width="stretch", config={"displaylogo": False, "responsive": True})

elif page == "Data Cleaning and Privacy":
    st.title("Data Cleaning and Privacy")
    if records.empty:
        notice_empty()
    else:
        st.write("Original free-text is not stored. Stored text is whitespace/Unicode normalized and email/phone-like strings are masked.")
        imported_count = int(active_dataset["imported_count"])
        stats = {
            "imported": imported_count,
            "validated": len(records),
            "rejected": max(0, imported_count - len(records)),
            "duplicates": int(records.duplicate_candidate.sum()) if "duplicate_candidate" in records else 0,
            "masked": int(records.feedback_text.str.contains(r"\[(EMAIL|PHONE)\]", regex=True).sum()),
            "invalid_dates": int(records.invalid_date.sum()) if "invalid_date" in records else 0,
        }
        cols = st.columns(5)
        for column, key, label in zip(cols, ["imported", "validated", "rejected", "duplicates", "masked"],
                                      ["Imported", "Validated", "Rejected", "Duplicate candidates", "Records with PII masked"]):
            column.metric(label, stats.get(key, "—"))
        st.caption(f"Rows with unparseable dates: {stats['invalid_dates']}. They are retained without a date and excluded from time trends.")
        candidates = records[records.duplicate_candidate == 1] if "duplicate_candidate" in records else pd.DataFrame()
        st.subheader("Duplicate candidates")
        st.caption("Exact matches are flagged for review; they are not automatically deleted.")
        st.dataframe(candidates[["record_id", "feedback_text", "date"]] if not candidates.empty else candidates,
                     width="stretch", hide_index=True)
        st.subheader("Stored anonymized data")
        st.dataframe(records[["record_id", "feedback_text", "date", "rating", "category", "source"]].head(100),
                     width="stretch", hide_index=True)

elif page == "Sentiment Analysis":
    st.title("Sentiment Analysis")
    if not run_id:
        notice_empty("Run analysis from the Overview Dashboard first.")
    else:
        st.caption(f"Model: {MODEL_VERSION}. Confidence is rule-strength, not correctness. Corrections are stored separately from model predictions.")
        filtered = filter_records(records)
        cols = ["record_id", "feedback_text", "predicted_sentiment", "sentiment", "confidence", "rating"]
        st.dataframe(filtered[cols].head(100), width="stretch", hide_index=True, column_config={"feedback_text": st.column_config.TextColumn("Feedback text", width="large"), "record_id": st.column_config.TextColumn("Record ID", width="small")})
        st.subheader("Correct a prediction")
        choices = filtered[["record_id", "feedback_text", "predicted_sentiment"]].head(500)
        if not choices.empty:
            selected_id = st.selectbox("Feedback record", choices.record_id,
                format_func=lambda rid: f"{rid[:8]} · {choices.loc[choices.record_id == rid, 'feedback_text'].iloc[0][:80]}")
            label = st.selectbox("Corrected sentiment", ["positive", "neutral", "negative", "uncertain"])
            reviewer = st.text_input("Reviewer")
            if st.button("Save correction"):
                try:
                    save_correction(selected_id, label, reviewer)
                    st.success("Correction saved separately; original prediction remains unchanged.")
                    st.rerun()
                except ValueError as exc:
                    st.error(str(exc))
        disagreements = records[records.rating.notna() & (((records.rating >= 4) & (records.sentiment == "negative")) |
                                                            ((records.rating <= 2) & (records.sentiment == "positive")))]
        st.subheader("Rating/text disagreements")
        st.dataframe(disagreements[["record_id", "rating", "sentiment", "feedback_text"]].head(50),
                     width="stretch", hide_index=True, column_config={"feedback_text": st.column_config.TextColumn("Feedback text", width="large")})

elif page == "Theme Discovery":
    st.title("Theme Discovery")
    if not run_id:
        notice_empty("Run analysis from the Overview Dashboard first.")
    else:
        theme_names = themes.set_index("theme_id").name.to_dict() if not themes.empty else {}
        enriched = records.copy()
        enriched["theme"] = enriched.theme_id.map(theme_names).fillna("Unassigned")
        summary = enriched.groupby(["theme_id", "theme"], dropna=False).agg(records=("record_id", "count")).reset_index()
        for theme in themes.to_dict("records"):
            group = enriched[enriched.theme_id == theme["theme_id"]]
            name_col, save_col = st.columns([3, 1])
            with name_col:
                new_name = st.text_input(f"Theme name · {theme['name']}", value=theme["name"], key=f"theme_{theme['theme_id']}")
                st.caption(f"Keywords: {', '.join(json.loads(theme['keywords']))}")
            with save_col:
                reviewer = st.text_input("Reviewer", key=f"theme_reviewer_{theme['theme_id']}")
                if st.button("Save approved name", key=f"save_theme_{theme['theme_id']}"):
                    try:
                        rename_theme(theme["theme_id"], new_name, reviewer)
                        st.success("Theme approved and saved.")
                        st.rerun()
                    except ValueError as exc:
                        st.error(str(exc))
            st.dataframe(group[["record_id", "sentiment", "feedback_text"]].head(8), width="stretch", hide_index=True, column_config={"feedback_text": st.column_config.TextColumn("Feedback text", width="large")})
        if not summary.empty:
            st.dataframe(summary[["theme", "records"]], width="stretch", hide_index=True)
        st.caption("Discovered themes are machine-generated clusters, not a fixed taxonomy. Rename approvals persist; merging and splitting are not implemented.")

elif page == "Trend Analysis":
    st.title("Trend Analysis")
    if not run_id:
        notice_empty("Run analysis from the Overview Dashboard first.")
    else:
        filtered = filter_records(records)
        frequency = st.selectbox("Time aggregation", ["D", "W", "MS"], format_func=lambda x: {"D": "Day", "W": "Week", "MS": "Month"}[x])
        trend = trend_data(filtered, frequency)
        if trend.empty:
            st.warning("At least two valid dated records are needed; no trend is inferred.")
        else:
            st.caption("Counts are shown alongside each period. Small samples (<10 records) are flagged. Trends do not establish causes.")
            st.plotly_chart(px.line(trend, x="period", y=[c for c in ["positive", "neutral", "negative", "uncertain"] if c in trend],
                                    markers=True, title="Sentiment by period"), width="stretch", config={"displaylogo": False, "responsive": True})
            st.dataframe(trend, width="stretch", hide_index=True)
            st.download_button("Download trend data", csv_bytes(trend), "feedback_trends.csv", "text/csv")
        if filtered.rating.notna().any():
            period_frequency = {"D": "D", "W": "W", "MS": "M"}[frequency]
            rating = filtered.assign(period=pd.to_datetime(filtered.date, errors="coerce").dt.to_period(period_frequency).astype(str))
            rating = rating.dropna(subset=["rating"]).groupby("period").rating.agg(average_rating="mean", records="count").reset_index()
            st.plotly_chart(px.line(rating, x="period", y="average_rating", hover_data=["records"], title="Average rating trend"), width="stretch", config={"displaylogo": False, "responsive": True})

elif page == "AI Insights":
    st.title("AI Insights")
    if not run_id:
        notice_empty("Run analysis from the Overview Dashboard first.")
    else:
        st.caption("Local template-based findings use deterministic model labels and cited records. Hypotheses are not verified causes.")
        if st.button("Generate evidence-backed findings"):
            count = generate_insights(run_id)
            st.success(f"Generated {count} new finding(s) from observed negative themes.")
        insights = load_insights(run_id)
        if insights.empty:
            st.info("No eligible findings have been generated. A finding requires at least two records labelled negative in a theme.")
        for item in insights.to_dict("records"):
            with st.container(border=True):
                st.subheader(item["title"])
                st.write(item["body"])
                evidence = json.loads(item["evidence_json"])
                st.caption(f"Evidence strength: descriptive; {evidence['negative_count']} negative of {evidence['theme_count']} records in theme. Not a calibrated probability.")
                st.write("Supporting records:", ", ".join(evidence["record_ids"]))
                st.write("Representative anonymized comments:")
                for comment in evidence["sample_comments"]:
                    st.write(f"> {comment}")
                st.caption(f"Review status: {item['status']}")

elif page == "Insight Review and Validation":
    st.title("Insight Review and Validation")
    if not run_id:
        notice_empty("Run analysis from the Overview Dashboard first.")
    else:
        insights = load_insights(run_id)
        if insights.empty:
            st.info("Generate findings in AI Insights first.")
        for item in insights.to_dict("records"):
            with st.expander(item["title"], expanded=item["status"] == "pending"):
                evidence = json.loads(item["evidence_json"])
                st.write("Evidence calculation:", f"{evidence['negative_count']} negative labels / {evidence['theme_count']} records.")
                st.write("Record IDs:", ", ".join(evidence["record_ids"]))
                title = st.text_input("Edit title", item["title"], key=f"ins_title_{item['insight_id']}")
                body = st.text_area("Edit wording", item["body"], key=f"ins_body_{item['insight_id']}")
                reviewer = st.text_input("Reviewer name", key=f"ins_reviewer_{item['insight_id']}")
                reason = st.text_input("Reason (required when dismissing)", key=f"ins_reason_{item['insight_id']}")
                c1, c2, c3 = st.columns(3)
                if c1.button("Save wording", key=f"edit_{item['insight_id']}"):
                    try:
                        edit_insight(item["insight_id"], title, body, reviewer)
                        st.success("Edited with an audit entry.")
                        st.rerun()
                    except ValueError as exc:
                        st.error(str(exc))
                if c2.button("Approve / verify", key=f"approve_{item['insight_id']}"):
                    try:
                        save_insight_review(item["insight_id"], "approved", reviewer)
                        st.success("Approved and recorded.")
                        st.rerun()
                    except ValueError as exc:
                        st.error(str(exc))
                if c3.button("Dismiss", key=f"dismiss_{item['insight_id']}"):
                    if not reason.strip():
                        st.error("Provide a dismissal reason.")
                    else:
                        try:
                            save_insight_review(item["insight_id"], "dismissed", reviewer, reason)
                            st.success("Dismissed with reason.")
                            st.rerun()
                        except ValueError as exc:
                            st.error(str(exc))
                if st.button("Flag for investigation", key=f"investigate_{item['insight_id']}"):
                    try:
                        save_insight_review(item["insight_id"], "investigate", reviewer, reason)
                        st.success("Flagged for further investigation.")
                        st.rerun()
                    except ValueError as exc:
                        st.error(str(exc))

elif page == "Export Center":
    st.title("Export Center")
    if records.empty:
        notice_empty()
    else:
        st.caption("Exports omit the original ID and dataset ID columns. Feedback text is already PII-masked before persistence.")
        format_choice = st.radio("Format", ["CSV", "Excel"], horizontal=True)
        payload = csv_bytes(records) if format_choice == "CSV" else excel_bytes(records)
        mime = "text/csv" if format_choice == "CSV" else "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
        st.download_button("Download anonymized feedback and analysis", payload,
                           "feedback_analysis.csv" if format_choice == "CSV" else "feedback_analysis.xlsx", mime)
        if run_id:
            insights = load_insights(run_id)
            metadata = {
                "analysis_date": pd.Timestamp.utcnow().isoformat(),
                "dataset": active_dataset["name"],
                "dataset_id": active_dataset["dataset_id"],
                "record_count": len(records),
                "model_version": MODEL_VERSION,
                "limitations": "Local lexicon model confidence is not correctness; hypotheses are unverified.",
            }
            st.download_button("Download insight report (JSON)", insight_json_bytes(insights, metadata),
                               "insight_report.json", "application/json")
        st.info("Excel and CSV exports are available. PNG chart and PDF report export are not implemented.")

else:
    st.title(page)
    notice_empty("This page is available after importing a dataset.")
