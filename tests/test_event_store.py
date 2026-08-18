"""EventStore contract tests (docs/10)."""

from lhas.domain.enums import EventType
from lhas.persistence.event_store import EventStore


def test_append_returns_sequence_and_persists(db):
    store = EventStore(db)
    ev = store.append(EventType.TASK_CREATED, task_id="t1", payload={"a": 1})
    assert ev.id is not None and ev.id >= 1
    assert ev.event_type is EventType.TASK_CREATED
    assert ev.payload == {"a": 1}
    assert store.count() == 1

    ev2 = store.append(EventType.RUN_STARTED, task_id="t1", run_id="r1")
    assert ev2.id > ev.id  # append-only, monotonic sequence


def test_filters_by_scope(db):
    store = EventStore(db)
    store.append(EventType.TASK_CREATED, task_id="t1")
    store.append(EventType.RUN_CREATED, task_id="t1", run_id="r1")
    store.append(EventType.ATTEMPT_STARTED, task_id="t1", run_id="r1", attempt_id="a1")
    store.append(EventType.TASK_CREATED, task_id="t2")

    assert len(store.list_for_task("t1")) == 3
    assert len(store.list_for_run("r1")) == 2
    assert len(store.list_for_attempt("a1")) == 1
    assert store.count() == 4
    # ordering preserved
    assert [e.id for e in store.list_for_task("t1")] == [1, 2, 3]


def test_events_are_immutable_shape(db):
    store = EventStore(db)
    ev = store.append(EventType.TASK_COMPLETED, task_id="t1", payload={"status": "COMPLETED"})
    assert ev.payload == {"status": "COMPLETED"}
    # every event carries the full scope triple (nullable)
    assert ev.task_id == "t1" and ev.run_id is None and ev.attempt_id is None
