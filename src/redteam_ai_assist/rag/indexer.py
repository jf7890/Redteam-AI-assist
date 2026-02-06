from __future__ import annotations

from pathlib import Path

from redteam_ai_assist.rag.embeddings import Embedder
from redteam_ai_assist.rag.loader import load_and_chunk
from redteam_ai_assist.rag.store import JsonVectorStore, VectorRecord


def build_rag_index(
    source_dir: Path,
    index_path: Path,
    embedder: Embedder,
    chunk_size: int = 1200,
) -> int:
    chunks = load_and_chunk(source_dir=source_dir, chunk_size=chunk_size)
    store = JsonVectorStore(index_path=index_path)
    if not chunks:
        store.write_records([])
        return 0

    embeddings = embedder.embed_texts([chunk.text for chunk in chunks])
    records: list[VectorRecord] = []
    for chunk, embedding in zip(chunks, embeddings, strict=True):
        records.append(
            VectorRecord(
                record_id=chunk.chunk_id,
                text=chunk.text,
                metadata=chunk.metadata,
                embedding=embedding,
            )
        )

    store.write_records(records)
    return len(records)
