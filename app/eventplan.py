"""跨场景联动的"方案 → 地址 → 下单"三步对话。

原则: 不替用户做决定。先给选项, 选完再确认配送地址, 确认后才真正落单。
"""
from __future__ import annotations

import re
from datetime import date, timedelta
from typing import Optional, Tuple

from . import planner
from .bank import TODAY, D

REGISTERED_ADDRESS = "北京市朝阳区XXX街道"

YES = ("是", "对", "是的", "确认", "用这个", "默认", "嗯", "可以", "好的")


def _menu(title: str, days: int) -> str:
    return (
        f"距离「{title}」还有 {days} 天，现在准备还来得及。\n\n"
        "我建议这样安排，你选一个（也可以直接说别的）：\n"
        "  ① 订鲜花：生日前 2 天送到，约 300 元\n"
        "  ② 订蛋糕：生日前 1 天送到，约 200 元\n"
        "  ③ 转个红包给 TA\n"
        "  ④ 先锁定 1000 元活期，确保到时候有钱花\n"
        "  ⑤ 其他安排（你说，我来办）\n\n"
        "回序号或直接说要哪个都行。"
    )


def propose(ledger, session, intent) -> str:
    event = planner._pick_event(ledger, str(intent.slots.get("text") or ""))
    day = event.day if event else TODAY + timedelta(days=18)
    title = event.title if event else "爱人生日"
    session.context["event"] = {"title": title, "day": day.isoformat(), "stage": "choose"}
    return _menu(title, (day - TODAY).days)


def _detail(text: str) -> str:
    parts = []
    m = re.search(r"(\d{1,2})\s*寸", text)
    if m:
        parts.append(f"{m.group(1)} 寸")
    for taste in ("巧克力", "水果", "奶油", "慕斯", "芝士", "抹茶"):
        if taste in text:
            parts.append(taste)
    if "少糖" in text or "不要太甜" in text:
        parts.append("少糖")
    return " · ".join(parts)


def followup(ledger, session, text: str) -> Optional[Tuple[str, Optional[dict]]]:
    """返回 (回复文本, 可选的新状态)。不涉及事件时返回 None。"""
    ev = session.context.get("event")
    if not ev:
        return None
    t = (text or "").strip()
    stage = ev.get("stage")

    if stage == "choose":
        kind = None
        if "鲜花" in t or t in ("1", "①"):
            kind = "鲜花"
        elif "蛋糕" in t or t in ("2", "②"):
            kind = "蛋糕"
        if kind:
            ev.update(stage="address", kind=kind, detail=_detail(t))
            return (f"好，{kind}我来安排。\n\n"
                    f"收货地址确认一下：\n"
                    f"  1️⃣ 是，用账户登记地址（{REGISTERED_ADDRESS}）\n"
                    f"  2️⃣ 添加新地址", None)
        if "锁定" in t or t in ("4", "④"):
            session.context.pop("event", None)
            res = ledger.lock_savings(D(1000), 30)
            return (f"已锁定 {res['amount']} 元到储蓄账户，锁定期 {res['days']} 天"
                    f"（至 {res['unlock_date']}），到时候要给 TA 用随时能取。", None)
        if "红包" in t or "转账" in t or t in ("3", "③"):
            session.context.pop("event", None)
            return ("好，转多少、转给谁？说一句就行，比如「给李静转 520 元」，"
                    "我会先给你确认卡，确认后才动钱。", None)
        if "其他" in t or t in ("5", "⑤"):
            return ("好，你说怎么安排——比如「订个蛋糕，10 寸巧克力，少糖」"
                    "「把明天的鲜花改成后天送」「先帮我算算这个月还能拿出多少」。", None)
        # 没命中任何选项: 释放上下文, 交还给常规意图理解, 不劫持后续对话
        session.context.pop("event", None)
        return None

    if stage == "address":
        kind = ev.get("kind") or "蛋糕"
        detail = ev.get("detail") or ""
        if "新地址" in t or "添加" in t or t in ("2", "②"):
            ev["stage"] = "new_address"
            return ("好，请把新地址发给我（例如：上海市浦东新区世纪大道 100 号），"
                    "我只用于这次配送。", None)
        if any(w == t or w in t for w in YES) or t in ("1", "①"):
            return _place(ledger, session, ev, kind, detail, REGISTERED_ADDRESS), None
        if len(t) >= 6 and not any(k in t for k in ("地址", "是", "确认")):
            return _place(ledger, session, ev, kind, detail, t), None
        return ("请回「1」使用登记地址，或回「2」添加新地址。", None)

    if stage == "new_address":
        if len(t) >= 6:
            kind = ev.get("kind") or "蛋糕"
            return _place(ledger, session, ev, kind, ev.get("detail") or "", t), None
        return ("地址有点短，能再具体一点吗？比如「上海市浦东新区世纪大道 100 号」。", None)

    return None


def _place(ledger, session, ev: dict, kind: str, detail: str, address: str) -> str:
    """地址确认后才真正落单。"""
    day = date.fromisoformat(ev["day"])
    deliver = day - timedelta(days=2 if kind == "鲜花" else 1)
    amount = D(300 if kind == "鲜花" else 200)
    order = ledger.schedule_order(kind, amount, deliver, address)
    session.context.pop("event", None)
    note = f"（{detail}）" if detail else ""
    return (f"已为你预约：{kind}{note} {amount} 元\n"
            f"  · 配送日期：{deliver.isoformat()}\n"
            f"  · 收货地址：{address}\n"
            f"  · 订单号：{order.id}\n\n"
            f"还需要加一句祝福卡吗？或者再安排别的（比如再订鲜花）说一声。")
