from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from threading import Lock
from typing import Any

import numpy as np


@dataclass(slots=True)
class VectorRecord:
    record_id: str
    text: str
    metadata: dict[str, Any]
    embedding: list[float]


class JsonVectorStore:
    """A simple JSONL vector store.

    MVP++ improvements:
    - In-memory caching of loaded records to avoid re-parsing JSONL for every query.
    - A lightweight index version token (mtime_ns + file size) for cache invalidation.
    """

    def __init__(self, index_path: Path) -> None:
        self.index_path = index_path
        self.index_path.parent.mkdir(parents=True, exist_ok=True)

        self._cache_lock = Lock()
        self._cached_signature: tuple[int, int] | None = None  # (mtime_ns, size)
        self._cached_records: list[VectorRecord] | None = None

    def write_records(self, records: list[VectorRecord]) -> None:
        with self.index_path.open("w", encoding="utf-8") as handle:
            for record in records:
                handle.write(
                    json.dumps(
                        {
                            "record_id": record.record_id,
                            "text": record.text,
                            "metadata": record.metadata,
                            "embedding": record.embedding,
                        },
                        ensure_ascii=True,
                    )
                )
                handle.write("\n")

        # Refresh cache after write.
        with self._cache_lock:
            self._cached_records = records
            self._cached_signature = self._index_signature()

    def index_version(self) -> str:
        """A token you can include in higher-level cache keys."""

        mtime_ns, size = self._index_signature()
        return f"{mtime_ns}:{size}"

    def load_records(self) -> list[VectorRecord]:
        signature = self._index_signature()

        with self._cache_lock:
            if self._cached_records is not None and self._cached_signature == signature:
                return self._cached_records

        if not self.index_path.exists():
            with self._cache_lock:
                self._cached_records = []
                self._cached_signature = signature
            return []

        records: list[VectorRecord] = []
        with self.index_path.open("r", encoding="utf-8") as handle:
            for line in handle:
                line = line.strip()
                if not line:
                    continue
                payload = json.loads(line)
                records.append(
                    VectorRecord(
                        record_id=payload["record_id"],
                        text=payload["text"],
                        metadata=payload["metadata"],
                        embedding=[float(value) for value in payload["embedding"]],
                    )
                )

        with self._cache_lock:
            self._cached_records = records
            self._cached_signature = signature

        return records

    def search(self, query_embedding: list[float], top_k: int = 4) -> list[tuple[VectorRecord, float]]:
        records = self.load_records()
        if not records:
            return []

        query = np.array(query_embedding, dtype=float)
        query_norm = np.linalg.norm(query)
        if query_norm == 0:
            return []

        scored: list[tuple[VectorRecord, float]] = []
        for record in records:
            candidate = np.array(record.embedding, dtype=float)
            denominator = np.linalg.norm(candidate) * query_norm
            score = float(np.dot(query, candidate) / denominator) if denominator else 0.0
            scored.append((record, score))

        scored.sort(key=lambda item: item[1], reverse=True)
        return scored[:top_k]

    def _index_signature(self) -> tuple[int, int]:
        try:
            stat = self.index_path.stat()
            return int(stat.st_mtime_ns), int(stat.st_size)
        except FileNotFoundError:
            return 0, 0
