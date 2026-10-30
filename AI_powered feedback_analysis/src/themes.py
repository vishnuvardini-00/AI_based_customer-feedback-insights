from __future__ import annotations

import re
import uuid


def discover_themes(texts: list[str]) -> tuple[list[dict], list[str | None]]:
    if not texts:
        return [], []
    try:
        import numpy as np
        from sklearn.cluster import KMeans
        from sklearn.feature_extraction.text import TfidfVectorizer

        vectorizer = TfidfVectorizer(
            stop_words="english", max_features=1500, ngram_range=(1, 2), min_df=1
        )
        matrix = vectorizer.fit_transform(texts)
        if matrix.shape[1] == 0:
            raise ValueError("No informative terms")
        n_clusters = min(8, max(1, int(len(texts) ** 0.5)), len(texts))
        if matrix.shape[0] < 4:
            n_clusters = 1
        labels = (
            KMeans(n_clusters=n_clusters, random_state=42, n_init=10)
            .fit_predict(matrix)
            if n_clusters > 1
            else np.zeros(len(texts), dtype=int)
        )
        terms = vectorizer.get_feature_names_out()
        themes, assignments = [], [None] * len(texts)
        for label in sorted(set(int(value) for value in labels)):
            indexes = [i for i, value in enumerate(labels) if int(value) == label]
            mean_scores = matrix[indexes].mean(axis=0).A1
            top = [str(terms[i]) for i in mean_scores.argsort()[::-1] if mean_scores[i] > 0][:5]
            name = " / ".join(word.title() for word in top[:2]) or "General Feedback"
            theme_id = str(uuid.uuid4())
            themes.append({"theme_id": theme_id, "name": name, "keywords": top})
            for index in indexes:
                assignments[index] = theme_id
        return themes, assignments
    except (ValueError, ImportError):
        theme_id = str(uuid.uuid4())
        keywords = _keywords(" ".join(texts))
        return [{"theme_id": theme_id, "name": "General Feedback", "keywords": keywords}], [theme_id] * len(texts)


def _keywords(text: str) -> list[str]:
    words = re.findall(r"[a-z]{4,}", text.casefold())
    common = {"this", "that", "with", "have", "from", "very", "they", "there", "were"}
    return [word for word, _ in __import__("collections").Counter(w for w in words if w not in common).most_common(5)]
