"""
Embedding generation service.

Vectors for transcripts, memories, notes and documents come from a local
all-MiniLM-L6-v2 model run through ONNX (fastembed). The ONNX build produces
the same 384-dimensional vectors as the PyTorch original, so databases
embedded with sentence-transformers keep working, while the dependency is
tens of megabytes instead of the two gigabytes PyTorch needs - which is what
makes a downloadable desktop build possible.

The model weights (~90 MB) are fetched on first use into EMBEDDING_CACHE_DIR
and reused from then on. Without them the service falls back to a
deterministic hash embedding so the application still runs.
"""
import asyncio
import threading
import numpy as np
from typing import List, Union
from app.config import settings
import logging

logger = logging.getLogger(__name__)


def _fastembed_name(model_name: str) -> str:
    """Accept the short sentence-transformers name people already have in .env."""
    if "/" in model_name:
        return model_name
    return f"sentence-transformers/{model_name}"


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

                self._model = TextEmbedding(
                    model_name=_fastembed_name(self.model_name),
                    cache_dir=str(settings.EMBEDDING_CACHE_DIR) if settings.EMBEDDING_CACHE_DIR else None,
                    # One thread: on shared-vCPU hosts more threads contend
                    # rather than speed up, and the desktop app should not
                    # peg every core while a meeting is being indexed.
                    threads=1,
                )
                self._initialized = True
                logger.info(f"Loaded embedding model: {self.model_name} (ONNX)")
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
