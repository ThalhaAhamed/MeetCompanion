"""
Embedding generation service.

Vectors for transcripts, memories, notes and documents come from a local
all-MiniLM-L6-v2 model run through ONNX (fastembed). The ONNX build produces
the same 384-dimensional vectors as the PyTorch original, so databases
embedded with sentence-transformers keep working, while the dependency is
tens of megabytes instead of the two gigabytes PyTorch needs - which is what
makes a downloadable desktop build possible.

The model weights (~90 MB) live in EMBEDDING_CACHE_DIR. The desktop build
ships them (see scripts/fetch_embedding_model.py) and copies them there on
first start; a server install fetches them on first use. Without them the
service falls back to a deterministic hash embedding so the application
still runs.
"""
import asyncio
import os
import shutil
import threading
import numpy as np
from pathlib import Path
from typing import List, Union
from app.config import settings
import logging

logger = logging.getLogger(__name__)


def _fastembed_name(model_name: str) -> str:
    """Accept the short sentence-transformers name people already have in .env."""
    if "/" in model_name:
        return model_name
    return f"sentence-transformers/{model_name}"


def seed_cache_from_bundle(cache_dir: str | None, bundle_dir: str | None) -> bool:
    """
    Copy bundled model weights into the cache directory if it has none yet.

    The desktop app ships the weights inside its (read-only) install and
    points MEET_COMPANION_BUNDLED_MODELS at them; fastembed wants a writable
    cache, so they are copied once into the data directory rather than read
    in place. Returns True when a copy happened.
    """
    if not cache_dir or not bundle_dir:
        return False
    src, dst = Path(bundle_dir), Path(cache_dir)
    if not src.is_dir() or not any(src.iterdir()):
        return False
    if dst.is_dir() and any(dst.glob("models--*")):
        return False
    dst.mkdir(parents=True, exist_ok=True)
    for entry in src.iterdir():
        if entry.name.startswith("."):
            continue  # hub lock files are not part of the model
        target = dst / entry.name
        if entry.is_dir():
            shutil.copytree(entry, target, dirs_exist_ok=True)
        else:
            shutil.copy2(entry, target)
    return True


class EmbeddingService:
    def __init__(self, model_name: str = settings.EMBEDDING_MODEL, dimension: int = settings.EMBEDDING_DIMENSION):
        self.model_name = model_name
        self.dimension = dimension
        self._model = None
        self._initialized = False
        # _init_model runs in worker threads (via asyncio.to_thread, from both the
        # startup warmup and any concurrent request that beats it there) - guard
        # against loading the multi-hundred-MB model twice in parallel.
        self._init_lock = threading.Lock()

    def _init_model(self):
        if self._initialized:
            return
        with self._init_lock:
            if self._initialized:
                return
            try:
                from fastembed import TextEmbedding

                if seed_cache_from_bundle(settings.EMBEDDING_CACHE_DIR, os.environ.get("MEET_COMPANION_BUNDLED_MODELS")):
                    logger.info("Copied the bundled embedding model into %s", settings.EMBEDDING_CACHE_DIR)
                kwargs = dict(
                    model_name=_fastembed_name(self.model_name),
                    cache_dir=str(settings.EMBEDDING_CACHE_DIR) if settings.EMBEDDING_CACHE_DIR else None,
                    # One thread: on shared-vCPU hosts more threads contend
                    # rather than speed up, and the desktop app should not
                    # peg every core while a meeting is being indexed.
                    threads=1,
                )
                # fastembed asks the hub before using its cache, and with no
                # network it gives up after minutes of retries - even when
                # every file is already on disk. Local first, download only
                # when there is nothing local.
                try:
                    self._model = TextEmbedding(local_files_only=True, **kwargs)
                    source = "local"
                except Exception:
                    self._model = TextEmbedding(**kwargs)
                    source = "downloaded"
                self._initialized = True
                logger.info(f"Loaded embedding model: {self.model_name} (ONNX, {source})")
            except Exception as e:
                logger.warning(f"Embedding model unavailable ({e}). Using deterministic fallback embedding.")
                self._initialized = True

    async def embed_text_async(self, text: str) -> List[float]:
        """Non-blocking version of embed_text - offloads the CPU-bound model call to a thread
        so it doesn't freeze the event loop (and every other in-flight request) while it runs."""
        return (await self.embed_batch_async([text]))[0]

    async def embed_batch_async(self, texts: List[str]) -> List[List[float]]:
        """Non-blocking version of embed_batch - see embed_text_async."""
        return await asyncio.to_thread(self.embed_batch, texts)

    async def warmup_async(self):
        """Load the model in a background thread so the first real request isn't the one
        paying the multi-second model load cost (and blocking the event loop while it does)."""
        await asyncio.to_thread(self._init_model)

    def embed_text(self, text: str) -> List[float]:
        """Generate embedding vector for a single text string."""
        return self.embed_batch([text])[0]

    def embed_batch(self, texts: List[str]) -> List[List[float]]:
        """Generate embedding vectors for a list of text strings."""
        if not texts:
            return []

        self._init_model()

        # Clean text
        clean_texts = [
            str(t or "").encode("utf-8", "ignore").decode("utf-8").strip()
            for t in texts
        ]

        if self._model is not None:
            return [np.asarray(vec, dtype=np.float32).tolist() for vec in self._model.embed(clean_texts)]

        # Deterministic lightweight fallback (e.g. if PyTorch cannot load on low disk space)
        # Generates a normalized 384-dimensional vector based on token hashing
        results = []
        for text in clean_texts:
            vec = np.zeros(self.dimension, dtype=np.float32)
            words = text.lower().split()
            for word in words:
                h = hash(word) % self.dimension
                vec[h] += 1.0
            norm = np.linalg.norm(vec)
            if norm > 0:
                vec = vec / norm
            results.append(vec.tolist())
        return results


embedding_service = EmbeddingService()
