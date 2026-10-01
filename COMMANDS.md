# Using the digest assistant

These are messages you send in a private DM with the bot, not slash commands. Channel discussion and supported uploads are the shared knowledge sources; bot DMs stay personal.

## Get started or update your profile

Send `start`. Click **Set up my digest**, enter your role, select projects, describe your responsibilities, and optionally set a current focus. Existing users send `settings` to edit the same form. The bot suggests relevance keywords from those responsibilities when Gemini is available; if that request fails, your profile is still saved with keywords from your own words. Send `profile` to review the saved result.

Roles are free text. The original mechanical, electrical, supply, manager and product roles are optional presets. You can enter “UX researcher,” “Customer success,” “Lab coordinator,” or another role without modifying code. Project phases are also free text. Other teams need their own configured channel-to-project mapping, not a different bot implementation.

The admin still installs the app, grants scopes, invites it to public source channels and configures `CHANNEL_PROJECTS`. Each user only needs a Slack account and membership in the relevant channels. No user API key or separate bot installation is required. The form offers accessible projects, and source permissions are checked again on every report or answer.

Quick setup remains available:

```text
setup mechanical atlas
setup "UX researcher" website | usability interviews, accessibility
responsibilities enclosure design, tolerance review, thermal testing
keywords auto
keywords thermal cooling enclosure assembly
focus supplier delivery
focus clear
```

The second example requires an admin-configured `website` project; it does not create a new project. Responsibilities and focus persist until you change or clear them. Quick setup preserves existing focus and responsibilities unless supplied explicitly. The settings form saves its entered values. Keywords are transparent, editable ranking terms, not an inferred job-title restriction.

## Living documentation

```text
docs atlas
docs atlas 2
```

Every ingested message, thread reply and supported file automatically refreshes a stored source entry in the project's documentation. Imported history is included. Related replies are grouped as one thread; document chunks are grouped as one document. Each entry keeps its original source link and a content fingerprint. No manually maintained web page is needed.

Opening `docs` generates or reuses concise summaries labeled by type and status, along with known owners and deadlines. Collection happens automatically during ingestion; AI summarization happens on demand, so a temporary model outage does not prevent source capture. New uploads are captured while the bot runs. Previously posted uploads require `digest backfill` from the terminal.

Supported file types remain UTF-8 TXT, MD, CSV/TSV, JSON, LOG, YAML and PY. PDF, Word, Excel, images and CAD are not parsed yet. Source summaries are derived from conversation, not authoritative engineering specifications. The bot does not overwrite original files or publish a separate document to another service. Cross-thread contradictions need human interpretation; sources remain linked for checking.

## Project status

```text
status atlas
get_project_status atlas
```

Shows phase, open blockers, risks, unanswered questions, decisions, resolved threads and reference documents. Owners/deadlines appear only when extracted from evidence. Both status and digests include older unresolved issues without an age cutoff. Matching [issue:your-id] tags link threads within one channel. Lack of a detected blocker is not proof that a project is unblocked. The overview shows up to two entries per category; use `docs atlas` and its pages for all entries.

## Changes since the last digest

```text
digest
changes
changes 2
get_changes_since_last_digest
What changed since my last digest?
```

After Slack accepts a digest, the bot records the source versions actually shown and the displayed project phases. `changes` compares current extracted fields against those versions, reporting new, updated, resolved, reopened and removed sources, plus phase changes. Unseen source changes remain pending; they may predate the most recent digest. Extracted-field comparison reduces acknowledgement noise, but model paraphrases can still cause false changes.

Your first digest establishes a baseline. Existing checkpoints are retained on upgrade, but historical omissions cannot be reconstructed. Separate per-issue version receipts begin with the first updated digest. Reading `changes`, `docs` or `status` does not advance it. A failed send does not advance it either. Sources from channels you no longer have access to are omitted. Removed sources are reported without repeating their deleted contents. Re-imported old history can appear as new knowledge when it was absent from the prior snapshot.

Daily and manual digests include a compact change summary (up to three items) plus the usual top five ranked updates. Only displayed source entries advance their checkpoints. Use changes and its pages to inspect pending entries; reading does not acknowledge them. Sources received during delivery remain new after the captured snapshot.

## Project phases

Configured admins can send:

```text
phase atlas validation
phase atlas production | manufacturing supplier shipment yield
phase website user research | interviews usability accessibility
```

Only admins listed in `PROJECT_ADMIN_IDS` can change a shared phase. Hardware presets remain convenient defaults, but any phase name and optional priority keywords are accepted. An unconfigured phase displays as “not set.”

## Discover commands

Send `help` for the complete in-Slack menu. Send any other question normally to use source-grounded RAG, such as `Why is testing blocked?` Use the existing Useful / Less relevant buttons to adjust individual issues' scores.

## Implementation notes

- `app/issues.py`: issue identity, current state and per-user delivered-version receipts.
- `app/knowledge.py`: materialized source documentation, snapshots, changes and project status.
- `app/commands.py`: command routing, help text and onboarding form.
- `app/reports.py`: compact source-linked Slack report layouts.
- `app/core.py`: custom profiles/keywords, custom phases and role-aware ranking.
- `app/slack.py`: command/action handlers and successful-delivery checkpointing.

Knowledge entries and digest checkpoints live in the existing local database as typed records. No new hosting account or Slack scopes are required for these features beyond the previously configured message/file/name access and interactivity. Restart the bot to load this update.

Long source summaries use the first 3,000 and last 13,000 characters when necessary, explicitly labeled as abbreviated; RAG still indexes the smaller source chunks. The system stores one principal signal per source, not a fully reconciled task graph. Source deletion events seen while running remove active documentation, but events missed while offline are not fully reconciled by history imports. Stored historical checkpoints/caches are not an automated retention policy. Run one bot/scheduler process: delivery and checkpoint storage are not a distributed exactly-once transaction.
