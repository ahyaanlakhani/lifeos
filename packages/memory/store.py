"""The memory store.

One seam, two backends — the same shape as `packages/agents/data.py`. Demo
mode reads `fixtures/memory.json` and embeds it with deterministic demo
vectors; outside demo mode this is where the Supabase pgvector queries go.

Recall is cosine similarity over embeddings, with an explicit `match` field on
every result saying how it was found. `packages/agents/data.search_memory` is
a keyword placeholder that says `match: "keyword"`; this says
`match: "vector"`. Both are honest about what they did, because "the agent
recalled it" means something different depending on which ran.

Outside demo mode with no Supabase configured, every read returns empty rather
than falling back to fixtures. A memory that invents plausible rows is worse
than one that is visibly empty.
"""

from __future__ import annotations

import sys
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Callable, Sequence

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from fixtures import loader as fixtures  # noqa: E402
from packages.memory import embeddings  # noqa: E402

EmitFn = Callable[[dict[str, Any]], None]


def _noop(_: dict[str, Any]) -> None:
    pass


@dataclass
class Recall:
    id: str
    kind: str
    text: str
    source: str
    confidence: float
    score: float
    match: str
    grounding: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "kind": self.kind,
            "text": self.text,
            "source": self.source,
            "confidence": self.confidence,
            "score": round(self.score, 4),
            "match": self.match,
            "grounding": self.grounding,
        }


class MemoryStore:
    """Vector recall over the memory rows.

    Embeddings are computed lazily on first use and cached, so demo mode has
    no build step and tests do not pay for a 4096-float index they never
    query.
    """

    def __init__(
        self,
        client: Any | None = None,
        emit: EmitFn | None = None,
        demo: bool | None = None,
    ) -> None:
        self.client = client
        self.emit = emit or _noop
        self._demo = demo
        self._rows: list[dict[str, Any]] | None = None
        self._vectors: dict[str, list[float]] = {}

    @property
    def demo(self) -> bool:
        return fixtures.is_demo() if self._demo is None else self._demo

    @property
    def backend(self) -> str:
        return "fixtures" if self.demo else "supabase"

    # -- rows -------------------------------------------------------------

    def rows(self) -> list[dict[str, Any]]:
        if self._rows is None:
            self._rows = self._load_rows()
        return self._rows

    def _load_rows(self) -> list[dict[str, Any]]:
        if self.demo:
            grounded = _grounding_state()
            return [
                {
                    **row,
                    "grounding": grounded.get(row["id"])
                    or row.get("grounding")
                    or {"status": "unverified", "last_checked": None},
                }
                for row in fixtures.memory_rows()
            ]
        # Supabase pgvector read goes here. Empty until it is wired: a memory
        # that invents rows is worse than one that is visibly empty.
        return []

    # -- recall -----------------------------------------------------------

    async def ensure_index(self) -> int:
        """Embed any rows not yet embedded. Returns how many were added.

        Resumable by construction — it only embeds what is missing, so an
        interrupted run costs nothing on the retry. The real re-index script
        drives off the same idea via `memory_rows_needing_embedding`.
        """
        missing = [row for row in self.rows() if row["id"] not in self._vectors]
        if not missing:
            return 0

        vectors = await embeddings.embed(
            [row["text"] for row in missing],
            client=self.client,
            emit=self.emit,
            demo=self.demo,
        )
        for row, vector in zip(missing, vectors):
            self._vectors[row["id"]] = vector
        return len(missing)

    async def recall(
        self,
        query: str,
        limit: int = 5,
        min_score: float = -1.0,
        kinds: Sequence[str] | None = None,
    ) -> list[Recall]:
        """Nearest rows to the query, best first.

        `min_score` defaults to -1.0, i.e. no floor. It used to default to 0.0,
        which silently discarded every row with negative cosine similarity —
        roughly half of them — so a filtered recall could come back empty while
        relevant rows existed. Cutting off a ranked result is a caller's
        decision, not a default.
        """
        await self.ensure_index()
        if not self.rows():
            return []

        query_vector = (
            await embeddings.embed([query], client=self.client, emit=self.emit, demo=self.demo)
        )[0]

        wanted = set(kinds) if kinds else None
        scored: list[Recall] = []
        for row in self.rows():
            if wanted and row["kind"] not in wanted:
                continue
            vector = self._vectors.get(row["id"])
            if vector is None:
                continue
            score = embeddings.cosine(query_vector, vector)
            if score < min_score:
                continue
            scored.append(
                Recall(
                    id=row["id"],
                    kind=row["kind"],
                    text=row["text"],
                    source=row["source"],
                    confidence=float(row.get("confidence", 0.0)),
                    score=score,
                    match="vector",
                    grounding=row.get("grounding", {}),
                )
            )

        scored.sort(key=lambda r: r.score, reverse=True)
        top = scored[:limit]

        self.emit(
            {
                "kind": "memory_write",
                "agent": "system",
                "summary": f"Recalled {len(top)} rows for: {query[:50]}",
                "detail": {
                    "query": query,
                    "returned": len(top),
                    "backend": self.backend,
                    "match": "vector",
                },
            }
        )
        return top

    # -- writes -----------------------------------------------------------

    async def remember(
        self,
        row_id: str,
        kind: str,
        text: str,
        source: str,
        confidence: float = 0.5,
        external_claim: str | None = None,
    ) -> dict[str, Any]:
        """Add or replace a row, embedding it immediately.

        In demo mode this writes to the in-memory copy only. The seed fixtures
        are never mutated: a demo that drifts from its fixtures stops being
        reproducible, and reproducibility is the whole point of demo mode.
        """
        if kind not in {"preference", "person", "fact", "commitment", "policy"}:
            raise ValueError(f"unknown memory kind {kind!r}")

        row = {
            "id": row_id,
            "kind": kind,
            "text": text,
            "source": source,
            "confidence": confidence,
            "external_claim": external_claim,
            "grounding": {"status": "unverified", "last_checked": None},
        }

        rows = self.rows()
        for index, existing in enumerate(rows):
            if existing["id"] == row_id:
                rows[index] = row
                break
        else:
            rows.append(row)

        self._vectors.pop(row_id, None)
        await self.ensure_index()

        self.emit(
            {
                "kind": "memory_write",
                "agent": "system",
                "summary": f"Remembered: {text[:60]}",
                "detail": {"id": row_id, "kind": kind, "source": source, "backend": self.backend},
            }
        )
        return row

    def forget(self, row_id: str) -> bool:
        rows = self.rows()
        before = len(rows)
        self._rows = [r for r in rows if r["id"] != row_id]
        self._vectors.pop(row_id, None)
        removed = len(self._rows) < before
        if removed:
            self.emit(
                {
                    "kind": "memory_write",
                    "agent": "system",
                    "summary": f"Forgot {row_id}",
                    "detail": {"id": row_id, "backend": self.backend},
                }
            )
        return removed


def _grounding_state() -> dict[str, dict[str, Any]]:
    from jobs.nightly_synthesis.grounding import load_state

    return load_state()
