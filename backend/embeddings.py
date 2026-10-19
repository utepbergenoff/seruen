"""Offline LSA embeddings of POI text; JSON/NPZ only, never untrusted pickle.

These are corpus-trained latent vectors, not a pretrained neural language model.
The same tokenizer and IDF are used for documents and queries.
"""

import json
import re
from pathlib import Path

import numpy as np

ALIASES = {
    "quiet": ["тихо", "тихий", "тихое", "спокойно", "тыныш", "quiet"],
    "sockets": ["розетки", "розетка", "sockets", "socket"],
    "wifi": ["wi-fi", "wifi", "интернет"],
    "coffee": ["кофе", "кофейня", "кафе", "coffee", "cafe"],
    "kids": ["детский", "детская", "ребенок", "child", "kids", "бала"],
    "park": ["парк", "прогулка", "прогуляться", "walk", "park", "серуен"],
    "culture": ["музей", "культура", "museum", "culture"],
    "unusual": ["необычное", "необычный", "unusual", "ерекше"],
    "indoor": ["крытое", "помещение", "indoor"],
}
LOOKUP = {v: k for k, values in ALIASES.items() for v in values}


def tokenize(text):
    text = text.lower().replace("ё", "е").replace("wi-fi", "wifi")
    return [LOOKUP.get(t, t) for t in re.findall(r"[\w]+", text) if len(t) > 1]


def poi_text(p):
    description = p.description if p.description_source != "generated" else ""
    tags = [tag for tag in p.tags if tag not in p.tags_inferred]
    return " ".join([p.name, p.name_en or "", p.name_kk or "", p.category, description, *tags])


def build_index(dataset, path: Path):
    from sklearn.decomposition import TruncatedSVD
    from sklearn.feature_extraction.text import TfidfVectorizer

    vectorizer = TfidfVectorizer(tokenizer=tokenize, token_pattern=None, lowercase=False)
    matrix = vectorizer.fit_transform(poi_text(p) for p in dataset.pois)
    dimensions = min(64, matrix.shape[0] - 1, matrix.shape[1] - 1)
    if dimensions < 1:
        raise ValueError("Not enough documents for LSA")
    svd = TruncatedSVD(n_components=dimensions, random_state=42)
    vectors = svd.fit_transform(matrix)
    norms = np.linalg.norm(vectors, axis=1, keepdims=True)
    vectors = vectors / np.maximum(norms, 1e-12)
    payload = dict(
        version=2,
        kind="tfidf_lsa",
        fingerprint=dataset.fingerprint,
        ids=[p.poi_id for p in dataset.pois],
        vocabulary=vectorizer.vocabulary_,
        idf=vectorizer.idf_.tolist(),
        components=svd.components_.tolist(),
        vectors=vectors.tolist(),
    )
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=False), encoding="utf-8")
    return dimensions


class Embeddings:
    def __init__(self, path, dataset):
        data = json.loads(path.read_text(encoding="utf-8"))
        if (
            data["fingerprint"] != dataset.fingerprint
            or data["ids"] != [p.poi_id for p in dataset.pois]
            or data["version"] != 2
        ):
            raise ValueError("stale_index")
        self.vocabulary = data["vocabulary"]
        self.idf = np.array(data["idf"])
        self.components = np.array(data["components"])
        self.vectors = np.array(data["vectors"])

    def similarities(self, text):
        query = np.zeros(len(self.vocabulary))
        for token in tokenize(text):
            if token in self.vocabulary:
                query[self.vocabulary[token]] += 1
        query *= self.idf
        query /= max(float(np.linalg.norm(query)), 1e-12)
        vector = self.components @ query
        vector /= max(float(np.linalg.norm(vector)), 1e-12)
        return np.clip(self.vectors @ vector, 0, 1)
