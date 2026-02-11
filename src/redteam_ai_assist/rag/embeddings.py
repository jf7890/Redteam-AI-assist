from __future__ import annotations

import hashlib
import math
from collections.abc import Sequence
from typing import Protocol


class Embedder(Protocol):
    def embed_texts(self, texts: list[str]) -> list[list[float]]:
        ...


class HashingEmbedder:
    """Zero-dependency deterministic embedder (fallback).

    It is *not* semantically great, but good enough for an MVP RAG pipeline
    in a fully offline environment.
    """

    def __init__(self, dimensions: int = 384) -> None:
        self.dimensions = dimensions

    def embed_texts(self, texts: list[str]) -> list[list[float]]:
        vectors: list[list[float]] = []
        for text in texts:
            vector = [0.0] * self.dimensions
            for token in text.lower().split():
                token_hash = int(hashlib.sha256(token.encode("utf-8")).hexdigest(), 16)
                vector[token_hash % self.dimensions] += 1.0
            norm = math.sqrt(sum(value * value for value in vector)) or 1.0
            vectors.append([value / norm for value in vector])
        return vectors


class HuggingFaceHostedEmbedder:
    """Hugging Face Inference API embedder.

    Import of huggingface_hub is intentionally lazy so unit tests (and offline
    environments) don't fail at import time.
    """

    def __init__(self, token: str, model: str, fallback: Embedder | None = None) -> None:
        try:
            from huggingface_hub import InferenceClient  # type: ignore
        except ModuleNotFoundError as exc:
            raise ModuleNotFoundError(
                "huggingface_hub is required for HuggingFaceHostedEmbedder. "
                "Install requirements.txt or set HF_TOKEN empty to use HashingEmbedder."
            ) from exc

        self.client = InferenceClient(token=token)
        self.model = model
        self.fallback = fallback

    def embed_texts(self, texts: list[str]) -> list[list[float]]:
        try:
            raw = self.client.feature_extraction(texts, model=self.model)
            return _normalize_feature_extraction_output(raw, len(texts))
        except Exception:
            if self.fallback is None:
                raise
            return self.fallback.embed_texts(texts)


def _normalize_feature_extraction_output(raw: object, expected_size: int) -> list[list[float]]:
    if not isinstance(raw, Sequence):
        raise ValueError("Unexpected embedding response type from Hugging Face inference API")

    if expected_size == 1 and raw and isinstance(raw[0], (float, int)):
        return [[float(value) for value in raw]]

    normalized: list[list[float]] = []
    for item in raw:
        if not isinstance(item, Sequence):
            raise ValueError("Invalid embedding row in Hugging Face output")
        normalized.append([float(value) for value in item])
    return normalized


class CachedEmbedder:
    """A small per-text embedding cache wrapper.

    This reduces repeated embedding calls when many sessions ask similar questions.

    The cache object only needs two methods:
      - get_json(key) -> Any|None
      - set_json(key, value, ttl_seconds=None)

    See: redteam_ai_assist.storage.sqlite_cache.SQLiteCache
    """

    def __init__(
        self,
        base: Embedder,
        cache,
        namespace: str,
        ttl_seconds: int | None = None,
        max_entries: int | None = 50_000,
    ) -> None:
        self.base = base
        self.cache = cache
        self.namespace = namespace
        self.ttl_seconds = ttl_seconds
        self.max_entries = max_entries

    def embed_texts(self, texts: list[str]) -> list[list[float]]:
        if not texts:
            return []

        results: list[list[float] | None] = [None] * len(texts)
        missing_texts: list[str] = []
        missing_keys: list[str] = []
        missing_indices: list[int] = []

        for idx, text in enumerate(texts):
            key = self._key_for(text)
            cached = None
            try:
                cached = self.cache.get_json(key)
            except Exception:
                cached = None

            if isinstance(cached, list) and cached and all(isinstance(x, (float, int)) for x in cached):
                results[idx] = [float(x) for x in cached]
            else:
                missing_texts.append(text)
                missing_keys.append(key)
                missing_indices.append(idx)

        if missing_texts:
            vectors = self.base.embed_texts(missing_texts)
            for key, out_idx, vec in zip(missing_keys, missing_indices, vectors, strict=False):
                results[out_idx] = vec
                try:
                    self.cache.set_json(key, vec, ttl_seconds=self.ttl_seconds)
                except Exception:
                    # Cache is best-effort.
                    pass

            # Best-effort pruning.
            try:
                if self.max_entries is not None and hasattr(self.cache, "prune"):
                    self.cache.prune(max_entries=self.max_entries)
            except Exception:
                pass

        # mypy: now all are filled
        return [vec if vec is not None else [0.0] for vec in results]

    def _key_for(self, text: str) -> str:
        normalized = " ".join(text.strip().split())
        digest = hashlib.sha256(f"{self.namespace}:{normalized}".encode("utf-8")).hexdigest()
        return f"emb:{digest}"
