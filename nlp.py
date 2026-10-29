"""Local sentiment (lexicon + negation, with 'uncertain') and TF-IDF/KMeans theme discovery."""
import re, time
import numpy as np
from .config import BATCH_SIZE, TIMEOUT_S
from sklearn.cluster import KMeans
from sklearn.feature_extraction.text import TfidfVectorizer

POS = set("great good love loved excellent fast easy helpful amazing perfect happy smooth friendly reliable fantastic satisfied nice quick intuitive fair value solved early".split())
NEG = set("bad slow broken terrible awful hate late crash crashes crashing buggy rude expensive poor worst confusing damaged refund unhelpful disappointed disappointing delayed useless error".split())
NOT = {"not", "no", "never", "isn't", "wasn't", "don't", "didn't", "can't", "won't", "hardly"}

def sentiment(text, min_conf=0.3):
    """Returns (label, score in [-1,1], confidence). 'uncertain' when evidence is weak or mixed."""
    toks = re.findall(r"[a-z']+", text.lower())
    p = n = 0
    for i, t in enumerate(toks):
        neg = any(x in NOT for x in toks[max(0, i - 3):i])
        if t in POS:
            p, n = (p, n + 1) if neg else (p + 1, n)
        elif t in NEG:
            p, n = (p + 1, n) if neg else (p, n + 1)
    m = p + n
    if m == 0:
        return "uncertain", 0.0, 0.0
    score = (p - n) / m
    conf = abs(score) * min(1.0, m / 2)
    if conf < min_conf:
        return "uncertain", score, conf
    return ("positive" if score > 0 else "negative"), score, conf

def agreement(label, rating):
    """Compare text sentiment with rating without assuming they agree."""
    if label == "uncertain":
        return "undetermined"
    if rating == 3:
        return "neutral rating"
    return "agree" if label == ("positive" if rating >= 4 else "negative") else "disagree"

def discover_themes(texts, k=5, seed=42):
    """Returns (theme names, distance-to-centroid). Lower distance = more representative."""
    n = len(texts)
    k = max(1, min(k, n // 5))
    vec = TfidfVectorizer(stop_words="english", ngram_range=(1, 2), min_df=2 if n >= 20 else 1, max_df=0.8)
    try:
        X = vec.fit_transform(texts)
    except ValueError:
        return ["unclassified"] * n, np.zeros(n)
    km = KMeans(k, n_init=10, random_state=seed).fit(X)
    terms, names = np.array(vec.get_feature_names_out()), {}
    for c in range(k):
        name = " / ".join(terms[np.argsort(km.cluster_centers_[c])[::-1][:3]])
        names[c] = name if name not in names.values() else f"{name} #{c}"
    return [names[l] for l in km.labels_], km.transform(X).min(axis=1)

def analyse(df, k=5, min_conf=0.3, progress=None, timeout_s=None):
    """Batched analysis. Raises TimeoutError if the time budget is exceeded (nothing is saved then).
    A record whose scoring fails is labelled 'uncertain' instead of aborting the run."""
    deadline = time.monotonic() + (timeout_s or TIMEOUT_S)
    out, total, res = df.copy(), len(df), []
    texts = out.text.tolist()
    for i in range(0, total, BATCH_SIZE):
        if time.monotonic() > deadline:
            raise TimeoutError(f"Analysis exceeded {timeout_s or TIMEOUT_S}s. Use a smaller file or raise FBI_TIMEOUT_S.")
        for t in texts[i:i + BATCH_SIZE]:
            try:
                res.append(sentiment(t, min_conf))
            except Exception:
                res.append(("uncertain", 0.0, 0.0))
        if progress:
            progress(0.6 * min(1, (i + BATCH_SIZE) / total), f"Scoring sentiment ({min(i + BATCH_SIZE, total)}/{total})...")
    out["sentiment"], out["score"], out["conf"] = zip(*res)
    out["agreement"] = [agreement(s, r) for s, r in zip(out.sentiment, out.rating)]
    if progress:
        progress(0.7, "Discovering themes...")
    if time.monotonic() > deadline:
        raise TimeoutError("Analysis exceeded its time limit before theme discovery.")
    out["theme"], out["dist"] = discover_themes(texts, k)
    return out
