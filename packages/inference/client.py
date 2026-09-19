"""Token Factory client.

The single door to inference. No agent calls a model API directly — they call
`complete()`, which is what makes the routing screen, the cost meter and the
"no silent work" rule possible at all.

Three transports behind one interface:

- `OpenAITransport`  — the real thing, OpenAI SDK against Token Factory.
- `ReplayTransport`  — recorded exchanges from tests/fixtures, so debugging a
  tool-calling loop does not burn credits. The spec is explicit that burning
  Token Factory credits on week-two debug loops is how week five is lost.
- `ScriptedTransport` — queued responses for tests.

Model ids and the base URL are never hardcoded and never guessed. They come
from `routing.yaml` and the environment, both sourced from the Token Factory
console.
"""

from __future__ import annotations

import json
import os
import re
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Callable, Iterable, Protocol

import tools as tool_adapter

ROUTING_PATH = Path(__file__).resolve().parent / "routing.yaml"

# Tasks the routing file must define. Agents name a task, never a model.
TASKS = ("plan", "execute", "summarize")

# A model id still carrying the scaffold's placeholder marker.
_PLACEHOLDER = re.compile(r"\bTODO\b", re.IGNORECASE)


class UnroutedTaskError(KeyError):
    pass


class PlaceholderModelError(RuntimeError):
    """Raised when routing.yaml still holds a scaffold placeholder.

    Better a loud failure here than a confusing 404 from the API, which is the
    shape this mistake otherwise takes.
    """


# -- routing --------------------------------------------------------------


@dataclass
class Routing:
    """Hot-reloaded model routing. Glass Box rewrites the file; this notices."""

    path: Path = ROUTING_PATH
    _table: dict[str, str] = field(default_factory=dict)
    _pricing: dict[str, dict[str, float]] = field(default_factory=dict)
    _mtime: float | None = None

    def _load(self) -> None:
        text = self.path.read_text(encoding="utf-8")
        data = _parse_routing(text)
        self._table = {k: v for k, v in data.items() if isinstance(v, str)}
        pricing = data.get("pricing")
        self._pricing = pricing if isinstance(pricing, dict) else {}
        self._mtime = self.path.stat().st_mtime

    def _maybe_reload(self) -> None:
        try:
            mtime = self.path.stat().st_mtime
        except FileNotFoundError as exc:
            raise FileNotFoundError(f"routing file missing: {self.path}") from exc
        if self._mtime != mtime:
            self._load()

    def model_for(self, task: str) -> str:
        self._maybe_reload()
        try:
            model = self._table[task]
        except KeyError as exc:
            raise UnroutedTaskError(
                f"no route for task {task!r}; routing.yaml defines {sorted(self._table)}"
            ) from exc
        if _PLACEHOLDER.search(model):
            raise PlaceholderModelError(
                f"routing.yaml still has a placeholder for {task!r}: {model!r}. "
                "Replace it with the exact model id from the Token Factory console."
            )
        return model

    def table(self) -> dict[str, str]:
        self._maybe_reload()
        return dict(self._table)

    def cost(self, model: str, prompt_tokens: int, completion_tokens: int) -> float | None:
        """USD for a call, or None when pricing has not been filled in.

        Returning None rather than 0.0 matters: a cost meter reading zero looks
        like a working meter reporting a free call.
        """
        self._maybe_reload()
        rates = self._pricing.get(model)
        if not rates:
            return None
        return (
            prompt_tokens / 1_000_000 * float(rates.get("input_per_mtok", 0))
            + completion_tokens / 1_000_000 * float(rates.get("output_per_mtok", 0))
        )


def _parse_routing(text: str) -> dict[str, Any]:
    """Parse routing.yaml.

    Uses PyYAML when present. The fallback handles the flat `key: value` and
    one level of nesting that this file actually contains, so the host keeps
    running if the dependency is missing on the VM — this file decides which
    model every agent uses, and it is not allowed to be the thing that breaks.
    """
    try:
        import yaml  # type: ignore[import-untyped]
    except ImportError:
        return _parse_simple_yaml(text)
    loaded = yaml.safe_load(text)
    return loaded if isinstance(loaded, dict) else {}


def _parse_simple_yaml(text: str) -> dict[str, Any]:
    """Indent-aware parser for the `key: value` and nested-mapping subset that
    routing.yaml uses. Not a YAML implementation — no lists, anchors or
    multi-line scalars, none of which belong in this file."""
    root: dict[str, Any] = {}
    stack: list[tuple[int, dict[str, Any]]] = [(-1, root)]

    for raw_line in text.splitlines():
        line = _strip_comment(raw_line).rstrip()
        if not line.strip():
            continue

        indent = len(line) - len(line.lstrip())
        key, separator, value = line.strip().partition(":")
        if not separator:
            continue
        key = key.strip()
        value = value.strip()

        while len(stack) > 1 and indent <= stack[-1][0]:
            stack.pop()
        parent = stack[-1][1]

        if value in ("", "{}"):
            child: dict[str, Any] = {}
            parent[key] = child
            if value == "":
                stack.append((indent, child))
        elif _is_quoted(value):
            parent[key] = value[1:-1]
        else:
            parent[key] = _coerce(value)

    return root


def _strip_comment(line: str) -> str:
    """Cut at the first `#` that is not inside a quoted scalar."""
    quote: str | None = None
    for index, char in enumerate(line):
        if quote:
            if char == quote:
                quote = None
        elif char in "\"'":
            quote = char
        elif char == "#":
            return line[:index]
    return line


def _is_quoted(value: str) -> bool:
    """Quoted scalars stay strings — `"3.0"` is a string in YAML, and a model
    id that happens to look numeric must not become a float."""
    return len(value) >= 2 and value[0] == value[-1] and value[0] in "\"'"


def _coerce(value: str) -> Any:
    try:
        return int(value)
    except ValueError:
        pass
    try:
        return float(value)
    except ValueError:
        return value


# -- transports -----------------------------------------------------------


class Transport(Protocol):
    async def create(self, **kwargs: Any) -> Any: ...


class OpenAITransport:
    """Token Factory over the OpenAI-compatible endpoint.

    The SDK is imported lazily so that the offline test suite, and demo mode on
    a machine with no credentials, never need it installed.
    """

    def __init__(self, base_url: str | None = None, api_key: str | None = None) -> None:
        self.base_url = base_url or os.environ.get("NEBIUS_BASE_URL", "")
        self.api_key = api_key or os.environ.get("NEBIUS_API_KEY", "")
        if not self.base_url or not self.api_key:
            raise RuntimeError(
                "NEBIUS_BASE_URL and NEBIUS_API_KEY must both be set. "
                "Both come from the Token Factory console — do not guess them."
            )
        self._client: Any | None = None

    def _ensure(self) -> Any:
        if self._client is None:
            from openai import AsyncOpenAI  # imported lazily on purpose

            self._client = AsyncOpenAI(base_url=self.base_url, api_key=self.api_key)
        return self._client

    async def create(self, **kwargs: Any) -> Any:
        return await self._ensure().chat.completions.create(**kwargs)


class ScriptedTransport:
    """Queued responses, for tests. Records the requests it was given."""

    def __init__(self, responses: Iterable[Any]) -> None:
        self.queue = list(responses)
        self.requests: list[dict[str, Any]] = []

    async def create(self, **kwargs: Any) -> Any:
        self.requests.append(kwargs)
        if not self.queue:
            raise AssertionError("ScriptedTransport ran out of responses")
        response = self.queue.pop(0)
        if isinstance(response, Exception):
            raise response
        return response


class ReplayTransport:
    """Replays recorded exchanges from a directory of JSON files.

    Keyed on the model plus the last user message, so an unchanged debug loop
    replays for free. A miss raises rather than falling through to the network:
    a silent live call is exactly the accident this exists to prevent.
    """

    def __init__(self, directory: str | os.PathLike[str]) -> None:
        self.directory = Path(directory)
        self._index: dict[str, Any] | None = None

    def _load(self) -> dict[str, Any]:
        if self._index is None:
            index: dict[str, Any] = {}
            for path in sorted(self.directory.glob("*.json")):
                record = json.loads(path.read_text(encoding="utf-8"))
                index[self._key(record["request"])] = record["response"]
            self._index = index
        return self._index

    @staticmethod
    def _key(request: dict[str, Any]) -> str:
        messages = request.get("messages") or []
        last = messages[-1].get("content") if messages else ""
        return f"{request.get('model')}|{last}"

    async def create(self, **kwargs: Any) -> Any:
        index = self._load()
        key = self._key(kwargs)
        if key not in index:
            raise KeyError(
                f"no recorded exchange for {key!r} in {self.directory}. "
                "Record one rather than letting the test reach the network."
            )
        return _Response.from_dict(index[key])


# -- a response shape that works for recorded JSON and the SDK alike -------


@dataclass
class _Usage:
    prompt_tokens: int = 0
    completion_tokens: int = 0


@dataclass
class _Response:
    """Minimal stand-in used by ReplayTransport.

    The real SDK object is passed through untouched; this exists only so a
    recorded JSON file can be used wherever one is.
    """

    raw: dict[str, Any]
    usage: _Usage

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "_Response":
        usage = data.get("usage") or {}
        return cls(
            raw=data,
            usage=_Usage(
                prompt_tokens=usage.get("prompt_tokens", 0),
                completion_tokens=usage.get("completion_tokens", 0),
            ),
        )

    @property
    def choices(self) -> list[Any]:
        return [_Choice(c) for c in self.raw.get("choices", [])]


@dataclass
class _Choice:
    raw: dict[str, Any]

    @property
    def message(self) -> dict[str, Any]:
        return self.raw.get("message", {})

    @property
    def finish_reason(self) -> str | None:
        return self.raw.get("finish_reason")


# -- the client -----------------------------------------------------------


EmitFn = Callable[[dict[str, Any]], None]


def _noop_emit(_: dict[str, Any]) -> None:
    """Default sink. Replaced by the agent host with the real event log."""


class InferenceClient:
    def __init__(
        self,
        transport: Transport | None = None,
        routing: Routing | None = None,
        emit: EmitFn | None = None,
    ) -> None:
        self.transport = transport or OpenAITransport()
        self.routing = routing or Routing()
        self.emit = emit or _noop_emit

    async def complete(
        self,
        task: str,
        messages: list[dict[str, Any]],
        tools: list[dict[str, Any]] | None = None,
        system: str | None = None,
        model_override: str | None = None,
        agent: str = "system",
        **kwargs: Any,
    ) -> Any:
        """One inference call, translated, timed and reported.

        `messages` are in the Agent SDK shape LifeOS agents are written in;
        translation to the OpenAI shape happens here so no agent has to know
        the difference.
        """
        model = model_override or self.routing.model_for(task)
        payload: dict[str, Any] = {
            "model": model,
            "messages": tool_adapter.to_openai_messages(messages, system=system),
            **kwargs,
        }
        converted_tools = tool_adapter.to_openai_tools(tools)
        if converted_tools:
            payload["tools"] = converted_tools

        started = time.monotonic()
        try:
            response = await self.transport.create(**payload)
        except Exception as exc:
            self.emit(
                {
                    "kind": "error",
                    "agent": agent,
                    "summary": f"Inference failed on {model}",
                    "detail": {
                        "task": task,
                        "model": model,
                        "error": f"{type(exc).__name__}: {exc}",
                        "latency_ms": int((time.monotonic() - started) * 1000),
                    },
                }
            )
            raise

        latency_ms = int((time.monotonic() - started) * 1000)
        usage = getattr(response, "usage", None)
        prompt_tokens = int(getattr(usage, "prompt_tokens", 0) or 0)
        completion_tokens = int(getattr(usage, "completion_tokens", 0) or 0)

        self.emit(
            {
                "kind": "inference",
                "agent": agent,
                "summary": f"{task} on {model}",
                "detail": {
                    "task": task,
                    "model": model,
                    "latency_ms": latency_ms,
                    "prompt_tokens": prompt_tokens,
                    "completion_tokens": completion_tokens,
                    "cost_usd": self.routing.cost(model, prompt_tokens, completion_tokens),
                    "tool_count": len(converted_tools or []),
                },
            }
        )
        return response

    async def complete_with_tools(
        self,
        task: str,
        messages: list[dict[str, Any]],
        tools: list[dict[str, Any]],
        max_repairs: int = 2,
        **kwargs: Any,
    ) -> dict[str, Any]:
        """`complete`, plus the JSON-repair retry loop.

        Nemotron may emit arguments that are almost-valid JSON. `tools.py`
        repairs what it safely can; when it cannot, the parse error is fed back
        to the model as a tool result and the call is retried. Returns the
        assistant turn in the Agent SDK shape.
        """
        history = list(messages)

        for attempt in range(max_repairs + 1):
            response = await self.complete(task, history, tools=tools, **kwargs)
            raw_message = _first_message(response)
            try:
                return tool_adapter.from_openai_message(raw_message)
            except tool_adapter.ToolArgumentError as exc:
                if attempt == max_repairs:
                    self.emit(
                        {
                            "kind": "error",
                            "agent": kwargs.get("agent", "system"),
                            "summary": f"Gave up repairing arguments for {exc.tool_name}",
                            "detail": {"raw": exc.raw, "reason": exc.reason},
                        }
                    )
                    raise
                history = history + [
                    {"role": "assistant", "content": [{"type": "text", "text": exc.raw}]},
                    {"role": "user", "content": [{"type": "text", "text": exc.feedback()}]},
                ]

        raise AssertionError("unreachable")  # pragma: no cover


def _first_message(response: Any) -> Any:
    choices = getattr(response, "choices", None) or []
    if not choices:
        raise ValueError("response carried no choices")
    return choices[0].message
