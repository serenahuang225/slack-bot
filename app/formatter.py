"""Render answers with trusted clickable links and non-interpreted model text."""
from urllib.parse import urlsplit


def answer_blocks(result):
    text = result["text"] or "I couldn't find an answer in the available sources."
    blocks = [{"type": "section", "text": {"type": "plain_text", "text": text[i:i+2900]}}
              for i in range(0, min(len(text), 29000), 2900)]
    links = []
    for source in result["sources"]:
        url = source["url"]
        # Only stored source URLs become markup. Model text remains plain text,
        # so it cannot mention users or inject Slack links.
        if not url or any(c.isspace() or c in "<>|" for c in url):
            continue
        try:
            parsed = urlsplit(url)
            if parsed.scheme != "https" or not parsed.hostname or parsed.username:
                continue
        except ValueError:
            continue
        safe_url = url.replace("&", "&amp;")
        links.append(f"<{safe_url}|[{source['number']}] View {source['kind']}>")
    if links:
        blocks.append({"type": "context", "elements": [
            {"type": "mrkdwn", "text": " · ".join(links), "verbatim": True}]})
    return blocks
