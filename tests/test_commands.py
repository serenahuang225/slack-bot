from app.commands import help_text, onboarding_values, onboarding_view, parse_command, quick_setup
from app.reports import docs_blocks, changes_blocks


def test_command_aliases_and_free_text_roles():
    assert parse_command("get_changes_since_last_digest") == ("changes", "")
    assert parse_command("get_project_status atlas") == ("status", "atlas")
    assert parse_command("What changed since my last digest?") == ("changes", "")
    assert parse_command("Why is the controller hot?")[0] == "ask"
    assert quick_setup('"UX researcher" website | interviews, usability') == ("UX researcher", ["website"], "interviews, usability")
    assert "docs <project>" in help_text(["atlas"])


def test_onboarding_freeform_role_and_validated_projects():
    view = onboarding_view(["atlas"], {"role": "Technical writer", "projects": ["atlas"]})
    assert view["blocks"][0]["element"]["type"] == "plain_text_input"
    submitted = {"state": {"values": {
        "role": {"value": {"value": "Technical writer"}},
        "projects": {"value": {"selected_options": [{"value": "atlas"}]}},
        "responsibilities": {"value": {"value": "Documentation"}},
        "focus": {"value": {"value": None}},
    }}}
    values, errors = onboarding_values(submitted, ["atlas"])
    assert not errors and values["role"] == "Technical writer"
    assert onboarding_values(submitted, ["other"])[1]["projects"]


def test_reports_page_without_exceeding_slack_limits():
    entries = {str(i): {"id": str(i), "updated": i, "summary": "Test result", "source_type": "thread",
                       "type": "update", "status": "open", "url": "https://example.com/source"} for i in range(20)}
    blocks = docs_blocks("atlas", {"items": entries, "phases": {}}, page=2)
    assert len(blocks) < 50 and "Page 2" in blocks[-1]["text"]["text"]
    assert "No previous digest" in changes_blocks({"has_baseline": False})[0]["text"]["text"]
