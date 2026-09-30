"""
ContentGuardrail — 内容安全护栏

轻量级内容安全检查，用于 AI 生成内容的输出过滤。
基于关键词匹配，后续可升级为 AI 审核模型。

设计原则：
- 默认"标记"模式（记录日志，不阻止），避免误杀
- 可配置为"阻止"模式（替换为安全提示）
- 规则可扩展，按内容类型分类
- 不影响正常内容生成（性能开销 < 1ms）

Phase 4 实施：先建骨架，默认标记模式，后续根据运营需求调整。
"""

from __future__ import annotations

import logging
import re
from dataclasses import dataclass, field
from enum import StrEnum

logger = logging.getLogger("content_guardrail")


class GuardrailAction(StrEnum):
    """护栏动作。"""

    LOG = "log"  # 仅记录日志（默认）
    REDACT = "redact"  # 替换敏感词为 ***
    BLOCK = "block"  # 阻止输出，返回安全提示


class ContentCategory(StrEnum):
    """内容分类。"""

    VIOLENCE = "violence"  # 暴力
    PORNOGRAPHY = "pornography"  # 色情/低俗
    POLITICS = "politics"  # 政治敏感
    PII = "pii"  # 个人隐私信息
    HATE_SPEECH = "hate_speech"  # 仇恨言论
    DRUGS = "drugs"  # 毒品/违禁品


@dataclass
class GuardrailRule:
    """单条护栏规则。"""

    category: ContentCategory
    pattern: str  # 正则表达式
    description: str = ""
    enabled: bool = True


@dataclass
class GuardrailResult:
    """护栏检查结果。"""

    passed: bool
    action: GuardrailAction
    violations: list[dict] = field(default_factory=list)  # [{category, matched, position}]
    original_text: str = ""
    filtered_text: str = ""

    @property
    def has_violation(self) -> bool:
        return len(self.violations) > 0

    @property
    def violation_categories(self) -> list[str]:
        return list({v["category"] for v in self.violations})


# 默认规则集（创作平台运营版，2026-09-14 调优）
# 调优原则：
# 1. PII 类规则保持严格（手机号/身份证/邮箱必须拦截）
# 2. 暴力/色情类规则只匹配极端词汇，避免误杀创作内容
# 3. 政治敏感类默认不启用（创作平台内容多样，避免过度审查）
# 4. 毒品类保持严格
# 5. 新增：银行卡号、IP 地址、URL（防钓鱼）
DEFAULT_RULES: list[GuardrailRule] = [
    # PII - 手机号（严格）
    GuardrailRule(
        category=ContentCategory.PII,
        pattern=r"1[3-9]\d{9}",
        description="手机号码",
    ),
    # PII - 身份证（严格）
    GuardrailRule(
        category=ContentCategory.PII,
        pattern=r"[1-9]\d{5}(18|19|20)\d{2}(0[1-9]|1[0-2])(0[1-9]|[12]\d|3[01])\d{3}[\dXx]",
        description="身份证号",
    ),
    # PII - 邮箱（严格）
    GuardrailRule(
        category=ContentCategory.PII,
        pattern=r"[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}",
        description="邮箱地址",
    ),
    # PII - 银行卡号（新增，严格）
    GuardrailRule(
        category=ContentCategory.PII,
        pattern=r"\b\d{16,19}\b",
        description="银行卡号",
    ),
    # PII - IP 地址（新增，防钓鱼）
    GuardrailRule(
        category=ContentCategory.PII,
        pattern=r"\b(?:\d{1,3}\.){3}\d{1,3}\b",
        description="IP 地址",
    ),
    # 暴力 - 极端暴力描述（只匹配极端词汇，避免误杀）
    GuardrailRule(
        category=ContentCategory.VIOLENCE,
        pattern=r"(杀人|碎尸|肢解|虐杀|酷刑|血腥|砍头|剖腹|分尸|焚尸)",
        description="极端暴力描述",
    ),
    # 色情 - explicit（只匹配极端词汇）
    GuardrailRule(
        category=ContentCategory.PORNOGRAPHY,
        pattern=r"(性交|做爱|口交|肛交|强奸|轮奸|迷奸|奸淫)",
        description="色情低俗内容",
    ),
    # 毒品（严格）
    GuardrailRule(
        category=ContentCategory.DRUGS,
        pattern=r"(海洛因|冰毒|摇头丸|K粉|大麻|可卡因|制毒|吸毒|贩毒|罂粟)",
        description="毒品/违禁品",
    ),
    # 仇恨言论（新增，基础版）
    GuardrailRule(
        category=ContentCategory.HATE_SPEECH,
        pattern=r"(去死|垃圾人|废物|脑残|智障|神经病)",
        description="仇恨/侮辱言论",
    ),
    # 政治敏感（默认禁用，创作平台内容多样）
    GuardrailRule(
        category=ContentCategory.POLITICS,
        pattern=r"(政治敏感|反党|反政府|颠覆国家)",
        description="政治敏感内容",
        enabled=False,  # 默认禁用，运营需要时开启
    ),
]


class ContentGuardrail:
    """内容安全护栏。

    Usage:
        guardrail = ContentGuardrail(action=GuardrailAction.LOG)
        result = guardrail.check(text)
        if result.has_violation:
            logger.warning("Content violation: %s", result.violation_categories)
            safe_text = result.filtered_text  # 如果 action=REDACT
    """

    def __init__(
        self,
        action: GuardrailAction = GuardrailAction.LOG,
        rules: list[GuardrailRule] | None = None,
        custom_patterns: list[str] | None = None,
    ):
        """
        Args:
            action: 默认动作（LOG/REDACT/BLOCK）
            rules: 自定义规则集，None 则使用默认规则
            custom_patterns: 额外的自定义正则模式
        """
        self.action = action
        self.rules = rules or DEFAULT_RULES
        self.custom_patterns = custom_patterns or []
        self._compiled: list[tuple[GuardrailRule, re.Pattern]] = []
        self._compile_rules()

    def _compile_rules(self):
        """预编译正则表达式。"""
        self._compiled = []
        for rule in self.rules:
            if rule.enabled:
                try:
                    self._compiled.append((rule, re.compile(rule.pattern, re.IGNORECASE)))
                except re.error as e:
                    logger.warning("Invalid guardrail pattern for %s: %s", rule.category, e)
        # 自定义模式
        for i, pattern in enumerate(self.custom_patterns):
            try:
                rule = GuardrailRule(
                    category=ContentCategory.PII,  # 自定义默认归为 PII
                    pattern=pattern,
                    description=f"custom_{i}",
                )
                self._compiled.append((rule, re.compile(pattern, re.IGNORECASE)))
            except re.error as e:
                logger.warning("Invalid custom guardrail pattern: %s", e)

    def check(self, text: str, action: GuardrailAction | None = None) -> GuardrailResult:
        """检查文本内容。

        Args:
            text: 待检查的文本
            action: 本次检查的动作，None 则使用默认动作

        Returns:
            GuardrailResult 检查结果
        """
        if not text:
            return GuardrailResult(passed=True, action=action or self.action, original_text=text, filtered_text=text)

        effective_action = action or self.action
        violations: list[dict] = []
        filtered_text = text

        for rule, pattern in self._compiled:
            for match in pattern.finditer(text):
                violations.append(
                    {
                        "category": rule.category.value,
                        "matched": match.group()[:50],  # 截断避免日志过大
                        "position": match.start(),
                        "description": rule.description,
                    }
                )
                if effective_action == GuardrailAction.REDACT:
                    filtered_text = filtered_text[: match.start()] + "***" + filtered_text[match.end() :]

        passed = len(violations) == 0 or effective_action != GuardrailAction.BLOCK

        if effective_action == GuardrailAction.BLOCK and violations:
            filtered_text = "[内容已被安全护栏拦截，请调整输入后重试]"

        if violations:
            logger.info(
                "ContentGuardrail: %d violation(s) in %d chars, categories=%s, action=%s",
                len(violations),
                len(text),
                [v["category"] for v in violations],
                effective_action.value,
            )

        return GuardrailResult(
            passed=passed,
            action=effective_action,
            violations=violations,
            original_text=text,
            filtered_text=filtered_text,
        )

    def add_rule(self, rule: GuardrailRule):
        """动态添加规则。"""
        self.rules.append(rule)
        if rule.enabled:
            try:
                self._compiled.append((rule, re.compile(rule.pattern, re.IGNORECASE)))
            except re.error as e:
                logger.warning("Invalid guardrail pattern: %s", e)


# 全局单例
_guardrail: ContentGuardrail | None = None


def init_guardrail(action: GuardrailAction = GuardrailAction.LOG, **kwargs) -> ContentGuardrail:
    """初始化全局内容护栏。"""
    global _guardrail
    _guardrail = ContentGuardrail(action=action, **kwargs)
    logger.info("ContentGuardrail initialized (action=%s, rules=%d)", action.value, len(_guardrail.rules))
    return _guardrail


def get_guardrail() -> ContentGuardrail:
    """获取全局内容护栏。"""
    global _guardrail
    if _guardrail is None:
        _guardrail = ContentGuardrail()  # 默认 LOG 模式
    return _guardrail
