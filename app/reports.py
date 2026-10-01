"""Compact Slack views for documentation, status, and changes."""
from datetime import datetime, timezone

from app.formatter import answer_blocks


def section(text):
    return {"type": "section", "text": {"type": "plain_text", "text": text[:2900]}}


def source_blocks(entry, prefix=""):
    text = prefix + entry["summary"]
    details = []
    if entry.get("owner"):
        details.append("Owner: " + str(entry["owner"]))
    if entry.get("deadline"):
        details.append("Due: " + str(entry["deadline"]))
    if entry.get("context_limited"):
        details.append("Long source: some middle context omitted; check the original.")
    if details:
        text += "\n" + " · ".join(details)
    return answer_blocks({"text": text, "sources": [{"number": 1, "url": entry.get("url", ""),
        "kind": "file" if entry.get("source_type") == "file" else "thread"}]})


def docs_blocks(project, snapshot, page=1):
    entries = sorted(snapshot["items"].values(), key=lambda e: (-e["updated"], e["id"]))
    phase = snapshot["phases"].get(project, {"phase": "not set"})["phase"]
    blocks = [section(f"{project} documentation · phase: {phase}\n{len(entries)} source entries. Automatically collected from channel threads and supported uploads; summaries are AI-derived.")]
    start = (page - 1) * 8
    if not entries:
        return blocks + [section("No accessible sources yet. Post in a configured channel or import its history.")]
    if start >= len(entries):
        return blocks + [section("No entries on this page. Start with docs " + project)]
    for entry in entries[start:start+8]:
        prefix = f"{entry['source_type'].upper()} · {entry['type']} · {entry['status']}\n"
        blocks.extend(source_blocks(entry, prefix))
    blocks.append(section(f"Page {page} · showing {start+1}–{min(start+8, len(entries))} of {len(entries)}" + (f"\nNext: docs {project} {page+1}" if start+8 < len(entries) else "")))
    return blocks


def status_blocks(status):
    blocks = [section(f"{status['project']} status · phase: {status['phase']}\nBased on {status['source_count']} accessible issue/document records. Status is extracted from discussion, not an independently verified project plan.")]
    groups = [("Open blockers", "blockers"), ("Open risks", "risks"), ("Open questions", "questions"), ("Decisions", "decisions"), ("Resolved", "resolved"), ("Reference documents", "documents")]
    for label, key in groups:
        entries = status[key]
        if not entries:
            continue
        blocks.append(section(f"{label} ({len(entries)})"))
        for entry in entries[:2]:
            blocks.extend(source_blocks(entry))
    if not status["source_count"]:
        blocks.append(section("No accessible project sources yet."))
    elif not status["blockers"]:
        blocks.append(section("No open blockers identified in the available sources. This is not a guarantee that the project is unblocked."))
    blocks.append(section(f"Showing up to two entries per category. Use docs {status['project']} to browse every source."))
    return blocks


def changes_blocks(changes, page=1, compact=False):
    if not changes["has_baseline"]:
        return [section("No previous digest checkpoint yet. Your next successfully delivered digest will establish one.")]
    since = datetime.fromtimestamp(changes["since"], timezone.utc).strftime("%b %d, %H:%M UTC")
    entries = changes["items"]
    phases = changes["phase_changes"]
    blocks = [section(f"Pending changes · last digest {since}\n{len(entries)} source changes · {len(phases)} phase changes\nIncludes earlier changes not yet shown in a digest.")]
    if not entries and not phases:
        return blocks + [section("No changes in your accessible project sources since that digest.")]
    if page == 1 and phases:
        blocks.append(section("\n".join(f"{p['project']}: {p['before']} → {p['after']}" for p in phases)))
    size = 3 if compact else 8
    start = (page-1) * size
    for entry in entries[start:start+size]:
        blocks.extend(source_blocks(entry, f"{entry['change'].upper()} · {entry['project']}\n"))
    if len(entries) > start+size:
        blocks.append(section(f"Showing {start+1}–{start+size} of {len(entries)}. " + ("Use docs <project> to browse current source details." if compact else f"Next: changes {page+1}")))
    if start >= len(entries) and entries:
        blocks.append(section("No source changes on this page. Send changes to start again."))
    return blocks
