"""Nightly memory grounding.

Runs as a Nebius Serverless Job. For every memory row carrying a claim about
the outside world, search for it and decide whether what LifeOS believes is
still true. The row is marked:

  confirmed     the search supports it
  stale         it was true and the search suggests it has moved on
  contradicted  the search says otherwise
  unverified    nothing conclusive, or the check has not run

This is the non-obvious use of Tavily, and the reason it is load-bearing:
a personal assistant that remembers things for months accumulates facts that
quietly stop being true, and a memory with no notion of freshness presents a
year-old job title with the same confidence as this morning's calendar.

The judgement is a model call routed to `plan`, which is Ultra — this is
exactly the long-horizon reasoning that tier exists for, and it runs nightly
rather than in the hot path, so the cost is fine.

Offline and in demo mode, the recorded verdict in `fixtures/tavily.json` is
used instead of a model call, on the same principle as every other recorded
fixture: the debug loop must not cost credits.
"""

from __future__ import annotations

import asyncio
import json
import os
import sys
import time
from pathlib import Path
from typing import Any, Callable

ROOT = Path(__file__).resolve().parents[2]
for extra in (ROOT, ROOT / "packages" / "inference", ROOT / "packages" / "agents" / "research"):
    if str(extra) not in sys.path:
        sys.path.insert(0, str(extra))

from fixtures import loader as fixtures  # noqa: E402
from packages.agents.research import search as tavily  # noqa: E402

STATUSES = ("confirmed", "stale", "contradicted", "unverified")

DEFAULT_STATE = ROOT / "data" / "grounding.json"

JUDGE_PROMPT = """You are verifying one thing a personal assistant remembers.

Remembered: {text}
Claim being checked: {claim}

Search results:
{evidence}

Reply with exactly one word:
confirmed     - the results support what is remembered
stale         - it was true but the results show it has since changed
contradicted  - the results say otherwise
unverified    - the results do not settle it

One word, nothing else."""


EmitFn = Callable[[dict[str, Any]], None]


def _noop(_: dict[str, Any]) -> None:
    pass


def _format_evidence(results: list[dict[str, Any]]) -> str:
    if not results:
        return "(no results)"
    return "\n".join(
        f"- {r.get('title', '')} ({r.get('published_date') or 'no date'}): {r.get('content', '')}"
        for r in results
    )


def _normalise(verdict: str) -> str:
    """Take the first recognised status word out of whatever the model said.

    Models add a sentence of explanation even when told not to. Falling back
    to `unverified` on anything unrecognised is the conservative choice: an
    unparsed verdict must never read as `confirmed`.
    """
    lowered = verdict.lower()
    for status in STATUSES:
        if status in lowered:
            return status
    return "unverified"


async def ground_row(
    row: dict[str, Any],
    client: Any | None = None,
    emit: EmitFn | None = None,
    demo: bool | None = None,
) -> dict[str, Any]:
    """Return the grounding record for one memory row."""
    emit = emit or _noop
    claim = row.get("external_claim")
    if not claim:
        return {"status": "unverified", "last_checked": None, "note": "no external claim"}

    use_demo = fixtures.is_demo() if demo is None else demo
    results = await tavily.search(claim, emit=emit, demo=use_demo)

    if client is None:
        # No inference available. Demo mode uses the recorded verdict; outside
        # demo mode the honest answer is that nothing was checked.
        if use_demo:
            recorded = fixtures.tavily_response(claim)
            status = _normalise(str(recorded.get("_expected_grounding", "unverified")))
            note = "recorded verdict (demo mode)"
        else:
            status, note = "unverified", "no inference client available"
        return {
            "status": status,
            "last_checked": time.time(),
            "note": note,
            "sources": [r.get("url") for r in results],
        }

    response = await client.complete(
        "plan",
        [
            {
                "role": "user",
                "content": JUDGE_PROMPT.format(
                    text=row.get("text", ""), claim=claim, evidence=_format_evidence(results)
                ),
            }
        ],
        agent="research",
    )
    message = response.choices[0].message
    verdict = message.get("content") if isinstance(message, dict) else getattr(message, "content", "")

    return {
        "status": _normalise(str(verdict or "")),
        "last_checked": time.time(),
        "note": "verified against live search",
        "sources": [r.get("url") for r in results],
    }


async def run(
    rows: list[dict[str, Any]] | None = None,
    client: Any | None = None,
    emit: EmitFn | None = None,
    state_path: Path | None = None,
    demo: bool | None = None,
) -> dict[str, dict[str, Any]]:
    """Ground every row that carries an external claim; write the results.

    Returns a map of row id -> grounding record. Results are written to a small
    JSON file rather than into the fixtures, so the seed data stays pristine
    and a demo can be reset by deleting one file.
    """
    emit = emit or _noop
    rows = rows if rows is not None else fixtures.memory_rows()
    path = state_path or DEFAULT_STATE

    results: dict[str, dict[str, Any]] = {}
    for row in rows:
        if not row.get("external_claim"):
            continue
        try:
            results[row["id"]] = await ground_row(row, client=client, emit=emit, demo=demo)
        except Exception as exc:  # noqa: BLE001 — one bad row must not lose the whole run
            emit(
                {
                    "kind": "error",
                    "agent": "research",
                    "summary": f"Grounding failed for {row['id']}",
                    "detail": {"row": row["id"], "error": f"{type(exc).__name__}: {exc}"},
                }
            )
            results[row["id"]] = {
                "status": "unverified",
                "last_checked": time.time(),
                "note": f"check failed: {type(exc).__name__}",
            }

    changed = sum(1 for r in results.values() if r["status"] != "unverified")
    emit(
        {
            "kind": "memory_write",
            "agent": "research",
            "summary": f"Grounded {len(results)} remembered claims; {changed} resolved",
            "detail": {"checked": len(results), "resolved": changed},
        }
    )

    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(results, indent=2, default=str), encoding="utf-8")
    return results


def load_state(state_path: Path | None = None) -> dict[str, dict[str, Any]]:
    """Read the last run's results. Missing or corrupt state grounds nothing
    rather than failing — a stale badge is worth less than a working page."""
    path = state_path or DEFAULT_STATE
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {}


def main() -> None:
    emit = lambda event: print(json.dumps(event, default=str))  # noqa: E731
    results = asyncio.run(run(emit=emit))
    resolved = sum(1 for r in results.values() if r["status"] != "unverified")
    print(f"grounded {len(results)} claims, {resolved} resolved", file=sys.stderr)


if __name__ == "__main__":
    main()
