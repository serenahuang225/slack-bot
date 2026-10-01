import time
from app.core import AI, Service, Store


def service():
    return Service(Store("sqlite://"), AI())


def add(s, channel="public", text="Supplier lead time risk delayed shipment", ts=None, **extra):
    event = {"channel": channel, "ts": ts or str(time.time()), "user": "Alex", "text": text, **extra}
    s.ingest("T", event, "atlas", "https://example.com/source")
    return event


def test_roles_change_ranking():
    s = service()
    add(s, text="Enclosure CAD tolerance material approved")
    add(s, text="Supplier lead time risk delayed shipment")
    me = s.profile("T", "ME", "mechanical", ["atlas"])
    supply = s.profile("T", "SC", "supply", ["atlas"])
    assert "Supplier" in s.digest(me, ["public"])[0]["text"]  # Shared risk wins over routine news.
    assert any("Enclosure" in d["text"] for d in s.digest(me, ["public"]))
    assert "Supplier" in s.digest(supply, ["public"])[0]["text"]


def test_robotics_demo_roles_change_ranking():
    s = service()
    add(s, text="Enclosure CAD tolerance material decision")
    add(s, text="PCB voltage controller power blocked")
    add(s, text="Supplier vendor lead shipment delayed")
    s.store.put("phase:T:atlas", "phase", {"phase": "prototype"})
    for role, expected in [("mechanical", "Supplier"), ("electrical", "PCB"), ("supply", "Supplier")]:
        p = s.profile("T", role, role, ["atlas"])
        assert expected in s.digest(p, ["public"])[0]["text"]


def test_retrieval_filters_permissions_and_workspace():
    s = service()
    add(s, channel="secret", text="Secret supplier terms")
    s.ingest("OTHER", {"channel": "public", "ts": str(time.time()), "user": "x", "text": "Secret supplier terms"}, "atlas")
    p = s.profile("T", "U", "supply", ["atlas"])
    assert "couldn't find" in s.ask(p, ["public"], "supplier")


def test_duplicate_edit_delete_and_resolution():
    s = service()
    e = add(s, text="Thermal test failed")
    s.ingest("T", e, "atlas")
    assert len(s.store.all("message")) == 1
    p = s.profile("T", "U", "mechanical", ["atlas"])
    assert s.digest(p, ["public"])
    s.ingest("T", {"channel": "public", "subtype": "message_changed", "message": dict(e, text="Resolved thermal issue")}, "atlas")
    assert not s.digest(p, ["public"])
    s.ingest("T", {"channel": "public", "subtype": "message_deleted", "deleted_ts": e["ts"]}, "atlas")
    assert not s.documents("T", ["public"])


def test_feedback_and_phase_change_score():
    s = service()
    add(s, text="Supplier shipment lead risk")
    p = s.profile("T", "U", "mechanical", ["atlas"])
    initial = s.digest(p, ["public"])[0]
    s.store.put("phase:T:atlas", "phase", {"phase": "production"})
    assert s.digest(p, ["public"])[0]["score"] > initial["score"] + 5
    s.store.put(f"feedback:T:U:{initial['id']}", "feedback", {"value": -1})
    assert s.digest(p, ["public"])[0]["score"] < initial["score"]


def test_thread_reply_and_long_chunks():
    s = service()
    parent = add(s, text="Thermal issue")
    add(s, text="Resolved in retest", thread_ts=parent["ts"])
    docs = s.documents("T", ["public"])
    assert len(docs) == 1 and "Resolved" in docs[0]["text"]
    add(s, text="long text " * 1000)
    assert all(len(d["text"]) < 4100 for d in s.documents("T", ["public"]))


def test_semantic_retrieval_without_keyword_overlap_and_cache():
    class SemanticStub(AI):
        def __init__(self):
            super().__init__()
            self.calls = 0

        def embed(self, text, query=False):
            self.calls += 1
            return ([1., 0.] if query or "hot" in text else [0., 1.]) + [0.] * 766

    ai = SemanticStub()
    s = Service(Store("sqlite://"), ai)
    add(s, text="Actuator runs hot")
    add(s, text="Shipment arrives tomorrow")
    p = s.profile("T", "U", "mechanical", ["atlas"])
    answer = s.ask(p, ["public"], "overheating")
    assert "Actuator runs hot" in answer and "Shipment" not in answer
    assert "https://example.com/source" in answer
    previous = ai.calls
    s.ask(p, ["public"], "overheating")
    assert ai.calls == previous + 1  # Only the new query needs embedding.
