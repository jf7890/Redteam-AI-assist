from __future__ import annotations

import hashlib
import math
from collections.abc import Sequence
from typing import Protocol

from huggingface_hub import InferenceClient


class Embedder(Protocol):
    def embed_texts(self, texts: list[str]) -> list[list[float]]:
        ...


class HashingEmbedder:
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
    def __init__(self, token: str, model: str, fallback: Embedder | None = None) -> None:
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
