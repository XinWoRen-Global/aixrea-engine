"""
后端国际化（i18n）模块 P0

轻量级字典翻译系统，不引入 gettext/babel 等重依赖。
参考大厂做法（Stripe / Shopify / Vercel）：
- 错误码驱动翻译（code → 多语言 message）
- Accept-Language header 优先，用户 profile 兜底
- 未翻译 key 自动回退英语，不报错
- 日志保持英语（便于搜索），仅用户可见消息本地化

使用方式：
    from app.gateway.i18n import t, resolve_locale, get_request_locale

    # 在路由中
    locale = get_request_locale(request)
    raise HTTPException(status_code=404, detail={
        "code": "thread_not_found",
        "message": t("thread_not_found", locale),
    })

    # 或使用 helper
    from app.gateway.i18n import localized_error
    return localized_error("thread_not_found", 404, locale)
"""

import logging
import re
from typing import Any

from fastapi import Request

logger = logging.getLogger(__name__)

# 支持的语言（与前端 LOCALE_REGISTRY 对齐）
SUPPORTED_LOCALES = {"en", "zh", "es", "ja", "ko"}
DEFAULT_LOCALE = "en"

# ─── 翻译字典 ───────────────────────────────────────────────
# 格式：{ "error_code_or_message_key": { "en": "...", "zh": "...", "es": "..." } }
# 支持 {placeholder} 插值，由 t() 的 **kwargs 填充

_TRANSLATIONS: dict[str, dict[str, str]] = {
    # ── 认证 / 授权 ──
    "auth_required": {
        "en": "Authentication required",
        "zh": "需要登录认证",
        "es": "Se requiere autenticación",
    },
    "auth_invalid_token": {
        "en": "Invalid or expired authentication token",
        "zh": "认证令牌无效或已过期",
        "es": "Token de autenticación inválido o expirado",
    },
    "auth_forbidden": {
        "en": "You do not have permission to perform this action",
        "zh": "您没有权限执行此操作",
        "es": "No tiene permiso para realizar esta acción",
    },
    "auth_admin_required": {
        "en": "Administrator privileges required",
        "zh": "需要管理员权限",
        "es": "Se requieren privilegios de administrador",
    },
    # ── 资源不存在 ──
    "not_found": {
        "en": "Resource not found",
        "zh": "资源不存在",
        "es": "Recurso no encontrado",
    },
    "thread_not_found": {
        "en": "Thread not found",
        "zh": "对话不存在",
        "es": "Hilo no encontrado",
    },
    "run_not_found": {
        "en": "Run not found",
        "zh": "运行记录不存在",
        "es": "Ejecución no encontrada",
    },
    "user_not_found": {
        "en": "User not found",
        "zh": "用户不存在",
        "es": "Usuario no encontrado",
    },
    "album_not_found": {
        "en": "Album not found",
        "zh": "项目不存在",
        "es": "Álbum no encontrado",
    },
    "content_not_found": {
        "en": "Content not found",
        "zh": "内容不存在",
        "es": "Contenido no encontrado",
    },
    # ── 参数验证 ──
    "invalid_parameter": {
        "en": "Invalid parameter: {param}",
        "zh": "参数无效：{param}",
        "es": "Parámetro inválido: {param}",
    },
    "missing_parameter": {
        "en": "Missing required parameter: {param}",
        "zh": "缺少必填参数：{param}",
        "es": "Falta el parámetro requerido: {param}",
    },
    "validation_error": {
        "en": "Validation failed: {detail}",
        "zh": "验证失败：{detail}",
        "es": "Validación fallida: {detail}",
    },
    # ── 业务错误 ──
    "insufficient_credits": {
        "en": "Insufficient credits. Required: {required}, Available: {available}",
        "zh": "积分不足。需要：{required}，可用：{available}",
        "es": "Créditos insuficientes. Requeridos: {required}, Disponibles: {available}",
    },
    "insufficient_balance": {
        "en": "Insufficient balance",
        "zh": "余额不足",
        "es": "Saldo insuficiente",
    },
    "payment_failed": {
        "en": "Payment processing failed. Please try again.",
        "zh": "支付处理失败，请重试。",
        "es": "El procesamiento del pago falló. Por favor intente de nuevo.",
    },
    "order_not_found": {
        "en": "Order not found",
        "zh": "订单不存在",
        "es": "Pedido no encontrado",
    },
    "refund_not_allowed": {
        "en": "Refund is not allowed for this order",
        "zh": "此订单不支持退款",
        "es": "No se permite reembolso para este pedido",
    },
    # ── 限流 / 配额 ──
    "rate_limited": {
        "en": "Too many requests. Please try again later.",
        "zh": "请求过于频繁，请稍后再试。",
        "es": "Demasiadas solicitudes. Por favor intente más tarde.",
    },
    "quota_exceeded": {
        "en": "Quota exceeded. Please upgrade your plan or try again later.",
        "zh": "配额已超出，请升级套餐或稍后再试。",
        "es": "Cuota excedida. Por favor actualice su plan o intente más tarde.",
    },
    # ── 服务不可用 ──
    "service_unavailable": {
        "en": "Service temporarily unavailable. Please try again later.",
        "zh": "服务暂时不可用，请稍后再试。",
        "es": "Servicio temporalmente no disponible. Por favor intente más tarde.",
    },
    "model_unavailable": {
        "en": "AI model is currently unavailable. Please try a different model or try again later.",
        "zh": "AI 模型当前不可用，请尝试其他模型或稍后再试。",
        "es": "El modelo de IA no está disponible actualmente. Por favor intente con otro modelo o más tarde.",
    },
    "executor_not_initialized": {
        "en": "Pipeline executor is not initialized. Please try again later.",
        "zh": "管线执行器未初始化，请稍后再试。",
        "es": "El ejecutor de pipeline no está inicializado. Por favor intente más tarde.",
    },
    # ── 内部错误 ──
    "internal_error": {
        "en": "An internal error occurred while processing your request",
        "zh": "处理您的请求时发生内部错误",
        "es": "Ocurrió un error interno al procesar su solicitud",
    },
    "upstream_error": {
        "en": "Upstream service returned an error",
        "zh": "上游服务返回错误",
        "es": "El servicio ascendente devolvió un error",
    },
    # ── 通知 / 邮件主题 ──
    "email_order_created_subject": {
        "en": "Your order has been created",
        "zh": "您的订单已创建",
        "es": "Su pedido ha sido creado",
    },
    "email_payment_success_subject": {
        "en": "Payment successful",
        "zh": "支付成功",
        "es": "Pago exitoso",
    },
    "email_refund_subject": {
        "en": "Refund processed",
        "zh": "退款已处理",
        "es": "Reembolso procesado",
    },
    "email_welcome_subject": {
        "en": "Welcome to {platform}",
        "zh": "欢迎加入 {platform}",
        "es": "Bienvenido a {platform}",
    },
    # ── 高频静态错误（P1 补充，覆盖全局异常处理器自动本地化）──
    "scheduled_task_not_found": {
        "en": "Scheduled task not found",
        "zh": "定时任务不存在",
        "es": "Tarea programada no encontrada",
    },
    "unknown_channel_provider": {
        "en": "Unknown channel provider",
        "zh": "未知的渠道提供商",
        "es": "Proveedor de canal desconocido",
    },
    "failed_to_create_thread": {
        "en": "Failed to create thread",
        "zh": "创建对话失败",
        "es": "Error al crear el hilo",
    },
    "channel_connections_disabled": {
        "en": "Channel connections are disabled",
        "zh": "渠道连接功能已禁用",
        "es": "Las conexiones de canal están deshabilitadas",
    },
    "channel_provider_not_enabled": {
        "en": "Channel provider is not enabled",
        "zh": "渠道提供商未启用",
        "es": "El proveedor de canal no está habilitado",
    },
    "artifact_too_large": {
        "en": "Artifact is too large to edit",
        "zh": "文件过大，无法编辑",
        "es": "El archivo es demasiado grande para editar",
    },
    "url_required": {
        "en": "URL is required",
        "zh": "URL 为必填项",
        "es": "La URL es obligatoria",
    },
    "turn_cannot_branch": {
        "en": "This turn can no longer be branched from.",
        "zh": "此轮对话已无法再分支。",
        "es": "Este turno ya no se puede ramificar.",
    },
    "provider_unavailable": {
        "en": "AI provider is currently unavailable. Please try a different model or try again later.",
        "zh": "AI 服务提供商当前不可用，请尝试其他模型或稍后再试。",
        "es": "El proveedor de IA no está disponible actualmente. Por favor intente con otro modelo o más tarde.",
    },
    "queue_unavailable": {
        "en": "Queue service is temporarily unavailable. Please try again later.",
        "zh": "排队服务暂不可用，请稍后重试。",
        "es": "El servicio de cola no está disponible temporalmente. Por favor intente más tarde.",
    },
    "free_limit_exceeded": {
        "en": "Free trial quota exceeded or model unavailable. Please try again later or upgrade to a paid model.",
        "zh": "免费体验额度不足或模型暂不可用，请稍后重试或升级至付费模型。",
        "es": "Cuota de prueba gratuita excedida o modelo no disponible. Por favor intente más tarde o actualice a un modelo de pago.",
    },
    # ── 认证/授权（P2 auth 路由迁移）──
    "auth_incorrect_email_or_password": {
        "en": "Incorrect email or password",
        "zh": "邮箱或密码错误",
        "es": "Correo o contraseña incorrectos",
    },
    "auth_registration_disabled": {
        "en": "Self-registration is disabled on this deployment",
        "zh": "本部署已禁用自助注册",
        "es": "El auto-registro está deshabilitado en este despliegue",
    },
    "auth_email_already_registered": {
        "en": "Email already registered",
        "zh": "邮箱已注册",
        "es": "El correo ya está registrado",
    },
    "auth_email_already_in_use": {
        "en": "Email already in use",
        "zh": "邮箱已被使用",
        "es": "El correo ya está en uso",
    },
    "auth_password_change_disabled": {
        "en": "Password changes are not available in this configuration",
        "zh": "当前配置下无法修改密码",
        "es": "Los cambios de contraseña no están disponibles en esta configuración",
    },
    "auth_oauth_cannot_change_password": {
        "en": "OAuth users cannot change password",
        "zh": "OAuth 登录用户无法修改密码",
        "es": "Los usuarios de OAuth no pueden cambiar la contraseña",
    },
    "auth_current_password_incorrect": {
        "en": "Current password is incorrect",
        "zh": "当前密码错误",
        "es": "La contraseña actual es incorrecta",
    },
    "auth_system_already_initialized": {
        "en": "System already initialized",
        "zh": "系统已初始化",
        "es": "El sistema ya está inicializado",
    },
    "auth_too_many_login_attempts": {
        "en": "Too many login attempts. Try again later.",
        "zh": "登录尝试次数过多，请稍后再试。",
        "es": "Demasiados intentos de inicio de sesión. Intente más tarde.",
    },
    "auth_sso_not_enabled": {
        "en": "SSO authentication is not enabled",
        "zh": "SSO 单点登录未启用",
        "es": "La autenticación SSO no está habilitada",
    },
    "auth_invalid_provider_id": {
        "en": "Invalid provider ID",
        "zh": "无效的提供商 ID",
        "es": "ID de proveedor inválido",
    },
    "auth_unknown_sso_provider": {
        "en": "Unknown SSO provider: {provider}",
        "zh": "未知的 SSO 提供商：{provider}",
        "es": "Proveedor de SSO desconocido: {provider}",
    },
    "auth_sso_connection_failed": {
        "en": "Failed to connect to SSO provider",
        "zh": "连接 SSO 提供商失败",
        "es": "Error al conectar con el proveedor de SSO",
    },
    "auth_missing_code_or_state": {
        "en": "Missing code or state parameter",
        "zh": "缺少 code 或 state 参数",
        "es": "Falta el parámetro code o state",
    },
    "auth_oidc_state_expired": {
        "en": "Missing or expired OIDC state cookie",
        "zh": "OIDC state cookie 缺失或已过期",
        "es": "Cookie de estado OIDC faltante o expirada",
    },
    "auth_oidc_state_mismatch": {
        "en": "OIDC state mismatch",
        "zh": "OIDC state 不匹配",
        "es": "Discrepancia de estado OIDC",
    },
    # ── 积分/扣费（P2 credits 路由迁移）──
    "credits_hold_not_found": {
        "en": "Hold {hold_id} not found",
        "zh": "扣费预占 {hold_id} 不存在",
        "es": "Retención {hold_id} no encontrada",
    },
    "credits_album_not_found": {
        "en": "Album {album_id} not found",
        "zh": "相册 {album_id} 不存在",
        "es": "Álbum {album_id} no encontrado",
    },
    "credits_album_no_nodes": {
        "en": "No content found for album {album_id}",
        "zh": "相册 {album_id} 中没有内容",
        "es": "No se encontró contenido en el álbum {album_id}",
    },
    "credits_estimation_failed": {
        "en": "Failed to estimate credits. Please try again later.",
        "zh": "积分预估失败，请稍后重试。",
        "es": "Error al estimar los créditos. Por favor intente más tarde.",
    },
    "credits_summary_failed": {
        "en": "Failed to generate usage summary. Please try again later.",
        "zh": "生成使用摘要失败，请稍后重试。",
        "es": "Error al generar el resumen de uso. Por favor intente más tarde.",
    },
    # ── 对话/运行（P2 threads 路由迁移，高频）──
    "thread_not_found_with_id": {
        "en": "Thread {thread_id} not found",
        "zh": "对话 {thread_id} 不存在",
        "es": "Hilo {thread_id} no encontrado",
    },
    "run_not_found_with_id": {
        "en": "Run {run_id} not found",
        "zh": "运行 {run_id} 不存在",
        "es": "Ejecución {run_id} no encontrada",
    },
    "message_not_found": {
        "en": "Message {message_id} not found in thread {thread_id}",
        "zh": "消息 {message_id} 不在对话 {thread_id} 中",
        "es": "Mensaje {message_id} no encontrado en el hilo {thread_id}",
    },
    "invalid_thread_status": {
        "en": "Invalid operation: thread is in {status} state",
        "zh": "操作无效：对话当前状态为 {status}",
        "es": "Operación inválida: el hilo está en estado {status}",
    },
    "thread_checkpoint_not_found": {
        "en": "Checkpoint {checkpoint_id} not found",
        "zh": "检查点 {checkpoint_id} 不存在",
        "es": "Punto de control {checkpoint_id} no encontrado",
    },
    "thread_no_checkpoint": {
        "en": "Thread {thread_id} has no checkpoint",
        "zh": "对话 {thread_id} 没有检查点",
        "es": "El hilo {thread_id} no tiene punto de control",
    },
    "run_active_on_another_worker": {
        "en": "Run {run_id} is active on another worker. Please retry shortly.",
        "zh": "运行 {run_id} 正在其他工作节点执行，请稍后重试。",
        "es": "La ejecución {run_id} está activa en otro trabajador. Por favor reintente pronto.",
    },
    "run_not_active_on_worker": {
        "en": "Run {run_id} is not active on this worker and cannot be streamed",
        "zh": "运行 {run_id} 不在此工作节点上，无法流式传输",
        "es": "La ejecución {run_id} no está activa en este trabajador y no se puede transmitir",
    },
    "thread_unknown_state_fields": {
        "en": "Unknown thread-state field(s): {fields}",
        "zh": "未知的对话状态字段：{fields}",
        "es": "Campo(s) de estado de hilo desconocido(s): {fields}",
    },
    "message_not_found_simple": {
        "en": "Message {message_id} not found",
        "zh": "消息 {message_id} 不存在",
        "es": "Mensaje {message_id} no encontrado",
    },
    # -- skills (P3) --
    "skill_not_found": {
        "en": "Skill {skill_name} not found",
        "zh": "技能 {skill_name} 不存在",
        "es": "Habilidad {skill_name} no encontrada",
    },
    "skill_no_history": {
        "en": "This skill has no execution history",
        "zh": "此技能没有执行历史",
        "es": "Esta habilidad no tiene historial",
    },
    "skill_security_scan_failed": {
        "en": "Security scan failed: {reason}",
        "zh": "安全扫描未通过：{reason}",
        "es": "Verificacion de seguridad fallo: {reason}",
    },
    "skill_operation_failed": {
        "en": "Skill operation failed. Please try again later.",
        "zh": "技能操作失败，请稍后重试。",
        "es": "Error en la operacion. Por favor intente mas tarde.",
    },
    "skill_delete_failed": {
        "en": "Failed to delete custom skill {skill_name}. Please try again later.",
        "zh": "删除自定义技能 {skill_name} 失败，请稍后重试。",
        "es": "No se pudo eliminar la habilidad personalizada {skill_name}. Por favor intente mas tarde.",
    },
    "feedback_not_found": {
        "en": "Feedback {feedback_id} not found",
        "zh": "反馈 {feedback_id} 不存在",
        "es": "Retroalimentacion {feedback_id} no encontrada",
    },
    "feedback_not_found_in_run": {
        "en": "Feedback {feedback_id} not found in run {run_id}",
        "zh": "反馈 {feedback_id} 不在运行 {run_id} 中",
        "es": "Feedback {feedback_id} no encontrado en ejecucion {run_id}",
    },
    "run_not_found_in_thread": {
        "en": "Run {run_id} not found in thread {thread_id}",
        "zh": "运行 {run_id} 不在对话 {thread_id} 中",
        "es": "Ejecucion {run_id} no encontrada en hilo {thread_id}",
    },
    "upload_file_too_large": {
        "en": "File too large: {filename}",
        "zh": "文件过大：{filename}",
        "es": "Archivo demasiado grande: {filename}",
    },
    "upload_too_many_files": {
        "en": "Too many files. Maximum is {max_files}",
        "zh": "文件数量过多，最多 {max_files} 个",
        "es": "Demasiados archivos. Maximo {max_files}",
    },
    "upload_failed": {
        "en": "File upload failed. Please try again.",
        "zh": "文件上传失败，请重试。",
        "es": "Error al subir el archivo. Por favor intente de nuevo.",
    },
    "upload_file_not_found": {
        "en": "File not found: {filename}",
        "zh": "文件不存在：{filename}",
        "es": "Archivo no encontrado: {filename}",
    },
    "upload_delete_failed": {
        "en": "Failed to delete file. Please try again.",
        "zh": "删除文件失败，请重试。",
        "es": "Error al eliminar el archivo. Por favor intente de nuevo.",
    },
    # -- AI Proxy (P3) --
    "model_not_available": {
        "en": "No available provider supports model: {model}",
        "zh": "当前没有可用的服务商支持模型：{model}",
        "es": "Ningun proveedor disponible soporta el modelo: {model}",
    },
    "all_providers_failed": {
        "en": "AI service is temporarily unavailable. Please try again later.",
        "zh": "AI 服务暂时不可用，请稍后重试。",
        "es": "Servicio de IA temporalmente no disponible. Por favor intente mas tarde.",
    },
    "media_generation_failed": {
        "en": "Media generation failed. Please try again.",
        "zh": "媒体生成失败，请重试。",
        "es": "Error en la generacion de medios. Por favor intente de nuevo.",
    },
    # -- Artifacts (P3) --
    "artifact_not_found": {
        "en": "Artifact not found",
        "zh": "文件不存在",
        "es": "Archivo no encontrado",
    },
    "not_a_file": {
        "en": "Path is not a file",
        "zh": "路径不是文件",
        "es": "La ruta no es un archivo",
    },
    "skill_file_not_found": {
        "en": "Skill file not found",
        "zh": "技能文件不存在",
        "es": "Archivo de habilidad no encontrado",
    },
    "file_not_in_archive": {
        "en": "File not found in skill archive",
        "zh": "文件不在技能包中",
        "es": "Archivo no encontrado en el paquete de habilidad",
    },
}

# ─── 核心函数 ───────────────────────────────────────────────

_PLACEHOLDER_RE = re.compile(r"\{(\w+)\}")


def t(key: str, locale: str = DEFAULT_LOCALE, **kwargs: Any) -> str:
    """翻译函数

    Args:
        key: 翻译键（错误码或消息 key）
        locale: 目标语言（en/zh/es/ja/ko）
        **kwargs: 插值参数，替换 {placeholder}

    Returns:
        翻译后的字符串。未找到 key 或语言时回退英语，再回退 key 本身。
    """
    # 规范化 locale（zh-CN → zh，en-US → en）
    norm_locale = _normalize_locale(locale)

    entry = _TRANSLATIONS.get(key)
    if entry is None:
        # 未注册的 key：返回 key 本身（便于发现未翻译项）
        logger.debug("i18n: key not found: %s", key)
        return key

    # 优先目标语言，回退英语
    template = entry.get(norm_locale) or entry.get(DEFAULT_LOCALE) or key

    # 插值替换
    if kwargs:

        def _replace(m: re.Match) -> str:
            return str(kwargs.get(m.group(1), m.group(0)))

        template = _PLACEHOLDER_RE.sub(_replace, template)

    return template


def _normalize_locale(locale: str) -> str:
    """规范化语言代码：zh-CN → zh, en-US → en"""
    if not locale:
        return DEFAULT_LOCALE
    base = locale.split("-")[0].split("_")[0].lower()
    return base if base in SUPPORTED_LOCALES else DEFAULT_LOCALE


def resolve_locale(request: Request) -> str:
    """从请求中解析语言

    优先级：
    1. X-Locale header（前端显式指定）
    2. Accept-Language header（浏览器自动）
    3. 默认英语

    注意：用户 profile 的 preferred_locale 需要在认证后从 DB 读取，
    由 auth middleware 注入 request.state.user_locale。
    """
    # 1. X-Locale header（最高优先级）
    x_locale = request.headers.get("X-Locale")
    if x_locale:
        return _normalize_locale(x_locale)

    # 2. 用户 profile（如果 auth middleware 已注入）
    user_locale = getattr(request.state, "user_locale", None)
    if user_locale:
        return _normalize_locale(user_locale)

    # 3. Accept-Language header
    accept_lang = request.headers.get("Accept-Language")
    if accept_lang:
        # 解析 q 值，取最高优先级的支持语言
        for part in accept_lang.split(","):
            part = part.strip()
            if not part:
                continue
            lang = part.split(";")[0].strip()
            normalized = _normalize_locale(lang)
            if normalized in SUPPORTED_LOCALES:
                return normalized

    return DEFAULT_LOCALE


def get_request_locale(request: Request) -> str:
    """获取当前请求的语言（便捷别名）"""
    return resolve_locale(request)


def localized_error(
    key: str,
    status_code: int = 400,
    locale: str = DEFAULT_LOCALE,
    **kwargs: Any,
) -> dict[str, Any]:
    """生成本地化的错误响应体

    使用方式：
        raise HTTPException(status_code=404, detail=localized_error("thread_not_found", 404, locale))

    Returns:
        统一格式的错误 dict
    """
    return {
        "code": key,
        "message": t(key, locale, **kwargs),
        "locale": _normalize_locale(locale),
    }


def register_translation(key: str, translations: dict[str, str]) -> None:
    """运行时注册新翻译（用于模块自注册，避免修改本文件）

    Args:
        key: 翻译键
        translations: { "en": "...", "zh": "..." } 至少包含 en
    """
    if "en" not in translations:
        logger.warning("i18n: register_translation missing 'en' fallback for key: %s", key)
    _TRANSLATIONS[key] = translations


def get_supported_locales() -> list[str]:
    """返回支持的语言列表"""
    return sorted(SUPPORTED_LOCALES)


def get_translation_stats() -> dict[str, Any]:
    """获取翻译统计（用于 /health 或管理后台）"""
    total_keys = len(_TRANSLATIONS)
    per_locale: dict[str, int] = {}
    missing: dict[str, list[str]] = {}
    for loc in SUPPORTED_LOCALES:
        count = sum(1 for entry in _TRANSLATIONS.values() if loc in entry)
        per_locale[loc] = count
        if count < total_keys:
            missing[loc] = [k for k, entry in _TRANSLATIONS.items() if loc not in entry]
    return {
        "total_keys": total_keys,
        "per_locale": per_locale,
        "missing": missing,
        "default_locale": DEFAULT_LOCALE,
    }


# ─── 全局异常处理器辅助 ─────────────────────────────────────

_EN_REVERSE_CACHE: dict[str, str] | None = None


def _build_en_reverse() -> dict[str, str]:
    """构建英语消息→key 的反向查找表（懒加载，仅静态消息）"""
    global _EN_REVERSE_CACHE
    if _EN_REVERSE_CACHE is not None:
        return _EN_REVERSE_CACHE
    reverse: dict[str, str] = {}
    for key, entry in _TRANSLATIONS.items():
        en_msg = entry.get("en")
        if en_msg and "{" not in en_msg:
            reverse[en_msg] = key
    _EN_REVERSE_CACHE = reverse
    return reverse


def localize_detail(detail: Any, locale: str) -> Any:
    """全局异常处理器用：自动本地化 HTTPException detail

    1. detail 是 dict（已结构化）→ 原样返回
    2. detail 是字符串且精确匹配已知英语翻译 → 返回本地化 dict
    3. 不匹配 → 原样返回（英语兜底，向后兼容）

    现有几百个 HTTPException(detail="English") 无需修改，
    静态错误消息自动本地化。动态插值消息保持英语，待逐模块迁移。
    """
    if isinstance(detail, dict):
        return detail
    if isinstance(detail, str):
        reverse = _build_en_reverse()
        key = reverse.get(detail)
        if key:
            return {
                "code": key,
                "message": t(key, locale),
                "locale": _normalize_locale(locale),
            }
    return detail
