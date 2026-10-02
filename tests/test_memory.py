"""Memory store and embedding tests. Offline — demo vectors, no API calls."""

from __future__ import annotations

import asyncio
import sys
from pathlib import Path
from typing import Any

import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from packages.memory import embeddings, store  # noqa: E402


def run(coro: Any) -> Any:
    return asyncio.run(coro)


@pytest.fixture(autouse=True)
def demo(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("DEMO", "true")


@pytest.fixture()
def events() -> list[dict[str, Any]]:
    return []


# -- embeddings -----------------------------------------------------------


def test_demo_embeddings_are_deterministic() -> None:
    """Retrieval has to be stable across runs or the demo is unreproducible."""
    assert embeddings.demo_embedding("hello") == embeddings.demo_embedding("hello")
    assert embeddings.demo_embedding("hello") != embeddings.demo_embedding("goodbye")


def test_demo_embeddings_are_unit_length() -> None:
    vector = embeddings.demo_embedding("anything at all")
    assert sum(v * v for v in vector) == pytest.approx(1.0, abs=1e-6)
    assert len(vector) == embeddings.DEMO_DIMENSIONS


def test_cosine_of_a_vector_with_itself_is_one() -> None:
    v = embeddings.demo_embedding("x")
    assert embeddings.cosine(v, v) == pytest.approx(1.0, abs=1e-6)


def test_cosine_rejects_a_dimension_mismatch() -> None:
    """A half-reindexed table can hold both widths; silently scoring them
    against each other would be worse than failing."""
    with pytest.raises(ValueError, match="dimension mismatch"):
        embeddings.cosine([1.0, 0.0], [1.0, 0.0, 0.0])


def test_cosine_of_a_zero_vector_is_zero_not_a_crash() -> None:
    assert embeddings.cosine([0.0, 0.0], [1.0, 0.0]) == 0.0


def test_demo_embedding_emits_an_event_saying_it_is_not_real(
    events: list[dict[str, Any]]
) -> None:
    """A timeline that cannot tell a real embedding from a stand-in is not
    worth having."""
    run(embeddings.embed(["a", "b"], emit=events.append, demo=True))
    assert events[0]["detail"]["real"] is False
    assert events[0]["detail"]["model"] == "demo"


def test_embedding_an_empty_batch_costs_nothing(events: list[dict[str, Any]]) -> None:
    assert run(embeddings.embed([], emit=events.append, demo=True)) == []
    assert events == []


def test_the_embedding_model_is_still_a_placeholder() -> None:
    """Flips when the routing key is read from the console. The Nemotron keys
    proved display names and routing keys differ unpredictably."""
    assert embeddings.is_placeholder() is True


def test_a_live_call_with_a_placeholder_model_refuses(events: list[dict[str, Any]]) -> None:
    class Client:
        transport = object()

    with pytest.raises(embeddings.EmbeddingError, match="routing key"):
        run(embeddings.embed(["x"], client=Client(), emit=events.append, demo=False))


def test_provenance_is_derived_from_config_not_prose() -> None:
    """So the submission cannot drift into claiming an NVIDIA embedding model
    it is not using."""
    p = embeddings.provenance()
    assert p["is_nvidia"] is False
    assert "not an NVIDIA model" in p["claim"]
    assert p["dimensions"] == 4096


def test_a_wrong_width_response_is_rejected(events: list[dict[str, Any]], monkeypatch: pytest.MonkeyPatch) -> None:
    """The schema column is fixed width, so a mismatch would fail on insert
    after the whole batch had been paid for."""
    monkeypatch.setattr(embeddings, "EMBEDDING_MODEL", "qwen/real-key")

    class Transport:
        async def create_embeddings(self, **kwargs: Any) -> Any:
            class R:
                data = [{"embedding": [0.1] * 16}]
                usage = None

            return R()

    class Client:
        transport = Transport()

    with pytest.raises(embeddings.EmbeddingError, match="4096"):
        run(embeddings.embed(["x"], client=Client(), emit=events.append, demo=False))


# -- the store ------------------------------------------------------------


def test_the_store_loads_the_seed_rows() -> None:
    assert len(store.MemoryStore().rows()) >= 10


def test_the_store_reports_its_backend() -> None:
    assert store.MemoryStore(demo=True).backend == "fixtures"
    assert store.MemoryStore(demo=False).backend == "supabase"


def test_outside_demo_mode_the_store_is_empty_rather_than_invented() -> None:
    """A memory that invents plausible rows is worse than a visibly empty one."""
    assert store.MemoryStore(demo=False).rows() == []


def test_indexing_is_resumable_and_does_no_work_twice(events: list[dict[str, Any]]) -> None:
    memory = store.MemoryStore(emit=events.append, demo=True)
    first = run(memory.ensure_index())
    assert first == len(memory.rows())
    assert run(memory.ensure_index()) == 0


def test_recall_finds_the_row_it_was_given_verbatim() -> None:
    """Demo vectors are a hash, so only an exact text match scores highly.
    That is the strongest claim this backend can honestly support."""
    memory = store.MemoryStore(demo=True)
    target = memory.rows()[0]
    hits = run(memory.recall(target["text"], limit=3))
    assert hits[0].id == target["id"]
    assert hits[0].score == pytest.approx(1.0, abs=1e-6)


def test_recall_says_how_it_matched() -> None:
    """`packages/agents/data.search_memory` says "keyword"; this says
    "vector". The agent recalling something means different things."""
    memory = store.MemoryStore(demo=True)
    hits = run(memory.recall(memory.rows()[0]["text"]))
    assert hits[0].match == "vector"


def test_recall_respects_the_limit() -> None:
    memory = store.MemoryStore(demo=True)
    assert len(run(memory.recall("anything", limit=2))) == 2


def test_recall_can_be_filtered_by_kind() -> None:
    memory = store.MemoryStore(demo=True)
    hits = run(memory.recall("anything", limit=10, kinds=["commitment"]))
    assert hits
    assert {h.kind for h in hits} == {"commitment"}


def test_recall_carries_the_grounding_badge_through() -> None:
    memory = store.MemoryStore(demo=True)
    row = next(r for r in memory.rows() if r.get("external_claim"))
    hits = run(memory.recall(row["text"], limit=1))
    assert "status" in hits[0].grounding


def test_recall_on_an_empty_store_returns_nothing() -> None:
    assert run(store.MemoryStore(demo=False).recall("anything")) == []


def test_recall_emits_an_event(events: list[dict[str, Any]]) -> None:
    memory = store.MemoryStore(emit=events.append, demo=True)
    run(memory.recall("gym"))
    assert any("Recalled" in e["summary"] for e in events)


# -- writes ---------------------------------------------------------------


def test_remembering_a_row_makes_it_recallable(events: list[dict[str, Any]]) -> None:
    memory = store.MemoryStore(emit=events.append, demo=True)
    run(memory.ensure_index())
    run(memory.remember("mem_new", "fact", "Lisbon office opens in November", "stated directly"))

    hits = run(memory.recall("Lisbon office opens in November", limit=1))
    assert hits[0].id == "mem_new"


def test_remembering_an_existing_id_replaces_rather_than_duplicates() -> None:
    memory = store.MemoryStore(demo=True)
    before = len(memory.rows())
    target = memory.rows()[0]["id"]
    run(memory.remember(target, "fact", "replaced text", "test"))

    assert len(memory.rows()) == before
    assert run(memory.recall("replaced text", limit=1))[0].id == target


def test_a_replaced_row_is_re_embedded_not_left_stale() -> None:
    memory = store.MemoryStore(demo=True)
    run(memory.ensure_index())
    target = memory.rows()[0]["id"]
    run(memory.remember(target, "fact", "entirely different text", "test"))

    hits = run(memory.recall("entirely different text", limit=1))
    assert hits[0].id == target
    assert hits[0].score == pytest.approx(1.0, abs=1e-6)


def test_an_unknown_kind_is_refused() -> None:
    memory = store.MemoryStore(demo=True)
    with pytest.raises(ValueError, match="unknown memory kind"):
        run(memory.remember("x", "vibes", "t", "s"))


def test_writing_does_not_mutate_the_seed_fixtures() -> None:
    """A demo that drifts from its fixtures stops being reproducible."""
    from fixtures import loader

    memory = store.MemoryStore(demo=True)
    run(memory.remember("mem_scratch", "fact", "scratch", "test"))
    assert "mem_scratch" not in {r["id"] for r in loader.memory_rows()}


def test_forgetting_removes_a_row(events: list[dict[str, Any]]) -> None:
    memory = store.MemoryStore(emit=events.append, demo=True)
    target = memory.rows()[0]["id"]
    assert memory.forget(target) is True
    assert target not in {r["id"] for r in memory.rows()}
    assert any("Forgot" in e["summary"] for e in events)


def test_forgetting_something_absent_reports_false() -> None:
    assert store.MemoryStore(demo=True).forget("nope") is False


def test_no_demo_vector_contains_nan_or_infinity() -> None:
    """The first version unpacked digest bytes as IEEE-754 floats, which
    produces NaN for some inputs. Every comparison with NaN is false, so one
    poisoned vector silently dropped the correct top hit out of a sorted
    result — recall returned a 0.0 match while an exact 1.0 match existed."""
    import math

    from fixtures import loader

    texts = [r["text"] for r in loader.memory_rows()] + ["", "x", "Lisbon office opens in November"]
    for text in texts:
        for value in embeddings.demo_embedding(text):
            assert math.isfinite(value), f"non-finite component for {text[:30]!r}"


def test_every_seed_row_scores_finitely_against_every_other() -> None:
    memory = store.MemoryStore(demo=True)
    run(memory.ensure_index())
    import math

    vectors = list(memory._vectors.values())
    for a in vectors:
        for b in vectors:
            assert math.isfinite(embeddings.cosine(a, b))


def test_recall_does_not_silently_floor_at_zero() -> None:
    """The default used to be min_score=0.0, which discarded every negative
    cosine — about half the rows — so a filtered recall came back empty while
    relevant rows existed. Cutting off a ranked result is the caller's call."""
    memory = store.MemoryStore(demo=True)
    everything = run(memory.recall("unrelated query text", limit=50))
    assert len(everything) == len(memory.rows())
    assert any(h.score < 0 for h in everything), "expected some negative similarities"


def test_min_score_still_filters_when_a_caller_asks() -> None:
    memory = store.MemoryStore(demo=True)
    target = memory.rows()[0]
    hits = run(memory.recall(target["text"], limit=50, min_score=0.9))
    assert [h.id for h in hits] == [target["id"]]
