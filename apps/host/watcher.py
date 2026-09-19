"""Workspace file watcher.

Agent identity, memory and config persist as files in the sandbox workspace.
Watching them is how the Memory screen gets its diffs, and how "the agent
learned something" becomes a visible event rather than an invisible one.

Polling rather than inotify, deliberately: the workspace may sit on a bind
mount or an overlay inside a container, where filesystem events are unreliable
or absent. A 1 s poll over a directory this small costs nothing and works
everywhere. Week-one unknown #2 is *what* lands here and how often; this module
does not need to know in advance.

Stdlib only.
"""

from __future__ import annotations

import asyncio
import difflib
import hashlib
import os
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any, AsyncIterator, Callable, Iterable

# Files that change constantly and say nothing. Keeps the timeline readable.
DEFAULT_IGNORES = (".git", "__pycache__", ".venv", "node_modules", ".DS_Store")

# Anything larger is recorded as a size/hash change without a textual diff.
MAX_DIFF_BYTES = 256 * 1024


@dataclass(frozen=True)
class FileState:
    path: str
    size: int
    mtime: float
    digest: str


@dataclass
class Change:
    """One observed file change, ready to become a `memory_write` event."""

    path: str
    action: str  # created | modified | deleted
    diff: str
    size: int
    detected_at: float

    def summary(self) -> str:
        return f"{self.action} {self.path}"

    def to_detail(self) -> dict[str, Any]:
        return {
            "path": self.path,
            "action": self.action,
            "diff": self.diff,
            "size": self.size,
        }


class WorkspaceWatcher:
    def __init__(
        self,
        root: str | os.PathLike[str],
        ignores: Iterable[str] = DEFAULT_IGNORES,
        max_diff_bytes: int = MAX_DIFF_BYTES,
    ) -> None:
        self.root = Path(root)
        self.ignores = tuple(ignores)
        self.max_diff_bytes = max_diff_bytes
        self._states: dict[str, FileState] = {}
        self._contents: dict[str, str] = {}
        self._primed = False

    # -- scanning ---------------------------------------------------------

    def _ignored(self, path: Path) -> bool:
        return any(part in self.ignores for part in path.parts)

    def _scan(self) -> dict[str, FileState]:
        states: dict[str, FileState] = {}
        if not self.root.exists():
            return states
        for path in self.root.rglob("*"):
            if not path.is_file() or self._ignored(path.relative_to(self.root)):
                continue
            try:
                stat = path.stat()
                digest = hashlib.sha256(path.read_bytes()).hexdigest()
            except OSError:
                # A file being written as we scan. It will show up next tick.
                continue
            rel = path.relative_to(self.root).as_posix()
            states[rel] = FileState(rel, stat.st_size, stat.st_mtime, digest)
        return states

    def _read_text(self, rel: str, size: int) -> str | None:
        if size > self.max_diff_bytes:
            return None
        try:
            return (self.root / rel).read_text(encoding="utf-8")
        except (OSError, UnicodeDecodeError):
            return None  # binary, or gone again

    def _diff(self, rel: str, before: str | None, after: str | None) -> str:
        if before is None and after is None:
            return ""
        lines = difflib.unified_diff(
            (before or "").splitlines(keepends=True),
            (after or "").splitlines(keepends=True),
            fromfile=f"a/{rel}",
            tofile=f"b/{rel}",
            n=2,
        )
        return "".join(lines)

    def poll(self) -> list[Change]:
        """One pass. Returns the changes since the previous pass.

        The first call primes and returns nothing: every pre-existing file is
        not news, and reporting the whole workspace as "created" on startup
        would bury the first real event.
        """
        now = time.time()
        states = self._scan()
        changes: list[Change] = []

        if not self._primed:
            self._states = states
            self._contents = {
                rel: text
                for rel, state in states.items()
                if (text := self._read_text(rel, state.size)) is not None
            }
            self._primed = True
            return changes

        for rel, state in states.items():
            previous = self._states.get(rel)
            if previous is not None and previous.digest == state.digest:
                continue

            after = self._read_text(rel, state.size)
            before = self._contents.get(rel)
            changes.append(
                Change(
                    path=rel,
                    action="created" if previous is None else "modified",
                    diff=self._diff(rel, before, after),
                    size=state.size,
                    detected_at=now,
                )
            )
            if after is None:
                self._contents.pop(rel, None)
            else:
                self._contents[rel] = after

        for rel in set(self._states) - set(states):
            changes.append(
                Change(
                    path=rel,
                    action="deleted",
                    diff=self._diff(rel, self._contents.get(rel), None),
                    size=0,
                    detected_at=now,
                )
            )
            self._contents.pop(rel, None)

        self._states = states
        changes.sort(key=lambda c: c.path)
        return changes

    async def watch(self, interval: float = 1.0) -> AsyncIterator[Change]:
        while True:
            for change in self.poll():
                yield change
            await asyncio.sleep(interval)

    async def run(
        self,
        emit: Callable[[str, str, str, dict[str, Any]], Any],
        agent: str = "system",
        interval: float = 1.0,
    ) -> None:
        """Pump changes into the event log until cancelled."""
        async for change in self.watch(interval):
            emit("memory_write", agent, change.summary(), change.to_detail())
