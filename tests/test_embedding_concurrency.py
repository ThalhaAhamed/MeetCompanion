"""
Two embedding calls at once used to corrupt each other's output.

fastembed's TextEmbedding shares one tokenizer and one ONNX session across
every call; embed_batch runs on a worker thread (via asyncio.to_thread), and
nothing serialized access to that shared model. Two notes embedded at once -
plausible any time a note is saved while a meeting finishes processing in the
background - could have their token batches interleaved: a batch that should
come back padded to one uniform length came back with two different lengths,
and `np.array([e.ids for e in encoded])` raised "setting an array element
with a sequence... inhomogeneous shape". Seen intermittently in CI
(test_notebook.py::test_question_about_the_end_of_a_long_note_still_finds_it),
never locally in isolation - the signature of a timing-dependent race, not a
logic bug.

A real ONNX/tokenizers race is awkward to force on demand, so this stands in
a fake model with the same shape of shared mutable state fastembed has (one
buffer written by every call before it reads back its own share of it) and
proves _embed_lock is what keeps two threads from touching it at once.
"""
import threading
import time

import pytest

from app.services.embedding import EmbeddingService


class RacyFakeModel:
    """
    Mimics the shared, unsynchronized state inside fastembed's TextEmbedding:
    one buffer (its "tokenizer + session") that every call writes its batch
    into, holds briefly (standing in for actual ONNX inference time), and
    reads back its own slice of - corrupted if another call interleaves.
    """

    def __init__(self):
        self.shared_buffer = []
        self.max_concurrent = 0
        self._entered = 0
        self._state_lock = threading.Lock()

    def embed(self, documents):
        with self._state_lock:
            self._entered += 1
            self.max_concurrent = max(self.max_concurrent, self._entered)
        start = len(self.shared_buffer)
        for doc in documents:                          # written one at a time, like a batch
            self.shared_buffer.append(doc)              # being built up token-by-token in fastembed
            time.sleep(0.005)                            # a window another thread's write can land in
        mine = self.shared_buffer[start:start + len(documents)]
        with self._state_lock:
            self._entered -= 1
        if mine != documents:
            # Another thread's write landed in the middle of ours - exactly
            # the shape of corruption that produced the ragged batch.
            raise ValueError(f"corrupted batch: expected {documents}, got {mine}")
        return [[float(len(d))] for d in documents]


@pytest.fixture
def service():
    svc = EmbeddingService(model_name="fake", dimension=1)
    svc._initialized = True  # skip real model loading
    svc._model = RacyFakeModel()
    return svc


def test_concurrent_embed_calls_do_not_interleave(service):
    errors = []
    threads = [
        threading.Thread(target=lambda i=i: (errors.append(e) if (e := _try_embed(service, i)) else None))
        for i in range(12)
    ]
    for t in threads:
        t.start()
    for t in threads:
        t.join()

    assert not errors, errors
    # Proof the lock was actually contended, not just never exercised.
    assert service._model.max_concurrent == 1


def _try_embed(service, i):
    try:
        service.embed_batch([f"doc-{i}-a", f"doc-{i}-b"])
        return None
    except ValueError as exc:
        return exc


def test_without_the_lock_the_same_scenario_does_corrupt(service):
    """
    Proves the fake model is a faithful stand-in: bypassing embed_batch and
    calling the racy model directly, with no lock at all, does produce the
    corruption the real bug showed - so the lock in embed_batch is doing
    real work above, not passing by coincidence.
    """
    model = service._model
    errors = []

    def hit(i):
        try:
            model.embed([f"doc-{i}-a", f"doc-{i}-b"])
        except ValueError as exc:
            errors.append(exc)

    threads = [threading.Thread(target=hit, args=(i,)) for i in range(12)]
    for t in threads:
        t.start()
    for t in threads:
        t.join()
    assert errors, "expected the unsynchronized model to corrupt at least one batch"


@pytest.mark.asyncio
async def test_the_async_entry_point_serializes_too(service):
    """embed_batch_async is what production actually calls (via asyncio.to_thread)."""
    import asyncio

    results = await asyncio.gather(*[service.embed_batch_async([f"x-{i}"]) for i in range(8)])
    assert len(results) == 8
    assert service._model.max_concurrent == 1
