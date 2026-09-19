"""Workspace watcher tests."""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "apps" / "host"))

from watcher import WorkspaceWatcher  # noqa: E402


@pytest.fixture()
def workspace(tmp_path: Path) -> Path:
    (tmp_path / "memory.md").write_text("one\ntwo\n", encoding="utf-8")
    return tmp_path


def test_the_first_poll_primes_and_reports_nothing() -> None:
    """Reporting the whole workspace as `created` on startup would bury the
    first real event."""
    watcher = WorkspaceWatcher(ROOT / "fixtures")
    assert watcher.poll() == []


def test_a_modification_produces_a_unified_diff(workspace: Path) -> None:
    watcher = WorkspaceWatcher(workspace)
    watcher.poll()

    (workspace / "memory.md").write_text("one\ntwo\nthree\n", encoding="utf-8")
    changes = watcher.poll()

    assert len(changes) == 1
    assert changes[0].action == "modified"
    assert changes[0].path == "memory.md"
    assert "+three" in changes[0].diff


def test_a_new_file_is_created_not_modified(workspace: Path) -> None:
    watcher = WorkspaceWatcher(workspace)
    watcher.poll()

    (workspace / "identity.md").write_text("I am LifeOS.\n", encoding="utf-8")
    changes = watcher.poll()
    assert [(c.path, c.action) for c in changes] == [("identity.md", "created")]
    assert "+I am LifeOS." in changes[0].diff


def test_a_deletion_is_reported_with_the_removed_content(workspace: Path) -> None:
    watcher = WorkspaceWatcher(workspace)
    watcher.poll()

    (workspace / "memory.md").unlink()
    changes = watcher.poll()
    assert [(c.path, c.action) for c in changes] == [("memory.md", "deleted")]
    assert "-one" in changes[0].diff


def test_nothing_is_reported_when_nothing_changed(workspace: Path) -> None:
    watcher = WorkspaceWatcher(workspace)
    watcher.poll()
    assert watcher.poll() == []


def test_a_rewrite_with_identical_content_is_not_a_change(workspace: Path) -> None:
    """Hashed, not mtime-compared. Agents rewrite whole files constantly and a
    timeline full of no-op writes is worse than no timeline."""
    watcher = WorkspaceWatcher(workspace)
    watcher.poll()

    target = workspace / "memory.md"
    target.write_text(target.read_text(encoding="utf-8"), encoding="utf-8")
    assert watcher.poll() == []


def test_nested_directories_are_watched(workspace: Path) -> None:
    watcher = WorkspaceWatcher(workspace)
    watcher.poll()

    nested = workspace / "notes" / "deep"
    nested.mkdir(parents=True)
    (nested / "a.md").write_text("x\n", encoding="utf-8")
    assert [c.path for c in watcher.poll()] == ["notes/deep/a.md"]


def test_noisy_directories_are_ignored(workspace: Path) -> None:
    watcher = WorkspaceWatcher(workspace)
    watcher.poll()

    (workspace / "__pycache__").mkdir()
    (workspace / "__pycache__" / "x.pyc").write_bytes(b"\x00\x01")
    (workspace / ".git").mkdir()
    (workspace / ".git" / "HEAD").write_text("ref: x\n", encoding="utf-8")
    assert watcher.poll() == []


def test_a_large_file_is_reported_without_a_textual_diff(workspace: Path) -> None:
    watcher = WorkspaceWatcher(workspace, max_diff_bytes=64)
    watcher.poll()

    (workspace / "big.md").write_text("x" * 500, encoding="utf-8")
    change = watcher.poll()[0]
    assert change.action == "created"
    assert change.size == 500
    assert change.diff == ""


def test_a_binary_file_is_reported_without_a_diff(workspace: Path) -> None:
    watcher = WorkspaceWatcher(workspace)
    watcher.poll()

    (workspace / "blob.bin").write_bytes(b"\xff\xfe\x00\x01")
    change = watcher.poll()[0]
    assert change.action == "created"
    assert change.diff == ""


def test_a_missing_workspace_is_tolerated(tmp_path: Path) -> None:
    """The sandbox may not have created it yet. Crashing the host over that
    would be a poor trade."""
    watcher = WorkspaceWatcher(tmp_path / "not-there-yet")
    assert watcher.poll() == []
    assert watcher.poll() == []


def test_a_workspace_appearing_later_is_picked_up(tmp_path: Path) -> None:
    root = tmp_path / "later"
    watcher = WorkspaceWatcher(root)
    watcher.poll()

    root.mkdir()
    (root / "memory.md").write_text("hello\n", encoding="utf-8")
    assert [c.path for c in watcher.poll()] == ["memory.md"]


def test_changes_come_back_in_a_stable_order(workspace: Path) -> None:
    watcher = WorkspaceWatcher(workspace)
    watcher.poll()

    for name in ("zebra.md", "apple.md", "mango.md"):
        (workspace / name).write_text("x\n", encoding="utf-8")
    assert [c.path for c in watcher.poll()] == ["apple.md", "mango.md", "zebra.md"]


def test_a_change_converts_to_an_event_payload(workspace: Path) -> None:
    watcher = WorkspaceWatcher(workspace)
    watcher.poll()
    (workspace / "memory.md").write_text("one\ntwo\nthree\n", encoding="utf-8")

    change = watcher.poll()[0]
    assert change.summary() == "modified memory.md"
    detail = change.to_detail()
    assert detail["path"] == "memory.md"
    assert detail["action"] == "modified"
    assert "diff" in detail
