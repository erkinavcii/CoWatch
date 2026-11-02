import asyncio
import dataclasses
import json
import re
import time

import httpx
import pytest
from fastapi.testclient import TestClient

from server import config, main, translate
from server.config import get_settings
from server.main import app
from server.translate import TranslateError, from_line, parse_lines, to_line

KEY = "test-key"
HOST = {"base_url": "http://localhost:8000", "cookies": {"cw_key": KEY}, "client": ("127.0.0.1", 5)}
FRIEND = {"base_url": "http://pc.tail1234.ts.net", "cookies": {"cw_key": KEY}, "client": ("127.0.0.1", 5),
          "headers": {"Tailscale-User-Login": "friend@example.com"}}


def cues(n):
    return [(float(i), i + 0.9, f"Line {i + 1}" + ("\nsecond" if i % 5 == 0 else "")) for i in range(n)]


class FakeModel:
    """Answers like a model would: a brief first, then every numbered line it was given, in "Turkish"."""

    def __init__(self, drop_once=()):
        self.prompts = []
        self.drop_once = set(drop_once)

    async def complete(self, system, prompt):
        self.prompts.append(prompt)
        if prompt.startswith("Below are the subtitles"):
            return "Summary: a test.\nCharacters: none."
        lines = prompt.split("Lines to translate:\n", 1)[1].splitlines()
        out = []
        for line in lines:
            number, text = re.match(r"#(\d+) (.*)", line).groups()
            if int(number) in self.drop_once:
                self.drop_once.discard(int(number))
                continue
            out.append(f"#{number} TR {text}")
        return "```\n" + "\n".join(out) + "\n```"  # fences are left out when reading


def test_lines_go_out_numbered_and_come_back_with_their_breaks():
    assert to_line("Home.\r\n  It's   late. ") == "Home.<br>It's late."
    assert from_line("Eve.<br/>Geç oldu. ") == "Eve.\nGeç oldu."
    answer = "<think>planning</think>\n#1 Bir\n#2: İki\nnote: done\n#9 not asked\n#3 "
    assert parse_lines(answer, {1, 2, 3}) == {1: "Bir", 2: "İki"}  # #3 is empty: missing


def test_two_passes_chunks_with_context_and_a_retry_for_missing_lines(monkeypatch):
    monkeypatch.setattr(translate, "CHUNK", 10)
    model = FakeModel(drop_once={4, 17})
    steps = []

    async def progress(done, total):
        steps.append((done, total))

    result = asyncio.run(translate.translate(model, cues(25), "en", "tr", title="Test", progress=progress))
    assert [text for _, _, text in result.cues][:2] == ["TR Line 1\nsecond", "TR Line 2"]
    assert all(text.startswith("TR ") for _, _, text in result.cues) and result.missing == 0
    assert [c[:2] for c in result.cues] == [c[:2] for c in cues(25)]  # the times are untouched
    assert steps[-1] == (4, 4) and len(steps) == 4  # the brief and three chunks
    brief, *chunk_prompts = model.prompts
    assert '"Test"' in brief and "Turkish" in brief and "#25 Line 25" in brief
    assert all("Summary: a test." in p and '"sen" or "siz"' in p for p in chunk_prompts)
    second = next(p for p in chunk_prompts if "#11 Line 11" in p.split("Lines to translate:")[1])
    assert "#10 Line 10" in second.split("Lines to translate:")[0]  # the lines before, as context only
    retries = [p for p in chunk_prompts if p.split("Lines to translate:\n")[1].count("\n") == 0]
    assert len(retries) == 2  # one line asked again in each of two chunks


def test_a_known_brief_skips_the_first_pass_and_too_many_missing_lines_fail():
    model = FakeModel()
    asyncio.run(translate.translate(model, cues(3), "en", "ru", brief="known"))
    assert len(model.prompts) == 1 and "known" in model.prompts[0] and "ты" in model.prompts[0]

    class Silent:
        async def complete(self, system, prompt):
            return "Sorry."

    with pytest.raises(TranslateError) as info:
        asyncio.run(translate.translate(Silent(), cues(10), "en", "tr", brief="x"))
    assert info.value.code == "ai_bad_output"
    with pytest.raises(TranslateError) as info:
        asyncio.run(translate.translate(Silent(), [], "en", "tr"))
    assert info.value.code == "ai_empty"


def test_openai_compatible_requests_models_and_errors(monkeypatch):
    seen = []

    def handler(request):
        seen.append(request)
        if request.url.path.endswith("/models"):
            return httpx.Response(200, json={"data": [{"id": "deepseek-v4-pro"}, {"id": "deepseek-flash"}]})
        if request.headers.get("authorization") == "Bearer bad":
            return httpx.Response(401, json={"error": "no"})
        if request.headers.get("authorization") == "Bearer poor":
            return httpx.Response(402, json={"error": "Insufficient Balance"})
        body = json.loads(request.content)
        return httpx.Response(200, json={"choices": [{"message": {"content": body["messages"][1]["content"][-9:]}}]})

    monkeypatch.setattr(translate, "TRANSPORT", httpx.MockTransport(handler))
    model = translate.make_model("openai", "https://api.deepseek.com/", "k", "deepseek-flash")
    assert asyncio.run(model.models()) == ["deepseek-flash", "deepseek-v4-pro"]
    assert asyncio.run(model.complete("sys", "hello there")) == "llo there"
    sent = seen[-1]
    assert str(sent.url) == "https://api.deepseek.com/chat/completions" and sent.headers["authorization"] == "Bearer k"
    body = json.loads(sent.content)
    assert body["model"] == "deepseek-flash" and body["messages"][0] == {"role": "system", "content": "sys"}
    for key, code in (("bad", "ai_auth"), ("poor", "ai_quota")):
        with pytest.raises(TranslateError) as info:
            asyncio.run(translate.make_model("openai", "https://x.example/v1", key, "m").complete("s", "p"))
        assert info.value.code == code
    with pytest.raises(TranslateError) as info:
        translate.make_model("openai", "ftp://x", "k", "m")
    assert info.value.code == "ai_base_invalid"


def test_claude_goes_through_the_sdk_with_low_effort_and_fallbacks(monkeypatch):
    import anthropic
    import httpx2

    seen = []

    def handler(request):
        seen.append(request)
        body = json.loads(request.content)
        refusal = "refuse" in body["messages"][0]["content"]
        return httpx2.Response(200, json={
            "id": "msg_1", "type": "message", "role": "assistant", "model": body["model"],
            "content": [] if refusal else [{"type": "text", "text": "#1 Merhaba"}],
            "stop_reason": "refusal" if refusal else "end_turn", "stop_sequence": None,
            "usage": {"input_tokens": 1, "output_tokens": 1},
        })

    monkeypatch.setattr(translate, "ANTHROPIC_HTTP", anthropic.DefaultAsyncHttpxClient(transport=httpx2.MockTransport(handler)))
    model = translate.make_model("anthropic", "", "sk-test", "claude-opus-5-5")
    assert asyncio.run(model.complete("sys", "#1 Hello")) == "#1 Merhaba"
    body = json.loads(seen[-1].content)
    assert body["output_config"] == {"effort": "low"} and body["fallbacks"] == "default"
    assert "server-side-fallback-2026-07-01" in seen[-1].headers["anthropic-beta"]
    assert body["system"][0]["cache_control"] == {"type": "ephemeral"} and "temperature" not in body
    with pytest.raises(TranslateError) as info:
        asyncio.run(model.complete("sys", "please refuse"))
    assert info.value.code == "ai_refused"

    # An Anthropic-compatible provider gets the plain request: no Claude-only fields.
    other = translate.make_model("anthropic", "https://api.deepseek.com/anthropic", "k", "deepseek-flash")
    asyncio.run(other.complete("sys", "#1 Hello"))
    body = json.loads(seen[-1].content)
    assert str(seen[-1].url).startswith("https://api.deepseek.com/anthropic/")
    assert "output_config" not in body and "fallbacks" not in body and body["system"] == "sys"


def test_settings_resolve_the_provider_and_need_a_key(monkeypatch, tmp_path):
    monkeypatch.setenv("DATA_DIR", str(tmp_path))
    try:
        get_settings.cache_clear()
        cfg = get_settings()
        assert (cfg.ai_provider, cfg.ai_protocol, cfg.ai_model) == ("deepseek", "openai", "deepseek-flash")
        assert not cfg.ai_enabled  # no key yet
        monkeypatch.setenv("AI_PROVIDER", "lmstudio")
        monkeypatch.setenv("AI_MODEL", "qwen")
        get_settings.cache_clear()
        cfg = get_settings()
        assert cfg.ai_base_url == "http://localhost:1234/v1" and cfg.ai_local and cfg.ai_enabled  # no key needed
        monkeypatch.setenv("AI_PROVIDER", "claude")
        monkeypatch.delenv("AI_MODEL")
        monkeypatch.setenv("AI_API_KEY", "sk")
        get_settings.cache_clear()
        cfg = get_settings()
        assert (cfg.ai_protocol, cfg.ai_model, cfg.ai_enabled, cfg.ai_label) == ("anthropic", "claude-opus-5-5", True, "Claude")
    finally:
        get_settings.cache_clear()


class Session:
    def __init__(self):
        self.source = type("Source", (), {"media_key": "film1", "title": "Test Film", "kind": "file"})()
        self.stream = None  # not playing yet: the room needs only the film's key and title here

    def stop(self):
        pass


def test_the_room_translates_once_and_only_the_trusted_may_start(monkeypatch, tmp_path):
    from server.subtitles import SubtitleStore

    monkeypatch.setattr(main, "cfg", dataclasses.replace(main.cfg, ai_provider="custom", ai_protocol="openai",
                                                         ai_base_url="https://llm.example/v1", ai_api_key="k",
                                                         ai_model="m", ai_translate="trusted", data_dir=tmp_path))
    monkeypatch.setattr(main.ctl, "store", SubtitleStore(tmp_path / "subs"))
    monkeypatch.setattr(main.ctl, "session", Session())
    monkeypatch.setattr(main.ctl, "translating", None)
    monkeypatch.setattr(main.ctl, "briefs", {})
    source = main.ctl.store.add("film1", "en", "upload", "upload", cues(12))
    calls = []

    async def complete(self, system, prompt):
        calls.append(prompt)
        return await FakeModel().complete(system, prompt)

    monkeypatch.setattr(translate.OpenAIModel, "complete", complete)
    with TestClient(app, **FRIEND) as friend:
        assert friend.get("/api/status").json()["ai"] == {"enabled": True, "allowed": False, "provider": "m", "busy": None}
        assert friend.post("/api/subtitles/translate", json={"source": source["id"], "lang": "tr"}).status_code == 403
    with TestClient(app, **HOST) as host:
        assert host.post("/api/subtitles/translate", json={"source": source["id"], "lang": "en"}).json()["detail"] == "ai_same_language"
        assert host.post("/api/subtitles/translate", json={"source": source["id"], "lang": "tr"}).status_code == 202
        deadline = time.monotonic() + 5
        while main.ctl.translating and time.monotonic() < deadline:
            time.sleep(0.05)
        made = main.ctl.store.find("film1", source="ai", lang="tr")
        assert made and made["fromTrack"] == source["id"] and made["label"] == "AI · m" and made["cues"] == 12
        assert main.ctl.store.cues("film1", made["id"])[0][2] == "TR Line 1\nsecond"
        count = len(calls)
        again = host.post("/api/subtitles/translate", json={"source": source["id"], "lang": "tr"}).json()
        assert again == {"track": made["id"], "cached": True} and len(calls) == count  # no second bill
        # Another language reuses the brief: no first pass this time.
        host.post("/api/subtitles/translate", json={"source": source["id"], "lang": "ru"})
        deadline = time.monotonic() + 5
        while main.ctl.translating and time.monotonic() < deadline:
            time.sleep(0.05)
        assert not any(p.startswith("Below are the subtitles") for p in calls[count:])


def test_the_settings_page_keeps_the_key_and_tries_the_model(monkeypatch, tmp_path):
    monkeypatch.setattr(main, "cfg", dataclasses.replace(main.cfg, data_dir=tmp_path))
    form = {k: v for k, v in config.DEFAULTS.items() if k not in ("osPassword", "aiApiKey")}
    with TestClient(app, **HOST) as host:
        assert host.post("/api/settings", json={**form, "aiApiKey": "secret-1"}).status_code == 200
        assert host.post("/api/settings", json={**form, "aiModel": "deepseek-v4-pro"}).status_code == 200
        values = host.get("/api/settings").json()["values"]
        assert values["hasAiKey"] and "aiApiKey" not in values and values["aiModel"] == "deepseek-v4-pro"
        assert config.load_saved(tmp_path)["aiApiKey"] == "secret-1"  # kept when the field stays empty
        assert host.post("/api/settings", json={**form, "aiBaseUrl": "file:///x"}).json()["detail"] == "ai_base_invalid"

        seen = []

        def handler(request):
            seen.append(request)
            prompt = json.loads(request.content)["messages"][1]["content"]
            lines = prompt.split("Lines to translate:\n")[1].splitlines()
            return httpx.Response(200, json={"choices": [{"message": {"content": "\n".join(
                f"{line.split(' ', 1)[0]} Nereye?" for line in lines)}}]})

        monkeypatch.setattr(translate, "TRANSPORT", httpx.MockTransport(handler))
        res = host.post("/api/settings/ai-test", json={"aiProvider": "deepseek", "lang": "tr"}).json()
        assert res == {"lines": ["Nereye?", "Nereye?"], "missing": 0}
        assert seen[-1].headers["authorization"] == "Bearer secret-1"  # the saved key, never sent to the page
    with TestClient(app, **FRIEND) as friend:
        assert friend.post("/api/settings/ai-models", json={"aiProvider": "deepseek"}).status_code == 403
