"""BYOK 凭据解析 — 请求级密钥注入（唯一解密入口）。

架构定位：DeerFlow 网关作为唯一执行权威，视频/音频 pipeline
（``pipeline_executor._execute_video_node/_execute_audio_node`` → ``ai_proxy``）
只认平台密钥（env / DB ``api_channels``）。要让企业自有 API 密钥（BYOK）接入
这些高单价 AI 能力，同时仍被 DeerFlow 全程感知（路由、幂等、审计、资产落库），
必须在**后端请求级**解析并注入用户密钥，而非前端直连厂商。

铁律：
1. 唯一执行权威 —— 所有 AI 调用必须经网关，BYOK 只是"凭据维度上的降级优先级"，
   ``config.videoModel`` 仍决定路由，BYOK 只换凭据不换路由。
2. 密钥安全 —— 密钥解密只在后端完成，企业密钥永不落入浏览器端。
3. 计费分离 —— BYOK 不扣平台积分（企业自费），平台池正常 ledger hold→commit/release，
   判定统一在 ledger 层，避免双写漂移。
4. 商务可配置 —— 降级语义由 ``extensions_config.json`` 的 ``byok`` 声明（trusted 配置）决定。

各 nodeType 是否允许 BYOK、支持哪些 provider、解析策略与降级语义，
由 ``extensions_config.json`` → ``pipeline.nodeRegistry[*].byok`` 配置驱动，
运行期可 ``reload_node_registry()`` 热更新。对齐见 docs/XINWOREN_AGENT_SKILL_ARCHITECTURE.md 第十一章。

加密/解密契约（与前端口径一致，详见 frontend/src/lib/crypto/aes.ts）：
- 存储格式：``{iv}.{tag}.{ciphertext}``（均为 hex，GCM tag 16 字节）
- 密钥派生：``sha256(BYOK_ENCRYPTION_KEY || INSFORGE_SERVICE_ROLE_KEY)``（32 字节 AES-256 key）
- 算法：AES-256-GCM（iv 16 字节）

Layer 2 已点亮：``resolve()`` 现从 ``user_api_keys`` 表读加密密钥（走 InsForge
PostgREST 服务角色，绕过 RLS），AES-256-GCM 解密后返回请求级 ``CredentialRef``；
解码失败/无密钥/节点未开 BYOK 一律返回 ``None`` → 调用方回退平台池（零回归）。
"""

from __future__ import annotations

import hashlib
import json
import logging
import os
from pathlib import Path

from cryptography.hazmat.primitives.ciphers import Cipher, algorithms, modes

from . import pipeline_insforge

logger = logging.getLogger("gateway.credential_resolver")

# ── 配置热更新缓存（mtime-based，零重启生效）──
# 缓存 extensions_config.json 的内容和文件 mtime，每次读取时检查 mtime，
# 文件修改后自动重新加载。避免每次请求都读文件的性能开销，同时保持热更新能力。
_config_cache: dict[str, object] = {"path": None, "mtime": None, "data": None}


def _load_extensions_config_cached() -> dict:
    """带 mtime 缓存的 extensions_config.json 加载器。

    热更新机制：
    - 首次调用：读取文件，缓存内容和 mtime
    - 后续调用：检查文件 mtime，未修改则返回缓存，已修改则重新加载
    - 文件不存在：返回空 dict（零回归，等价配置缺失）
    - 解析失败：返回空 dict（配置损坏不阻断解析，视为 BYOK 关闭）

    线程安全：CPython GIL 保证简单赋值原子性，无需额外锁。
    """
    global _config_cache
    cfg_path = _find_extensions_config()
    if cfg_path is None:
        # 文件不存在时清空缓存，返回空 dict
        if _config_cache["path"] is not None:
            _config_cache = {"path": None, "mtime": None, "data": None}
        return {}

    try:
        current_mtime = cfg_path.stat().st_mtime
    except OSError:
        return {}

    # 缓存命中：路径和 mtime 都未变 → 直接返回缓存
    if _config_cache["path"] == str(cfg_path) and _config_cache["mtime"] == current_mtime and _config_cache["data"] is not None:
        return _config_cache["data"]  # type: ignore[return-value]

    # 缓存未命中或文件已修改 → 重新读取
    try:
        with open(cfg_path, encoding="utf-8") as f:
            data = json.load(f) or {}
        _config_cache = {"path": str(cfg_path), "mtime": current_mtime, "data": data}
        logger.info("extensions_config.json (re)loaded: path=%s, mtime=%s", cfg_path, current_mtime)
        return data
    except Exception as e:  # noqa: BLE001 — 配置损坏不阻断解析，视为 BYOK 关闭
        logger.warning("Failed to load extensions_config.json: %s", e)
        # 解析失败时保留旧缓存（如果有），避免频繁重读
        if _config_cache["data"] is not None:
            return _config_cache["data"]  # type: ignore[return-value]
        return {}


class CredentialResolverError(Exception):
    """凭据解析失败（密钥缺失 / 未授权 / 解密失败等）。"""


class CredentialRef:
    """一份已解析的请求级凭据。

    仅存活于当前请求作用域：解析完成后由调用方注入到具体厂商请求，
    用完即弃，不落入日志、资产元数据或数据库保留字段。
    """

    __slots__ = ("provider", "api_key", "base_url", "source")

    def __init__(
        self,
        provider: str,
        api_key: str,
        base_url: str,
        source: str = "byok",
    ) -> None:
        self.provider = provider
        self.api_key = api_key  # 已解密，仅存活于当前请求作用域
        self.base_url = base_url
        self.source = source  # "byok"（企业自有） / "platform"（平台池）


def _find_extensions_config() -> Path | None:
    """定位 extensions_config.json（与 pipeline_executor._find_extensions_config 同一查找面）。"""
    env_path = os.environ.get("DEER_FLOW_EXTENSIONS_CONFIG_PATH")
    if env_path and os.path.exists(env_path):
        return Path(env_path)
    root = Path.cwd().resolve()
    for cand in (root / "extensions_config.json", root.parent / "extensions_config.json", Path("/app/extensions_config.json")):
        if cand.is_file():
            return cand
    return None


def _load_byok_cfg(node_type: str) -> dict:
    """读取 extensions_config.json 中 ``pipeline.nodeRegistry[node_type].byok`` 声明。

    使用带 mtime 缓存的加载器（``_load_extensions_config_cached``），
    文件修改后自动热更新，无需重启进程。

    解析失败/未声明/类型不符 → 空 dict（等价 BYOK 关闭，零回归）。
    """
    data = _load_extensions_config_cached()
    spec = ((data.get("pipeline") or {}).get("nodeRegistry") or {}).get(node_type)
    byok = (spec or {}).get("byok") if isinstance(spec, dict) else None
    return byok if isinstance(byok, dict) else {}


def _encryption_key() -> bytes | None:
    """派生 AES-256 加密 key（与前端口径一致：sha256(BYOK_ENCRYPTION_KEY || INSFORGE_SERVICE_ROLE_KEY)）。

    环境变量缺省时回退 InsForge service role key（pipeline_insforge._get_config 默认值），
    与前端口径完全对齐；均缺失 → None（本进程不做解密，一律回退平台池）。
    """
    key = os.environ.get("BYOK_ENCRYPTION_KEY") or os.environ.get("INSFORGE_SERVICE_ROLE_KEY")
    if not key:
        try:
            _, srk, _ = pipeline_insforge._get_config()
            key = srk
        except Exception as e:  # noqa: BLE001
            logger.warning("BYOK encryption key unavailable: %s", e)
            return None
    return hashlib.sha256(key.encode("utf-8")).digest()


def _decrypt_aes256_gcm(stored: str, enc_key: bytes) -> str:
    """解 AES-256-GCM 密文（存储格式 ``{iv}.{tag}.{ciphertext}``，均为 hex）。"""
    parts = stored.split(".")
    if len(parts) != 3 or not all(parts):
        raise CredentialResolverError("Invalid encrypted data format")
    iv, tag, ciphertext = parts
    decipher = Cipher(
        algorithms.AES(enc_key),
        modes.GCM(bytes.fromhex(iv), bytes.fromhex(tag)),
    ).decryptor()
    plain = decipher.update(bytes.fromhex(ciphertext)) + decipher.finalize()
    return plain.decode("utf-8")


def _parse_custom_base_url(label: str) -> str | None:
    """从 user_api_keys.label 解析自定义 provider 的 base_url。

    前端自定义 provider 保存时，label 格式为：``custom:{base_url}|{用户标签}``
    例如：``custom:https://api.example.com/v1|My Custom LLM``

    解析规则：
    - label 以 ``custom:`` 开头时，提取 ``|`` 之前的部分作为 base_url
    - label 不以 ``custom:`` 开头时，返回 None（官方 provider，使用硬编码 base_url）
    - 解析失败时返回 None（零回归，回退官方 provider 逻辑）

    Returns:
        base_url 字符串，或 None（非自定义 provider）
    """
    if not label or not label.startswith("custom:"):
        return None
    try:
        # 格式：custom:{base_url}|{用户标签}
        rest = label[len("custom:") :]
        # 取第一个 | 之前的部分作为 base_url
        base_url = rest.split("|", 1)[0].strip()
        if base_url and (base_url.startswith("http://") or base_url.startswith("https://")):
            return base_url
        return None
    except Exception:
        return None


class CredentialResolver:
    """BYOK 凭据解析器。

    Layer 2 已点亮：``resolve()`` 校验节点 BYOK 白名单 → PostgREST 读 ``user_api_keys``
    → AES-256-GCM 解密 → 返回请求级 ``CredentialRef``。任一环节失败均返回 ``None``，
    调用方回退平台密钥池，保证零回归。
    """

    def __init__(self, db=None) -> None:
        """db: 可选的凭据存储适配器（预留；默认走 pipeline_insforge 服务角色通道）。"""
        self.db = db

    def is_byok_enabled(self, node_type: str, provider: str) -> bool:
        """node_type 是否开启 BYOK 且 provider 在白名单内（读取 nodeRegistry.byok）。

        未配置 byok 声明 / byok 关闭 / provider 不在白名单 → False（走平台池）。
        """
        byok = _load_byok_cfg(node_type)
        if not byok or not byok.get("enabled"):
            return False
        providers = byok.get("providers") or []
        return bool(providers) and provider in providers

    async def resolve(self, user_id: str, provider: str, node_type: str) -> CredentialRef | None:
        """resolve(user_id, provider, node_type) -> CredentialRef | None。

        无密钥 / provider 未授权 / 节点未开 BYOK / 解密失败 → None（调用方回退平台池）。
        """
        if not user_id or not provider:
            return None
        if not self.is_byok_enabled(node_type, provider):
            return None
        enc_key = _encryption_key()
        if enc_key is None:
            return None
        try:
            rows = await pipeline_insforge._request(
                "GET",
                "user_api_keys",
                query={
                    "user_id": f"eq.{user_id}",
                    "provider": f"eq.{provider}",
                    "select": "encrypted_key,label",
                    "order": "updated_at.desc",
                    "limit": "1",
                },
            )
        except Exception as e:  # noqa: BLE001 — 查询失败不阻断节点，回退平台池
            logger.warning("BYOK user_api_keys query failed for %s/%s: %s", user_id, provider, e)
            return None
        if not rows:
            logger.info("BYOK no user key for %s/%s (node=%s)", user_id, provider, node_type)
            return None
        stored = rows[0].get("encrypted_key")
        if not stored:
            return None
        try:
            api_key = _decrypt_aes256_gcm(stored, enc_key)
        except Exception as e:  # noqa: BLE001 — 解密失败（含旧明文数据）回退平台池
            logger.warning("BYOK decrypt failed for %s/%s: %s", user_id, provider, e)
            return None
        if not api_key:
            return None

        # 解析自定义 provider 的 base_url（label 格式：custom:{base_url}|{用户标签}）
        label = rows[0].get("label") or ""
        custom_base_url = _parse_custom_base_url(label)
        if custom_base_url:
            logger.info("BYOK custom provider base_url resolved: provider=%s, base_url=%s", provider, custom_base_url)

        return CredentialRef(provider=provider, api_key=api_key, base_url=custom_base_url or "", source="byok")
