"""Tool-schema and message translation tests.

All offline. These are the tests that let the adapter be debugged without
burning Token Factory credits on a live loop, which is the stated reason for
recording fixtures at all.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "packages" / "inference"))

from tools import (  # noqa: E402
    ToolArgumentError,
    from_openai_call,
    from_openai_message,
    parse_tool_arguments,
    repair_json,
    to_openai_messages,
    to_openai_tool,
    to_openai_tools,
)

SEND_EMAIL = {
    "name": "send_email",
    "description": "Send an email. Requires approval.",
    "input_schema": {
        "type": "object",
        "properties": {
            "to": {"type": "string"},
            "subject": {"type": "string"},
            "body": {"type": "string"},
        },
        "required": ["to", "subject", "body"],
    },
}


# -- tool definitions -----------------------------------------------------


def test_input_schema_becomes_parameters() -> None:
    converted = to_openai_tool(SEND_EMAIL)
    assert converted["type"] == "function"
    assert converted["function"]["name"] == "send_email"
    assert converted["function"]["parameters"]["required"] == ["to", "subject", "body"]


def test_a_no_argument_tool_still_gets_an_object_envelope() -> None:
    """Servers validating the OpenAI shape reject a bare schema."""
    converted = to_openai_tool({"name": "list_today", "description": "", "input_schema": {}})
    assert converted["function"]["parameters"] == {"type": "object", "properties": {}}


def test_a_tool_with_no_schema_at_all_is_tolerated() -> None:
    converted = to_openai_tool({"name": "ping"})
    assert converted["function"]["parameters"]["type"] == "object"
    assert converted["function"]["description"] == ""


def test_an_already_openai_shaped_schema_passes_through() -> None:
    converted = to_openai_tool({"name": "x", "parameters": {"type": "object"}})
    assert converted["function"]["parameters"]["type"] == "object"


def test_a_nameless_tool_fails_loudly() -> None:
    with pytest.raises(ValueError, match="no name"):
        to_openai_tool({"description": "oops"})


def test_none_stays_none_but_an_empty_list_also_becomes_none() -> None:
    """Some servers reject `tools: []`; omitting the field is the safe form."""
    assert to_openai_tools(None) is None
    assert to_openai_tools([]) is None
    assert len(to_openai_tools([SEND_EMAIL])) == 1


def test_conversion_does_not_mutate_the_source_definition() -> None:
    original = json.loads(json.dumps(SEND_EMAIL))
    to_openai_tool(SEND_EMAIL)
    assert SEND_EMAIL == original


# -- messages: ours -> OpenAI ---------------------------------------------


def test_plain_text_history_passes_through_with_a_system_message() -> None:
    out = to_openai_messages([{"role": "user", "content": "hello"}], system="You are LifeOS.")
    assert out == [
        {"role": "system", "content": "You are LifeOS."},
        {"role": "user", "content": "hello"},
    ]


def test_text_blocks_are_joined() -> None:
    out = to_openai_messages(
        [{"role": "user", "content": [{"type": "text", "text": "a"}, {"type": "text", "text": "b"}]}]
    )
    assert out[0]["content"] == "a\nb"


def test_assistant_tool_use_becomes_tool_calls() -> None:
    out = to_openai_messages(
        [
            {
                "role": "assistant",
                "content": [
                    {"type": "text", "text": "Sending it."},
                    {
                        "type": "tool_use",
                        "id": "call_1",
                        "name": "send_email",
                        "input": {"to": "a@b.example"},
                    },
                ],
            }
        ]
    )
    assert len(out) == 1
    assert out[0]["content"] == "Sending it."
    call = out[0]["tool_calls"][0]
    assert call["id"] == "call_1"
    assert json.loads(call["function"]["arguments"]) == {"to": "a@b.example"}


def test_one_turn_with_two_tool_uses_fans_out_to_two_tool_calls() -> None:
    out = to_openai_messages(
        [
            {
                "role": "assistant",
                "content": [
                    {"type": "tool_use", "id": "c1", "name": "a", "input": {}},
                    {"type": "tool_use", "id": "c2", "name": "b", "input": {}},
                ],
            }
        ]
    )
    assert len(out) == 1
    assert [c["id"] for c in out[0]["tool_calls"]] == ["c1", "c2"]
    assert out[0]["content"] is None


def test_one_user_turn_with_two_tool_results_fans_out_to_two_messages() -> None:
    """This fan-out is why the history builder is a rewrite, not a patch."""
    out = to_openai_messages(
        [
            {
                "role": "user",
                "content": [
                    {"type": "tool_result", "tool_use_id": "c1", "content": "ok one"},
                    {"type": "tool_result", "tool_use_id": "c2", "content": "ok two"},
                ],
            }
        ]
    )
    assert [m["role"] for m in out] == ["tool", "tool"]
    assert [m["tool_call_id"] for m in out] == ["c1", "c2"]
    assert out[0]["content"] == "ok one"


def test_a_tool_result_turn_emits_no_empty_user_message() -> None:
    """An extra empty user message between a call and its result makes some
    servers reject the whole history."""
    out = to_openai_messages(
        [{"role": "user", "content": [{"type": "tool_result", "tool_use_id": "c1", "content": "ok"}]}]
    )
    assert len(out) == 1
    assert out[0]["role"] == "tool"


def test_tool_result_content_blocks_are_flattened_to_a_string() -> None:
    out = to_openai_messages(
        [
            {
                "role": "user",
                "content": [
                    {
                        "type": "tool_result",
                        "tool_use_id": "c1",
                        "content": [{"type": "text", "text": "line"}],
                    }
                ],
            }
        ]
    )
    assert out[0]["content"] == "line"


def test_structured_tool_result_content_is_json_encoded() -> None:
    out = to_openai_messages(
        [
            {
                "role": "user",
                "content": [
                    {"type": "tool_result", "tool_use_id": "c1", "content": {"count": 3}}
                ],
            }
        ]
    )
    assert json.loads(out[0]["content"]) == {"count": 3}


def test_unknown_block_types_are_dropped_not_fatal() -> None:
    out = to_openai_messages(
        [{"role": "user", "content": [{"type": "image", "source": {}}, {"type": "text", "text": "hi"}]}]
    )
    assert out[0]["content"] == "hi"


def test_a_full_tool_round_trip_keeps_calls_and_results_adjacent() -> None:
    history = [
        {"role": "user", "content": "Email Priya."},
        {
            "role": "assistant",
            "content": [{"type": "tool_use", "id": "c1", "name": "send_email", "input": {}}],
        },
        {"role": "user", "content": [{"type": "tool_result", "tool_use_id": "c1", "content": "sent"}]},
        {"role": "assistant", "content": "Done."},
    ]
    out = to_openai_messages(history)
    assert [m["role"] for m in out] == ["user", "assistant", "tool", "assistant"]
    assert out[2]["tool_call_id"] == out[1]["tool_calls"][0]["id"]


# -- messages: OpenAI -> ours ---------------------------------------------


def test_from_openai_call_parses_arguments() -> None:
    parsed = from_openai_call(
        {"id": "c1", "function": {"name": "send_email", "arguments": '{"to":"a@b.example"}'}}
    )
    assert parsed == {"id": "c1", "name": "send_email", "input": {"to": "a@b.example"}}


def test_from_openai_call_accepts_sdk_objects_not_just_dicts() -> None:
    class Fn:
        name = "send_email"
        arguments = '{"to":"a@b.example"}'

    class Call:
        id = "c1"
        function = Fn()

    assert from_openai_call(Call())["input"] == {"to": "a@b.example"}


def test_from_openai_message_round_trips_back_through_the_builder() -> None:
    assistant = from_openai_message(
        {
            "content": "On it.",
            "tool_calls": [
                {"id": "c1", "function": {"name": "search", "arguments": '{"q":"x"}'}}
            ],
        }
    )
    assert assistant["role"] == "assistant"
    again = to_openai_messages([assistant])
    assert again[0]["tool_calls"][0]["id"] == "c1"
    assert json.loads(again[0]["tool_calls"][0]["function"]["arguments"]) == {"q": "x"}


def test_from_openai_message_with_no_tool_calls() -> None:
    assert from_openai_message({"content": "just text"})["content"] == [
        {"type": "text", "text": "just text"}
    ]


# -- argument parsing and repair ------------------------------------------


def test_valid_json_is_returned_untouched() -> None:
    assert parse_tool_arguments("t", '{"a": 1, "b": [2, 3]}') == {"a": 1, "b": [2, 3]}


def test_a_dict_passes_straight_through() -> None:
    assert parse_tool_arguments("t", {"a": 1}) == {"a": 1}


@pytest.mark.parametrize("raw", ["", "   ", None, "{}"])
def test_no_argument_tools_produce_an_empty_dict(raw: object) -> None:
    assert parse_tool_arguments("list_today", raw) == {}


def test_code_fences_are_stripped() -> None:
    assert parse_tool_arguments("t", '```json\n{"a": 1}\n```') == {"a": 1}


def test_prose_either_side_of_the_object_is_carved_away() -> None:
    raw = 'Sure! Here you go: {"to": "a@b.example"} Let me know if that works.'
    assert parse_tool_arguments("send_email", raw) == {"to": "a@b.example"}


def test_trailing_commas_are_repaired() -> None:
    assert parse_tool_arguments("t", '{"a": 1, "b": [2, 3,],}') == {"a": 1, "b": [2, 3]}


def test_python_literals_are_repaired() -> None:
    assert parse_tool_arguments("t", '{"ok": True, "no": False, "gone": None}') == {
        "ok": True,
        "no": False,
        "gone": None,
    }


def test_raw_newlines_inside_a_drafted_body_are_escaped() -> None:
    """Models emit these constantly when a tool argument holds an email body."""
    raw = '{"body": "Hi Priya,\nCan we move Friday?\n\nThanks"}'
    parsed = parse_tool_arguments("send_email", raw)
    assert parsed["body"].startswith("Hi Priya,\nCan we move")


def test_braces_inside_strings_do_not_confuse_the_carver() -> None:
    raw = 'note: {"body": "use {curly} braces", "n": 1} done'
    assert parse_tool_arguments("t", raw) == {"body": "use {curly} braces", "n": 1}


def test_an_escaped_quote_inside_a_string_survives_carving() -> None:
    raw = r'{"body": "she said \"hi\" then left"}'
    assert parse_tool_arguments("t", raw)["body"] == 'she said "hi" then left'


def test_repair_never_alters_something_that_was_already_valid() -> None:
    """The untouched original is tried first, so a transform cannot quietly
    change the meaning of valid input."""
    raw = '{"text": "True", "note": "trailing, comma inside a string,"}'
    assert repair_json(raw) == {"text": "True", "note": "trailing, comma inside a string,"}


def test_unrepairable_arguments_raise_with_retry_feedback() -> None:
    with pytest.raises(ToolArgumentError) as excinfo:
        parse_tool_arguments("send_email", "I'm not going to call a tool actually")
    feedback = excinfo.value.feedback()
    assert "send_email" in feedback
    assert "JSON object" in feedback
    assert excinfo.value.raw.startswith("I'm not")


def test_arguments_that_parse_to_a_non_object_are_rejected() -> None:
    with pytest.raises(ToolArgumentError, match="not an object"):
        parse_tool_arguments("t", "[1, 2, 3]")


def test_arguments_of_the_wrong_python_type_are_rejected() -> None:
    with pytest.raises(ToolArgumentError, match="int"):
        parse_tool_arguments("t", 7)


def test_repair_json_returns_none_rather_than_raising() -> None:
    assert repair_json("definitely not json") is None
