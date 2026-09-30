import asyncio
from unittest.mock import AsyncMock

from app.gateway.routers import ai_proxy


def _patch_pool(monkeypatch, vendor_response):
    chat = AsyncMock(return_value=vendor_response)
    monkeypatch.setattr(ai_proxy.pool, "chat_completions", chat)
    monkeypatch.setattr(ai_proxy, "_detect_region", lambda request, explicit=None: "cn")
    # Force fallback to pool by making get_gateway raise RuntimeError
    monkeypatch.setattr(
        "app.gateway.ai_gateway.get_gateway",
        lambda: (_ for _ in ()).throw(RuntimeError("gateway not configured")),
    )
    return chat


def test_run_oneshot_via_pool_builds_openai_payload_and_extracts_text(monkeypatch):
    vendor_response = {"choices": [{"message": {"role": "assistant", "content": "  polished text  "}}]}
    chat = _patch_pool(monkeypatch, vendor_response)

    raw = asyncio.run(
        ai_proxy.run_oneshot_via_pool(
            system_instruction="sys prompt",
            user_content="user prompt",
            run_name="input_polish",
            request=object(),
        )
    )

    assert raw == "  polished text  "
    chat.assert_awaited_once()
    model_arg, payload_arg, region_arg = chat.await_args.args
    assert model_arg == "llama-3.1-8b"
    assert region_arg == "cn"
    assert payload_arg["messages"] == [
        {"role": "system", "content": "sys prompt"},
        {"role": "user", "content": "user prompt"},
    ]
    assert payload_arg["temperature"] == 0.7


def test_run_oneshot_via_pool_forwards_model_override(monkeypatch):
    chat = _patch_pool(monkeypatch, {"choices": [{"message": {"content": "ok"}}]})

    asyncio.run(
        ai_proxy.run_oneshot_via_pool(
            system_instruction="sys",
            user_content="user",
            run_name="suggest_agent",
            request=object(),
            model="polish-model",
            temperature=0.3,
        )
    )

    model_arg, payload_arg, _region = chat.await_args.args
    assert model_arg == "polish-model"
    assert payload_arg["model"] == "polish-model"
    assert payload_arg["temperature"] == 0.3


def test_extract_chat_text_handles_missing_or_malformed_choices():
    assert ai_proxy._extract_chat_text({"choices": [{"message": {"content": "hi"}}]}) == "hi"
    assert ai_proxy._extract_chat_text({"choices": []}) == ""
    assert ai_proxy._extract_chat_text({"choices": [{}]}) == ""
    assert ai_proxy._extract_chat_text({}) == ""
