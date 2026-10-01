"""Read-only Slack history import and bounded text attachment extraction."""
import json
import os
from pathlib import PurePosixPath
from urllib.parse import urlparse

import requests
from slack_sdk import WebClient
from slack_sdk.errors import SlackApiError

TEXT_EXTENSIONS = {".txt", ".md", ".csv", ".tsv", ".json", ".log", ".yaml", ".yml", ".py"}
MAX_BYTES = 1024 * 1024
MAX_CHARS = 60000


def download_text(file, token):
    name = file.get("name", "")
    if PurePosixPath(name).suffix.lower() not in TEXT_EXTENSIONS:
        raise ValueError("unsupported type (supported: TXT, MD, CSV, TSV, JSON, LOG, YAML, PY)")
    if file.get("size", 0) > MAX_BYTES:
        raise ValueError("file exceeds 1 MiB limit")
    url = file.get("url_private_download") or file.get("url_private", "")
    parsed = urlparse(url)
    if parsed.scheme != "https" or parsed.hostname != "files.slack.com" or parsed.username or parsed.port not in (None, 443):
        raise ValueError("not a supported Slack-hosted download URL")
    # Never forward the bearer token to an arbitrary host or redirect target.
    with requests.get(url, headers={"Authorization": f"Bearer {token}"}, timeout=20,
                      allow_redirects=False, stream=True) as response:
        if response.status_code != 200:
            raise ValueError(f"download returned HTTP {response.status_code}")
        if "text/html" in response.headers.get("Content-Type", ""):
            raise ValueError("download returned HTML rather than file contents")
        data = bytearray()
        for chunk in response.iter_content(16384):
            data.extend(chunk)
            if len(data) > MAX_BYTES:
                raise ValueError("file exceeds 1 MiB limit")
    text = data.decode("utf-8-sig")
    if "\x00" in text:
        raise ValueError("binary content is unsupported")
    if len(text) > MAX_CHARS:
        raise ValueError("file exceeds 60,000 character limit")
    return text


def import_files(service, client, team, channel, message, project, report):
    for attachment in message.get("files", []):
        file_id = attachment.get("id")
        if not file_id:
            continue
        key = f"file:{team}:{channel}:{message['ts']}:{file_id}"
        try:
            file = client.files_info(file=file_id)["file"]
            text = download_text(file, client.token)
            service.store.put(key, "file", {
                "id": key, "file_id": file_id, "team": team, "channel": channel,
                "project": project, "message_ts": message["ts"],
                "name": file.get("name", file_id), "text": text,
                "url": file.get("permalink", ""),
                "updated": float(file.get("updated", file.get("created", message["ts"])))})
            report["files"] += 1
        except (SlackApiError, requests.RequestException, ValueError, UnicodeError) as exc:
            # Remove old extracted text if the current source is unavailable/unsupported.
            service.store.delete(key)
            reason = exc.response.get("error", "Slack API error") if isinstance(exc, SlackApiError) else type(exc).__name__ if isinstance(exc, requests.RequestException) else str(exc)
            report["warnings"].append(f"File {file_id}: {reason}")
    service.knowledge.refresh(team, [channel])


def ingest_message(service, client, team, channel, message, project, report):
    if message.get("bot_id") or message.get("subtype") not in (None, "file_share", "thread_broadcast"):
        return
    url = client.chat_getPermalink(channel=channel, message_ts=message["ts"])["permalink"]
    service.ingest(team, dict(message, channel=channel), project, url)
    report["messages"] += 1
    import_files(service, client, team, channel, message, project, report)


def backfill(service, client, mapping, limit=500):
    if not mapping or limit < 1:
        raise ValueError("Configure CHANNEL_PROJECTS and use a positive --limit")
    team = client.auth_test()["team_id"]
    report = {"messages": 0, "files": 0, "warnings": []}
    for channel, project in mapping.items():
        try:
            info = client.conversations_info(channel=channel)["channel"]
            if info.get("is_private") or not info.get("is_member"):
                report["warnings"].append(f"{channel}: invite the bot to this public channel first")
                continue
            cursor, count, seen_threads = None, 0, set()
            while True:
                page = client.conversations_history(channel=channel, cursor=cursor, limit=min(100, limit-count))
                for message in page["messages"]:
                    if count >= limit:
                        break
                    ingest_message(service, client, team, channel, message, project, report)
                    count += 1
                    root = message.get("thread_ts", message["ts"])
                    if message.get("reply_count", 0) and root not in seen_threads:
                        seen_threads.add(root)
                        reply_cursor, replies_read = None, 0
                        try:
                            while True:
                                replies = client.conversations_replies(channel=channel, ts=root, cursor=reply_cursor, limit=100)
                                for reply in replies["messages"]:
                                    if reply["ts"] != message["ts"]:
                                        ingest_message(service, client, team, channel, reply, project, report)
                                    replies_read += 1
                                reply_cursor = replies.get("response_metadata", {}).get("next_cursor")
                                if not reply_cursor:
                                    break
                                if replies_read >= limit:
                                    report["warnings"].append(f"{channel} thread {root}: reply limit reached; increase --limit")
                                    break
                        except SlackApiError as exc:
                            report["warnings"].append(f"{channel} thread {root}: {exc.response.get('error')}; replies incomplete")
                cursor = page.get("response_metadata", {}).get("next_cursor")
                if not cursor:
                    break
                if count >= limit:
                    report["warnings"].append(f"{channel}: history limit reached; increase --limit")
                    break
        except SlackApiError as exc:
            error = exc.response.get("error", "unknown_error")
            report["warnings"].append(f"{channel}: {error}; partial import saved. Fix permissions or retry later if rate-limited.")
    return report


def configured_backfill(service, limit):
    client = WebClient(token=os.environ["SLACK_BOT_TOKEN"])
    return backfill(service, client, json.loads(os.getenv("CHANNEL_PROJECTS", "{}")), limit)
