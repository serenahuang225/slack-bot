import pytest
from sqlalchemy import create_engine
from app.vectors import VectorIndex, normalize


def vector(axis=0):
    result = [0.] * 768
    result[axis] = 1.
    return result


def doc(id="a", channel="C", project="atlas", text="Motor overheating"):
    return {"id": id, "channel": channel, "project": project, "text": text}


def test_native_vector_search_persists_and_filters_before_limit(tmp_path):
    url = f"sqlite:///{tmp_path / 'vectors.db'}"
    index = VectorIndex(create_engine(url))
    index.sync("T", ["C"], ["atlas"], [doc()], "model", lambda _: vector())
    index.sync("OTHER", ["C"], ["atlas"], [doc("other")], "model", lambda _: vector())
    index.sync("T", ["SECRET"], ["atlas"], [doc("private", channel="SECRET")], "model", lambda _: vector())
    index.sync("T", ["C"], ["other"], [doc("project", project="other")], "model", lambda _: vector())
    reopened = VectorIndex(create_engine(url))
    hits = reopened.search("T", ["C"], ["atlas"], "model", vector(), ["a", "other", "private", "project"], limit=1)
    assert hits == [("a", pytest.approx(1.))]
    assert not reopened.search("T", [], ["atlas"], "model", vector(), ["a"])
    assert not reopened.search("T", ["C"], ["atlas"], "different-model", vector(), ["a"])


def test_index_updates_model_changes_and_deletions():
    index = VectorIndex(create_engine("sqlite://"))
    calls = []
    def embed(text):
        calls.append(text)
        return vector()
    assert index.sync("T", ["C"], ["atlas"], [doc()], "m1", embed)["embedded"] == 1
    assert index.sync("T", ["C"], ["atlas"], [doc()], "m1", embed)["unchanged"] == 1
    assert len(calls) == 1
    assert index.sync("T", ["C"], ["atlas"], [doc(text="Cooling resolved")], "m1", embed)["embedded"] == 1
    assert index.sync("T", ["C"], ["atlas"], [doc(text="Cooling resolved")], "m2", embed)["embedded"] == 1
    # Current-source allowlist prevents a stale indexed document from leaking.
    assert not index.search("T", ["C"], ["atlas"], "m2", vector(), [])
    assert index.sync("T", ["C"], ["atlas"], [], "m2", embed)["removed"] == 1
    assert index.count() == 0


def test_invalid_vectors_are_rejected():
    for bad in [[1., 2.], [0.] * 768, [float("nan")] * 768]:
        with pytest.raises(ValueError):
            normalize(bad)


def test_vector_retrieval_does_not_call_summary_model():
    from app.core import AI, Service, Store
    class EmbedOnly(AI):
        def embed(self, text, query=False):
            return vector()
        def extract(self, text):
            raise AssertionError("Retrieval must not summarize documents")
    service = Service(Store("sqlite://"), EmbedOnly())
    service.ingest("T", {"channel": "C", "ts": "1", "user": "U", "text": "Actuator temperature high"}, "atlas")
    p = service.profile("T", "U", "mechanical", ["atlas"])
    hits = service.retrieve(p, ["C"], "overheating")
    assert hits and hits[0]["similarity"] == pytest.approx(1.)
