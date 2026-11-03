"""Keyless lexical retrieval (BM25) for memory stores without an embedding model.

Pure Python, no extra dependencies. Tokenisation lowercases the text, applies
Unicode NFC normalisation (so Vietnamese diacritics compare consistently) and
splits on non-word characters. CJK ideographs have no spaces between words, so
they are indexed as single characters plus adjacent bigrams.
"""

from __future__ import annotations

import math
import re
import unicodedata
from collections import Counter
from typing import Iterable, List, Sequence, Tuple, TypeVar

T = TypeVar("T")

_WORD_RE = re.compile(r"\w+", re.UNICODE)
_CJK_RE = re.compile(r"[぀-ヿ㐀-䶿一-鿿豈-﫿가-힯]")

# BM25 parameters (standard defaults).
_K1 = 1.5
_B = 0.75


def tokenize(text: str | None) -> List[str]:
    """Split ``text`` into lowercase Unicode word tokens."""
    if not text:
        return []
    normalized = unicodedata.normalize("NFC", str(text)).lower()
    tokens: List[str] = []
    for word in _WORD_RE.findall(normalized):
        if word == "_" * len(word):
            continue
        if _CJK_RE.search(word):
            tokens.extend(_split_cjk(word))
        else:
            tokens.append(word)
    return tokens


def _split_cjk(word: str) -> Iterable[str]:
    """Emit non-CJK runs as words, CJK runs as unigrams + bigrams."""
    run: List[str] = []
    buffer = ""
    out: List[str] = []

    def flush_run() -> None:
        if not run:
            return
        out.extend(run)
        out.extend(run[i] + run[i + 1] for i in range(len(run) - 1))
        run.clear()

    for ch in word:
        if _CJK_RE.match(ch):
            if buffer:
                out.append(buffer)
                buffer = ""
            run.append(ch)
        else:
            flush_run()
            buffer += ch
    flush_run()
    if buffer:
        out.append(buffer)
    return out


def bm25_scores(query: str, documents: Sequence[str]) -> List[float]:
    """Return a BM25 score per document for ``query`` (0.0 = no overlap)."""
    query_terms = set(tokenize(query))
    if not query_terms or not documents:
        return [0.0] * len(documents)

    doc_tokens = [tokenize(doc) for doc in documents]
    doc_counts = [Counter(tokens) for tokens in doc_tokens]
    lengths = [len(tokens) for tokens in doc_tokens]
    n_docs = len(documents)
    avg_len = (sum(lengths) / n_docs) or 1.0

    doc_freq = {term: sum(1 for counts in doc_counts if term in counts) for term in query_terms}

    scores: List[float] = []
    for counts, length in zip(doc_counts, lengths):
        score = 0.0
        for term in query_terms:
            tf = counts.get(term, 0)
            if not tf:
                continue
            df = doc_freq[term]
            idf = math.log(1.0 + (n_docs - df + 0.5) / (df + 0.5))
            score += idf * (tf * (_K1 + 1)) / (tf + _K1 * (1 - _B + _B * length / avg_len))
        scores.append(score)
    return scores


def rank_by_keywords(
    query: str,
    items: Sequence[T],
    *,
    text_of,
    top_k: int,
    similarity_threshold: float = -1.0,
) -> List[Tuple[T, float]]:
    """Rank ``items`` by BM25 relevance to ``query``.

    Scores are normalised to ``(0, 1]`` relative to the best match so that
    ``similarity_threshold`` (``-1`` = disabled) keeps a familiar meaning. Items
    sharing no token with the query are never returned; an empty query returns
    nothing.
    """
    if not items or top_k <= 0:
        return []
    raw = bm25_scores(query, [text_of(item) or "" for item in items])
    best = max(raw, default=0.0)
    if best <= 0.0:
        return []
    ranked = [
        (item, score / best)
        for item, score in zip(items, raw)
        if score > 0.0 and score / best >= similarity_threshold
    ]
    # Stable sort keeps insertion order for ties; prefer newer items on ties.
    ranked = list(reversed(ranked))
    ranked.sort(key=lambda entry: entry[1], reverse=True)
    return ranked[:top_k]


__all__ = ["tokenize", "bm25_scores", "rank_by_keywords"]
