"""
Download the embedding model into a directory the desktop build ships.

The server normally fetches all-MiniLM-L6-v2 (~90 MB) on first use. A
desktop install on a machine without internet at first launch - or behind a
proxy that blocks Hugging Face - then has no search, Ask AI retrieval or
knowledge graph, and the failure is quiet. Bundling the weights removes
that dependency: the release workflow runs this before PyInstaller, and
desktop/server.spec ships the directory as `models/`, which the frozen
server copies into its data directory on first start.

    python scripts/fetch_embedding_model.py            # into desktop/models
    python scripts/fetch_embedding_model.py some/dir
"""
from __future__ import annotations

import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

from app.config import settings  # noqa: E402
from app.services.embedding import _fastembed_name  # noqa: E402


def main() -> None:
    target = Path(sys.argv[1] if len(sys.argv) > 1 else PROJECT_ROOT / "desktop" / "models").resolve()
    target.mkdir(parents=True, exist_ok=True)
    from fastembed import TextEmbedding

    model = TextEmbedding(model_name=_fastembed_name(settings.EMBEDDING_MODEL), cache_dir=str(target), threads=1)
    # One real embedding proves the files are complete, not just present.
    vector = next(iter(model.embed(["ready"])))
    assert len(vector) == settings.EMBEDDING_DIMENSION, len(vector)
    size = sum(p.stat().st_size for p in target.rglob("*") if p.is_file())
    print(f"embedding model {settings.EMBEDDING_MODEL} ready in {target} ({size / 1_048_576:.0f} MB)")


if __name__ == "__main__":
    main()
