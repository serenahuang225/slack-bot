"""Living source documentation and per-user successful-digest checkpoints.

Source capture is deterministic and automatic. AI summaries are cached on read,
so message ingestion does not depend on model availability.
"""
import hashlib
import time


class Knowledge:
    def __init__(self, service):
        self.service, self.store = service, service.store

    def refresh(self, team, channels):
        groups = {}
        for doc in self.service.documents(team, channels):
            # Same thread/file stays one knowledge entry regardless of chunk count.
            key = (doc.get("source_type", "thread"), doc["channel"],
                   doc["id"].rsplit(":", 1)[0] if doc.get("source_type") == "file" else doc["thread"])
            groups.setdefault(key, []).append(doc)
        current = set()
        for group in groups.values():
            first = group[0]
            content = "\n".join(d["text"] for d in group)
            raw = "\n".join(d.get("raw_text", d["text"]) for d in group)
            signature = hashlib.sha256(raw.encode()).hexdigest()
            entry = dict(first, team=team, text=content, raw_text=raw,
                         source_type=first.get("source_type", "thread"),
                         updated=max(d["updated"] for d in group), content_hash=signature)
            entry["context_limited"] = len(content) > 16000
            if entry["context_limited"]:
                entry["text"] = content[:3000] + "\n[Middle of long source omitted]\n" + content[-13000:]
            key = "knowledge:" + first["id"]
            current.add(key)
            old = self.store.get(key)
            if old != entry:
                self.store.put(key, "knowledge", entry)
        for old in self.store.all("knowledge"):
            if old["team"] == team and old["channel"] in channels and "knowledge:" + old["id"] not in current:
                self.store.delete("knowledge:" + old["id"])

    def entries(self, profile, channels, project=None):
        if project and project not in profile["projects"]:
            raise ValueError("That project is not in your profile. Use settings to update your projects.")
        self.refresh(profile["team"], channels)
        entries = [e for e in self.store.all("knowledge")
                   if e["team"] == profile["team"] and e["channel"] in channels
                   and e["project"] in profile["projects"] and (not project or e["project"] == project)]
        return sorted(entries, key=lambda e: (-e["updated"], e["id"]))

    def snapshot(self, profile, channels, entries=None):
        entries = self.entries(profile, channels) if entries is None else entries
        items = {}
        for entry in entries:
            entry = self.service.enrich(entry)
            signal = entry["signal"]
            signal = dict(signal, summary=self.service.names.text(profile["team"], signal["summary"]))
            for field in ("owner", "deadline"):
                if signal.get(field) is not None:
                    signal[field] = self.service.names.text(profile["team"], str(signal[field]))
            items[entry["id"]] = {
                "id": entry["id"], "content_hash": entry["content_hash"],
                "project": entry["project"], "channel": entry["channel"],
                "url": entry["url"], "updated": entry["updated"],
                "source_type": entry["source_type"], "context_limited": entry["context_limited"],
                **signal}
        visible_projects = {e["project"] for e in entries}
        phases = {p: self.store.get(f"phase:{profile['team']}:{p}", {"phase": "not set"})
                  for p in profile["projects"] if p in visible_projects}
        return {"at": time.time(), "items": items, "phases": phases}

    def baseline(self, profile):
        return self.store.get(f"digest_checkpoint:{profile['team']}:{profile['user']}")

    def mark_delivered(self, profile, snapshot, delivered_ids):
        # Called only AFTER Slack accepts the digest. Use the snapshot prepared
        # before sending, so new events during delivery remain new next time.
        previous = self.baseline(profile) or {"items": {}}
        items = dict(previous["items"])
        for key in delivered_ids:
            if key in snapshot["items"]:
                items[key] = snapshot["items"][key]
            else:
                items.pop(key, None)
        self.store.put(f"digest_checkpoint:{profile['team']}:{profile['user']}", "digest_checkpoint",
                       dict(snapshot, items=items, delivered_ids=list(delivered_ids), delivered_at=time.time()))

    def changes(self, profile, channels, snapshot=None):
        current = snapshot if snapshot is not None else self.snapshot(profile, channels)
        previous = self.baseline(profile)
        if not previous:
            return {"has_baseline": False, "since": None, "items": [], "phase_changes": []}
        result = []
        old_items = previous["items"]
        for key, entry in current["items"].items():
            old = old_items.get(key)
            kind = None
            if old is None:
                kind = "new"
            elif any(old.get(f) != entry.get(f) for f in ("summary", "type", "status", "owner", "deadline", "action", "dependency")):
                kind = "resolved" if old["status"] != "resolved" and entry["status"] == "resolved" else "reopened" if old["status"] == "resolved" and entry["status"] != "resolved" else "updated"
            if kind:
                result.append(dict(entry, change=kind))
        for key, old in old_items.items():
            if key not in current["items"] and old["channel"] in channels and old["project"] in profile["projects"]:
                # Do not repeat deleted source contents or disclose lost access.
                result.append({"id": key, "project": old["project"], "channel": old["channel"],
                               "change": "removed", "summary": "A previously indexed source was removed.",
                               "url": "", "source_type": old.get("source_type", "thread"),
                               "updated": current["at"], "owner": None, "deadline": None})
        phases = [{"project": p, "before": previous["phases"][p]["phase"], "after": data["phase"]}
                  for p, data in current["phases"].items()
                  if p in previous["phases"] and data != previous["phases"][p]]
        result.sort(key=lambda e: (-e["updated"], e["id"]))
        return {"has_baseline": True, "since": previous.get("delivered_at", previous["at"]),
                "items": result, "phase_changes": phases}

    def project_status(self, profile, channels, project):
        entries = self.entries(profile, channels, project)
        snap = self.snapshot(profile, channels, entries)
        issues = self.service.issues.current(profile, channels)
        items = [dict(i, **i["signal"]) for i in issues if i["project"] == project]
        items += [e for e in snap["items"].values() if e["source_type"] == "file"]
        return {"project": project, "phase": snap["phases"].get(project, {"phase": "not set"})["phase"],
                "source_count": len(items),
                "blockers": [e for e in items if e["source_type"] != "file" and e["type"] == "blocker" and e["status"] != "resolved"],
                "risks": [e for e in items if e["source_type"] != "file" and e["type"] == "risk" and e["status"] != "resolved"],
                "questions": [e for e in items if e["source_type"] != "file" and e["type"] == "question" and e["status"] != "resolved"],
                "decisions": [e for e in items if e["type"] == "decision"],
                "resolved": [e for e in items if e["status"] == "resolved"],
                "documents": [e for e in items if e["source_type"] == "file"]}
