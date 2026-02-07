from __future__ import annotations

from redteam_ai_assist.core.models import RetrievedContext
from redteam_ai_assist.rag.embeddings import Embedder
from redteam_ai_assist.rag.store import JsonVectorStore, VectorRecord

REPORT_HINTS = ("report", "template", "timeline", "findings", "final notes")
RECON_HINTS = ("recon", "reconnaissance", "inventory", "service versions")


class RagRetriever:
    def __init__(self, embedder: Embedder, store: JsonVectorStore) -> None:
        self.embedder = embedder
        self.store = store

    def query(self, text: str, top_k: int = 4) -> list[RetrievedContext]:
        text = text.strip()
        if not text:
            return []

        query_embedding = self.embedder.embed_texts([text])[0]
        candidate_k = max(top_k * 2, top_k)
        matches = self.store.search(query_embedding, top_k=candidate_k)
        boosted = self._apply_keyword_boost(text, matches)
        return [
            RetrievedContext(
                source=str(record.metadata.get("source", "unknown")),
                score=score,
                content=record.text,
            )
            for record, score in boosted[:top_k]
        ]

    @staticmethod
    def _apply_keyword_boost(
        query: str, matches: list[tuple[VectorRecord, float]]
    ) -> list[tuple[VectorRecord, float]]:
        query_lower = query.lower()
        boosted: list[tuple[VectorRecord, float]] = []
        wants_report = any(hint in query_lower for hint in REPORT_HINTS)
        wants_recon = any(hint in query_lower for hint in RECON_HINTS)

        for record, score in matches:
            text_lower = record.text.lower()
            source_lower = str(record.metadata.get("source", "")).lower()
            boost = 0.0
            if wants_report and (
                "report" in source_lower or "template" in source_lower or "report" in text_lower
            ):
                boost += 0.15
            if wants_recon and (
                "recon" in text_lower or "checklist" in source_lower or "recon" in source_lower
            ):
                boost += 0.1
            boosted.append((record, score + boost))

        boosted.sort(key=lambda item: item[1], reverse=True)
        return boosted
