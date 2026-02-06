from __future__ import annotations

import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
SRC_DIR = PROJECT_ROOT / "src"
if str(SRC_DIR) not in sys.path:
    sys.path.insert(0, str(SRC_DIR))

from redteam_ai_assist.config import get_settings
from redteam_ai_assist.services.assistant_service import AssistantService


def main() -> None:
    settings = get_settings()
    service = AssistantService(settings=settings)
    result = service.rebuild_rag_index()
    print(
        f"Indexed {result.indexed_chunks} chunks from "
        f"{result.source_dir} -> {result.index_path}"
    )


if __name__ == "__main__":
    main()
