"""
Embedding generation service.
Provides vector embeddings for meeting transcripts, structured memories, and company documents.
Supports local SentenceTransformers with fallback to API or fast hash/onnx embedding.
"""
import asyncio
import threading
import numpy as np
from typing import List, Union
from app.config import settings


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
                # On a constrained/shared-vCPU container (e.g. Railway's default
                # plan), PyTorch's default of spawning one thread per visible CPU
                # causes severe contention rather than speedup - each encode()
                # call was taking 14+ seconds instead of the expected tens of
                # milliseconds. Pinning to a single thread removes that overhead.
                import torch
                torch.set_num_threads(1)
                from sentence_transformers import SentenceTransformer
                self._model = SentenceTransformer(self.model_name)
                self._initialized = True
                print(f"[INFO] Loaded SentenceTransformer model: {self.model_name}")
            except Exception as e:
                print(f"[WARN] SentenceTransformers unavailable ({e}). Using deterministic fallback embedding.")
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
            embeddings = self._model.encode(clean_texts, show_progress_bar=False)
            return [vec.tolist() for vec in embeddings]

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
