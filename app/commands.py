"""Discoverable DM commands and Slack onboarding form (no external calls)."""
import json
import shlex


def help_text(projects):
    return (
        "Commands — send these in a DM with me:\n"
        "• start / setup / settings — open your setup form\n"
        "• profile — show your role, projects, responsibilities and focus\n"
        "• setup mechanical atlas — quick setup; any role is accepted\n"
        '• setup "UX researcher" my-project | interviews, usability — custom role\n'
        "• responsibilities <what you own> — update your ongoing responsibilities\n"
        "• keywords <words> — set your relevance keywords; keywords auto suggests them\n"
        "• focus <topic> — prioritize until changed; focus clear removes it\n"
        "• digest — your personalized digest and a summary of what changed\n"
        "• changes — new, updated, resolved or removed sources since your last delivered digest\n"
        "• status <project> — current blockers, risks, decisions and known owners\n"
        "• docs <project> — living documentation from channel threads and supported uploads\n"
        "• docs <project> 2 / changes 2 — next page of results\n"
        "• phase <project> <phase> | optional keywords — admin-only; any phase name\n"
        "• help — this command list\n\n"
        "Aliases: get_project_status <project>, get_changes_since_last_digest.\n"
        "Or ask a normal question, such as ‘Why is testing blocked?’\n"
        "Supported uploads: TXT, MD, CSV/TSV, JSON, LOG, YAML and PY.\n"
        "Project choices: " + (", ".join(sorted(projects)) or "No accessible configured projects yet; ask your admin to map a channel.")
    )


def parse_command(text):
    clean = text.strip()
    normalized = clean.lower().rstrip("?.!")
    if normalized in {"commands", "what can you do", "what commands can i use"}:
        return "help", ""
    if normalized in {"what changed since my last digest", "what changed since the last digest", "get_changes_since_last_digest"}:
        return "changes", ""
    head, _, tail = clean.partition(" ")
    aliases = {"documentation": "docs", "get_project_status": "status", "get_changes_since_last_digest": "changes", "onboard": "start"}
    head = aliases.get(head.lower(), head.lower())
    commands = {"help", "start", "setup", "settings", "profile", "responsibilities", "keywords", "focus", "digest", "changes", "status", "docs", "phase"}
    return (head, tail.strip()) if head in commands else ("ask", clean)


def quick_setup(tail):
    main, sep, responsibilities = tail.partition("|")
    parts = shlex.split(main)
    if len(parts) < 2:
        raise ValueError('Use setup <role> <project>, e.g. setup "UX researcher" website | interviews, usability')
    return " ".join(parts[:-1]), parts[-1].split(","), responsibilities.strip() if sep else None


def project_args(tail, profile, page=False):
    parts = shlex.split(tail)
    number = 1
    if page and len(parts) >= 2 and parts[-1].isdigit():
        number = int(parts.pop())
    if not parts:
        if len(profile["projects"]) != 1:
            raise ValueError("Choose a project: " + ", ".join(profile["projects"]))
        project = profile["projects"][0]
    else:
        project = " ".join(parts)
    if number < 1:
        raise ValueError("Page numbers start at 1")
    return project, number


def welcome_blocks(projects, profile=None):
    return [
        {"type": "section", "text": {"type": "plain_text", "text":
            "Tell me your role, projects and responsibilities. Your role can be anything; I'll tailor your digests to what you own."}},
        {"type": "actions", "elements": [{"type": "button", "text": {"type": "plain_text", "text": "Edit my settings" if profile else "Set up my digest"},
            "action_id": "open_onboarding", "value": json.dumps(sorted(projects)[:100])}]},
        {"type": "context", "elements": [{"type": "plain_text", "text": "Send help for all commands. Source access still follows your channel memberships."}]}]


def onboarding_view(projects, profile=None):
    profile = profile or {}
    options = [{"text": {"type": "plain_text", "text": p[:75]}, "value": p} for p in sorted(projects)[:100]]
    if not options:
        raise ValueError("No accessible projects yet. Join a configured project channel, then send start again.")
    selection = {"type": "multi_static_select", "action_id": "value", "options": options}
    selected = [o for o in options if o["value"] in profile.get("projects", [])]
    if selected:
        selection["initial_options"] = selected
    blocks = []
    for key, label, limit in [("role", "Your role (any title)", 100), ("responsibilities", "What are you responsible for?", 1000), ("focus", "Current focus (until changed)", 500)]:
        element = {"type": "plain_text_input", "action_id": "value", "max_length": limit}
        if key == "responsibilities":
            element["multiline"] = True
        if profile.get(key):
            element["initial_value"] = profile[key]
        blocks.append({"type": "input", "block_id": key, "label": {"type": "plain_text", "text": label},
                       "optional": key != "role", "element": element})
    blocks.insert(1, {"type": "input", "block_id": "projects", "label": {"type": "plain_text", "text": "Your projects"}, "element": selection})
    return {"type": "modal", "callback_id": "save_onboarding", "title": {"type": "plain_text", "text": "Your digest settings"},
            "submit": {"type": "plain_text", "text": "Save"}, "close": {"type": "plain_text", "text": "Cancel"}, "blocks": blocks}


def onboarding_values(view, projects):
    values = view["state"]["values"]
    role = (values["role"]["value"].get("value") or "").strip()
    chosen = [o["value"] for o in values["projects"]["value"].get("selected_options", [])]
    responsibilities = (values["responsibilities"]["value"].get("value") or "").strip()
    focus = (values["focus"]["value"].get("value") or "").strip()
    errors = {}
    if not role or len(role) > 100:
        errors["role"] = "Enter your role (up to 100 characters)."
    if not chosen or not set(chosen) <= set(projects):
        errors["projects"] = "Choose at least one configured project."
    if len(responsibilities) > 1000:
        errors["responsibilities"] = "Use up to 1,000 characters."
    if len(focus) > 500:
        errors["focus"] = "Use up to 500 characters."
    return {"role": role, "projects": chosen, "responsibilities": responsibilities, "focus": focus}, errors
