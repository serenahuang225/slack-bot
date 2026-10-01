from app.formatter import answer_blocks
from app.core import AI, Service, Store
import time


def test_clickable_sources_with_safe_model_text():
    blocks = answer_blocks({"text": "Testing is blocked [1]. <!channel>", "sources": [
        {"number": 1, "url": "https://example.com/thread?a=1&b=2", "kind": "thread"}]})
    assert blocks[0]["text"]["type"] == "plain_text"
    assert blocks[1]["elements"][0]["text"] == "<https://example.com/thread?a=1&amp;b=2|[1] View thread>"
    assert blocks[1]["elements"][0]["type"] == "mrkdwn"


def test_unsafe_source_cannot_inject_markup():
    blocks = answer_blocks({"text": "Answer", "sources": [
        {"number": 1, "url": "https://example.com/|fake> <!channel>", "kind": "thread"}]})
    assert len(blocks) == 1


def test_only_used_citations_are_rendered():
    class CitingAI(AI):
        def answer(self, question, hits):
            assert len(hits) == 2
            return "Controller test failed [1]."
    s = Service(Store("sqlite://"), CitingAI())
    for i in range(2):
        s.ingest("T", {"channel": "C", "ts": str(time.time()+i), "text": f"Controller test {i}", "user": "U"}, "atlas", f"https://example.com/{i}")
    p = s.profile("T", "U", "electrical", ["atlas"])
    result = s.ask_result(p, ["C"], "controller test")
    assert len(result["sources"]) == 1
    assert result["sources"][0]["number"] == 1
