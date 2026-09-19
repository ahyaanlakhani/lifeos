"""Nano summarization of the activity feed.

Raw log lines are unreadable on camera. Nano rewrites each into one clean
sentence — but *batched*, because one inference call per log line would be
slow, expensive, and would make the timeline lag behind the agents it is
supposed to be showing.

The shape that matters:

1. An event is emitted immediately with the raw line and `summary_pending`.
   The timeline is live from the first moment.
2. Pending events collect over a short window, up to a batch size.
3. One call rewrites the whole batch.
4. Summaries are patched back in. The line fills in a beat later, which reads
   as deliberate rather than laggy.

The model is told not to invent. A summarizer that embellishes what an agent
did is worse than raw log lines, because the whole point of the timeline is
that you can trust it.
"""

from __future__ import annotations

import asyncio
import json
import sys
from pathlib import Path
from typing import Any, Iterable

HOST_DIR = Path(__file__).resolve().parent
if str(HOST_DIR) not in sys.path:
    sys.path.insert(0, str(HOST_DIR))

from events import Event, EventLog  # noqa: E402

WINDOW_SECONDS = 2.0
MAX_BATCH = 20

SYSTEM_PROMPT = """You rewrite raw agent log lines into one short sentence each, for a live activity feed a person is watching.

Rules:
- One line in, one line out. Same order. Never merge or drop lines.
- Plain past tense, under 90 characters, no trailing full stop.
- Say only what the line says. Never infer intent, outcome or success.
- Keep concrete identifiers (event ids, thread ids, hostnames) if present.
- A blocked or denied action must still read as blocked. Never soften it.

Reply with a JSON array of strings and nothing else."""


def build_prompt(events: list[Event]) -> str:
    lines = [f"{index + 1}. {event.summary}" for index, event in enumerate(events)]
    return "Rewrite these {n} lines:\n\n{body}".format(n=len(events), body="\n".join(lines))


def parse_batch(raw: str, expected: int) -> list[str] | None:
    """Parse the model's array, or None if it cannot be trusted.

    A batch whose length does not match would silently misalign summaries onto
    the wrong events — a worse failure than leaving them raw, because it looks
    right.
    """
    import sys as _sys

    _sys.path.insert(0, str(HOST_DIR.parents[1] / "packages" / "inference"))
    from tools import repair_json

    parsed = repair_json(raw) if raw else None
    if parsed is None:
        # The model may have returned a bare array the object-carver missed.
        try:
            parsed = json.loads(raw[raw.index("[") : raw.rindex("]") + 1])
        except (ValueError, json.JSONDecodeError):
            return None

    if not isinstance(parsed, list) or len(parsed) != expected:
        return None
    if not all(isinstance(item, str) for item in parsed):
        return None
    return [item.strip() for item in parsed]


class Summarizer:
    """Collects pending events and patches Nano's rewrite back in."""

    def __init__(
        self,
        log: EventLog,
        client: Any | None,
        window: float = WINDOW_SECONDS,
        max_batch: int = MAX_BATCH,
    ) -> None:
        self.log = log
        self.client = client
        self.window = window
        self.max_batch = max_batch
        self.queue: asyncio.Queue[Event] = asyncio.Queue()
        self.batches = 0
        self.summarized = 0

    def enqueue(self, event: Event) -> None:
        if event.summary_pending:
            self.queue.put_nowait(event)

    def attach(self) -> Any:
        """Subscribe to the log. Returns the unsubscribe callable."""
        return self.log.subscribe(self.enqueue)

    async def _collect(self) -> list[Event]:
        """One event, then whatever else arrives inside the window."""
        first = await self.queue.get()
        batch = [first]
        deadline = asyncio.get_running_loop().time() + self.window

        while len(batch) < self.max_batch:
            remaining = deadline - asyncio.get_running_loop().time()
            if remaining <= 0:
                break
            try:
                batch.append(await asyncio.wait_for(self.queue.get(), timeout=remaining))
            except asyncio.TimeoutError:
                break
        return batch

    async def summarize(self, events: list[Event]) -> None:
        if not events or self.client is None:
            return

        response = await self.client.complete(
            "summarize",
            [{"role": "user", "content": build_prompt(events)}],
            system=SYSTEM_PROMPT,
            agent="system",
        )
        message = response.choices[0].message
        raw = message.get("content") if isinstance(message, dict) else getattr(message, "content", "")

        summaries = parse_batch(str(raw or ""), len(events))
        self.batches += 1
        if summaries is None:
            # Leave the raw lines. They are honest and readable enough; a
            # misaligned summary would not be.
            self.log.emit(
                "error",
                "system",
                "Nano returned an unusable batch; left the lines raw",
                {"expected": len(events)},
            )
            return

        for event, summary in zip(events, summaries):
            if summary:
                self.log.patch_summary(event.id, summary)
                self.summarized += 1

    async def run(self) -> None:
        """Pump until cancelled."""
        while True:
            batch = await self._collect()
            try:
                await self.summarize(batch)
            except Exception as exc:  # noqa: BLE001 — never take down the host
                self.log.emit(
                    "error",
                    "system",
                    "Summarization failed",
                    {"error": f"{type(exc).__name__}: {exc}", "batch": len(batch)},
                )
