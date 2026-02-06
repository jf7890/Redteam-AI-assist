from __future__ import annotations

from redteam_ai_assist.core.models import RetrievedContext
from redteam_ai_assist.rag.embeddings import Embedder
from redteam_ai_assist.rag.store import JsonVectorStore


class RagRetriever:
    def __init__(self, embedder: Embedder, store: JsonVectorStore) -> None:
        self.embedder = embedder
        self.store = store

    def query(self, text: str, top_k: int = 4) -> list[RetrievedContext]:
        text = text.strip()
        if not text:
            return []

        query_embedding = self.embedder.embed_texts([text])[0]
        matches = self.store.search(query_embedding, top_k=top_k)
        return [
            RetrievedContext(
                source=str(record.metadata.get("source", "unknown")),
                score=score,
                content=record.text,
            )
            for record, score in matches
        ]
