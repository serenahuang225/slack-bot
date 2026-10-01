"""One-workspace Slack app. Public allowlisted project channels only."""
import json
import logging
import os
from datetime import datetime
from zoneinfo import ZoneInfo

from app.core import configured_service, relevance_words
from app.commands import (help_text, onboarding_values, onboarding_view, parse_command,
                          project_args, quick_setup, welcome_blocks)
from app.reports import changes_blocks, docs_blocks, section, status_blocks


def build_app():
    from slack_bolt import App
    service = configured_service()
    app = App(token=os.environ["SLACK_BOT_TOKEN"], signing_secret=os.getenv("SLACK_SIGNING_SECRET", ""))
    def lookup_name(user):
        from slack_sdk.errors import SlackApiError
        try:
            member = app.client.users_info(user=user)["user"]
            profile = member.get("profile", {})
            return (profile.get("display_name") or profile.get("real_name")
                    or member.get("real_name") or member.get("name"))
        except SlackApiError as exc:
            logging.warning("Name lookup unavailable: %s. Check users:read scope.", exc.response.get("error"))
            return None
    service.names.lookup = lookup_name
    mapping = json.loads(os.getenv("CHANNEL_PROJECTS", "{}"))
    admins = set(os.getenv("PROJECT_ADMIN_IDS", "").split(","))

    def allowed_channels(team, user):
        # Recheck membership for every response; fail closed on API failure.
        allowed = []
        for channel in mapping:
            info = app.client.conversations_info(channel=channel)["channel"]
            if info.get("is_private"):
                continue
            cursor = None
            while True:
                result = app.client.conversations_members(channel=channel, cursor=cursor, limit=200)
                if user in result["members"]:
                    allowed.append(channel)
                    break
                cursor = result.get("response_metadata", {}).get("next_cursor")
                if not cursor:
                    break
        return allowed

    def post_digest(profile):
        channels = allowed_channels(profile["team"], profile["user"])
        entries = service.knowledge.entries(profile, channels)
        snapshot = service.knowledge.snapshot(profile, channels, entries)
        changes = service.knowledge.changes(profile, channels, snapshot)
        items = service.digest(profile, channels, entries=entries)
        dm = app.client.conversations_open(users=profile["user"])["channel"]["id"]
        blocks = [{"type": "section", "text": {"type": "plain_text", "text": f"Your {profile['role']} digest · {', '.join(profile['projects'])}"}}]
        if snapshot["phases"]:
            blocks.append(section("Project phases: " + "; ".join(f"{p}: {v['phase']}" for p, v in snapshot["phases"].items())))
        for d in items:
            summary = service.names.text(profile["team"], d['signal']['summary'])
            detail = f"{d['change']} · {d['signal']['type'].upper()}: {summary}\nWhy you: {d['why']}"
            for field, label in [("action", "Next action (from source)"), ("dependency", "Depends on"), ("owner", "Owner"), ("deadline", "Due")]:
                if d['signal'].get(field):
                    detail += f"\n{label}: {d['signal'][field]}"
            if not d['signal'].get("action") and d['signal']['status'] != 'resolved':
                detail += "\nNext action: not specified in the sources."
            if d.get("context_limited"):
                detail += "\nLong evidence abbreviated; check original sources."
            blocks.append(section(service.names.text(profile["team"], detail)))
            urls = list(dict.fromkeys(s["url"] for s in reversed(d["sources"]) if s["url"]))[:3]
            elements = [{"type": "button", "text": {"type": "plain_text", "text": f"Source {i+1}"},
                         "url": url, "action_id": f"issue_source_{i}"} for i, url in enumerate(urls)]
            for label, action in [("Useful", "useful"), ("Less relevant", "irrelevant")]:
                elements.append({"type": "button", "text": {"type": "plain_text", "text": label}, "action_id": action, "value": d["id"]})
            blocks.append({"type": "actions", "elements": elements})
        if not items:
            blocks.append(section("No new relevant issues or open blockers/risks to highlight. Use status for the full current picture."))
        blocks.extend(changes_blocks(changes, compact=True))
        app.client.chat_postMessage(channel=dm, text="Your daily project digest", blocks=blocks)
        service.issues.mark_delivered(profile, items)
        shown = [source for d in items for source in d["source_ids"]]
        shown += [d["id"] for d in changes["items"][:3]]
        service.knowledge.mark_delivered(profile, snapshot, shown)

    def accessible_projects(team, user):
        return {mapping[c] for c in allowed_channels(team, user)}

    def send_plain(say, text):
        say(text="Digest assistant", blocks=[section(text)])

    @app.event("message")
    def message(event, body, say, logger):
        if event.get("bot_id") or event.get("subtype") == "bot_message":
            return
        team, user = body["team_id"], event.get("user")
        try:
            if event.get("channel_type") != "im":
                channel = event["channel"]
                if channel not in mapping:
                    return
                info = app.client.conversations_info(channel=channel)["channel"]
                if info.get("is_private"):
                    return
                msg = event.get("message", event)
                url = ""
                if event.get("subtype") != "message_deleted":
                    url = app.client.chat_getPermalink(channel=channel, message_ts=msg["ts"])["permalink"]
                service.ingest(team, event, mapping[channel], url)
                if msg.get("files"):
                    from app.history import import_files
                    report = {"files": 0, "warnings": []}
                    import_files(service, app.client, team, channel, msg, mapping[channel], report)
                    for warning in report["warnings"]:
                        logger.warning(warning)
                return
            # Only ordinary human DMs trigger commands; edits do not resend answers.
            if event.get("subtype") or not user:
                return
            text = event.get("text", "").strip()
            command, tail = parse_command(text)
            profile = service.store.get(f"user:{team}:{user}")
            if command == "help":
                send_plain(say, help_text(accessible_projects(team, user)))
                return
            if command in {"start", "settings"} or (command == "setup" and not tail) or not text:
                say(text="Set up your digest", blocks=welcome_blocks(accessible_projects(team, user), profile))
                return
            if command == "setup":
                role, projects, responsibilities = quick_setup(tail)
                available = accessible_projects(team, user)
                if not set(projects) <= available:
                    raise ValueError("Choose a project you can access: " + ", ".join(sorted(available)))
                service.profile(team, user, role, projects, responsibilities=responsibilities)
                send_plain(say, "Profile saved. Send keywords auto to suggest relevance terms, digest for updates, or help for all commands.")
                return
            if not profile:
                say(text="Welcome — let's set up your digest", blocks=welcome_blocks(accessible_projects(team, user)))
                return
            if command == "profile":
                focus = profile.get("focus", "")
                send_plain(say, f"Role: {profile['role']}\nProjects: {', '.join(profile['projects'])}\nResponsibilities: {profile.get('responsibilities') or 'not set'}\nFocus: {focus or 'none'}\nKeywords: {', '.join(profile.get('keywords', [])) or 'role defaults'}\nSend settings to edit.")
            elif command == "responsibilities":
                if not tail:
                    raise ValueError("Use responsibilities <what you own>, or responsibilities clear")
                service.profile(team, user, profile["role"], profile["projects"], responsibilities="" if tail.lower() == "clear" else tail)
                send_plain(say, "Responsibilities updated. Keywords now reflect your role and responsibilities. Send keywords auto for AI suggestions.")
            elif command == "keywords":
                if not tail:
                    raise ValueError("Use keywords <comma-separated terms> or keywords auto")
                if tail.lower() == "auto":
                    profile = service.suggest_profile_keywords(profile)
                else:
                    profile = dict(profile, keywords=sorted(relevance_words(tail))[:40])
                    service.store.put(f"user:{team}:{user}", "user", profile)
                send_plain(say, "Relevance keywords: " + ", ".join(profile["keywords"]))
            elif command == "focus":
                if not tail:
                    raise ValueError("Use focus <topic>, or focus clear")
                service.profile(team, user, profile["role"], profile["projects"], "" if tail.lower() == "clear" else tail)
                send_plain(say, "Focus cleared." if tail.lower() == "clear" else "Focus saved until you change or clear it.")
            elif command == "phase":
                if user not in admins:
                    raise ValueError("Only configured project admins can change shared phases.")
                main, _, keywords = tail.partition("|")
                project, _, phase = main.strip().partition(" ")
                if not phase or project not in accessible_projects(team, user):
                    raise ValueError("Use phase <accessible project> <phase name> | optional priority keywords")
                service.set_phase(team, project, phase, keywords)
                send_plain(say, "Project phase updated.")
            elif command == "digest":
                post_digest(profile)
            elif command == "changes":
                page = int(tail) if tail.isdigit() else 1
                if page < 1 or (tail and not tail.isdigit()):
                    raise ValueError("Use changes or changes <page number>")
                report = service.knowledge.changes(profile, allowed_channels(team, user))
                say(text="Changes since your last digest", blocks=changes_blocks(report, page), unfurl_links=False)
            elif command in {"status", "docs"}:
                project, page = project_args(tail, profile, page=command == "docs")
                channels = allowed_channels(team, user)
                if command == "status":
                    blocks = status_blocks(service.knowledge.project_status(profile, channels, project))
                else:
                    entries = service.knowledge.entries(profile, channels, project)
                    blocks = docs_blocks(project, service.knowledge.snapshot(profile, channels, entries), page)
                say(text="Project " + command, blocks=blocks, unfurl_links=False)
            else:
                from app.formatter import answer_blocks
                answer = service.ask_result(profile, allowed_channels(team, user), text)
                say(text="Answer to your project question", blocks=answer_blocks(answer),
                    unfurl_links=False, unfurl_media=False)
        except ValueError as exc:
            if event.get("channel_type") == "im":
                send_plain(say, str(exc))
        except Exception:
            logger.exception("Slack event failed")
            if event.get("channel_type") == "im":
                say(text="I couldn't complete that request. Check the local app log and retry.")

    @app.action("open_onboarding")
    def open_onboarding(ack, body, action, client):
        ack()
        # Options were access-filtered when the setup button was created. Avoid
        # remote lookups here: Slack's trigger expires after three seconds.
        projects = set(json.loads(action["value"])) & set(mapping.values())
        profile = service.store.get(f"user:{body['team']['id']}:{body['user']['id']}")
        if not projects:
            client.chat_postMessage(channel=body["user"]["id"], text="Join a configured project channel, then send start again.")
            return
        client.views_open(trigger_id=body["trigger_id"], view=onboarding_view(projects, profile))

    @app.view("save_onboarding")
    def save_onboarding(ack, body, view, client, logger):
        values, errors = onboarding_values(view, set(mapping.values()))
        if errors:
            ack(response_action="errors", errors=errors)
            return
        ack()
        team, user = body["team"]["id"], body["user"]["id"]
        try:
            if not set(values["projects"]) <= accessible_projects(team, user):
                client.chat_postMessage(channel=user, text="Your channel access changed. Send start and choose an accessible project.")
                return
            profile = service.profile(team, user, **values)
            note = ""
            try:
                profile = service.suggest_profile_keywords(profile)
            except Exception:
                logger.exception("Role suggestions failed; saved profile uses entered responsibilities")
                note = " AI keyword suggestions were unavailable; your entered responsibilities are still saved."
            client.chat_postMessage(channel=user, text="Profile saved", blocks=[section(
                f"Saved: {profile['role']} · {', '.join(profile['projects'])}\nKeywords: {', '.join(profile['keywords'])}\nSend digest, changes, status, docs or help." + note)])
        except Exception:
            logger.exception("Onboarding save failed")
            client.chat_postMessage(channel=user, text="I couldn't save your settings. Please send start to retry.")

    @app.action("source")
    def source(ack):
        ack()

    for index in range(3):
        app.action(f"issue_source_{index}")(source)

    @app.event("file_deleted")
    def file_deleted(event, body):
        channels = set()
        for file in service.store.all("file"):
            if file["team"] == body["team_id"] and file["file_id"] == event["file_id"]:
                channels.add(file["channel"])
                service.store.delete(file["id"])
        service.knowledge.refresh(body["team_id"], list(channels))

    def feedback(ack, body, action, respond):
        ack()
        team, user = body["team"]["id"], body["user"]["id"]
        doc_id = action["value"]
        profile = service.store.get(f"user:{team}:{user}")
        if not profile or doc_id not in {d["id"] for d in service.issues.current(profile, allowed_channels(team, user))}:
            respond("This source is no longer accessible.")
            return
        service.store.put(f"feedback:{team}:{user}:{doc_id}", "feedback", {"value": 1 if action["action_id"] == "useful" else -1})
        respond("Feedback saved for future digests.")

    app.action("useful")(feedback)
    app.action("irrelevant")(feedback)

    def daily():
        team = app.client.auth_test()["team_id"]
        date = datetime.now(ZoneInfo(os.getenv("DIGEST_TIMEZONE", "America/New_York"))).date().isoformat()
        for profile in service.store.all("user"):
            if profile["team"] != team:
                continue
            key = f"delivery:{team}:{profile['user']}:{date}"
            if service.store.get(key):
                continue
            try:
                post_digest(profile)
                service.store.put(key, "delivery", {"date": date})
            except Exception:
                logging.exception("Daily delivery failed for %s", profile["user"])
    return app, daily


def run():
    from apscheduler.schedulers.background import BackgroundScheduler
    from slack_bolt.adapter.socket_mode import SocketModeHandler
    app, daily = build_app()
    scheduler = BackgroundScheduler(timezone=os.getenv("DIGEST_TIMEZONE", "America/New_York"))
    scheduler.add_job(daily, "cron", hour=int(os.getenv("DIGEST_HOUR", "9")), minute=0, max_instances=1, coalesce=True)
    scheduler.start()
    try:
        SocketModeHandler(app, os.environ["SLACK_APP_TOKEN"]).start()
    finally:
        scheduler.shutdown(wait=False)
