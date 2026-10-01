"""Evidence-backed current issues and per-recipient version receipts.

Explicit issue tags merge threads within a channel, never across access scopes.
Records are rebuilt from live sources so deleted evidence cannot remain active.
"""
import hashlib
import json
import re
import time


class Issues:
    def __init__(self, service):
        self.service, self.store = service, service.store

    def current(self, profile, channels, entries=None):
        entries = self.service.knowledge.entries(profile, channels) if entries is None else entries
        groups = {}
        for entry in entries:
            if (entry.get("source_type") == "file" or entry.get("team") != profile["team"]
                    or entry["channel"] not in channels or entry["project"] not in profile["projects"]):
                continue
            tags = set(re.findall(r"\[issue:([a-zA-Z0-9_-]{1,64})\]", entry["text"]))
            # Ambiguous multi-issue threads remain separate, rather than guessing.
            identity = "tag:" + next(iter(tags)).lower() if len(tags) == 1 else "thread:" + entry["thread"]
            key = ":".join([profile["team"], entry["project"], entry["channel"], identity])
            groups.setdefault(key, []).append(entry)
        result = []
        for key, sources in groups.items():
            sources.sort(key=lambda d: (d["updated"], d["id"]))
            latest = sources[-1]
            text = "\n".join(s["text"] for s in sources)
            if len(sources) > 1:
                threads = {s["thread"] for s in sources}
                messages = [m for m in self.store.all("message")
                            if m["team"] == profile["team"] and m["channel"] == latest["channel"]
                            and m["thread"] in threads and m["project"] == latest["project"]]
                messages.sort(key=lambda m: (float(m["ts"]), m["changed"]))
                text = self.service.names.text(profile["team"], "\n".join(f"{m['user']}: {m['text']}" for m in messages))
            limited = len(text) > 16000 or any(s.get("context_limited") for s in sources)
            if len(text) > 16000:
                text = text[:3000] + "\n[Middle omitted]\n" + text[-13000:]
            issue_id = "issue:" + hashlib.sha256(key.encode()).hexdigest()[:32]
            doc = dict(latest, id=issue_id, text=text, raw_text="\n".join(s.get("raw_text", s["text"]) for s in sources), context_limited=limited)
            signal = self.service.enrich(doc)["signal"]
            version = hashlib.sha256(json.dumps(signal, sort_keys=True).encode()).hexdigest()
            issue = dict(doc, signal=signal, version=version,
                         source_ids=[s["id"] for s in sources],
                         sources=[{"id": s["id"], "url": s["url"]} for s in sources],
                         issue_key=key)
            self.store.put(issue_id, "issue", issue)
            result.append(issue)
        active = {i["id"] for i in result}
        for old in self.store.all("issue"):
            if (old["team"] == profile["team"] and old["channel"] in channels
                    and old["project"] in profile["projects"] and old["id"] not in active):
                self.store.delete(old["id"])
        return result

    def receipt(self, profile, issue):
        return self.store.get(f"issue_receipt:{profile['team']}:{profile['user']}:{issue['id']}")

    def context(self, profile, issue):
        phase = self.store.get(f"phase:{profile['team']}:{issue['project']}", {"phase": "not set"})
        data = {k: profile.get(k) for k in ("role", "responsibilities", "focus", "keywords")}
        return hashlib.sha256(json.dumps([data, phase], sort_keys=True).encode()).hexdigest()

    def mark_delivered(self, profile, issues):
        # Save only the exact versions actually sent, never the whole candidate set.
        for issue in issues:
            self.store.put(f"issue_receipt:{profile['team']}:{profile['user']}:{issue['id']}",
                           "issue_receipt", {"version": issue["version"],
                           "context": issue.get("delivery_context", self.context(profile, issue)),
                           "status": issue["signal"]["status"], "at": time.time()})
