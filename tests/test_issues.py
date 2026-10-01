from app.core import AI, Service, Store


def setup():
    s = Service(Store("sqlite://"), AI())
    return s, s.profile("T", "U", "mechanical", ["atlas"], focus="thermal")


def add(s, ts, text, channel="C", **extra):
    s.ingest("T", {"channel": channel, "ts": str(ts), "text": text, "user": "U", **extra}, "atlas", "https://example.com/source")


def test_focus_and_unresolved_issues_do_not_expire():
    s, p = setup()
    p["focus_until"] = 1  # Legacy profiles also stop expiring.
    add(s, 1, "Thermal failed")
    d = s.digest(p, ["C"], now=9999999999)[0]
    assert "current focus" in d["why"]
    s.issues.mark_delivered(p, [d])
    assert s.digest(p, ["C"])[0]["change"] == "Still open"


def test_actual_delivery_only_and_context_changes():
    s, p = setup()
    for i in range(1, 8):
        add(s, i, f"Enclosure CAD decision version {i}")
    first = s.digest(p, ["C"])
    assert len(first) == 5
    s.issues.mark_delivered(p, first)
    second = s.digest(p, ["C"])
    assert len(second) == 2
    assert not ({d["id"] for d in first} & {d["id"] for d in second})
    s.issues.mark_delivered(p, second)
    assert not s.digest(p, ["C"])
    p = s.profile("T", "U", "mechanical", ["atlas"], focus="enclosure")
    assert s.digest(p, ["C"])[0]["change"] == "Priorities changed"


def test_tagged_cross_thread_resolution_and_delete_rebuild():
    s, p = setup()
    add(s, 1, "[issue:thermal-01] Thermal failed")
    first = s.digest(p, ["C"])
    s.issues.mark_delivered(p, first)
    add(s, 2, "[issue:thermal-01] Resolved: retest passed")
    resolved = s.digest(p, ["C"])
    assert len(resolved) == 1 and resolved[0]["change"] == "Resolved"
    assert resolved[0]["id"] == first[0]["id"]
    assert len(resolved[0]["sources"]) == 2
    assert not s.knowledge.project_status(p, ["C"], "atlas")["blockers"]
    s.issues.mark_delivered(p, resolved)
    assert not s.digest(p, ["C"])
    s.ingest("T", {"channel": "C", "subtype": "message_deleted", "deleted_ts": "2"}, "atlas")
    assert s.digest(p, ["C"])[0]["signal"]["status"] == "open"


def test_no_cross_channel_merge_or_receipt_leak():
    s, p = setup()
    add(s, 1, "[issue:x] Thermal failed")
    add(s, 2, "[issue:x] Resolved secret detail", channel="SECRET")
    assert len(s.issues.current(p, ["C", "SECRET"])) == 2
    assert s.digest(p, ["C"])[0]["signal"]["status"] == "open"
    assert "secret" not in str(s.digest(p, ["C"]))
    assert s.digest(p, []) == []


def test_acknowledgement_does_not_change_issue_version():
    s, p = setup()
    add(s, 1, "Thermal failed")
    first = s.digest(p, ["C"])
    s.issues.mark_delivered(p, first)
    add(s, 2, "Thanks!", thread_ts="1")
    assert s.digest(p, ["C"])[0]["change"] == "Still open"


def test_unshown_source_changes_remain_pending():
    s, p = setup()
    add(s, 1, "Thermal failed")
    add(s, 2, "Enclosure CAD approved")
    snap = s.knowledge.snapshot(p, ["C"])
    shown = next(key for key, value in snap["items"].items() if "Thermal" in value["summary"])
    s.knowledge.mark_delivered(p, snap, [shown])
    changes = s.knowledge.changes(p, ["C"])
    assert len(changes["items"]) == 1
    assert "Enclosure" in changes["items"][0]["summary"]


def test_role_phase_focus_have_explanations_and_no_invented_action():
    s, p = setup()
    add(s, 1, "Thermal test failed")
    s.set_phase("T", "atlas", "validation")
    item = s.digest(p, ["C"])[0]
    assert "mechanical responsibilities" in item["why"]
    assert "validation phase" in item["why"]
    assert "current focus" in item["why"]
    assert item["signal"]["action"] is None


def test_same_evidence_different_roles_and_changed_phase():
    s, _ = setup()
    add(s, 1, "Enclosure CAD tolerance decision")
    add(s, 2, "PCB voltage controller decision")
    add(s, 3, "Procurement order decision")
    for role, expected in [("mechanical", "Enclosure"), ("electrical", "PCB"), ("supply", "Procurement")]:
        profile = s.profile("T", role, role, ["atlas"])
        top = s.digest(profile, ["C"])[0]
        assert expected in top["signal"]["summary"]
        assert role in top["why"]
    p = s.profile("T", "general", "coordinator", ["atlas"])
    s.set_phase("T", "atlas", "design", "enclosure cad tolerance")
    assert "Enclosure" in s.digest(p, ["C"])[0]["text"]
    s.set_phase("T", "atlas", "purchasing", "procurement order")
    assert "Procurement" in s.digest(p, ["C"])[0]["text"]


def test_resolution_of_delivered_issue_is_not_discarded_as_irrelevant():
    s, p = setup()
    add(s, 1, "Thermal failed")
    s.issues.mark_delivered(p, s.digest(p, ["C"]))
    add(s, 2, "Resolved: all good", thread_ts="1")
    result = s.digest(p, ["C"])
    assert result[0]["change"] == "Resolved"
    assert "previously delivered" in result[0]["why"]
