"""Event model, ring buffer and JSONL sink for the LifeOS agent host.

One event type for everything. Glass Box renders a single stream, so adding a
new kind of observable thing never means touching the transport.

The ring buffer serves the live view and the backfill on page load; the JSONL
file on disk serves Replay. Both are cheap and both are wanted.

Stdlib only, on purpose — this module is imported by every other part of the
host and must never be a source of dependency trouble.
"""

from __future__ import annotations

import json
import os
import re
import threading
import time
import uuid
from collections import deque
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any, Callable, Iterable, Iterator

# The full set of observable things. Additive changes only — Glass Box
# switches on this value, and old JSONL files must stay readable.
EVENT_KINDS = frozenset(
    {
        "action",           # an agent did something
        "inference",        # a Token Factory call, with model/latency/tokens
        "egress_request",   # sandbox asked to reach a host not on its allowlist
        "egress_decision",  # allow/deny came back
        "memory_write",     # workspace file or pgvector row changed
        "search",           # Tavily call — evidence of a runtime call
        "voice",            # Parakeet transcript segment or resulting intent
        "error",
    }
)

AGENTS = frozenset({"calendar", "email", "research", "system"})

RING_CAPACITY = 5000


@dataclass
class Event:
    """One observable thing.

    `id` is not in the spec's sketch but is required by it: the host emits an
    event immediately with the raw log line, then patches in Nano's one-line
    summary a beat later. Patching needs an address.
    """

    kind: str
    agent: str
    summary: str
    session: str
    detail: dict[str, Any] = field(default_factory=dict)
    ts: float = field(default_factory=time.time)
    id: str = field(default_factory=lambda: uuid.uuid4().hex)
    # True until Nano rewrites `summary`. Glass Box renders these slightly
    # dimmed so the fill-in reads as deliberate rather than laggy.
    summary_pending: bool = False

    def __post_init__(self) -> None:
        if self.kind not in EVENT_KINDS:
            raise ValueError(f"unknown event kind: {self.kind!r}")
        if self.agent not in AGENTS:
            raise ValueError(f"unknown agent: {self.agent!r}")

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)

    def to_json(self) -> str:
        # default=str so a stray datetime or Path in `detail` degrades to a
        # string instead of taking down the whole event stream.
        return json.dumps(self.to_dict(), separators=(",", ":"), default=str)

    @classmethod
    def from_dict(cls, raw: dict[str, Any]) -> "Event":
        """Rebuild from a JSONL line. Unknown extra keys are dropped so that
        a newer host can still read an older session file, and vice versa."""
        known = {
            "kind", "agent", "summary", "session",
            "detail", "ts", "id", "summary_pending",
        }
        return cls(**{k: v for k, v in raw.items() if k in known})


class EventLog:
    """Ring buffer for the live view, append-only JSONL for replay.

    Thread-safe: the host runs the log tailer, the workspace watcher, the
    egress poller and the API server concurrently, and any of them can emit.
    """

    def __init__(
        self,
        session: str,
        data_dir: str | os.PathLike[str] = "data/sessions",
        capacity: int = RING_CAPACITY,
    ) -> None:
        self.session = session
        self.capacity = capacity
        self._buf: deque[Event] = deque(maxlen=capacity)
        self._by_id: dict[str, Event] = {}
        self._lock = threading.RLock()
        self._subscribers: list[Callable[[Event], None]] = []

        self.path = Path(data_dir) / f"{session}.jsonl"
        self.path.parent.mkdir(parents=True, exist_ok=True)

    # -- emitting ---------------------------------------------------------

    def emit(
        self,
        kind: str,
        agent: str,
        summary: str,
        detail: dict[str, Any] | None = None,
        summary_pending: bool = False,
    ) -> Event:
        event = Event(
            kind=kind,
            agent=agent,
            summary=summary,
            session=self.session,
            detail=detail or {},
            summary_pending=summary_pending,
        )
        return self.append(event)

    def append(self, event: Event) -> Event:
        with self._lock:
            evicted = self._buf[0] if len(self._buf) == self.capacity else None
            self._buf.append(event)
            if evicted is not None:
                self._by_id.pop(evicted.id, None)
            self._by_id[event.id] = event
            self._write_line(event.to_json())
        self._publish(event)
        return event

    def patch_summary(self, event_id: str, summary: str) -> Event | None:
        """Fill in Nano's one-line summary for an already-emitted event.

        Appends a `summary_patch` line to the JSONL rather than rewriting the
        file, so replay stays a forward-only read of an append-only log.
        Returns None if the event has already aged out of the ring.
        """
        with self._lock:
            event = self._by_id.get(event_id)
            if event is None:
                return None
            event.summary = summary
            event.summary_pending = False
            self._write_line(
                json.dumps(
                    {"summary_patch": event_id, "summary": summary, "ts": time.time()},
                    separators=(",", ":"),
                )
            )
        self._publish(event)
        return event

    def _write_line(self, line: str) -> None:
        # Caller holds the lock. Flushed every write: a crash mid-demo must
        # not cost the timeline, and the volume here is trivial.
        with self.path.open("a", encoding="utf-8") as fh:
            fh.write(line + "\n")
            fh.flush()

    # -- reading ----------------------------------------------------------

    def since(self, ts: float) -> list[Event]:
        """Backfill for GET /api/events?since=<ts>, oldest first."""
        with self._lock:
            return [e for e in self._buf if e.ts > ts]

    def recent(self, limit: int = 200) -> list[Event]:
        with self._lock:
            return list(self._buf)[-limit:]

    def get(self, event_id: str) -> Event | None:
        with self._lock:
            return self._by_id.get(event_id)

    def __len__(self) -> int:
        with self._lock:
            return len(self._buf)

    # -- live stream ------------------------------------------------------

    def subscribe(self, callback: Callable[[Event], None]) -> Callable[[], None]:
        """Register a WebSocket fan-out callback. Returns an unsubscribe fn."""
        with self._lock:
            self._subscribers.append(callback)

        def unsubscribe() -> None:
            with self._lock:
                if callback in self._subscribers:
                    self._subscribers.remove(callback)

        return unsubscribe

    def _publish(self, event: Event) -> None:
        with self._lock:
            subscribers = list(self._subscribers)
        for callback in subscribers:
            try:
                callback(event)
            except Exception:  # noqa: BLE001 — a dead socket must not stop the host
                pass


def read_session(path: str | os.PathLike[str]) -> Iterator[Event]:
    """Replay a session from disk, applying summary patches in order.

    Yields events oldest first, with summaries already filled in — which is
    what the Replay scrubber wants. Malformed lines are skipped rather than
    raising: a truncated final line after a crash should not make a whole
    session unreplayable.
    """
    events: list[Event] = []
    index: dict[str, Event] = {}

    with Path(path).open("r", encoding="utf-8") as fh:
        for line in fh:
            line = line.strip()
            if not line:
                continue
            try:
                raw = json.loads(line)
            except json.JSONDecodeError:
                continue

            if "summary_patch" in raw:
                target = index.get(raw["summary_patch"])
                if target is not None:
                    target.summary = raw.get("summary", target.summary)
                    target.summary_pending = False
                continue

            try:
                event = Event.from_dict(raw)
            except (TypeError, ValueError):
                continue
            events.append(event)
            index[event.id] = event

    yield from events


def new_session_id(now: float | None = None) -> str:
    stamp = time.strftime("%Y%m%d-%H%M%S", time.gmtime(now or time.time()))
    return f"{stamp}-{uuid.uuid4().hex[:6]}"


# -- log lines -> typed events --------------------------------------------

_LEVELS = {"DEBUG", "INFO", "WARN", "WARNING", "ERROR", "BLOCK", "TRACE"}
_KV = re.compile(r'(\w+)=("[^"]*"|\S+)')


def parse_log_line(line: str, session: str) -> Event | None:
    """Turn one sandbox log line into an Event, or None if it carries nothing.

    The summary starts as the raw line with `summary_pending` set. Nano rewrites
    it a beat later via `EventLog.patch_summary`; emitting immediately is what
    keeps the timeline live rather than stalling behind a batched inference
    call.

    Unparseable lines still become events. A log line the host does not
    understand is exactly the thing an operator needs to see, and swallowing it
    would violate "no silent work".
    """
    line = line.rstrip()
    if not line.strip():
        return None

    head, _, rest = line.partition(" ")
    level = head.strip().upper()
    if level not in _LEVELS:
        level, rest = "INFO", line

    fields = {
        key: value[1:-1] if value.startswith('"') and value.endswith('"') else value
        for key, value in _KV.findall(rest)
    }

    agent = fields.get("agent", "system")
    if agent not in AGENTS:
        agent = "system"

    return Event(
        kind=_kind_for(level, rest, fields),
        agent=agent,
        summary=line,
        session=session,
        detail={"level": level, "raw": line, **fields},
        summary_pending=True,
    )


def _kind_for(level: str, rest: str, fields: dict[str, str]) -> str:
    """Classify from the level, the bare marker tokens, and the key=value
    fields. Markers like `egress` and `memory_write` appear as bare tokens in
    the log format, not as keys, so the raw text is checked too."""
    if level == "BLOCK" or "egress" in rest:
        return "egress_request"
    if level == "ERROR":
        return "error"
    if "memory_write" in rest:
        return "memory_write"
    if "search" in fields.get("tool", ""):
        return "search"
    if fields.get("voice") or "transcript" in rest:
        return "voice"
    return "action"
