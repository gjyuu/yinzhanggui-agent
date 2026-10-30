"""多渠道适配层: 把 Web / APP / IM 的输入归一化到同一套执行引擎。

赛题要求"用户可通过 APP、IM 等渠道与 Agent 联通"。渠道差异只体现在
输入形态与渲染方式上, 权限、风控、审计完全共用同一条链路 —— 换渠道不会绕过风控。

IM 渠道要点: 没有按钮, 用纯文本完成"确认/取消/输验证码"三种交互。
"""
from __future__ import annotations

import re
from typing import Dict, List

from . import executor

APPROVE_WORDS = {"确认", "确认执行", "确定", "是", "好的", "可以", "y", "yes", "ok"}
REJECT_WORDS = {"取消", "不用了", "不要", "算了", "否", "n", "no", "abort"}
RESUME_WORDS = {"继续", "接着来", "恢复"}

GATE_STATUS = ("awaiting_confirm", "awaiting_mfa")


def _plain(text: str) -> str:
    """把 Web 端的富文本回复压平成 IM 友好文本。

    只做两件事: 去掉我们自己生成的成对粗体记号、折叠多余空行。
    绝不能对 * 和 _ 做单字符清洗 —— 手机号掩码 139****3382 与交易号 t_00125 里都有它们。
    """
    out = re.sub(r"\*\*(.+?)\*\*", r"\1", text or "")
    out = re.sub(r"(?m)^[>#]+\s*", "", out)
    out = re.sub(r"\n{3,}", "\n\n", out)
    return out.strip()


def _quick_replies(payload: dict) -> List[str]:
    status = payload.get("status")
    if status == "awaiting_confirm":
        reds = [p for p in payload.get("pending") or [] if p["tier"] == "red"]
        return ["确认执行", "取消"] + (["查看权限说明"] if reds else [])
    if status == "awaiting_mfa":
        return ["重新发送验证码", "取消"]
    if status == "paused":
        return ["继续", "取消"]
    return []


def _card_brief(payload: dict) -> str:
    cards = payload.get("pending") or []
    if not cards:
        return ""
    lines = ["\n需要你确认:"]
    for i, c in enumerate(cards, 1):
        tag = "🔴强验证" if c["tier"] == "red" else "🟡确认"
        lines.append(f"{i}. {tag} {c['title']}")
        for d in c.get("details", [])[:4]:
            lines.append(f"   {d['label']}: {d['value']}")
    return "\n".join(lines)


def handle(session_id: str, user_id: str, channel: str, text: str) -> dict:
    raw = (text or "").strip()
    key = raw.lower()
    session = executor.store.get(session_id)

    # IM 的"按钮"就是这几个词 —— 同样走服务端状态机, 不做客户端信任
    if key in APPROVE_WORDS and session.status in GATE_STATUS:
        payload = executor.confirm(session_id, "approve")
    elif key in REJECT_WORDS and session.status in GATE_STATUS:
        payload = executor.confirm(session_id, "reject")
    elif key in RESUME_WORDS and session.status == "paused":
        payload = executor.chat(session_id, "继续")
    elif session.status == "awaiting_mfa" and re.fullmatch(r"\d{6}", raw):
        payload = executor.verify_mfa(session_id, "sms", raw)
    else:
        payload = executor.chat(session_id, text)

    body = _plain(payload.get("reply", ""))
    if payload.get("status") == "awaiting_confirm":
        body += _card_brief(payload)
    if payload.get("status") == "awaiting_mfa":
        demo = (payload.get("mfa") or {}).get("demo_code")
        body += "\n请回复 6 位短信验证码完成强验证。"
        if demo:
            body += f" (演示环境验证码 {demo})"
    if payload.get("status") == "blocked":
        body += "\n(本次请求已被安全策略拦截, 未执行任何操作)"

    return {
        "channel": channel,
        "user_id": user_id,
        "session_id": payload["session_id"],
        "trace_id": payload.get("trace_id"),
        "status": payload.get("status"),
        "text": body,
        "quick_replies": _quick_replies(payload),
        "plan_size": len((payload.get("plan") or {}).get("nodes") or []),
        "tiers": sorted({p["tier"] for p in payload.get("pending") or []}),
        "latency_ms": payload.get("latency_ms"),
    }
