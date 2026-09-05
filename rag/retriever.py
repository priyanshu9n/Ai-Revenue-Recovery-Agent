"""
Small RAG retriever over the policy_docs/ knowledge base.

Uses scikit-learn's TF-IDF + cosine similarity instead of standing up a
FAISS/Chroma server - for ~6 short documents a full vector DB is
overkill, and this keeps the buildathon submission dependency-light
while still being genuine retrieval (not a hardcoded lookup table).
Swapping in FAISS/Chroma later is a drop-in change to `_load_index`.
"""

from pathlib import Path

from sklearn.feature_extraction.text import TfidfVectorizer
from sklearn.metrics.pairwise import cosine_similarity

DOCS_DIR = Path(__file__).parent / "policy_docs"

_vectorizer = None
_doc_matrix = None
_doc_names = None
_doc_texts = None


def _load_index():
    global _vectorizer, _doc_matrix, _doc_names, _doc_texts
    if _vectorizer is not None:
        return
    paths = sorted(DOCS_DIR.glob("*.md"))
    _doc_names = [p.name for p in paths]
    _doc_texts = [p.read_text() for p in paths]
    _vectorizer = TfidfVectorizer(stop_words="english")
    _doc_matrix = _vectorizer.fit_transform(_doc_texts)


def retrieve(query: str, top_k: int = 2):
    """Returns [{"source": filename, "text": doc_text, "score": float}, ...]"""
    _load_index()
    q_vec = _vectorizer.transform([query])
    sims = cosine_similarity(q_vec, _doc_matrix)[0]
    ranked = sorted(range(len(sims)), key=lambda i: sims[i], reverse=True)[:top_k]
    return [
        {"source": _doc_names[i], "text": _doc_texts[i], "score": float(sims[i])}
        for i in ranked
    ]


if __name__ == "__main__":
    for r in retrieve("Can I retry this transaction?"):
        print(f"[{r['score']:.2f}] {r['source']}")
        print(r["text"][:200], "...\n")
