"""Nano batch-summarization tests. Offline — the client is scripted."""

from __future__ import annotations

import asyncio
import json
import sys
from pathlib import Path
from typing import Any

import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "apps" / "host"))

from events import EventLog  # noqa: E402
from summarize import Summarizer, build_prompt, parse_batch  # noqa: E402


def run(coro: Any) -> Any:
    return asyncio.run(coro)


class ScriptedClient:
    def __init__(self, *replies: str) -> None:
        self.replies = list(replies)
        self.calls: list[dict[str, Any]] = []

    async def complete(self, task: str, messages: list[dict[str, Any]], **kwargs: Any) -> Any:
        self.calls.append({"task": task, "messages": messages, **kwargs})
        reply = self.replies.pop(0) if self.replies else "[]"
        if isinstance(reply, Exception):
            raise reply

        class Choice:
            message = {"content": reply}

        class Response:
            choices = [Choice()]

        return Response()


@pytest.fixture()
def log(tmp_path: Path) -> EventLog:
    return EventLog("s", data_dir=tmp_path)


def pending(log: EventLog, *lines: str) -> list[Any]:
    return [log.emit("action", "email", line, summary_pending=True) for line in lines]


# -- parsing --------------------------------------------------------------


def test_a_clean_array_parses() -> None:
    assert parse_batch('["one", "two"]', 2) == ["one", "two"]


def test_a_fenced_array_parses() -> None:
    assert parse_batch('```json\n["one"]\n```', 1) == ["one"]


def test_an_array_with_prose_either_side_parses() -> None:
    assert parse_batch('Sure: ["one", "two"] hope that helps', 2) == ["one", "two"]


def test_a_wrong_length_batch_is_rejected() -> None:
    """A short or long array would misalign summaries onto the wrong events —
    worse than leaving them raw, because it looks right."""
    assert parse_batch('["only one"]', 3) is None
    assert parse_batch('["a","b","c","d"]', 3) is None


def test_a_non_array_is_rejected() -> None:
    assert parse_batch('{"summaries": ["a"]}', 1) is None


def test_an_array_of_non_strings_is_rejected() -> None:
    assert parse_batch("[1, 2]", 2) is None


def test_unparseable_output_is_rejected() -> None:
    assert parse_batch("I'd rather not", 1) is None
    assert parse_batch("", 1) is None


def test_the_prompt_numbers_the_lines_so_order_is_recoverable(log: EventLog) -> None:
    events = pending(log, "first raw", "second raw")
    prompt = build_prompt(events)
    assert "1. first raw" in prompt
    assert "2. second raw" in prompt


# -- batching -------------------------------------------------------------


def test_summaries_are_patched_back_onto_the_right_events(log: EventLog) -> None:
    events = pending(log, "raw a", "raw b")
    client = ScriptedClient(json.dumps(["Read the inbox", "Classified a newsletter"]))
    summarizer = Summarizer(log, client)

    run(summarizer.summarize(events))

    assert log.get(events[0].id).summary == "Read the inbox"
    assert log.get(events[1].id).summary == "Classified a newsletter"
    assert all(not log.get(e.id).summary_pending for e in events)


def test_one_call_serves_the_whole_batch(log: EventLog) -> None:
    """One inference call per log line would be slow and expensive, and the
    timeline would lag behind the agents it is meant to be showing."""
    events = pending(log, *[f"raw {i}" for i in range(12)])
    client = ScriptedClient(json.dumps([f"line {i}" for i in range(12)]))

    run(Summarizer(log, client).summarize(events))
    assert len(client.calls) == 1


def test_summarization_is_routed_to_the_cheap_tier(log: EventLog) -> None:
    events = pending(log, "raw")
    client = ScriptedClient(json.dumps(["clean"]))
    run(Summarizer(log, client).summarize(events))
    assert client.calls[0]["task"] == "summarize"


def test_the_system_prompt_forbids_softening_a_block(log: EventLog) -> None:
    """A summarizer that embellishes is worse than raw lines, and a blocked
    action reading as ordinary would undo the whole point of the timeline."""
    events = pending(log, "raw")
    client = ScriptedClient(json.dumps(["clean"]))
    run(Summarizer(log, client).summarize(events))
    system = client.calls[0]["system"]
    assert "Never infer" in system
    assert "Never soften" in system


def test_an_unusable_batch_leaves_the_lines_raw_and_says_so(log: EventLog) -> None:
    events = pending(log, "raw a", "raw b")
    run(Summarizer(log, ScriptedClient('["only one"]')).summarize(events))

    assert log.get(events[0].id).summary == "raw a"
    assert log.get(events[0].id).summary_pending is True
    assert any(e.kind == "error" and "raw" in e.summary for e in log.recent())


def test_an_empty_summary_string_leaves_that_line_alone(log: EventLog) -> None:
    events = pending(log, "raw a", "raw b")
    run(Summarizer(log, ScriptedClient(json.dumps(["", "fine"]))).summarize(events))

    assert log.get(events[0].id).summary == "raw a"
    assert log.get(events[1].id).summary == "fine"


def test_with_no_client_nothing_happens_and_nothing_breaks(log: EventLog) -> None:
    """The state before Token Factory credentials exist. Raw lines, dimmed."""
    events = pending(log, "raw")
    run(Summarizer(log, None).summarize(events))
    assert log.get(events[0].id).summary_pending is True


def test_a_failing_call_does_not_take_down_the_host(log: EventLog) -> None:
    events = pending(log, "raw")
    summarizer = Summarizer(log, ScriptedClient(RuntimeError("502")), window=0.01)

    async def one_pass() -> None:
        summarizer.enqueue(events[0])
        task = asyncio.create_task(summarizer.run())
        await asyncio.sleep(0.15)
        task.cancel()
        try:
            await task
        except asyncio.CancelledError:
            pass

    run(one_pass())
    assert any(e.kind == "error" and "Summarization failed" in e.summary for e in log.recent())


def test_only_pending_events_are_queued(log: EventLog) -> None:
    summarizer = Summarizer(log, ScriptedClient())
    summarizer.attach()

    log.emit("action", "email", "already clean")
    log.emit("action", "email", "raw", summary_pending=True)

    assert summarizer.queue.qsize() == 1


def test_a_batch_closes_on_the_window_not_only_when_full(log: EventLog) -> None:
    client = ScriptedClient(json.dumps(["a", "b"]))
    summarizer = Summarizer(log, client, window=0.05, max_batch=20)

    async def scenario() -> None:
        summarizer.attach()
        task = asyncio.create_task(summarizer.run())
        log.emit("action", "email", "raw a", summary_pending=True)
        log.emit("action", "email", "raw b", summary_pending=True)
        await asyncio.sleep(0.25)
        task.cancel()
        try:
            await task
        except asyncio.CancelledError:
            pass

    run(scenario())
    assert len(client.calls) == 1
    assert summarizer.summarized == 2


def test_a_batch_closes_early_when_it_hits_max_size(log: EventLog) -> None:
    client = ScriptedClient(json.dumps(["x", "y"]), json.dumps(["z"]))
    summarizer = Summarizer(log, client, window=5.0, max_batch=2)

    async def scenario() -> None:
        summarizer.attach()
        task = asyncio.create_task(summarizer.run())
        for line in ("a", "b", "c"):
            log.emit("action", "email", line, summary_pending=True)
        await asyncio.sleep(0.1)
        task.cancel()
        try:
            await task
        except asyncio.CancelledError:
            pass

    run(scenario())
    # The first batch must not have waited out the 5 s window.
    assert client.calls[0]["messages"][0]["content"].count("\n") == 3
    assert summarizer.batches == 1
