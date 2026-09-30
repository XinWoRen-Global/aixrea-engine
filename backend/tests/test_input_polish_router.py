import asyncio
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest
from fastapi import HTTPException

from app.gateway.routers import input_polish


def _config(
    *,
    enabled: bool = True,
    max_chars: int = 4000,
    model_name: str | None = None,
):
    return SimpleNamespace(
        input_polish=SimpleNamespace(
            enabled=enabled,
            max_chars=max_chars,
            model_name=model_name,
        ),
    )


def test_clean_rewritten_text_removes_think_and_fence():
    text = "<think>reasoning</think>\n```text\nrewrite this\n```"
    assert input_polish._clean_rewritten_text(text) == "rewrite this"


def test_clean_rewritten_text_keeps_literal_think_tag():
    # A polished draft may legitimately mention the <think> tag. The cleaner
    # must not truncate at the dangling open tag (which would drop the rest of
    # the rewrite and can surface as a spurious 503).
    text = "Explain what the <think> tag does in reasoning models."
    assert input_polish._clean_rewritten_text(text) == "Explain what the <think> tag does in reasoning models."


def test_polish_input_passes_config_model_and_preserves_response(monkeypatch):
    request = input_polish.InputPolishRequest(
        text="/web-dev 做一个页面",
        locale="zh-CN",
        thread_id="thread-1",
    )
    helper = AsyncMock(return_value="/web-dev 请设计并实现一个视觉精致的页面。")
    monkeypatch.setattr(input_polish, "run_oneshot_via_pool", helper)

    result = asyncio.run(
        input_polish.polish_input.__wrapped__(
            request,
            request=None,
            config=_config(model_name="polish-model"),
        ),
    )

    assert result.rewritten_text == "/web-dev 请设计并实现一个视觉精致的页面。"
    assert result.changed is True
    helper.assert_awaited_once()
    kwargs = helper.await_args.kwargs
    assert kwargs["model"] == "polish-model"
    assert kwargs["run_name"] == "input_polish"
    assert kwargs["system_instruction"]
    assert "/web-dev 做一个页面" in kwargs["user_content"]
    assert "zh-CN" in kwargs["user_content"]


def test_polish_input_uses_default_model_when_config_model_is_missing(monkeypatch):
    request = input_polish.InputPolishRequest(text="make this clearer")
    helper = AsyncMock(return_value="Make this clearer.")
    monkeypatch.setattr(input_polish, "run_oneshot_via_pool", helper)

    result = asyncio.run(
        input_polish.polish_input.__wrapped__(
            request,
            request=None,
            config=_config(model_name=None),
        ),
    )

    assert result.rewritten_text == "Make this clearer."
    assert helper.await_args.kwargs["model"] is None


def test_polish_input_returns_404_when_disabled(monkeypatch):
    request = input_polish.InputPolishRequest(text="hello")
    helper = AsyncMock(return_value="whatever")
    monkeypatch.setattr(input_polish, "run_oneshot_via_pool", helper)

    with pytest.raises(HTTPException) as exc_info:
        asyncio.run(
            input_polish.polish_input.__wrapped__(
                request,
                request=None,
                config=_config(enabled=False),
            ),
        )

    assert exc_info.value.status_code == 404
    helper.assert_not_awaited()


def test_polish_input_rejects_empty_or_too_long_input(monkeypatch):
    helper = AsyncMock(return_value="whatever")
    monkeypatch.setattr(input_polish, "run_oneshot_via_pool", helper)

    with pytest.raises(HTTPException) as empty_exc:
        asyncio.run(
            input_polish.polish_input.__wrapped__(
                input_polish.InputPolishRequest(text="  "),
                request=None,
                config=_config(),
            ),
        )
    assert empty_exc.value.status_code == 400

    with pytest.raises(HTTPException) as long_exc:
        asyncio.run(
            input_polish.polish_input.__wrapped__(
                input_polish.InputPolishRequest(text="hello"),
                request=None,
                config=_config(max_chars=4),
            ),
        )
    assert long_exc.value.status_code == 400
    helper.assert_not_awaited()


@pytest.mark.parametrize("error", [RuntimeError("boom"), HTTPException(status_code=503, detail="All providers failed")])
def test_polish_input_maps_pool_failure_to_503(monkeypatch, error):
    # The unified pool raises its own HTTPException(503) when every provider
    # fails; the router must wrap that into its own 503 either way.
    request = input_polish.InputPolishRequest(text="hello")
    helper = AsyncMock(side_effect=error)
    monkeypatch.setattr(input_polish, "run_oneshot_via_pool", helper)

    with pytest.raises(HTTPException) as exc_info:
        asyncio.run(
            input_polish.polish_input.__wrapped__(
                request,
                request=None,
                config=_config(),
            ),
        )

    assert exc_info.value.status_code == 503
    assert exc_info.value.detail == "Failed to polish input"


def test_polish_input_rejects_whitespace_only_draft(monkeypatch):
    # A padded draft that is empty after normalization is rejected as empty,
    # matching the normalized view used for the model input.
    helper = AsyncMock(return_value="whatever")
    monkeypatch.setattr(input_polish, "run_oneshot_via_pool", helper)

    with pytest.raises(HTTPException) as exc_info:
        asyncio.run(
            input_polish.polish_input.__wrapped__(
                input_polish.InputPolishRequest(text="   \n\t  "),
                request=None,
                config=_config(),
            ),
        )

    assert exc_info.value.status_code == 400
    helper.assert_not_awaited()


def test_polish_input_validates_and_sends_normalized_text(monkeypatch):
    # The length boundary and the model input must agree on one normalized view:
    # a draft whose raw length exceeds max_chars only due to padding is accepted
    # (strip fits), and the model receives the stripped text, not the padding.
    raw_draft = "   summarize report   "  # 22 chars raw, 16 chars stripped
    helper = AsyncMock(return_value="Please summarize the report clearly.")
    monkeypatch.setattr(input_polish, "run_oneshot_via_pool", helper)

    result = asyncio.run(
        input_polish.polish_input.__wrapped__(
            input_polish.InputPolishRequest(text=raw_draft),
            request=None,
            config=_config(max_chars=len(raw_draft.strip())),
        ),
    )

    assert result.rewritten_text == "Please summarize the report clearly."
    user_content = helper.await_args.kwargs["user_content"]
    assert "summarize report" in user_content
    assert "   summarize report   " not in user_content
