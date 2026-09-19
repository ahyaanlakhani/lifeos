"""Demo-mode fixture loader.

`DEMO=true` swaps every data source for the synthetic data in this directory.
Judges run this, the demo video is shot against it, and it must work with zero
real credentials.

Two things this module is responsible for beyond reading JSON:

1. **Defaulting to demo.** `is_demo()` is true unless `DEMO` is explicitly set
   to a falsey value. Failing closed means a misconfigured environment reads
   fixtures rather than a real inbox.

2. **Rebasing dates.** Fixtures are authored against an anchor date. On load,
   every date in the file is shifted by a whole number of **weeks**, so the
   anchor lands on the nearest same-weekday to today. Whole weeks rather than
   whole days because the fixtures talk about "Friday" and "Monday's call" in
   prose that no rebasing can rewrite — a day-granular shift would put the
   Friday meeting on a Tuesday and the mismatch would be visible on camera.

   The consequence: demo-world "today" is not necessarily the real today. It is
   the anchor's weekday in the current week. Agents must read `demo_today()`
   rather than `date.today()`, or they will reason about the wrong day.

Stdlib only.
"""

from __future__ import annotations

import json
import os
import re
from datetime import date, datetime, timedelta
from functools import lru_cache
from pathlib import Path
from typing import Any

FIXTURE_DIR = Path(__file__).resolve().parent

# Matches a bare date (2026-10-02) or an ISO datetime, with or without offset.
_DATE_RE = re.compile(
    r"(?P<date>\d{4}-\d{2}-\d{2})"
    r"(?P<rest>[T ]\d{2}:\d{2}(?::\d{2})?(?:\.\d+)?(?:Z|[+-]\d{2}:?\d{2})?)?"
)

_FALSEY = {"0", "false", "no", "off", ""}


def is_demo() -> bool:
    """True unless DEMO is explicitly set to a falsey value.

    Fails closed on purpose: an unset or misspelt DEMO must not silently reach
    a real inbox.
    """
    return os.environ.get("DEMO", "true").strip().lower() not in _FALSEY


def require_demo() -> None:
    if not is_demo():
        raise RuntimeError(
            "fixtures.loader was used with DEMO disabled. "
            "Demo fixtures must never stand in for real data unprompted."
        )


def _shift_weeks(anchor: date, today: date) -> int:
    """Whole weeks from the anchor to the nearest same-weekday to today."""
    return round((today - anchor).days / 7)


def _rebase_string(value: str, delta: timedelta) -> str:
    def repl(match: re.Match[str]) -> str:
        try:
            shifted = date.fromisoformat(match.group("date")) + delta
        except ValueError:
            return match.group(0)
        return shifted.isoformat() + (match.group("rest") or "")

    return _DATE_RE.sub(repl, value)


def _rebase(node: Any, delta: timedelta) -> Any:
    if isinstance(node, str):
        return _rebase_string(node, delta)
    if isinstance(node, list):
        return [_rebase(item, delta) for item in node]
    if isinstance(node, dict):
        # Keys are identifiers, never dates. Only values are rebased.
        return {key: _rebase(value, delta) for key, value in node.items()}
    return node


def load(name: str, today: date | None = None, rebase: bool = True) -> dict[str, Any]:
    """Load a fixture by name ("inbox", "calendar", "contacts", ...).

    `today` is injectable so tests are not a function of the wall clock.
    """
    path = FIXTURE_DIR / f"{name}.json"
    if not path.exists():
        available = sorted(p.stem for p in FIXTURE_DIR.glob("*.json"))
        raise FileNotFoundError(f"no fixture {name!r}; have {available}")

    data = json.loads(path.read_text(encoding="utf-8"))

    anchor_raw = data.get("anchor_date")
    if not rebase or not anchor_raw:
        return data

    anchor = date.fromisoformat(anchor_raw)
    delta = timedelta(weeks=_shift_weeks(anchor, today or date.today()))
    return _rebase(data, delta)


@lru_cache(maxsize=None)
def _anchor(name: str) -> date:
    raw = json.loads((FIXTURE_DIR / f"{name}.json").read_text(encoding="utf-8"))
    return date.fromisoformat(raw["anchor_date"])


def demo_today(today: date | None = None) -> date:
    """The date agents should treat as "today" in demo mode.

    The calendar fixture's anchor, shifted into the current week. Agents that
    call `date.today()` directly will reason about the wrong day and the
    timeline will look wrong on camera.
    """
    real_today = today or date.today()
    anchor = _anchor("calendar")
    return anchor + timedelta(weeks=_shift_weeks(anchor, real_today))


def tavily_response(query: str, today: date | None = None) -> dict[str, Any]:
    """Recorded Tavily response for a query, or the `_default` miss record.

    Lets the Research agent and the nightly grounding pass run with no
    TAVILY_API_KEY at all.
    """
    responses = load("tavily", today=today).get("responses", {})
    key = " ".join(query.lower().split())
    hit = responses.get(key)
    if hit is not None:
        return hit
    miss = dict(responses.get("_default", {"results": []}))
    miss["query"] = query
    return miss


def upcoming_events(within_days: int = 7, today: date | None = None) -> list[dict[str, Any]]:
    """Calendar events from demo-today forward, soonest first."""
    data = load("calendar", today=today)
    start = demo_today(today)
    end = start + timedelta(days=within_days)

    def event_date(event: dict[str, Any]) -> date:
        return datetime.fromisoformat(event["start"]).date()

    return sorted(
        (e for e in data["events"] if start <= event_date(e) <= end),
        key=lambda e: e["start"],
    )


def unread_threads(today: date | None = None) -> list[dict[str, Any]]:
    return [t for t in load("inbox", today=today)["threads"] if t.get("unread")]


def memory_rows(today: date | None = None) -> list[dict[str, Any]]:
    return load("memory", today=today)["rows"]


def contacts(today: date | None = None) -> list[dict[str, Any]]:
    return load("contacts", today=today, rebase=False)["contacts"]
