import time
from app.core import AI, Service, Store
from app.names import Names


def test_names_are_workspace_scoped_and_cached():
    store = Store("sqlite://")
    calls = []
    def lookup(user):
        calls.append(user)
        return "serena mit"
    names = Names(store, lookup)
    assert names.text("T1", "U0C4T5SENHF: ask <@U0C4T5SENHF>") == "serena mit: ask serena mit"
    assert calls == ["U0C4T5SENHF"]
    assert Names(store).get("T2", "U0C4T5SENHF") == "U0C4T5SENHF"


def test_resolved_names_keep_personal_mention_score():
    s = Service(Store("sqlite://"), AI())
    s.names.lookup = lambda user: "serena"
    s.ingest("T", {"channel": "C", "ts": str(time.time()), "user": "U0C4T5SENHF", "text": "<@U0C4T5QVC4R> please check controller"}, "atlas")
    p = s.profile("T", "U0C4T5QVC4R", "electrical", ["atlas"])
    d = s.digest(p, ["C"])[0]
    assert "U0C4T5" not in d["text"]
    assert "mentions you" in d["why"]


def test_missing_permission_keeps_cached_name_and_urls():
    store = Store("sqlite://")
    store.put("name:T:U0C4T5SENHF", "name", {"name": "serena mit", "checked": 0})
    names = Names(store, lambda user: None)
    assert names.text("T", "U0C4T5SENHF https://example.com/U0C4T5SENHF") == "serena mit https://example.com/U0C4T5SENHF"
