import argparse
import time
import json
import os
from app.core import AI, Service, Store, configured_service


def demo():
    service = Service(Store("sqlite://"), AI())
    samples = [
        ("hardware", "Maya", "Enclosure CAD tolerance decision: approved aluminum material for the prototype."),
        ("hardware", "Alex", "Motor controller failed thermal test. Validation is blocked pending retest."),
        ("supply", "Jordan", "Supplier risk: encoder lead time delayed from 3 to 8 weeks. Shipment order at risk."),
        ("hardware", "Sam", "Customer requirement decision: launch needs quieter actuator operation."),
        ("hardware", "Alex", "PCB voltage test passed. Power rail stable at 12V."),
        ("hardware", "Maya", "Milestone deadline Friday: integration blocked; owner Maya needs enclosure signoff."),
    ]
    for i, (channel, user, text) in enumerate(samples):
        service.ingest("demo", {"channel": channel, "ts": str(time.time() + i/100), "user": user, "text": text}, "atlas")
    for role in ["mechanical", "supply", "manager"]:
        profile = service.profile("demo", role, role, ["atlas"])
        print(f"\n{role.upper()} DIGEST (offline demo)")
        for item in service.digest(profile, ["hardware", "supply"]):
            print(f"- {item['signal']['summary']}\n  Score {item['score']:.1f}: {item['why']}")
    print("\nRAG / RETRIEVAL DEMO")
    print(service.ask(profile, ["hardware", "supply"], "encoder supplier lead time"))


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("command", choices=["demo", "init", "slack", "send-daily", "backfill", "reindex", "search"])
    parser.add_argument("--limit", type=int, default=500, help="Maximum channel history messages per channel for backfill")
    parser.add_argument("--question", help="Query for the local search diagnostic; does not post to Slack")
    parser.add_argument("--user", help="Registered Slack user ID for local search")
    args = parser.parse_args()
    if args.command == "demo":
        demo()
    elif args.command == "init":
        configured_service()
        print("Database initialized.")
    elif args.command == "backfill":
        from app.history import configured_backfill
        service = configured_service()
        print(json.dumps(configured_backfill(service, args.limit), indent=2))
    elif args.command == "reindex":
        service = configured_service()
        mapping = json.loads(os.getenv("CHANNEL_PROJECTS", "{}"))
        if not mapping:
            parser.error("Configure CHANNEL_PROJECTS first")
        teams = sorted({m["team"] for m in service.store.all("message") if m["channel"] in mapping})
        if not teams:
            print("No messages to index. Run digest backfill first.")
        for team in teams:
            result = service.reindex(team, list(mapping), list(set(mapping.values())))
            print(json.dumps({"team": team, "backend": service.vector_index.backend, **result}), flush=True)
    elif args.command == "search":
        if not args.question or not args.user:
            parser.error("search requires --question and --user")
        service = configured_service()
        profiles = [p for p in service.store.all("user") if p["user"] == args.user]
        if len(profiles) != 1:
            parser.error("Expected one matching registered Slack profile")
        # Match Slack's live permission check; never use the configured channel
        # list alone as evidence that the selected user has access.
        from slack_sdk import WebClient
        client = WebClient(token=os.environ["SLACK_BOT_TOKEN"])
        profile = profiles[0]
        if client.auth_test()["team_id"] != profile["team"]:
            parser.error("Profile workspace does not match bot workspace")
        channels = []
        for channel in json.loads(os.getenv("CHANNEL_PROJECTS", "{}")):
            info = client.conversations_info(channel=channel)["channel"]
            if info.get("is_private"):
                continue
            cursor = None
            while True:
                page = client.conversations_members(channel=channel, cursor=cursor, limit=200)
                if profile["user"] in page["members"]:
                    channels.append(channel)
                    break
                cursor = page.get("response_metadata", {}).get("next_cursor")
                if not cursor:
                    break
        hits = service.retrieve(profile, channels, args.question)
        print(json.dumps([{"source": d["url"], "similarity": round(d["similarity"], 3),
                           "keyword_score": round(d["keyword_score"], 3)} for d in hits], indent=2))
    elif args.command == "slack":
        from app.slack import run
        run()
    else:
        from app.slack import build_app
        _, daily = build_app()
        daily()


if __name__ == "__main__":
    main()
