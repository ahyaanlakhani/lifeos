"""Embeddings for the memory store.

Token Factory serves no NVIDIA embedding model — checked in the console on
2 Oct 2026, the only embedding endpoint is Qwen3-Embedding-8B at 4096
dimensions. So the choice is self-hosting `llama-nemotron-embed-1b-v2` on AI
Cloud or using the Qwen model, and the decision for now is Qwen: one config
line against a week of infrastructure, with self-hosting reserved for a calm
week four.

**This is an honesty seam.** The submission must say whichever is true on the
day. `MODEL_IS_NVIDIA` below exists so that claim is derived from the config
rather than from memory — see `provenance()`.

Embeddings go through Token Factory like everything else. No agent and no job
calls an embedding API directly, for the same reason they do not call a chat
API directly: the routing and the telemetry have to live in one place.
"""

from __future__ import annotations

import hashlib
import math
import os
import sys
from pathlib import Path
from typing import Any, Callable, Sequence

ROOT = Path(__file__).resolve().parents[2]
for extra in (ROOT, ROOT / "packages" / "inference"):
    if str(extra) not in sys.path:
        sys.path.insert(0, str(extra))

from fixtures import loader as fixtures  # noqa: E402

# Routing key and dimensions for the embedding model, kept here rather than in
# routing.yaml because that file is the chat-tier policy Glass Box rewrites and
# an embedding model is not a tier you flip mid-task.
#
# VERIFY the routing key in the console before the first live call. The display
# name is "Qwen3-Embedding-8B"; the Nemotron keys showed that display names and
# routing keys differ unpredictably, so this one is not assumed.
EMBEDDING_MODEL = os.environ.get("LIFEOS_EMBEDDING_MODEL", "TODO/Qwen3-Embedding-8B")
EMBEDDING_DIMENSIONS = 4096
MODEL_IS_NVIDIA = False

# Demo vectors are deterministic and this many dimensions, so fixtures stay
# small and tests do not carry 4096 floats per row.
DEMO_DIMENSIONS = 64


class EmbeddingError(RuntimeError):
    pass


def is_placeholder() -> bool:
    return "TODO" in EMBEDDING_MODEL


def provenance() -> dict[str, Any]:
    """What to say in the README and the prior-work disclosure.

    Derived from configuration rather than written by hand, so the submission
    cannot drift into claiming an NVIDIA embedding model it is not using.
    """
    return {
        "model": EMBEDDING_MODEL,
        "dimensions": EMBEDDING_DIMENSIONS,
        "is_nvidia": MODEL_IS_NVIDIA,
        "claim": (
            "Memory embeddings run on an NVIDIA model."
            if MODEL_IS_NVIDIA
            else f"Memory embeddings run on {EMBEDDING_MODEL}, which is not an NVIDIA model."
        ),
    }


def demo_embedding(text: str, dimensions: int = DEMO_DIMENSIONS) -> list[float]:
    """A deterministic pseudo-embedding for demo mode.

    Not a real embedding and not pretending to be: it is a hash expanded to a
    unit vector. Identical text gives an identical vector, so retrieval is
    stable and testable, but similar text gives unrelated vectors — so demo
    mode must not be used to argue anything about retrieval quality.
    """
    # Digest bytes are mapped to [-1, 1) as integers rather than reinterpreted
    # as IEEE-754 floats. Reinterpreting them produces NaN and inf for some
    # inputs, and because every comparison with NaN is false, a single poisoned
    # vector silently drops the correct top hit out of a sorted result.
    out: list[float] = []
    counter = 0
    while len(out) < dimensions:
        digest = hashlib.sha256(f"{text}|{counter}".encode()).digest()
        out.extend(
            int.from_bytes(digest[i : i + 4], "big") / 2**31 - 1.0
            for i in range(0, len(digest), 4)
        )
        counter += 1
    vector = out[:dimensions]

    norm = sum(v * v for v in vector) ** 0.5 or 1.0
    return [v / norm for v in vector]


EmitFn = Callable[[dict[str, Any]], None]


def _noop(_: dict[str, Any]) -> None:
    pass


async def embed(
    texts: Sequence[str],
    client: Any | None = None,
    emit: EmitFn | None = None,
    demo: bool | None = None,
) -> list[list[float]]:
    """Embed a batch. One call for the whole batch, like the summarizer.

    `client` is an InferenceClient. Without one, or in demo mode, deterministic
    demo vectors are returned and the event says so — a timeline that cannot
    distinguish a real embedding from a stand-in is not worth having.
    """
    emit = emit or _noop
    if not texts:
        return []

    use_demo = fixtures.is_demo() if demo is None else demo

    if use_demo or client is None:
        vectors = [demo_embedding(t) for t in texts]
        emit(
            {
                "kind": "memory_write",
                "agent": "system",
                "summary": f"Embedded {len(texts)} rows (demo vectors)",
                "detail": {
                    "count": len(texts),
                    "model": "demo",
                    "dimensions": DEMO_DIMENSIONS,
                    "real": False,
                },
            }
        )
        return vectors

    if is_placeholder():
        raise EmbeddingError(
            f"LIFEOS_EMBEDDING_MODEL is still {EMBEDDING_MODEL!r}. Replace it with "
            "the routing key from the Token Factory console — the Nemotron keys "
            "showed display names and routing keys differ unpredictably."
        )

    response = await client.transport.create_embeddings(model=EMBEDDING_MODEL, input=list(texts))
    vectors = [row["embedding"] if isinstance(row, dict) else row.embedding for row in response.data]

    if any(len(v) != EMBEDDING_DIMENSIONS for v in vectors):
        got = {len(v) for v in vectors}
        raise EmbeddingError(
            f"expected {EMBEDDING_DIMENSIONS}-dimensional vectors, got {sorted(got)}. "
            "The schema column is fixed-width, so a mismatch would fail on insert "
            "after the whole batch had been paid for."
        )

    usage = getattr(response, "usage", None)
    emit(
        {
            "kind": "memory_write",
            "agent": "system",
            "summary": f"Embedded {len(texts)} rows on {EMBEDDING_MODEL}",
            "detail": {
                "count": len(texts),
                "model": EMBEDDING_MODEL,
                "dimensions": EMBEDDING_DIMENSIONS,
                "prompt_tokens": int(getattr(usage, "prompt_tokens", 0) or 0),
                "real": True,
            },
        }
    )
    return vectors


def cosine(a: Sequence[float], b: Sequence[float]) -> float:
    """Cosine similarity. Vectors from `embed` are already unit length, but
    this does not assume it — a half-reindexed table can hold both."""
    if len(a) != len(b):
        raise ValueError(f"dimension mismatch: {len(a)} vs {len(b)}")
    dot = sum(x * y for x, y in zip(a, b))
    norm = (sum(x * x for x in a) ** 0.5) * (sum(y * y for y in b) ** 0.5)
    return dot / norm if norm else 0.0
