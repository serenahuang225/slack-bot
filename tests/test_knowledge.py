import time
from app.core import AI, Service, Store


def setup():
    service = Service(Store("sqlite://"), AI())
    profile = service.profile("T", "U", "mechanical", ["atlas"])
    return service, profile


def message(service, ts, text, channel="C", team="T", **extra):
    service.ingest(team, {"channel": channel, "ts": str(ts), "text": text,
                          "user": "U", **extra}, "atlas", "https://example.com/thread")


def test_documentation_automatically_updates_and_deletes():
    s, p = setup()
    message(s, 1, "Thermal test failed")
    assert len(s.store.all("knowledge")) == 1
    message(s, 2, "Resolved: new heat sink passed", thread_ts="1")
    assert len(s.store.all("knowledge")) == 1
    assert "Resolved" in s.store.all("knowledge")[0]["text"]
    assert not s.knowledge.project_status(p, ["C"], "atlas")["blockers"]
    assert len(s.knowledge.project_status(p, ["C"], "atlas")["resolved"]) == 1
    s.ingest("T", {"channel": "C", "subtype": "message_deleted", "deleted_ts": "2"}, "atlas")
    assert len(s.knowledge.project_status(p, ["C"], "atlas")["blockers"]) == 1


def test_old_open_blocker_remains_in_daily_digest():
    s, p = setup()
    message(s, 1, "Thermal test failed")
    assert len(s.digest(p, ["C"])) == 1
    assert len(s.knowledge.project_status(p, ["C"], "atlas")["blockers"]) == 1


def test_changes_since_successful_checkpoint_are_repeatable():
    s, p = setup()
    message(s, 1, "Thermal failed")
    assert not s.knowledge.changes(p, ["C"])["has_baseline"]
    snapshot = s.knowledge.snapshot(p, ["C"])
    # Preparing a digest does not advance a checkpoint.
    assert s.knowledge.baseline(p) is None
    s.knowledge.mark_delivered(p, snapshot, list(snapshot["items"]))
    message(s, 2, "Resolved: thermal passed", thread_ts="1")
    message(s, 3, "Supplier shipment delayed")
    changes = s.knowledge.changes(p, ["C"])
    assert {e["change"] for e in changes["items"]} == {"new", "resolved"}
    assert s.knowledge.changes(p, ["C"]) == changes
    # An event arriving after preparation remains new after delivery.
    before_send = s.knowledge.snapshot(p, ["C"])
    message(s, 4, "Voltage test failed")
    s.knowledge.mark_delivered(p, before_send, list(before_send["items"]))
    assert [e["summary"] for e in s.knowledge.changes(p, ["C"])["items"]] == ["U: Voltage test failed"]


def test_changes_do_not_disclose_removed_access_or_deleted_contents():
    s, p = setup()
    message(s, 1, "Sensitive supplier terms", channel="SECRET")
    message(s, 2, "Public enclosure test", channel="C")
    snapshot = s.knowledge.snapshot(p, ["C", "SECRET"])
    s.knowledge.mark_delivered(p, snapshot, list(snapshot["items"]))
    assert not s.knowledge.changes(p, ["C"])["items"]
    s.ingest("T", {"channel": "C", "subtype": "message_deleted", "deleted_ts": "2"}, "atlas")
    changes = s.knowledge.changes(p, ["C"])
    assert len(changes["items"]) == 1
    assert changes["items"][0]["change"] == "removed"
    assert "Public enclosure" not in str(changes)


def test_snapshot_diffs_content_not_ai_paraphrase_and_tracks_phases():
    s, p = setup()
    message(s, 1, "Thermal test failed")
    s.set_phase("T", "atlas", "validation")
    snapshot = s.knowledge.snapshot(p, ["C"])
    s.knowledge.mark_delivered(p, snapshot, list(snapshot["items"]))
    s.set_phase("T", "atlas", "production")
    changes = s.knowledge.changes(p, ["C"])
    assert not changes["items"]
    assert changes["phase_changes"] == [{"project": "atlas", "before": "validation", "after": "production"}]
    message(s, 1, "Thermal test failed")  # Duplicate delivery is not a change.
    assert not s.knowledge.changes(p, ["C"])["items"]


def test_custom_roles_and_phases_preserve_profile_preferences():
    s, _ = setup()
    p = s.profile("T", "UX", "UX researcher", ["website"], focus="interviews", responsibilities="usability interviews")
    assert "usability" in p["keywords"]
    p = s.profile("T", "UX", "UX researcher", ["website"], responsibilities="accessibility audits")
    assert p["focus"] == "interviews" and "accessibility" in p["keywords"]
    phase = s.set_phase("T", "website", "user research", "interviews usability")
    assert phase["phase"] == "user research" and "usability" in phase["keywords"]
    s.ingest("T", {"channel": "C", "ts": str(time.time()), "user": "U", "text": "Accessibility audits decision"}, "website")
    s.ingest("T", {"channel": "C", "ts": str(time.time()+1), "user": "U", "text": "Unrelated shipment note"}, "website")
    assert "Accessibility" in s.digest(p, ["C"])[0]["text"]


def test_sources_are_filtered_by_team_project_and_channel():
    s, p = setup()
    message(s, 1, "Secret failure", channel="SECRET")
    message(s, 2, "Other workspace failure", team="OTHER")
    s.ingest("T", {"channel": "C", "ts": "3", "user": "U", "text": "Other project failure"}, "other")
    assert s.knowledge.entries(p, ["C"]) == []
    assert s.knowledge.project_status(p, ["C"], "atlas")["source_count"] == 0
