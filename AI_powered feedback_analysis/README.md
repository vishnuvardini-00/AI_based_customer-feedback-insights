# AI-Based Customer Feedback Insights

A local Streamlit application for importing approved feedback, masking common PII, discovering sentiment and themes, reviewing evidence-backed findings, and exporting anonymized analysis. The included demo data is synthetic and fictional.

## Features

- CSV and Excel import with column mapping, file/row limits, row validation, stable IDs within an import, and rejected-row reporting.
- Unicode/whitespace cleanup, exact-duplicate flags, basic email/phone masking, and no persistence of uploaded raw text.
- SQLite persistence for datasets, feedback, analysis runs, predictions, theme clusters, insights, analyst sentiment corrections, and review audit history.
- Local lexicon sentiment baseline with an uncertain state; TF-IDF/K-means theme discovery; dashboard filters, time trends, rating comparisons, evidence records, review, and CSV/Excel/JSON exports.
- Synthetic data can be loaded in the Import Feedback page.

## Requirements and installation

Python 3.11+ is recommended. From the project folder:

**Windows PowerShell**

```powershell
python -m venv .venv
.venv\Scripts\Activate.ps1
python -m pip install -r requirements.txt
Copy-Item .env.example .env
streamlit run app.py
```

**Linux/macOS**

```sh
python3 -m venv .venv
source .venv/bin/activate
python -m pip install -r requirements.txt
cp .env.example .env
streamlit run app.py
```

The app initializes SQLite automatically. By default the database is `data/feedback.sqlite3`; set `FEEDBACK_DATABASE` or `FEEDBACK_DATA_DIR` to use a private location. Keep database and exports out of public version control. To back up safely, stop Streamlit and copy the SQLite file to a protected location.

## Workflow

1. Open **Import Feedback** and load the synthetic example, or upload an approved CSV/XLS/XLSX file (maximum 10 MB / 10,000 rows).
2. Preview the source, map the feedback-text column and any available optional columns, then validate and save. Invalid text/rating rows are reported; download rejected rows if needed.
3. Review PII masking and duplicate candidates under **Data Cleaning and Privacy**. Exact duplicates are flagged rather than silently deleted.
4. On **Overview Dashboard**, run the analysis. Sentiment predictions, TF-IDF themes, and generated findings are saved in SQLite. Use the shared sidebar filters and inspect trends, ratings, comments, and cited record IDs.
5. Review and correct sentiment labels, rename/approve themes, and edit, approve, investigate, or dismiss insight findings in their respective pages. Reviewer actions are audited.
6. Download anonymized CSV/Excel analysis or the JSON insight report from **Export Center**. The report includes dataset and model metadata.
7. Restart the app and select the dataset to view persisted analysis and review state.

## Input schema

`feedback_text` is required. `feedback_id`, `date`, `rating`, `category`, `source`, `product`, and `customer_segment` are optional and can be mapped to arbitrary source column names. Ratings must be numeric in the range 0–5. Unparseable dates are retained as missing; trend charts require at least two valid dated records. Original identifiers may be supplied for matching but are omitted from exports.

## Architecture

- `app.py`: Streamlit navigation, controls, charts, and presentation.
- `src/ingestion.py`, `privacy.py`: import validation, normalization, PII masking, duplicate flags.
- `src/sentiment.py`, `themes.py`, `trends.py`: local NLP and deterministic analytics.
- `src/database.py`: SQLite schema, transactions, persistence, corrections, reviews, and evidence.
- `src/exports.py`: privacy-filtered tabular and JSON output.
- `data/demo_feedback.csv`: fictional sample records.

## Models, privacy, and limitations

Sentiment uses a transparent English-oriented word lexicon (`local-lexicon-1.0`); it is not trained, calibrated, or validated on the imported data. Its score is not a probability of correctness. Negation handling is intentionally simple, and multilingual, sarcastic, short, or domain-specific text can be misclassified. “Uncertain” is not a substitute for human review.

Themes use scikit-learn TF-IDF and K-means with a fixed seed; theme names are derived from cluster keywords. Small datasets can yield unstable or uninformative clusters. No external AI API or credential is needed.

The importer normalizes text and masks common email and phone patterns before saving. Detection is incomplete; text may contain identifying information that is not recognized. This is a local single-user app with no authentication, encryption, or multi-user access control; it is not automatically suitable for sensitive or production customer data. Use only public, synthetic, or explicitly approved datasets. Findings are descriptive, hypotheses are unverified, and human review is required before business decisions.

## Tests and troubleshooting

Run the core tests:

```sh
python -m pytest -q
```

If Excel import/export fails, install dependencies from `requirements.txt` (Excel support uses openpyxl). If an upload is rejected, confirm its extension, size/row limit, and feedback-text mapping. If there are no trends, verify at least two date values parse successfully. The SQLite database is initialized automatically; close the app before moving or backing it up.

## Current scope

Implemented: core import/clean/mask/analyse/persist/review/filter/export flow and synthetic demo. Not implemented: authentication, advanced PII detection or deletion workflow, configurable language models, supervised training/evaluation, theme merge/split/exclusion, manual-review sampling, PDF/PNG exports, formal schema migrations, and multi-user production controls. The app does not claim model validation or causal findings.
