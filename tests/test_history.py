import pytest
from app.core import AI, Service, Store
from app.history import backfill, download_text


class Slack:
    token = "fake"

    def auth_test(self):
        return {"team_id": "T"}

    def conversations_info(self, **kwargs):
        return {"channel": {"is_member": True, "is_private": False}}

    def conversations_history(self, cursor=None, **kwargs):
        if cursor:
            return {"messages": [{"ts": "2", "user": "U", "text": "Encoder decision"}]}
        return {"messages": [{"ts": "1", "user": "U", "text": "Thermal blocked", "reply_count": 1,
                              "files": [{"id": "F"}]}], "response_metadata": {"next_cursor": "next"}}

    def conversations_replies(self, **kwargs):
        return {"messages": [{"ts": "3", "thread_ts": "1", "user": "U", "text": "Resolved cooling"}]}

    def chat_getPermalink(self, **kwargs):
        return {"permalink": "https://example.com/message"}

    def files_info(self, **kwargs):
        return {"file": {"id": "F", "name": "spec.txt", "permalink": "https://example.com/file"}}


def test_paginated_import_repeat_and_file_retrieval(monkeypatch):
    monkeypatch.setattr("app.history.download_text", lambda *args: "Encoder operating voltage is five volts")
    service = Service(Store("sqlite://"), AI())
    report = backfill(service, Slack(), {"C": "atlas"})
    assert report == {"messages": 3, "files": 1, "warnings": []}
    backfill(service, Slack(), {"C": "atlas"})
    assert len(service.store.all("message")) == 3
    assert len(service.store.all("file")) == 1
    assert len([e for e in service.store.all("knowledge") if e["source_type"] == "file"]) == 1
    p = service.profile("T", "U", "electrical", ["atlas"])
    assert "five volts" in service.ask(p, ["C"], "operating voltage")
    assert "five volts" not in service.ask(p, [], "operating voltage")
    service.ingest("T", {"channel": "C", "subtype": "message_deleted", "deleted_ts": "1"}, "atlas")
    assert not service.store.all("file")
    assert not [e for e in service.store.all("knowledge") if e["source_type"] == "file"]
    assert "five volts" not in service.ask(p, ["C"], "operating voltage")


def test_private_channel_is_not_imported():
    class Private(Slack):
        def conversations_info(self, **kwargs):
            return {"channel": {"is_private": True, "is_member": True}}
    s = Service(Store("sqlite://"), AI())
    report = backfill(s, Private(), {"C": "atlas"})
    assert report["warnings"] and not s.store.all("message")


def test_unsupported_and_unsafe_downloads_rejected():
    with pytest.raises(ValueError, match="unsupported type"):
        download_text({"name": "spec.pdf"}, "secret")
    with pytest.raises(ValueError, match="URL"):
        download_text({"name": "spec.txt", "url_private": "https://evil.example/file"}, "secret")
    with pytest.raises(ValueError, match="limit"):
        download_text({"name": "spec.txt", "size": 2000000}, "secret")


def test_removing_attachment_from_edited_message(monkeypatch):
    monkeypatch.setattr("app.history.download_text", lambda *args: "Secret specification")
    s = Service(Store("sqlite://"), AI())
    backfill(s, Slack(), {"C": "atlas"})
    s.ingest("T", {"channel": "C", "subtype": "message_changed",
                   "message": {"ts": "1", "text": "Attachment removed", "files": []}}, "atlas")
    assert not s.store.all("file")
