"""LangChain-backed chat callable for LLMPlanner.

Wraps deerflow.models.factory.create_chat_model into the simple
``async (prompt: str) -> str`` contract that LLMPlanner expects.

Use a cheap model (e.g. gpt-4o-mini) for planning. Per design doc,
Planner must be cheap; Developer and QA can use stronger models.
"""

from __future__ import annotations

import logging

logger = logging.getLogger(__name__)


def make_langchain_chat(
    model_name: str = "gpt-4o-mini",
    app_config: object | None = None,
):
    """Return an async callable ``(prompt: str) -> str`` backed by LangChain.

    Falls back to a stub if create_chat_model cannot be imported or
    instantiated (e.g. missing API key in tests).
    """
    try:
        from deerflow.models.factory import create_chat_model
    except Exception as e:  # pragma: no cover
        logger.warning("create_chat_model unavailable: %s; using stub chat", e)

        async def stub(_prompt: str) -> str:
            return '{"scope": "continue", "acceptance": ["no regression"], "preserve": []}'

        return stub

    try:
        model = create_chat_model(name=model_name, app_config=app_config, attach_tracing=False)
    except Exception as e:  # pragma: no cover
        logger.warning("create_chat_model(%s) failed: %s; using stub chat", model_name, e)

        async def stub(_prompt: str) -> str:
            return '{"scope": "continue", "acceptance": ["no regression"], "preserve": []}'

        return stub

    async def chat(prompt: str) -> str:
        resp = await model.ainvoke([{"role": "user", "content": prompt}])
        content = getattr(resp, "content", "") or str(resp)
        return content

    return chat
