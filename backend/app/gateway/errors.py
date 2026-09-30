"""
统一错误处理工具（入口架构优化 P1）

参考大厂做法（Canva/Adobe/抖音/剪映）：
- 统一错误响应格式
- 错误追踪 ID（便于日志关联）
- 分级错误处理（用户可见错误 vs 内部错误）
- 结构化错误日志

使用方式：
    from app.gateway.errors import PipelineError, error_response, handle_pipeline_error

    try:
        result = await execute_pipeline(album_id)
    except PipelineError as e:
        return error_response(e)
    except Exception as e:
        return handle_pipeline_error(e, album_id=album_id)
"""

import logging
import uuid
from datetime import datetime
from typing import Any

from fastapi import HTTPException

from app.gateway.i18n import DEFAULT_LOCALE, t

logger = logging.getLogger(__name__)


class PipelineError(Exception):
    """管线执行错误（用户可见的业务错误）

    参考大厂做法：将业务错误与系统错误分离，
    业务错误返回明确的用户提示，系统错误返回通用提示并记录追踪 ID。

    i18n：如果 code 匹配 i18n 翻译键，to_dict() 自动用 t(code, locale)
    替换 message。未匹配的 code 保持原始 message（英语兜底，向后兼容）。
    """

    def __init__(
        self,
        message: str,
        code: str = "pipeline_error",
        status_code: int = 400,
        details: dict[str, Any] | None = None,
        album_id: str | None = None,
        retryable: bool = False,
        locale: str = DEFAULT_LOCALE,
    ):
        super().__init__(message)
        self.message = message
        self.code = code
        self.locale = locale
        self.status_code = status_code
        self.details = details or {}
        self.album_id = album_id
        self.retryable = retryable
        self.trace_id = str(uuid.uuid4())[:8]
        self.timestamp = datetime.utcnow().isoformat()

    def to_dict(self) -> dict[str, Any]:
        """转换为统一错误响应格式（自动 i18n）"""
        # 如果 code 匹配翻译键，用本地化消息覆盖原始 message
        localized_message = t(self.code, self.locale, **self.details)
        # t() 在 key 不存在时返回 key 本身，此时回退原始 message
        if localized_message == self.code:
            localized_message = self.message

        result = {
            "error": {
                "code": self.code,
                "message": localized_message,
                "trace_id": self.trace_id,
                "timestamp": self.timestamp,
                "retryable": self.retryable,
                "locale": self.locale,
            }
        }
        if self.album_id:
            result["error"]["album_id"] = self.album_id
        if self.details:
            result["error"]["details"] = self.details
        return result


class AlbumNotFoundError(PipelineError):
    """项目不存在错误"""

    def __init__(self, album_id: str, locale: str = DEFAULT_LOCALE):
        super().__init__(
            message=f"Album {album_id} not found",
            code="album_not_found",
            status_code=404,
            album_id=album_id,
            retryable=False,
            locale=locale,
        )


class ExecutorNotInitializedError(PipelineError):
    """执行器未初始化错误"""

    def __init__(self, locale: str = DEFAULT_LOCALE):
        super().__init__(
            message="Pipeline executor not initialized",
            code="executor_not_initialized",
            status_code=503,
            retryable=True,
            locale=locale,
        )


class InvalidParameterError(PipelineError):
    """参数无效错误"""

    def __init__(self, param_name: str, reason: str, album_id: str | None = None, locale: str = DEFAULT_LOCALE):
        super().__init__(
            message=f"Invalid parameter '{param_name}': {reason}",
            code="invalid_parameter",
            status_code=400,
            details={"param": f"{param_name}: {reason}"},
            album_id=album_id,
            retryable=False,
            locale=locale,
        )


def error_response(error: PipelineError) -> HTTPException:
    """将 PipelineError 转换为 FastAPI HTTPException

    统一错误响应格式，包含追踪 ID 便于日志关联。
    """
    return HTTPException(
        status_code=error.status_code,
        detail=error.to_dict()["error"],
    )


def handle_pipeline_error(
    error: Exception,
    album_id: str | None = None,
    operation: str = "unknown",
    locale: str = DEFAULT_LOCALE,
) -> HTTPException:
    """处理未预期的管线执行错误

    参考大厂做法：
    - 系统错误返回通用提示，不暴露内部实现细节
    - 记录详细的错误日志，包含追踪 ID
    - 用户可通过追踪 ID 反馈问题
    - i18n：消息自动本地化
    """
    trace_id = str(uuid.uuid4())[:8]
    timestamp = datetime.utcnow().isoformat()

    # 记录详细的错误日志（日志保持英语，便于搜索）
    logger.error(
        "Pipeline error [trace_id=%s] [album_id=%s] [operation=%s]: %s",
        trace_id,
        album_id or "N/A",
        operation,
        str(error),
        exc_info=True,
    )

    # 返回通用错误提示（本地化），不暴露内部实现细节
    return HTTPException(
        status_code=500,
        detail={
            "code": "internal_error",
            "message": t("internal_error", locale),
            "trace_id": trace_id,
            "timestamp": timestamp,
            "retryable": True,
            "locale": locale,
            **({"album_id": album_id} if album_id else {}),
        },
    )


def validate_album_id(album_id: str) -> None:
    """验证 album_id 格式

    统一参数验证，避免无效 album_id 进入执行流程。
    """
    if not album_id or not isinstance(album_id, str):
        raise InvalidParameterError("album_id", "must be a non-empty string")

    # album_id 通常以 album_ 开头，后跟时间戳和随机字符串
    if not album_id.startswith("album_"):
        logger.warning(
            "Album ID does not start with 'album_': %s (may be valid in some cases)",
            album_id,
        )

    # 检查长度（合理范围）
    if len(album_id) < 10 or len(album_id) > 100:
        raise InvalidParameterError(
            "album_id",
            f"length must be between 10 and 100 characters (got {len(album_id)})",
        )
