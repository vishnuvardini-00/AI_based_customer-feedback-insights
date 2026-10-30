import re
import unicodedata

import pandas as pd

EMAIL = re.compile(r"\b[A-Z0-9._%+-]+@[A-Z0-9.-]+\.[A-Z]{2,}\b", re.I)
PHONE = re.compile(r"(?<!\w)(?:\+?\d[\d\s().-]{7,}\d)(?!\w)")


def normalize_text(value: object) -> str:
    if value is None or pd.isna(value):
        return ""
    text = unicodedata.normalize("NFKC", str(value))
    text = "".join(char for char in text if char.isprintable() or char in "\t\n")
    return re.sub(r"\s+", " ", text).strip()


def mask_pii(value: object) -> str:
    text = normalize_text(value)
    text = EMAIL.sub("[EMAIL]", text)
    return PHONE.sub("[PHONE]", text)


def duplicate_key(value: object) -> str:
    return re.sub(r"[^\w]", "", normalize_text(value).casefold())
