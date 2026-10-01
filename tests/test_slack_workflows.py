"""Exercise actual registered Slack handlers with no network or real messages."""
import logging
import time

from app.core import AI, Service, Store


class Client:
    def __init__(self):
        self.sent = []
        self.fail_send = False
        self.views = []

    def conversations_info(self, **kwargs):
        return {"channel": {"is_private": False, "is_member": True}}

    def conversations_members(self, **kwargs):
        return {"members": ["U"]}

    def conversations_open(self, **kwargs):
        return {"channel": {"id": "D"}}

    def chat_postMessage(self, **kwargs):
        if self.fail_send:
            raise RuntimeError("simulated Slack send failure")
        self.sent.append(kwargs)
        return {"ok": True, "ts": "1"}

    def views_open(self, **kwargs):
        self.views.append(kwargs)


class App:
    def __init__(self, **kwargs):
        self.client = Client()
        self.handlers = {}

    def register(self, name):
        def decorator(fn):
            self.handlers[name] = fn
            return fn
        return decorator

    event = action = view = register


def setup(monkeypatch):
    import slack_bolt
    import app.slack
    service = Service(Store("sqlite://"), AI())
    monkeypatch.setattr(slack_bolt, "App", App)
    monkeypatch.setattr(app.slack, "configured_service", lambda: service)
    monkeypatch.setenv("SLACK_BOT_TOKEN", "fake")
    monkeypatch.setenv("CHANNEL_PROJECTS", '{"C":"atlas"}')
    monkeypatch.setenv("PROJECT_ADMIN_IDS", "U")
    bot, _ = app.slack.build_app()
    service.profile("T", "U", "mechanical", ["atlas"])
    service.ingest("T", {"channel": "C", "ts": str(time.time()), "user": "U", "text": "Thermal test failed"}, "atlas", "https://example.com/source")
    return service, bot


def dm(bot, text):
    replies = []
    bot.handlers["message"]({"channel_type": "im", "channel": "D", "user": "U", "text": text},
                            {"team_id": "T"}, lambda **kw: replies.append(kw), logging.getLogger("test"))
    return replies


def test_failed_slack_send_does_not_advance_changes(monkeypatch):
    service, bot = setup(monkeypatch)
    profile = service.store.get("user:T:U")
    bot.client.fail_send = True
    dm(bot, "digest")
    assert service.knowledge.baseline(profile) is None
    assert service.store.all("issue_receipt") == []
    bot.client.fail_send = False
    dm(bot, "digest")
    assert service.knowledge.baseline(profile)
    assert bot.client.sent
    assert service.store.all("issue_receipt")
    assert "Why you:" in str(bot.client.sent)
    assert "not specified in the sources" in str(bot.client.sent)


def test_help_docs_status_changes_and_settings_handlers(monkeypatch):
    service, bot = setup(monkeypatch)
    for command in ["help", "docs atlas", "get_project_status atlas", "get_changes_since_last_digest", "settings", "profile"]:
        reply = dm(bot, command)
        assert reply and "blocks" in reply[0]
        assert "couldn't complete" not in str(reply)
    dm(bot, 'setup "Technical writer" atlas | documentation and training')
    assert service.store.get("user:T:U")["role"] == "Technical writer"
    dm(bot, "phase atlas user research | interviews")
    assert service.store.get("phase:T:atlas")["phase"] == "user research"


def test_onboarding_button_and_submission(monkeypatch):
    service, bot = setup(monkeypatch)
    acknowledged = []
    body = {"team": {"id": "T"}, "user": {"id": "U"}, "trigger_id": "trigger"}
    bot.handlers["open_onboarding"](lambda **kw: acknowledged.append(kw), body,
                                    {"value": '["atlas"]'}, bot.client)
    assert acknowledged and bot.client.views
    values = {"role": {"value": {"value": "Designer"}},
              "projects": {"value": {"selected_options": [{"value": "atlas"}]}},
              "responsibilities": {"value": {"value": "usability research"}},
              "focus": {"value": {"value": "interviews"}}}
    bot.handlers["save_onboarding"](lambda **kw: acknowledged.append(kw), body,
        {"state": {"values": values}}, bot.client, logging.getLogger("test"))
    assert service.store.get("user:T:U")["role"] == "Designer"
    assert "usability" in service.store.get("user:T:U")["keywords"]


def test_onboarding_saves_even_when_ai_suggestions_fail(monkeypatch):
    service, bot = setup(monkeypatch)
    def fail(*args):
        raise RuntimeError("Model temporarily unavailable")
    monkeypatch.setattr(service.ai, "role_keywords", fail)
    body = {"team": {"id": "T"}, "user": {"id": "U"}}
    values = {"role": {"value": {"value": "Researcher"}},
              "projects": {"value": {"selected_options": [{"value": "atlas"}]}},
              "responsibilities": {"value": {"value": "interviews"}},
              "focus": {"value": {"value": None}}}
    bot.handlers["save_onboarding"](lambda **kw: None, body, {"state": {"values": values}},
                                    bot.client, logging.getLogger("test"))
    profile = service.store.get("user:T:U")
    assert profile["role"] == "Researcher" and "interviews" in profile["keywords"]
    assert "unavailable" in str(bot.client.sent[-1])
