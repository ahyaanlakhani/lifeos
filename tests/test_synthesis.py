"""Nightly synthesis tests.

This is the only place in LifeOS that writes to memory without a human in the
loop, so most of these are about what it refuses to write.
"""

from __future__ import annotations

import asyncio
import json
import sys
from pathlib import Path
from typing import Any

import pytest

ROOT = Path(__file__).resolve().parents[1]
for extra in (ROOT, ROOT / "apps" / "host"):
    sys.path.insert(0, str(extra))

from events import EventLog  # noqa: E402
from jobs.nightly_synthesis import synthesis  # noqa: E402
from packages.memory.store import MemoryStore  # noqa: E402


def run(coro: Any) -> Any:
    return asyncio.run(coro)


@pytest.fixture(autouse=True)
def demo(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("DEMO", "true")


@pytest.fixture()
def events() -> list[dict[str, Any]]:
    return []


@pytest.fixture()
def session(tmp_path: Path) -> tuple[Path, list[Any]]:
    """A small day: a couple of real actions plus noise that must be ignored."""
    log = EventLog("day", data_dir=tmp_path)
    written = [
        log.emit("action", "calendar", "Priya asked to move quarterly planning to Friday"),
        log.emit("action", "email", "Drafted a reply to Dana about deployment timelines"),
        log.emit("search", "research", "Searched: Meridian Labs procurement"),
        log.emit("inference", "system", "execute on super"),      # machinery, excluded
        log.emit("error", "system", "transient failure"),          # machinery, excluded
    ]
    return log.path, written


class Client:
    """Returns one canned payload and records what it was asked."""

    def __init__(self, payload: Any) -> None:
        self.payload = payload
        self.calls: list[dict[str, Any]] = []

    async def complete(self, task: str, messages: list[dict[str, Any]], **kwargs: Any) -> Any:
        self.calls.append({"task": task, "messages": messages, **kwargs})
        body = self.payload if isinstance(self.payload, str) else json.dumps(self.payload)

        class Choice:
            message = {"content": body}

        class Response:
            choices = [Choice()]

        return Response()


def proposal(text: str, ids: list[str], **over: Any) -> dict[str, Any]:
    base = {"kind": "preference", "text": text, "confidence": 0.8,
            "from_events": ids, "external_claim": None}
    base.update(over)
    return base


# -- reading the day ------------------------------------------------------


def test_only_the_kinds_worth_summarising_are_read(session: tuple[Path, list[Any]]) -> None:
    """Inference and error events describe the machinery, not the day.
    Feeding them in teaches the model to remember its own plumbing."""
    path, _ = session
    kinds = {e["kind"] for e in synthesis.events_for_session(path)}
    assert kinds == {"action", "search"}


def test_the_prompt_carries_event_ids_and_what_is_already_known(
    session: tuple[Path, list[Any]]
) -> None:
    path, written = session
    events = synthesis.events_for_session(path)
    prompt = synthesis.build_prompt(events, ["Gym is protected"])
    assert f"[{written[0].id}]" in prompt
    assert "Gym is protected" in prompt
    assert "do not restate" in prompt


def test_the_latest_session_is_the_one_picked(tmp_path: Path) -> None:
    import os

    old = tmp_path / "old.jsonl"
    old.write_text("", encoding="utf-8")
    os.utime(old, (0, 0))
    new = tmp_path / "new.jsonl"
    new.write_text("", encoding="utf-8")
    assert synthesis.latest_session(tmp_path) == new


# -- validation: what it refuses to write ---------------------------------


def test_a_proposal_citing_no_real_event_is_dropped(
    session: tuple[Path, list[Any]], events: list[dict[str, Any]]
) -> None:
    """The most important rejection. A memory you cannot trace is one you
    cannot later correct."""
    path, _ = session
    day = synthesis.events_for_session(path)
    kept = synthesis.validate(
        [proposal("Priya prefers Friday planning", ["evt_does_not_exist"])],
        day, [], events.append,
    )
    assert kept == []
    assert any("cites no real event" in r["why"] for r in events[0]["detail"]["rejected"])


def test_a_proposal_with_no_citations_at_all_is_dropped(
    session: tuple[Path, list[Any]], events: list[dict[str, Any]]
) -> None:
    path, _ = session
    day = synthesis.events_for_session(path)
    assert synthesis.validate([proposal("Something invented", [])], day, [], events.append) == []


def test_a_proposal_unsupported_by_its_cited_events_is_dropped(
    session: tuple[Path, list[Any]], events: list[dict[str, Any]]
) -> None:
    """Catches the model citing a real event while summarising its own prior
    knowledge instead of the log."""
    path, written = session
    day = synthesis.events_for_session(path)
    kept = synthesis.validate(
        [proposal("The principal enjoys sailing holidays in Croatia", [written[0].id])],
        day, [], events.append,
    )
    assert kept == []
    assert any("not supported" in r["why"] for r in events[0]["detail"]["rejected"])


def test_a_well_grounded_proposal_survives(session: tuple[Path, list[Any]]) -> None:
    path, written = session
    day = synthesis.events_for_session(path)
    kept = synthesis.validate(
        [proposal("Priya asked to move quarterly planning to Friday", [written[0].id])],
        day, [], lambda _: None,
    )
    assert len(kept) == 1
    assert kept[0]["from_events"] == [written[0].id]


def test_a_low_confidence_proposal_is_dropped(session: tuple[Path, list[Any]]) -> None:
    path, written = session
    day = synthesis.events_for_session(path)
    kept = synthesis.validate(
        [proposal("Priya asked to move quarterly planning to Friday",
                  [written[0].id], confidence=0.1)],
        day, [], lambda _: None,
    )
    assert kept == []


def test_an_unknown_kind_is_dropped(session: tuple[Path, list[Any]]) -> None:
    path, written = session
    day = synthesis.events_for_session(path)
    kept = synthesis.validate(
        [proposal("Priya asked to move quarterly planning to Friday",
                  [written[0].id], kind="vibes")],
        day, [], lambda _: None,
    )
    assert kept == []


def test_a_near_duplicate_of_an_existing_row_is_skipped(
    session: tuple[Path, list[Any]]
) -> None:
    """Otherwise running the job nightly slowly fills memory with
    restatements of the same fact."""
    path, written = session
    day = synthesis.events_for_session(path)
    kept = synthesis.validate(
        [proposal("Priya asked to move quarterly planning to Friday", [written[0].id])],
        day,
        ["Priya asked to move quarterly planning to Friday"],
        lambda _: None,
    )
    assert kept == []


def test_two_identical_proposals_in_one_run_only_write_once(
    session: tuple[Path, list[Any]]
) -> None:
    path, written = session
    day = synthesis.events_for_session(path)
    same = proposal("Priya asked to move quarterly planning to Friday", [written[0].id])
    kept = synthesis.validate([same, dict(same)], day, [], lambda _: None)
    assert len(kept) == 1


def test_a_run_is_capped(session: tuple[Path, list[Any]]) -> None:
    """One bad night should not be able to rewrite the memory."""
    path, written = session
    day = synthesis.events_for_session(path)
    many = [
        proposal(f"Priya asked to move quarterly planning to Friday variant {i}", [written[0].id])
        for i in range(30)
    ]
    kept = synthesis.validate(many, day, [], lambda _: None)
    assert len(kept) <= synthesis.MAX_NEW_ROWS


def test_a_non_list_payload_is_rejected_loudly(events: list[dict[str, Any]]) -> None:
    assert synthesis.validate({"text": "nope"}, [], [], events.append) == []
    assert events[0]["kind"] == "error"


def test_garbage_elements_do_not_stop_the_good_ones(
    session: tuple[Path, list[Any]]
) -> None:
    path, written = session
    day = synthesis.events_for_session(path)
    kept = synthesis.validate(
        ["a string", 42, proposal("Priya asked to move quarterly planning to Friday",
                                  [written[0].id])],
        day, [], lambda _: None,
    )
    assert len(kept) == 1


# -- the run --------------------------------------------------------------


def test_synthesis_runs_on_the_planning_tier(session: tuple[Path, list[Any]]) -> None:
    """Long-horizon reasoning, nightly, off the hot path — what Ultra is for."""
    path, written = session
    client = Client([proposal("Priya asked to move quarterly planning to Friday",
                              [written[0].id])])
    run(synthesis.run(MemoryStore(demo=True), client=client, session_path=path))
    assert client.calls[0]["task"] == "plan"


def test_a_written_row_records_the_events_it_came_from(
    session: tuple[Path, list[Any]], events: list[dict[str, Any]]
) -> None:
    path, written = session
    store = MemoryStore(emit=events.append, demo=True)
    client = Client([proposal("Priya asked to move quarterly planning to Friday",
                              [written[0].id])])

    result = run(synthesis.run(store, client=client, session_path=path, emit=events.append))
    assert result["written"] == 1

    row = next(r for r in store.rows() if r["id"].startswith("syn_"))
    assert written[0].id in row["source"]
    assert "nightly synthesis" in row["source"]


def test_a_dry_run_writes_nothing(session: tuple[Path, list[Any]]) -> None:
    path, written = session
    store = MemoryStore(demo=True)
    before = len(store.rows())
    client = Client([proposal("Priya asked to move quarterly planning to Friday",
                              [written[0].id])])

    result = run(synthesis.run(store, client=client, session_path=path, dry_run=True))
    assert result["written"] == 0
    assert len(store.rows()) == before


def test_without_a_client_it_says_so_rather_than_guessing(
    session: tuple[Path, list[Any]], events: list[dict[str, Any]]
) -> None:
    """The state before Token Factory credentials exist. Writing guesses into
    memory would be far worse than writing nothing."""
    path, _ = session
    store = MemoryStore(demo=True)
    before = len(store.rows())

    result = run(synthesis.run(store, client=None, session_path=path, emit=events.append))
    assert result["skipped"] == "no client"
    assert len(store.rows()) == before
    assert any("no model to judge with" in e["summary"] for e in events)


def test_unparseable_output_writes_nothing(
    session: tuple[Path, list[Any]], events: list[dict[str, Any]]
) -> None:
    path, _ = session
    store = MemoryStore(demo=True)
    before = len(store.rows())

    result = run(synthesis.run(store, client=Client("I'd rather not"),
                               session_path=path, emit=events.append))
    assert result["skipped"] == "unparseable"
    assert len(store.rows()) == before
    assert any(e["kind"] == "error" for e in events)


def test_a_fenced_array_is_still_parsed(session: tuple[Path, list[Any]]) -> None:
    path, written = session
    payload = json.dumps([proposal("Priya asked to move quarterly planning to Friday",
                                   [written[0].id])])
    client = Client(f"```json\n{payload}\n```")
    result = run(synthesis.run(MemoryStore(demo=True), client=client, session_path=path))
    assert result["written"] == 1


def test_an_empty_session_is_not_an_error(tmp_path: Path) -> None:
    empty = tmp_path / "empty.jsonl"
    empty.write_text("", encoding="utf-8")
    result = run(synthesis.run(MemoryStore(demo=True), client=Client([]), session_path=empty))
    assert result["skipped"] == "no events"


def test_a_missing_session_is_not_an_error(tmp_path: Path, events: list[dict[str, Any]]) -> None:
    result = run(synthesis.run(MemoryStore(demo=True), client=Client([]),
                               data_dir=tmp_path, emit=events.append))
    assert result["skipped"] == "no session"


def test_the_new_row_becomes_recallable(session: tuple[Path, list[Any]]) -> None:
    path, written = session
    store = MemoryStore(demo=True)
    text = "Priya asked to move quarterly planning to Friday"
    run(synthesis.run(store, client=Client([proposal(text, [written[0].id])]),
                      session_path=path))
    assert run(store.recall(text, limit=1))[0].text == text


def test_an_external_claim_survives_so_grounding_can_check_it(
    session: tuple[Path, list[Any]]
) -> None:
    """Synthesis feeds grounding: a claim learned tonight is verified in the
    same run rather than sitting unverified until tomorrow."""
    path, written = session
    store = MemoryStore(demo=True)
    run(synthesis.run(
        store,
        client=Client([proposal(
            "Searched Meridian Labs procurement for Dana",
            [written[2].id],
            kind="fact",
            external_claim="Meridian Labs procurement process",
        )]),
        session_path=path,
    ))
    row = next(r for r in store.rows() if r["id"].startswith("syn_"))
    assert row["external_claim"] == "Meridian Labs procurement process"


# -- the helpers ----------------------------------------------------------


def test_grounded_overlap_is_one_for_a_verbatim_quote() -> None:
    event = [{"summary": "Priya asked to move quarterly planning"}]
    assert synthesis.grounded_overlap("Priya asked to move quarterly planning", event) == 1.0


def test_grounded_overlap_is_zero_for_unrelated_text() -> None:
    event = [{"summary": "Priya asked to move quarterly planning"}]
    assert synthesis.grounded_overlap("sailing holidays Croatia", event) == 0.0


def test_near_duplicate_detection_is_not_fooled_by_word_order() -> None:
    assert synthesis.is_near_duplicate(
        "quarterly planning moved to Friday by Priya",
        ["Priya moved quarterly planning to Friday"],
    )


def test_distinct_facts_are_not_treated_as_duplicates() -> None:
    assert not synthesis.is_near_duplicate(
        "Dana wants deployment timelines in writing",
        ["Priya moved quarterly planning to Friday"],
    )


# -- condensing -----------------------------------------------------------


def test_repeated_actions_collapse_to_one() -> None:
    """An agent doing the same thing forty times is one fact, not forty, and
    paying Ultra to read it forty times buys nothing. Measured on a real demo
    session: 3,606 events condensed to 18."""
    events = [
        {"id": f"e{i}", "ts": float(i), "kind": "action", "agent": "email",
         "summary": "read the inbox"}
        for i in range(40)
    ]
    condensed = synthesis.condense(events)
    assert len(condensed) == 1
    assert condensed[0]["repeats"] == 40


def test_the_first_occurrence_is_the_one_kept() -> None:
    """It carries the event id a proposal will have to cite."""
    events = [
        {"id": "first", "ts": 1.0, "kind": "action", "agent": "email", "summary": "same"},
        {"id": "later", "ts": 2.0, "kind": "action", "agent": "email", "summary": "same"},
    ]
    assert synthesis.condense(events)[0]["id"] == "first"


def test_the_same_text_from_different_agents_stays_distinct() -> None:
    events = [
        {"id": "a", "ts": 1.0, "kind": "action", "agent": "email", "summary": "checked"},
        {"id": "b", "ts": 2.0, "kind": "action", "agent": "calendar", "summary": "checked"},
    ]
    assert len(synthesis.condense(events)) == 2


def test_condensing_keeps_chronological_order() -> None:
    events = [
        {"id": "c", "ts": 3.0, "kind": "action", "agent": "email", "summary": "third"},
        {"id": "a", "ts": 1.0, "kind": "action", "agent": "email", "summary": "first"},
        {"id": "b", "ts": 2.0, "kind": "action", "agent": "email", "summary": "second"},
    ]
    assert [e["id"] for e in synthesis.condense(events)] == ["a", "b", "c"]


def test_the_most_recent_events_survive_the_cap() -> None:
    events = [
        {"id": f"e{i}", "ts": float(i), "kind": "action", "agent": "email",
         "summary": f"distinct action {i}"}
        for i in range(50)
    ]
    condensed = synthesis.condense(events, limit=10)
    assert len(condensed) == 10
    assert condensed[-1]["id"] == "e49"


def test_a_repeat_count_reaches_the_prompt() -> None:
    events = [
        {"id": "a", "ts": 1.0, "kind": "action", "agent": "email", "summary": "retried send"},
        {"id": "b", "ts": 2.0, "kind": "action", "agent": "email", "summary": "retried send"},
    ]
    prompt = synthesis.build_prompt(synthesis.condense(events), [])
    assert "(x2)" in prompt


def test_a_single_occurrence_gets_no_repeat_marker() -> None:
    events = [{"id": "a", "ts": 1.0, "kind": "action", "agent": "email", "summary": "one off"}]
    assert "(x" not in synthesis.build_prompt(synthesis.condense(events), [])
