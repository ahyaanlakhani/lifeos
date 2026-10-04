"""Nightly memory synthesis.

Runs as a Nebius Serverless Job. Reads the day's event log, asks Ultra what is
worth remembering, and writes the result into the memory store.

This is the one place in LifeOS where something writes to memory without a
human in the loop, so it is built to be distrusted:

- **Every proposal carries the event ids it came from.** A row with no
  provenance is discarded rather than stored, because a memory you cannot
  trace is one you cannot later correct.
- **Nothing is invented.** The prompt forbids inference beyond the events, and
  a proposal whose text has no lexical overlap with its cited events is
  dropped — a cheap check that catches the obvious case of the model
  summarising its own prior knowledge instead of the log.
- **Near-duplicates of existing rows are skipped**, so running the job twice
  does not slowly fill memory with restatements of the same fact.
- **A per-run cap** bounds the damage from one bad night.

The judgement runs on the `plan` tier — Ultra — because this is exactly the
long-horizon reasoning that tier exists for, and nightly batch work is where
its cost is affordable.
"""

from __future__ import annotations

import asyncio
import json
import re
import sys
import time
from pathlib import Path
from typing import Any, Callable, Iterable

ROOT = Path(__file__).resolve().parents[2]
for extra in (ROOT, ROOT / "apps" / "host", ROOT / "packages" / "inference"):
    if str(extra) not in sys.path:
        sys.path.insert(0, str(extra))

from events import read_session  # noqa: E402

# A single night should not be able to rewrite the memory.
MAX_NEW_ROWS = 8
# Upper bound on what gets put in front of the model. A long-running host
# produces tens of thousands of events a day, and most of a busy log is the
# same few actions repeated — so duplicates are collapsed first and only then
# is the tail taken. Measured: an uncapped demo session fed 3,606 events,
# about 72k tokens, almost all of it repetition.
MAX_EVENTS = 1200
MIN_CONFIDENCE = 0.3
# Proportion of a proposal's content words that must appear in its cited
# events. Deliberately low: it is a guard against wholesale invention, not a
# paraphrase detector.
MIN_GROUNDED_OVERLAP = 0.3

KINDS = ("preference", "person", "fact", "commitment", "policy")

SYSTEM_PROMPT = """You distil one day of an assistant's activity log into things worth remembering long term.

What is worth remembering:
- a preference or constraint the principal stated or clearly demonstrated
- something durable about a person they deal with
- a commitment made, by them or to them
- a fact about the outside world the assistant relied on

What is not:
- anything already obvious from the calendar or inbox itself
- one-off mechanics ("read the inbox", "listed events")
- your own inferences about what the principal is like

Rules:
- Every item must cite the event ids it came from. No citation, no item.
- Say only what the events say. If an event does not support it, leave it out.
- Prefer four good items to twelve thin ones. Zero is a valid answer.
- confidence is 0 to 1: how firmly the cited events support the claim.

Reply with a JSON array and nothing else. Each element:
{"kind": one of preference|person|fact|commitment|policy,
 "text": "the thing to remember, one sentence",
 "confidence": 0.0-1.0,
 "from_events": ["event-id", ...],
 "external_claim": "a searchable claim about the outside world, or null"}"""


EmitFn = Callable[[dict[str, Any]], None]


def _noop(_: dict[str, Any]) -> None:
    pass


# -- reading the day ------------------------------------------------------


def events_for_session(path: Path, kinds: Iterable[str] | None = None) -> list[dict[str, Any]]:
    """Load a session, keeping the kinds worth summarising.

    Inference and error events are excluded: they describe the machinery, not
    the day. Including them teaches the model to remember its own plumbing.
    """
    wanted = set(kinds) if kinds else {"action", "search", "memory_write", "egress_decision"}
    return [
        {"id": e.id, "ts": e.ts, "kind": e.kind, "agent": e.agent, "summary": e.summary}
        for e in read_session(path)
        if e.kind in wanted
    ]


def condense(events: list[dict[str, Any]], limit: int = MAX_EVENTS) -> list[dict[str, Any]]:
    """Collapse repeated actions, then keep the most recent `limit`.

    An agent doing the same thing forty times is one fact, not forty, and
    paying Ultra to read it forty times buys nothing. The first occurrence is
    kept — it carries the event id a proposal will cite — with a `repeats`
    count so the model can still see that something happened often.
    """
    first: dict[str, dict[str, Any]] = {}
    for event in events:
        key = f"{event['agent']}|{event['summary']}"
        if key in first:
            first[key]["repeats"] += 1
        else:
            first[key] = {**event, "repeats": 1}

    unique = sorted(first.values(), key=lambda e: e["ts"])
    return unique[-limit:]


def latest_session(data_dir: Path) -> Path | None:
    sessions = sorted(data_dir.glob("*.jsonl"), key=lambda p: p.stat().st_mtime, reverse=True)
    return sessions[0] if sessions else None


def build_prompt(events: list[dict[str, Any]], existing: list[str]) -> str:
    lines = [
        f"- [{e['id']}] {e['agent']}: {e['summary']}"
        + (f"  (x{e['repeats']})" if e.get("repeats", 1) > 1 else "")
        for e in events
    ]
    known = "\n".join(f"- {t}" for t in existing) or "(nothing yet)"
    return (
        f"Already remembered, do not restate:\n{known}\n\n"
        f"Today's activity, {len(events)} events:\n" + "\n".join(lines)
    )


# -- validating what comes back -------------------------------------------

_WORD = re.compile(r"[a-z0-9]{4,}")


def _content_words(text: str) -> set[str]:
    return set(_WORD.findall(text.lower()))


def grounded_overlap(text: str, cited: list[dict[str, Any]]) -> float:
    """How much of the proposal's vocabulary appears in the events it cites."""
    words = _content_words(text)
    if not words:
        return 0.0
    evidence: set[str] = set()
    for event in cited:
        evidence |= _content_words(event["summary"])
    return len(words & evidence) / len(words)


def is_near_duplicate(text: str, existing: Iterable[str], threshold: float = 0.6) -> bool:
    """Jaccard over content words. Crude, and that is the point: it only has
    to stop the job restating what it stored last night."""
    words = _content_words(text)
    if not words:
        return False
    for other in existing:
        other_words = _content_words(other)
        if not other_words:
            continue
        union = words | other_words
        if union and len(words & other_words) / len(union) >= threshold:
            return True
    return False


def validate(
    proposals: Any,
    events: list[dict[str, Any]],
    existing: Iterable[str],
    emit: EmitFn,
) -> list[dict[str, Any]]:
    """Drop everything that cannot be justified. Returns what survives."""
    if not isinstance(proposals, list):
        emit({"kind": "error", "agent": "system",
              "summary": "Synthesis returned something that was not a list",
              "detail": {"got": type(proposals).__name__}})
        return []

    by_id = {e["id"]: e for e in events}
    kept: list[dict[str, Any]] = []
    rejected: list[dict[str, str]] = []
    seen: list[str] = list(existing)

    for raw in proposals:
        if not isinstance(raw, dict):
            rejected.append({"text": str(raw)[:60], "why": "not an object"})
            continue

        text = str(raw.get("text", "")).strip()
        kind = str(raw.get("kind", "")).strip()
        cited_ids = [str(i) for i in raw.get("from_events") or []]
        cited = [by_id[i] for i in cited_ids if i in by_id]

        try:
            confidence = float(raw.get("confidence", 0))
        except (TypeError, ValueError):
            confidence = 0.0

        if not text:
            rejected.append({"text": "", "why": "empty"})
        elif kind not in KINDS:
            rejected.append({"text": text[:60], "why": f"unknown kind {kind!r}"})
        elif not cited:
            # The most important rejection: a memory you cannot trace is one
            # you cannot later correct.
            rejected.append({"text": text[:60], "why": "cites no real event"})
        elif confidence < MIN_CONFIDENCE:
            rejected.append({"text": text[:60], "why": f"confidence {confidence:.2f}"})
        elif grounded_overlap(text, cited) < MIN_GROUNDED_OVERLAP:
            rejected.append({"text": text[:60], "why": "not supported by its cited events"})
        elif is_near_duplicate(text, seen):
            rejected.append({"text": text[:60], "why": "near-duplicate of an existing row"})
        else:
            claim = raw.get("external_claim")
            kept.append({
                "kind": kind,
                "text": text,
                "confidence": min(confidence, 1.0),
                "from_events": [e["id"] for e in cited],
                "external_claim": str(claim).strip() if claim else None,
            })
            seen.append(text)

        if len(kept) >= MAX_NEW_ROWS:
            break

    if rejected:
        emit({"kind": "memory_write", "agent": "system",
              "summary": f"Synthesis rejected {len(rejected)} of {len(proposals)} proposals",
              "detail": {"rejected": rejected}})
    return kept


# -- the job --------------------------------------------------------------


async def run(
    store: Any,
    client: Any | None = None,
    session_path: Path | None = None,
    data_dir: Path | None = None,
    emit: EmitFn | None = None,
    dry_run: bool = False,
) -> dict[str, Any]:
    """One night's synthesis. Returns a summary of what happened."""
    emit = emit or _noop
    started = time.monotonic()

    path = session_path or latest_session(data_dir or (ROOT / "data" / "sessions"))
    if path is None or not path.exists():
        emit({"kind": "memory_write", "agent": "system",
              "summary": "Synthesis found no session to read", "detail": {}})
        return {"events": 0, "proposed": 0, "written": 0, "skipped": "no session"}

    raw_events = events_for_session(path)
    events = condense(raw_events)
    existing = [row["text"] for row in store.rows()]

    if not events:
        return {"events": 0, "proposed": 0, "written": 0, "skipped": "no events"}

    if client is None:
        # Nothing to judge with. Saying so beats writing guesses into memory.
        emit({"kind": "memory_write", "agent": "system",
              "summary": f"Synthesis read {len(events)} events but has no model to judge with",
              "detail": {"events": len(events), "events_raw": len(raw_events),
                         "session": path.stem}})
        return {"events": len(events), "proposed": 0, "written": 0, "skipped": "no client"}

    response = await client.complete(
        "plan",
        [{"role": "user", "content": build_prompt(events, existing)}],
        system=SYSTEM_PROMPT,
        agent="system",
    )
    message = response.choices[0].message
    raw = message.get("content") if isinstance(message, dict) else getattr(message, "content", "")

    sys.path.insert(0, str(ROOT / "packages" / "inference"))
    from tools import repair_json

    parsed = repair_json(str(raw or "")) if raw else None
    if parsed is None:
        try:
            text = str(raw or "")
            parsed = json.loads(text[text.index("[") : text.rindex("]") + 1])
        except (ValueError, json.JSONDecodeError):
            emit({"kind": "error", "agent": "system",
                  "summary": "Synthesis output could not be parsed; wrote nothing",
                  "detail": {"raw": str(raw)[:300]}})
            return {"events": len(events), "proposed": 0, "written": 0, "skipped": "unparseable"}

    kept = validate(parsed, events, existing, emit)

    written = 0
    if not dry_run:
        for index, row in enumerate(kept):
            await store.remember(
                row_id=f"syn_{path.stem}_{index:02d}",
                kind=row["kind"],
                text=row["text"],
                source=f"nightly synthesis of {path.stem}, from {', '.join(row['from_events'])}",
                confidence=row["confidence"],
                external_claim=row["external_claim"],
            )
            written += 1

    emit({"kind": "memory_write", "agent": "system",
          "summary": f"Nightly synthesis: {written} new rows from {len(events)} events",
          "detail": {"session": path.stem, "events": len(events), "events_raw": len(raw_events),
                     "proposed": len(parsed) if isinstance(parsed, list) else 0,
                     "written": written, "dry_run": dry_run,
                     "elapsed_s": round(time.monotonic() - started, 2)}})

    return {"events": len(events),
            "proposed": len(parsed) if isinstance(parsed, list) else 0,
            "written": written, "rows": kept, "session": path.stem}


def main() -> None:
    """Entry point for the Serverless Job.

    Synthesis first, then grounding — so anything learned tonight that makes a
    claim about the outside world is checked in the same run rather than
    sitting unverified until tomorrow.
    """
    from packages.memory.store import MemoryStore
    from jobs.nightly_synthesis import grounding

    emit = lambda event: print(json.dumps(event, default=str))  # noqa: E731
    store = MemoryStore(emit=emit)

    async def both() -> None:
        result = await run(store, client=store.client, emit=emit)
        print(f"synthesis: {result}", file=sys.stderr)
        grounded = await grounding.run(client=store.client, emit=emit)
        print(f"grounding: {len(grounded)} claims checked", file=sys.stderr)

    asyncio.run(both())


if __name__ == "__main__":
    main()
