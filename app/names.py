"""Workspace-scoped Slack names, cached to avoid repeated API requests."""
import re
import time

USER_ID = re.compile(r"\b[UW][A-Z0-9]{8,}\b")
MENTION = re.compile(r"<@([UW][A-Z0-9]+)(?:\|[^>]+)?>")


class Names:
    def __init__(self, store, lookup=None):
        self.store, self.lookup = store, lookup
        self.attempted = {}

    def get(self, team, user):
        if not USER_ID.fullmatch(user):
            return user
        key = f"name:{team}:{user}"
        cached = self.store.get(key)
        now = time.time()
        if self.lookup and (not cached or now - cached.get("checked", 0) > 86400) and now - self.attempted.get(key, 0) > 300:
            self.attempted[key] = now
            name = self.lookup(user)
            if name:
                cached = {"name": name, "checked": now}
                self.store.put(key, "name", cached)
        return cached["name"] if cached else user

    def text(self, team, text):
        # Convert mentions first and avoid rewriting characters inside URLs.
        text = MENTION.sub(lambda m: self.get(team, m[1]), text)
        return re.sub(r"https?://\S+|\b[UW][A-Z0-9]{8,}\b",
                      lambda m: m[0] if m[0].startswith("http") else self.get(team, m[0]), text)
