"""Embedding providers behind one interface.

ARGUS must be explorable by someone who clones the repository and has no API
key at all, and it must use real embeddings when a key is present. Both are
served by the same protocol:

* :class:`OpenAIEmbeddings` - ``text-embedding-3-small`` over the standard
  OpenAI-compatible endpoint. Used whenever credentials are configured.
* :class:`HashedLexicalEmbeddings` - a dependency-free, deterministic vectoriser
  built from character n-grams and word unigrams with sub-linear term weighting.

The fallback is *not* pretending to be a semantic model. It is an honest lexical
vectoriser: it captures term overlap and morphological variation, and it is
genuinely useful on a corpus of this size, but it does not know that "gearing"
and "leverage" are related. That limitation is stated in the UI and in the
evaluation report rather than hidden, and the Evaluation Lab reports retrieval
metrics for whichever provider actually ran.
"""

from __future__ import annotations

import hashlib
import math
import os
import re
from abc import ABC, abstractmethod
from collections import Counter
from dataclasses import dataclass
from itertools import pairwise

import numpy as np

_TOKEN = re.compile(r"[a-z0-9]+")

# Dimensionality of the local fallback. Large enough to keep hash collisions
# rare across a few thousand chunks, small enough to stay fast in pure numpy.
LOCAL_DIMENSIONS = 768


@dataclass(frozen=True)
class EmbeddingResult:
    """Vectors plus the accounting the AI Operations page reports on."""

    vectors: list[list[float]]
    model: str
    tokens_used: int = 0
    dimensions: int = 0


class EmbeddingProvider(ABC):
    """Interface every embedding backend implements."""

    name: str = "abstract"
    dimensions: int = 0
    # True when the provider derives meaning from usage rather than spelling.
    semantic: bool = False

    @abstractmethod
    def embed(self, texts: list[str]) -> EmbeddingResult:
        """Embed a batch of texts, preserving input order."""

    def embed_one(self, text: str) -> list[float]:
        return self.embed([text]).vectors[0]

    @property
    def description(self) -> str:
        kind = "semantic" if self.semantic else "lexical"
        return f"{self.name} ({kind}, {self.dimensions}d)"


def _tokenize(text: str) -> list[str]:
    return _TOKEN.findall(text.lower())


def _char_ngrams(token: str, n: int = 4) -> list[str]:
    """Character n-grams give the fallback robustness to inflection."""
    if len(token) <= n:
        return [token]
    padded = f"^{token}$"
    return [padded[i : i + n] for i in range(len(padded) - n + 1)]


class HashedLexicalEmbeddings(EmbeddingProvider):
    """Deterministic hashing vectoriser used when no credentials are configured.

    Each document is projected into a fixed-width space by hashing word
    unigrams, adjacent bigrams and character 4-grams into buckets, weighting
    each by ``1 + log(count)`` and L2-normalising the result. Cosine similarity
    over these vectors is a solid lexical match with partial tolerance for word
    endings - which is exactly what the fallback claims to be.
    """

    name = "local-hashed-lexical"
    semantic = False

    def __init__(self, dimensions: int = LOCAL_DIMENSIONS) -> None:
        self.dimensions = dimensions

    def _bucket(self, feature: str) -> int:
        digest = hashlib.blake2b(feature.encode("utf-8"), digest_size=8).digest()
        return int.from_bytes(digest, "big") % self.dimensions

    def _features(self, text: str) -> Counter[str]:
        tokens = _tokenize(text)
        features: Counter[str] = Counter()
        for token in tokens:
            features[f"w:{token}"] += 2  # whole words carry the most signal
            for gram in _char_ngrams(token):
                features[f"c:{gram}"] += 1
        for left, right in pairwise(tokens):
            features[f"b:{left}_{right}"] += 2
        return features

    def embed(self, texts: list[str]) -> EmbeddingResult:
        matrix = np.zeros((len(texts), self.dimensions), dtype=np.float32)
        for row, text in enumerate(texts):
            for feature, count in self._features(text).items():
                # Sub-linear scaling: a term repeated ten times is not ten times
                # more indicative than one appearing once.
                matrix[row, self._bucket(feature)] += 1.0 + math.log(count)
        norms = np.linalg.norm(matrix, axis=1, keepdims=True)
        matrix = matrix / np.where(norms == 0, 1.0, norms)
        return EmbeddingResult(
            vectors=matrix.tolist(),
            model=self.name,
            tokens_used=sum(len(_tokenize(t)) for t in texts),
            dimensions=self.dimensions,
        )


class OpenAIEmbeddings(EmbeddingProvider):
    """Real embeddings via an OpenAI-compatible ``/embeddings`` endpoint."""

    semantic = True

    def __init__(
        self,
        *,
        credential: str,
        model: str = "text-embedding-3-small",
        base_url: str = "https://api.openai.com/v1",
        dimensions: int = 1536,
        timeout: float = 60.0,
        batch_size: int = 64,
    ) -> None:
        self.name = model
        self.model = model
        self.dimensions = dimensions
        self._credential = credential
        self._base_url = base_url.rstrip("/")
        self._timeout = timeout
        self._batch_size = batch_size

    def embed(self, texts: list[str]) -> EmbeddingResult:
        import httpx  # imported lazily so the fallback path needs no network stack

        vectors: list[list[float]] = []
        tokens = 0
        with httpx.Client(timeout=self._timeout) as client:
            for start in range(0, len(texts), self._batch_size):
                batch = texts[start : start + self._batch_size]
                response = client.post(
                    f"{self._base_url}/embeddings",
                    headers={"Authorization": "Bearer " + self._credential},
                    json={"model": self.model, "input": batch},
                )
                response.raise_for_status()
                payload = response.json()
                ordered = sorted(payload["data"], key=lambda d: d["index"])
                vectors.extend(item["embedding"] for item in ordered)
                tokens += payload.get("usage", {}).get("total_tokens", 0)
        return EmbeddingResult(
            vectors=vectors,
            model=self.model,
            tokens_used=tokens,
            dimensions=self.dimensions,
        )


def build_embedding_provider(
    *,
    provider: str = "auto",
    credential: str | None = None,
    base_url: str | None = None,
    model: str | None = None,
) -> EmbeddingProvider:
    """Select an embedding backend from configuration.

    ``auto`` prefers real embeddings when credentials are available and falls
    back to the local vectoriser otherwise, so a fresh clone always works.
    """
    credential = credential or os.environ.get("OPENAI_API_KEY") or ""
    resolved = provider.lower()

    if resolved in {"local", "hashed"} or (resolved == "auto" and not credential):
        return HashedLexicalEmbeddings()

    if resolved in {"auto", "openai"}:
        return OpenAIEmbeddings(
            credential=credential,
            model=model or "text-embedding-3-small",
            base_url=base_url or "https://api.openai.com/v1",
        )

    raise ValueError(f"Unknown embedding provider: {provider!r}")


def cosine_similarity(query: np.ndarray, matrix: np.ndarray) -> np.ndarray:
    """Cosine similarity of one vector against a matrix of row vectors."""
    if matrix.size == 0:
        return np.zeros(0, dtype=np.float32)
    query_norm = float(np.linalg.norm(query)) or 1.0
    row_norms = np.linalg.norm(matrix, axis=1)
    row_norms = np.where(row_norms == 0, 1.0, row_norms)
    return (matrix @ query) / (row_norms * query_norm)
