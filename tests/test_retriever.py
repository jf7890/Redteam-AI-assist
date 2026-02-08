from pathlib import Path

from redteam_ai_assist.rag.embeddings import HashingEmbedder
from redteam_ai_assist.rag.retriever import RagRetriever
from redteam_ai_assist.rag.store import JsonVectorStore, VectorRecord


def test_retriever_focus_report_filters_context(tmp_path: Path) -> None:
    embedder = HashingEmbedder()
    store = JsonVectorStore(index_path=tmp_path / "index.jsonl")

    texts = [
        "Recon checklist: inventory services and exposed ports.",
        "Reporting template: timeline, findings, and evidence references.",
    ]
    vectors = embedder.embed_texts(texts)
    records = [
        VectorRecord(
            record_id="recon-1",
            text=texts[0],
            metadata={"source": "01_phase_checklist.md"},
            embedding=vectors[0],
        ),
        VectorRecord(
            record_id="report-1",
            text=texts[1],
            metadata={"source": "02_reporting_template.md"},
            embedding=vectors[1],
        ),
    ]
    store.write_records(records)

    retriever = RagRetriever(embedder=embedder, store=store)
    result = retriever.query("need report template", top_k=2, focus="report")

    assert result
    assert "report" in result[0].source.lower() or "template" in result[0].content.lower()
