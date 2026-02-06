from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path


@dataclass(slots=True)
class TextChunk:
    chunk_id: str
    text: str
    metadata: dict[str, str]


def load_documents(source_dir: Path) -> list[tuple[Path, str]]:
    if not source_dir.exists():
        return []

    docs: list[tuple[Path, str]] = []
    for path in sorted(source_dir.rglob("*")):
        if not path.is_file():
            continue
        if path.suffix.lower() not in {".md", ".txt"}:
            continue
        content = path.read_text(encoding="utf-8")
        if content.strip():
            docs.append((path, content))
    return docs


def chunk_document(path: Path, content: str, chunk_size: int = 1200) -> list[TextChunk]:
    chunks: list[TextChunk] = []
    paragraphs = [paragraph.strip() for paragraph in content.split("\n\n") if paragraph.strip()]
    buffer = ""
    index = 0

    for paragraph in paragraphs:
        candidate = f"{buffer}\n\n{paragraph}".strip() if buffer else paragraph
        if len(candidate) <= chunk_size:
            buffer = candidate
            continue

        if buffer:
            chunk_id = f"{path.stem}-{index:03d}"
            chunks.append(
                TextChunk(
                    chunk_id=chunk_id,
                    text=buffer,
                    metadata={"source": str(path), "chunk": str(index)},
                )
            )
            index += 1

        buffer = paragraph

    if buffer:
        chunk_id = f"{path.stem}-{index:03d}"
        chunks.append(
            TextChunk(
                chunk_id=chunk_id,
                text=buffer,
                metadata={"source": str(path), "chunk": str(index)},
            )
        )
    return chunks


def load_and_chunk(source_dir: Path, chunk_size: int = 1200) -> list[TextChunk]:
    chunks: list[TextChunk] = []
    for path, content in load_documents(source_dir):
        chunks.extend(chunk_document(path, content, chunk_size=chunk_size))
    return chunks
