"""权限分级引擎 (Policy Engine)。

三级权限: 绿色自动 / 黄色确认 / 红色强验证。
关键点: 分级由确定性代码判定, 模型无权自行"降级", 也不能通过对话改变阈值。
"""
from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import Dict, List, Optional

from . import config


class Tier(str, Enum):
    GREEN = "green"
    YELLOW = "yellow"
    RED = "red"


TIER_LABEL = {
    Tier.GREEN: "绿色 · 自动执行",
    Tier.YELLOW: "黄色 · 用户确认",
    Tier.RED: "红色 · 强验证",
}
TIER_ORDER = {Tier.GREEN: 0, Tier.YELLOW: 1, Tier.RED: 2}

# 动作 -> 固定级别 (金额相关的动作在 classify 中动态判定)
STATIC_TIERS: Dict[str, Tier] = {
    # 纯查询类 —— 绿色
    "query_balance": Tier.GREEN,
    "query_txn": Tier.GREEN,
    "analyze_bills": Tier.GREEN,
    "detect_anomaly": Tier.GREEN,
    "query_wealth": Tier.GREEN,
    "recommend_wealth": Tier.GREEN,
    "quote_wealth": Tier.GREEN,
    "compare_wealth": Tier.GREEN,
    "plan_budget": Tier.GREEN,
    "list_subscriptions": Tier.GREEN,
    "query_cards": Tier.GREEN,
    "query_calendar": Tier.GREEN,
    "resolve_contact": Tier.GREEN,
    "compute": Tier.GREEN,
    # 需确认 —— 黄色
    "split_aa": Tier.YELLOW,
    "lock_savings": Tier.YELLOW,
    "apply_physical_card": Tier.YELLOW,
    "apply_virtual_card": Tier.YELLOW,
    "set_txn_limit": Tier.YELLOW,
    "cancel_subscription": Tier.YELLOW,
    "redeem_wealth": Tier.YELLOW,
    "schedule_order": Tier.YELLOW,
    # 强验证 —— 红色
    "subscribe_wealth": Tier.RED,
    "freeze_card": Tier.RED,
    "unfreeze_card": Tier.RED,
    "adjust_card_limit": Tier.RED,
    "change_password": Tier.RED,
}

# 资金类动作 (金额动态判定)
AMOUNT_ACTIONS = {"transfer"}

# 红色操作可选的多因子认证方式
MFA_FOR_ACTION = {
    "transfer": ["face", "sms"],
    "split_aa": ["face", "sms"],
    "subscribe_wealth": ["face", "sms", "ushield"],
    "redeem_wealth": ["sms"],
    "freeze_card": ["face", "sms"],
    "unfreeze_card": ["face", "sms"],
    "adjust_card_limit": ["face", "ushield"],
    "change_password": ["face", "sms", "ushield"],
}


@dataclass
class PolicyDecision:
    action: str
    tier: Tier
    reason: str
    requires_confirmation: bool
    requires_mfa: bool
    mfa_methods: List[str] = field(default_factory=list)
    review_flag: bool = False
    detail: Dict[str, object] = field(default_factory=dict)

    def to_dict(self) -> dict:
        return {
            "action": self.action,
            "tier": self.tier.value,
            "tier_label": TIER_LABEL[self.tier],
            "reason": self.reason,
            "requires_confirmation": self.requires_confirmation,
            "requires_mfa": self.requires_mfa,
            "mfa_methods": self.mfa_methods,
            "review_flag": self.review_flag,
            "detail": self.detail,
        }


def classify(action: str, args: Optional[dict] = None, context: Optional[dict] = None) -> PolicyDecision:
    """对单个动作做出权限判定。context 需提供 daily_transfer_total (今日转账累计)。"""
    args = args or {}
    context = context or {}

    if action in AMOUNT_ACTIONS:
        amount = float(args.get("amount") or 0.0)
        daily = float(context.get("daily_transfer_total") or 0.0)
        projected = daily + amount * int(args.get("payee_count", 1))
        label = "转账" if action == "transfer" else "AA 收款拆分"
        detail = {
            "amount": amount,
            "daily_before": daily,
            "daily_projected": round(projected, 2),
            "limit": config.YELLOW_TRANSFER_LIMIT,
        }
        if args.get("when"):
            # 预约/定时转账: 不占用今日额度, 按单笔金额判定
            if amount > config.YELLOW_TRANSFER_LIMIT:
                return PolicyDecision(action, Tier.RED,
                                      f"预约转账单笔 {amount:,.2f} 元超过 {config.YELLOW_TRANSFER_LIMIT:.0f} 元, 升级为红色强验证",
                                      True, True, MFA_FOR_ACTION.get(action, config.MFA_METHODS),
                                      amount >= config.RED_SINGLE_AMOUNT, detail)
            return PolicyDecision(action, Tier.YELLOW,
                                  f"预约转账 {amount:,.2f} 元, 未超过免验额度, 需你确认后预约",
                                  True, False, [], False, detail)
        if projected > config.YELLOW_TRANSFER_LIMIT:
            review = amount >= config.RED_SINGLE_AMOUNT
            reason = (
                f"{label}日累计将达 {round(projected, 2)} 元, 超过 {config.YELLOW_TRANSFER_LIMIT:.0f} 元免验阈值, "
                f"升级为红色强验证"
            )
            if review:
                reason += f"; 单笔金额 ≥ {config.RED_SINGLE_AMOUNT:.0f} 元, 建议人工复核"
            return PolicyDecision(action, Tier.RED, reason, True, True,
                                  MFA_FOR_ACTION.get(action, config.MFA_METHODS), review, detail)
        return PolicyDecision(
            action, Tier.YELLOW,
            f"{label}日累计 {round(projected, 2)} 元, 在 {config.YELLOW_TRANSFER_LIMIT:.0f} 元免验额度内, 需你确认后执行",
            True, False, [], False, detail,
        )

    tier = STATIC_TIERS.get(action)
    if tier is None:
        # 未知动作默认按最高风险处理 —— 失败即关闭 (fail-closed)
        return PolicyDecision(action, Tier.RED, "未登记的动作类型, 按最严格策略处理",
                              True, True, config.MFA_METHODS, True, {})

    if tier is Tier.GREEN:
        return PolicyDecision(action, Tier.GREEN, "纯查询类操作, 不改变资金与账户状态, 直接执行",
                              False, False, [], False, {})
    if tier is Tier.YELLOW:
        return PolicyDecision(action, Tier.YELLOW, "会改变账户或业务状态, 执行前需你明确确认",
                              True, False, [], False, {})
    return PolicyDecision(action, Tier.RED,
                          "高风险操作, 须通过人脸识别 / 短信验证码 / U 盾等多因子认证",
                          True, True, MFA_FOR_ACTION.get(action, config.MFA_METHODS), False, {})


def max_tier(actions: List[str], args_by_action: Optional[Dict[str, dict]] = None,
             context: Optional[dict] = None) -> PolicyDecision:
    """一个计划内所有动作取最严格的那一个作为整体级别。"""
    best: Optional[PolicyDecision] = None
    args_by_action = args_by_action or {}
    for a in actions:
        d = classify(a, args_by_action.get(a), context)
        if best is None or TIER_ORDER[d.tier] > TIER_ORDER[best.tier]:
            best = d
    return best or PolicyDecision("noop", Tier.GREEN, "无动作", False, False, [], False, {})
