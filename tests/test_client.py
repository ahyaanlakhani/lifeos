"""Token Factory client tests. Entirely offline — no transport reaches a network."""

from __future__ import annotations

import asyncio
import json
import sys
from pathlib import Path
from typing import Any

import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "packages" / "inference"))

import client as inference  # noqa: E402
from tools import ToolArgumentError  # noqa: E402


def run(coro: Any) -> Any:
    return asyncio.run(coro)


def response(
    content: str | None = "ok",
    tool_calls: list[dict[str, Any]] | None = None,
    prompt_tokens: int = 100,
    completion_tokens: int = 20,
) -> Any:
    message: dict[str, Any] = {"content": content}
    if tool_calls:
        message["tool_calls"] = tool_calls
    return inference._Response.from_dict(
        {
            "choices": [{"message": message, "finish_reason": "stop"}],
            "usage": {
                "prompt_tokens": prompt_tokens,
                "completion_tokens": completion_tokens,
            },
        }
    )


@pytest.fixture()
def routing_file(tmp_path: Path) -> Path:
    path = tmp_path / "routing.yaml"
    path.write_text(
        "plan: ultra-id\n"
        "execute: super-id\n"
        "summarize: nano-id\n"
        "pricing:\n"
        "  super-id:\n"
        "    input_per_mtok: 3.0\n"
        "    output_per_mtok: 9.0\n",
        encoding="utf-8",
    )
    return path


@pytest.fixture()
def events() -> list[dict[str, Any]]:
    return []


# -- routing --------------------------------------------------------------


def test_the_shipped_routing_file_parses_and_defines_every_task() -> None:
    routing = inference.Routing()
    table = routing.table()
    for task in inference.TASKS:
        assert task in table, task


def test_the_shipped_routing_file_still_holds_placeholders() -> None:
    """A guard, not a wish: this test flips to the assertion below once the
    real ids are in, and until then it documents why nothing can call out."""
    routing = inference.Routing()
    with pytest.raises(inference.PlaceholderModelError, match="Token Factory console"):
        routing.model_for("execute")


def test_routing_resolves_tasks_to_models(routing_file: Path) -> None:
    routing = inference.Routing(path=routing_file)
    assert routing.model_for("plan") == "ultra-id"
    assert routing.model_for("summarize") == "nano-id"


def test_an_unrouted_task_names_the_tasks_that_do_exist(routing_file: Path) -> None:
    routing = inference.Routing(path=routing_file)
    with pytest.raises(inference.UnroutedTaskError, match="plan"):
        routing.model_for("teleport")


def test_routing_hot_reloads_when_glass_box_rewrites_the_file(routing_file: Path) -> None:
    routing = inference.Routing(path=routing_file)
    assert routing.model_for("execute") == "super-id"

    import os

    routing_file.write_text("plan: ultra-id\nexecute: nano-id\nsummarize: nano-id\n", encoding="utf-8")
    os.utime(routing_file, (0, 0))  # force a different mtime, not a later one

    assert routing.model_for("execute") == "nano-id"


def test_a_missing_routing_file_fails_with_its_path(tmp_path: Path) -> None:
    routing = inference.Routing(path=tmp_path / "gone.yaml")
    with pytest.raises(FileNotFoundError, match="gone.yaml"):
        routing.model_for("plan")


def test_cost_is_none_when_pricing_is_unknown(routing_file: Path) -> None:
    """None rather than 0.0 — a meter reading zero looks like a working meter
    reporting a free call."""
    routing = inference.Routing(path=routing_file)
    assert routing.cost("ultra-id", 1000, 1000) is None


def test_cost_is_computed_when_pricing_is_known(routing_file: Path) -> None:
    routing = inference.Routing(path=routing_file)
    cost = routing.cost("super-id", 1_000_000, 1_000_000)
    assert cost == pytest.approx(12.0)


def test_the_fallback_yaml_parser_matches_pyyaml_on_this_file(routing_file: Path) -> None:
    """The host must keep routing even if PyYAML is missing on the VM."""
    text = routing_file.read_text(encoding="utf-8")
    fallback = inference._parse_simple_yaml(text)
    assert fallback["execute"] == "super-id"
    assert fallback["pricing"]["super-id"]["input_per_mtok"] == 3.0

    pytest.importorskip("yaml")
    assert fallback == inference._parse_routing(text)


def test_the_fallback_parser_handles_the_shipped_file_with_its_comments() -> None:
    text = inference.ROUTING_PATH.read_text(encoding="utf-8")
    parsed = inference._parse_simple_yaml(text)
    assert parsed["execute"].endswith("nemotron-3-super")
    assert "#" not in parsed["execute"]


# -- completion and telemetry ---------------------------------------------


def test_complete_emits_an_inference_event_with_telemetry(
    routing_file: Path, events: list[dict[str, Any]]
) -> None:
    transport = inference.ScriptedTransport([response()])
    client = inference.InferenceClient(
        transport=transport, routing=inference.Routing(path=routing_file), emit=events.append
    )

    run(client.complete("execute", [{"role": "user", "content": "hi"}], agent="calendar"))

    assert len(events) == 1
    event = events[0]
    assert event["kind"] == "inference"
    assert event["agent"] == "calendar"
    assert event["detail"]["model"] == "super-id"
    assert event["detail"]["prompt_tokens"] == 100
    assert event["detail"]["latency_ms"] >= 0
    assert event["detail"]["cost_usd"] == pytest.approx(100 / 1e6 * 3 + 20 / 1e6 * 9)


def test_every_call_emits_even_with_no_usage_reported(
    routing_file: Path, events: list[dict[str, Any]]
) -> None:
    """No silent work. A model that reports no usage still gets an event."""
    bare = inference._Response.from_dict({"choices": [{"message": {"content": "x"}}]})
    client = inference.InferenceClient(
        transport=inference.ScriptedTransport([bare]),
        routing=inference.Routing(path=routing_file),
        emit=events.append,
    )
    run(client.complete("summarize", [{"role": "user", "content": "hi"}]))
    assert events[0]["detail"]["prompt_tokens"] == 0


def test_a_failed_call_emits_an_error_event_and_re_raises(
    routing_file: Path, events: list[dict[str, Any]]
) -> None:
    client = inference.InferenceClient(
        transport=inference.ScriptedTransport([RuntimeError("502 upstream")]),
        routing=inference.Routing(path=routing_file),
        emit=events.append,
    )
    with pytest.raises(RuntimeError, match="502"):
        run(client.complete("execute", [{"role": "user", "content": "hi"}]))

    assert events[0]["kind"] == "error"
    assert "502" in events[0]["detail"]["error"]


def test_messages_are_translated_before_they_leave(routing_file: Path) -> None:
    transport = inference.ScriptedTransport([response()])
    client = inference.InferenceClient(
        transport=transport, routing=inference.Routing(path=routing_file)
    )
    run(
        client.complete(
            "execute",
            [
                {
                    "role": "assistant",
                    "content": [{"type": "tool_use", "id": "c1", "name": "t", "input": {"a": 1}}],
                },
                {
                    "role": "user",
                    "content": [{"type": "tool_result", "tool_use_id": "c1", "content": "done"}],
                },
            ],
            system="You are LifeOS.",
        )
    )
    sent = transport.requests[0]["messages"]
    assert [m["role"] for m in sent] == ["system", "assistant", "tool"]


def test_tools_are_translated_and_omitted_when_empty(routing_file: Path) -> None:
    transport = inference.ScriptedTransport([response(), response()])
    client = inference.InferenceClient(
        transport=transport, routing=inference.Routing(path=routing_file)
    )
    messages = [{"role": "user", "content": "hi"}]

    run(client.complete("execute", messages, tools=[{"name": "search", "input_schema": {}}]))
    assert transport.requests[0]["tools"][0]["function"]["name"] == "search"

    run(client.complete("execute", messages, tools=[]))
    assert "tools" not in transport.requests[1]


def test_model_override_wins_over_routing(routing_file: Path) -> None:
    """This is the routing screen flipping Super to Ultra mid-task on camera."""
    transport = inference.ScriptedTransport([response()])
    client = inference.InferenceClient(
        transport=transport, routing=inference.Routing(path=routing_file)
    )
    run(client.complete("execute", [{"role": "user", "content": "hi"}], model_override="ultra-id"))
    assert transport.requests[0]["model"] == "ultra-id"


def test_extra_kwargs_reach_the_transport(routing_file: Path) -> None:
    transport = inference.ScriptedTransport([response()])
    client = inference.InferenceClient(
        transport=transport, routing=inference.Routing(path=routing_file)
    )
    run(client.complete("execute", [{"role": "user", "content": "hi"}], temperature=0.2))
    assert transport.requests[0]["temperature"] == 0.2


# -- the JSON-repair retry loop -------------------------------------------


def test_a_clean_tool_call_needs_no_retry(routing_file: Path) -> None:
    transport = inference.ScriptedTransport(
        [response(None, [{"id": "c1", "function": {"name": "search", "arguments": '{"q":"x"}'}}])]
    )
    client = inference.InferenceClient(
        transport=transport, routing=inference.Routing(path=routing_file)
    )
    turn = run(
        client.complete_with_tools("execute", [{"role": "user", "content": "go"}], tools=[{"name": "search"}])
    )
    assert turn["content"][0]["input"] == {"q": "x"}
    assert len(transport.requests) == 1


def test_almost_valid_json_is_repaired_without_a_retry(routing_file: Path) -> None:
    transport = inference.ScriptedTransport(
        [
            response(
                None,
                [{"id": "c1", "function": {"name": "search", "arguments": '```json\n{"q": "x",}\n```'}}],
            )
        ]
    )
    client = inference.InferenceClient(
        transport=transport, routing=inference.Routing(path=routing_file)
    )
    turn = run(
        client.complete_with_tools("execute", [{"role": "user", "content": "go"}], tools=[{"name": "search"}])
    )
    assert turn["content"][0]["input"] == {"q": "x"}
    assert len(transport.requests) == 1


def test_unrepairable_arguments_trigger_a_retry_carrying_the_error_back(
    routing_file: Path,
) -> None:
    broken = response(None, [{"id": "c1", "function": {"name": "search", "arguments": "not json"}}])
    good = response(None, [{"id": "c2", "function": {"name": "search", "arguments": '{"q":"x"}'}}])
    transport = inference.ScriptedTransport([broken, good])
    client = inference.InferenceClient(
        transport=transport, routing=inference.Routing(path=routing_file)
    )

    turn = run(
        client.complete_with_tools("execute", [{"role": "user", "content": "go"}], tools=[{"name": "search"}])
    )
    assert turn["content"][0]["input"] == {"q": "x"}
    assert len(transport.requests) == 2

    retry_messages = transport.requests[1]["messages"]
    assert "not valid JSON" in retry_messages[-1]["content"]
    assert "search" in retry_messages[-1]["content"]


def test_the_repair_loop_gives_up_and_says_so(
    routing_file: Path, events: list[dict[str, Any]]
) -> None:
    broken = lambda: response(  # noqa: E731
        None, [{"id": "c1", "function": {"name": "search", "arguments": "still not json"}}]
    )
    transport = inference.ScriptedTransport([broken(), broken()])
    client = inference.InferenceClient(
        transport=transport, routing=inference.Routing(path=routing_file), emit=events.append
    )

    with pytest.raises(ToolArgumentError):
        run(
            client.complete_with_tools(
                "execute",
                [{"role": "user", "content": "go"}],
                tools=[{"name": "search"}],
                max_repairs=1,
            )
        )
    assert len(transport.requests) == 2
    assert any(e["kind"] == "error" and "Gave up" in e["summary"] for e in events)


def test_a_response_with_no_choices_fails_clearly(routing_file: Path) -> None:
    empty = inference._Response.from_dict({"choices": [], "usage": {}})
    client = inference.InferenceClient(
        transport=inference.ScriptedTransport([empty]),
        routing=inference.Routing(path=routing_file),
    )
    with pytest.raises(ValueError, match="no choices"):
        run(client.complete_with_tools("execute", [{"role": "user", "content": "x"}], tools=[]))


# -- replay transport -----------------------------------------------------


def test_replay_serves_a_recorded_exchange(tmp_path: Path) -> None:
    (tmp_path / "one.json").write_text(
        json.dumps(
            {
                "request": {"model": "nano-id", "messages": [{"role": "user", "content": "hi"}]},
                "response": {
                    "choices": [{"message": {"content": "recorded"}}],
                    "usage": {"prompt_tokens": 5, "completion_tokens": 2},
                },
            }
        ),
        encoding="utf-8",
    )
    transport = inference.ReplayTransport(tmp_path)
    got = run(transport.create(model="nano-id", messages=[{"role": "user", "content": "hi"}]))
    assert got.choices[0].message["content"] == "recorded"
    assert got.usage.prompt_tokens == 5


def test_a_replay_miss_raises_rather_than_reaching_the_network(tmp_path: Path) -> None:
    transport = inference.ReplayTransport(tmp_path)
    with pytest.raises(KeyError, match="no recorded exchange"):
        run(transport.create(model="nano-id", messages=[{"role": "user", "content": "unseen"}]))


# -- credentials ----------------------------------------------------------


def test_the_real_transport_refuses_to_guess_its_endpoint(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.delenv("NEBIUS_BASE_URL", raising=False)
    monkeypatch.delenv("NEBIUS_API_KEY", raising=False)
    with pytest.raises(RuntimeError, match="do not guess"):
        inference.OpenAITransport()
