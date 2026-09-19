"""Tool-schema and message translation between the Claude Agent SDK shape that
LifeOS agents are written in and the OpenAI-compatible shape Token Factory
serves.

This is where the port lives or dies. Everything else is plumbing around it.

Three separate problems, deliberately kept separate:

1. **Tool definitions.** Mechanical: `input_schema` becomes `parameters`,
   wrapped in a `function` envelope.

2. **Message history.** Not mechanical. The Agent SDK carries tool calls and
   tool results as *content blocks inside* user and assistant messages. The
   OpenAI shape carries them as a `tool_calls` array on the assistant message
   and separate messages with `role: "tool"`. This is a rewrite, not a patch —
   one assistant message with two tool_use blocks becomes one assistant
   message plus two tool messages.

3. **Argument parsing.** Nemotron may emit arguments that are almost-valid
   JSON. Every repair here is *verified by re-parsing*: a transform is only
   accepted if the result actually loads. If nothing works, the raised error
   carries a message to feed back to the model, which is the documented retry
   path.

Stdlib only.
"""

from __future__ import annotations

import json
import re
from typing import Any, Iterable

__all__ = [
    "ToolArgumentError",
    "to_openai_tool",
    "to_openai_tools",
    "to_openai_messages",
    "from_openai_call",
    "from_openai_message",
    "parse_tool_arguments",
    "repair_json",
]


class ToolArgumentError(ValueError):
    """Raised when a tool call's arguments cannot be parsed or repaired.

    Carries `feedback()` — the message to append to the history so the model
    can correct itself on the retry.
    """

    def __init__(self, tool_name: str, raw: str, reason: str) -> None:
        super().__init__(f"{tool_name}: {reason}")
        self.tool_name = tool_name
        self.raw = raw
        self.reason = reason

    def feedback(self) -> str:
        return (
            f"Your arguments for {self.tool_name} were not valid JSON ({self.reason}). "
            "Reply with the tool call again, with arguments as a single JSON object "
            "and nothing else — no prose, no code fences, no trailing commas."
        )


# -- tool definitions -----------------------------------------------------


def to_openai_tool(tool: dict[str, Any]) -> dict[str, Any]:
    """Agent SDK tool definition -> OpenAI function definition."""
    try:
        name = tool["name"]
    except KeyError as exc:  # noqa: PERF203 — the message matters more than the speed
        raise ValueError(f"tool definition has no name: {tool!r}") from exc

    schema = tool.get("input_schema") or tool.get("parameters") or {}
    return {
        "type": "function",
        "function": {
            "name": name,
            "description": tool.get("description", ""),
            "parameters": _normalise_schema(schema),
        },
    }


def to_openai_tools(tools: Iterable[dict[str, Any]] | None) -> list[dict[str, Any]] | None:
    """None stays None — passing `tools: []` is not the same as omitting it,
    and some servers reject an empty array."""
    if tools is None:
        return None
    converted = [to_openai_tool(t) for t in tools]
    return converted or None


def _normalise_schema(schema: dict[str, Any]) -> dict[str, Any]:
    """Guarantee a JSON-Schema object envelope.

    A bare or empty schema is legal in the Agent SDK for a no-argument tool,
    but servers validating against the OpenAI shape commonly reject it.
    """
    normalised = dict(schema)
    normalised.setdefault("type", "object")
    if normalised["type"] == "object":
        normalised.setdefault("properties", {})
    return normalised


# -- messages: ours -> OpenAI ---------------------------------------------


def to_openai_messages(
    messages: Iterable[dict[str, Any]],
    system: str | None = None,
) -> list[dict[str, Any]]:
    """Agent SDK message history -> OpenAI chat messages.

    Handles the three shapes that actually occur:
      - plain text content (a string, or a list of text blocks)
      - an assistant turn containing `tool_use` blocks
      - a user turn containing `tool_result` blocks

    A single assistant turn with N tool_use blocks becomes one assistant
    message carrying N tool_calls. A single user turn with N tool_result
    blocks becomes N messages with role "tool". That fan-out is the part that
    cannot be patched into the old builder.
    """
    out: list[dict[str, Any]] = []
    if system:
        out.append({"role": "system", "content": system})

    for message in messages:
        role = message.get("role")
        content = message.get("content")

        if isinstance(content, str):
            out.append({"role": role, "content": content})
            continue

        if content is None:
            out.append({"role": role, "content": ""})
            continue

        text_parts: list[str] = []
        tool_calls: list[dict[str, Any]] = []
        tool_results: list[dict[str, Any]] = []

        for block in content:
            if not isinstance(block, dict):
                text_parts.append(str(block))
                continue

            kind = block.get("type")
            if kind == "text":
                text_parts.append(block.get("text", ""))
            elif kind == "tool_use":
                tool_calls.append(
                    {
                        "id": block["id"],
                        "type": "function",
                        "function": {
                            "name": block["name"],
                            "arguments": json.dumps(block.get("input", {})),
                        },
                    }
                )
            elif kind == "tool_result":
                tool_results.append(
                    {
                        "role": "tool",
                        "tool_call_id": block["tool_use_id"],
                        "content": _stringify_result(block.get("content", "")),
                    }
                )
            else:
                # Unknown block types are dropped rather than crashing the
                # history builder mid-run. Images would land here.
                continue

        if role == "assistant" and tool_calls:
            assistant: dict[str, Any] = {
                "role": "assistant",
                "content": "\n".join(p for p in text_parts if p) or None,
                "tool_calls": tool_calls,
            }
            out.append(assistant)
        elif text_parts or not tool_results:
            out.append({"role": role, "content": "\n".join(text_parts)})

        # Tool results always follow the turn they belong to.
        out.extend(tool_results)

    return out


def _stringify_result(content: Any) -> str:
    """Tool results must be a string on the OpenAI side."""
    if isinstance(content, str):
        return content
    if isinstance(content, list):
        parts = [
            block.get("text", "") if isinstance(block, dict) else str(block)
            for block in content
        ]
        return "\n".join(p for p in parts if p)
    return json.dumps(content, default=str)


# -- messages: OpenAI -> ours ---------------------------------------------


def from_openai_call(tool_call: Any) -> dict[str, Any]:
    """One OpenAI tool call -> the Agent SDK tool_use shape.

    Accepts either an SDK object or a plain dict, so tests can run against
    recorded JSON without constructing SDK types.
    """
    if isinstance(tool_call, dict):
        call_id = tool_call.get("id", "")
        function = tool_call.get("function", {})
        name = function.get("name", "")
        arguments = function.get("arguments", "")
    else:
        call_id = getattr(tool_call, "id", "")
        function = getattr(tool_call, "function", None)
        name = getattr(function, "name", "")
        arguments = getattr(function, "arguments", "")

    return {
        "id": call_id,
        "name": name,
        "input": parse_tool_arguments(name, arguments),
    }


def from_openai_message(message: Any) -> dict[str, Any]:
    """An OpenAI assistant message -> an Agent SDK assistant message.

    Round-trips through `to_openai_messages` so a multi-turn loop can keep its
    history in one shape.
    """
    if isinstance(message, dict):
        text = message.get("content")
        raw_calls = message.get("tool_calls") or []
    else:
        text = getattr(message, "content", None)
        raw_calls = getattr(message, "tool_calls", None) or []

    blocks: list[dict[str, Any]] = []
    if text:
        blocks.append({"type": "text", "text": text})
    for call in raw_calls:
        parsed = from_openai_call(call)
        blocks.append(
            {
                "type": "tool_use",
                "id": parsed["id"],
                "name": parsed["name"],
                "input": parsed["input"],
            }
        )

    return {"role": "assistant", "content": blocks}


# -- argument parsing and JSON repair -------------------------------------

_FENCE = re.compile(r"^\s*```(?:json)?\s*(.*?)\s*```\s*$", re.DOTALL)
_TRAILING_COMMA = re.compile(r",\s*([}\]])")
_PY_LITERAL = re.compile(r"\b(True|False|None)\b")
_PY_MAP = {"True": "true", "False": "false", "None": "null"}


def parse_tool_arguments(tool_name: str, raw: Any) -> dict[str, Any]:
    """Parse a tool call's arguments, repairing what can be safely repaired.

    Raises ToolArgumentError with retry feedback when it cannot.
    """
    if isinstance(raw, dict):
        return raw
    if raw is None or (isinstance(raw, str) and not raw.strip()):
        # A no-argument tool legitimately produces "" or "{}".
        return {}
    if not isinstance(raw, str):
        raise ToolArgumentError(tool_name, str(raw), f"arguments were {type(raw).__name__}")

    parsed = repair_json(raw)
    if parsed is None:
        raise ToolArgumentError(tool_name, raw, "could not be parsed or repaired")
    if not isinstance(parsed, dict):
        raise ToolArgumentError(
            tool_name, raw, f"parsed to a {type(parsed).__name__}, not an object"
        )
    return parsed


def repair_json(text: str) -> Any | None:
    """Best-effort JSON recovery. Returns None if nothing parses.

    Every candidate transform is verified by actually parsing the result, so a
    repair can never quietly change the meaning of something that was already
    valid — the untouched original is always tried first.
    """
    for candidate in _candidates(text):
        try:
            return json.loads(candidate)
        except (json.JSONDecodeError, ValueError):
            continue
    return None


def _candidates(text: str) -> Iterable[str]:
    yield text

    stripped = text.strip()
    yield stripped

    fenced = _FENCE.match(stripped)
    if fenced:
        inner = fenced.group(1)
        yield inner
        stripped = inner

    # Prose either side of the object: "Sure! {...} Let me know."
    carved = _carve_object(stripped)
    if carved and carved != stripped:
        yield carved
        stripped = carved

    no_trailing = _TRAILING_COMMA.sub(r"\1", stripped)
    if no_trailing != stripped:
        yield no_trailing

    pythonish = _PY_LITERAL.sub(lambda m: _PY_MAP[m.group(1)], no_trailing)
    if pythonish != no_trailing:
        yield pythonish

    escaped = _escape_raw_newlines_in_strings(pythonish)
    if escaped != pythonish:
        yield escaped


def _carve_object(text: str) -> str | None:
    """The outermost balanced {...}, ignoring braces inside strings."""
    start = text.find("{")
    if start == -1:
        return None

    depth = 0
    in_string = False
    escaped = False
    for index in range(start, len(text)):
        char = text[index]
        if in_string:
            if escaped:
                escaped = False
            elif char == "\\":
                escaped = True
            elif char == '"':
                in_string = False
            continue
        if char == '"':
            in_string = True
        elif char == "{":
            depth += 1
        elif char == "}":
            depth -= 1
            if depth == 0:
                return text[start : index + 1]
    return None


def _escape_raw_newlines_in_strings(text: str) -> str:
    """A literal newline inside a JSON string is invalid. Models emit them
    constantly when a tool argument holds a drafted email body."""
    out: list[str] = []
    in_string = False
    escaped = False
    for char in text:
        if in_string:
            if escaped:
                escaped = False
            elif char == "\\":
                escaped = True
            elif char == '"':
                in_string = False
            elif char == "\n":
                out.append("\\n")
                continue
            elif char == "\r":
                out.append("\\r")
                continue
            elif char == "\t":
                out.append("\\t")
                continue
        elif char == '"':
            in_string = True
        out.append(char)
    return "".join(out)
