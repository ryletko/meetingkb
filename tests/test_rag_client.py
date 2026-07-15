from meetingkb.rag.client import LLMConfig, OpenAICompatibleClient


def test_chat_posts_and_returns_content(monkeypatch):
    class _Resp:
        ok = True
        def json(self): return {"choices": [{"message": {"content": " hi "}}]}
        def raise_for_status(self): pass
    import meetingkb.rag.client as mod
    monkeypatch.setattr(mod.requests, "post", lambda *a, **k: _Resp())
    client = OpenAICompatibleClient(LLMConfig(base_url="http://x/v1", model="m"))
    assert client.chat([{"role": "user", "content": "hello"}]) == "hi"
