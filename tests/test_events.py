"""Tests for the agent host event model. No network, no live APIs."""

from __future__ import annotations

import json
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "apps" / "host"))

from events import Event, EventLog, read_session, new_session_id  # noqa: E402


@pytest.fixture()
def log(tmp_path: Path) -> EventLog:
    return EventLog(session="test-session", data_dir=tmp_path)


def test_rejects_unknown_kind(log: EventLog) -> None:
    with pytest.raises(ValueError):
        log.emit("teleport", "calendar", "nope")


def test_rejects_unknown_agent(log: EventLog) -> None:
    with pytest.raises(ValueError):
        log.emit("action", "crm", "out of scope")


def test_emit_lands_on_disk(log: EventLog) -> None:
    event = log.emit("action", "calendar", "Moved standup to 10:00")

    lines = log.path.read_text(encoding="utf-8").strip().splitlines()
    assert len(lines) == 1
    assert json.loads(lines[0])["id"] == event.id
    assert json.loads(lines[0])["summary"] == "Moved standup to 10:00"


def test_every_event_kind_is_emittable(log: EventLog) -> None:
    from events import EVENT_KINDS

    for kind in sorted(EVENT_KINDS):
        log.emit(kind, "system", f"a {kind}")
    assert len(log) == len(EVENT_KINDS)


def test_inference_event_carries_telemetry(log: EventLog) -> None:
    """The routing screen and cost meter are built from these fields."""
    event = log.emit(
        "inference",
        "research",
        "Planned the week",
        detail={
            "task": "plan",
            "model": "nemotron-3-ultra",
            "latency_ms": 1840,
            "prompt_tokens": 2201,
            "completion_tokens": 318,
        },
    )
    assert event.detail["latency_ms"] == 1840
    assert event.detail["prompt_tokens"] + event.detail["completion_tokens"] == 2519


def test_patch_summary_updates_event_and_appends_a_patch_line(log: EventLog) -> None:
    event = log.emit(
        "action",
        "email",
        "raw: POST /gmail/v1/users/me/messages/send 200",
        summary_pending=True,
    )
    assert event.summary_pending is True

    patched = log.patch_summary(event.id, "Sent the reply to the landlord")
    assert patched is not None
    assert patched.summary == "Sent the reply to the landlord"
    assert patched.summary_pending is False

    lines = log.path.read_text(encoding="utf-8").strip().splitlines()
    assert len(lines) == 2
    assert json.loads(lines[1])["summary_patch"] == event.id


def test_patch_summary_on_unknown_id_returns_none(log: EventLog) -> None:
    assert log.patch_summary("nope", "x") is None


def test_ring_buffer_evicts_but_disk_keeps_everything(tmp_path: Path) -> None:
    log = EventLog(session="s", data_dir=tmp_path, capacity=10)
    for i in range(25):
        log.emit("action", "system", f"step {i}")

    assert len(log) == 10
    assert log.recent(100)[0].summary == "step 15"

    lines = log.path.read_text(encoding="utf-8").strip().splitlines()
    assert len(lines) == 25


def test_evicted_events_are_dropped_from_the_id_index(tmp_path: Path) -> None:
    """Otherwise the index grows without bound over a six-week demo run."""
    log = EventLog(session="s", data_dir=tmp_path, capacity=3)
    first = log.emit("action", "system", "one")
    for i in range(5):
        log.emit("action", "system", f"more {i}")

    assert log.get(first.id) is None
    assert len(log._by_id) == 3


def test_since_backfills_only_newer_events(log: EventLog) -> None:
    old = log.emit("action", "system", "old")
    newer = log.emit("action", "system", "newer")
    newer.ts = old.ts + 100

    assert [e.summary for e in log.since(old.ts + 1)] == ["newer"]
    assert len(log.since(0)) == 2


def test_subscribe_receives_emits_and_patches(log: EventLog) -> None:
    seen: list[str] = []
    unsubscribe = log.subscribe(lambda e: seen.append(e.summary))

    event = log.emit("voice", "system", "raw transcript", summary_pending=True)
    log.patch_summary(event.id, "Asked to reschedule Thursday")
    assert seen == ["raw transcript", "Asked to reschedule Thursday"]

    unsubscribe()
    log.emit("action", "system", "after")
    assert len(seen) == 2


def test_a_broken_subscriber_does_not_stop_the_host(log: EventLog) -> None:
    def explode(_: Event) -> None:
        raise RuntimeError("socket closed")

    delivered: list[Event] = []
    log.subscribe(explode)
    log.subscribe(delivered.append)

    log.emit("action", "system", "still works")
    assert len(delivered) == 1


def test_replay_applies_patches_in_order(log: EventLog) -> None:
    a = log.emit("action", "calendar", "raw a", summary_pending=True)
    log.emit("action", "email", "plain b")
    log.patch_summary(a.id, "Rescheduled the dentist")

    replayed = list(read_session(log.path))
    assert [e.summary for e in replayed] == ["Rescheduled the dentist", "plain b"]
    assert replayed[0].summary_pending is False


def test_replay_survives_a_truncated_final_line(log: EventLog) -> None:
    log.emit("action", "system", "good")
    with log.path.open("a", encoding="utf-8") as fh:
        fh.write('{"kind":"action","agent":"sys')  # crash mid-write

    assert [e.summary for e in read_session(log.path)] == ["good"]


def test_replay_ignores_unknown_fields_from_a_newer_host(tmp_path: Path) -> None:
    path = tmp_path / "s.jsonl"
    path.write_text(
        json.dumps(
            {
                "kind": "action",
                "agent": "system",
                "summary": "from the future",
                "session": "s",
                "detail": {},
                "ts": 1.0,
                "id": "abc",
                "summary_pending": False,
                "trace_id": "added-in-week-5",
            }
        )
        + "\n",
        encoding="utf-8",
    )
    assert [e.summary for e in read_session(path)] == ["from the future"]


def test_detail_with_an_unserializable_value_still_emits(log: EventLog) -> None:
    event = log.emit("error", "system", "boom", detail={"path": Path("/tmp/x")})
    assert json.loads(event.to_json())["detail"]["path"]


def test_session_ids_are_unique_and_sortable() -> None:
    a = new_session_id(1_700_000_000)
    b = new_session_id(1_700_000_001)
    assert a != b
    assert a[:8] == b[:8]
