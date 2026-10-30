"""工具层 (Tool Registry) —— Agent 唯一可以触碰世界的接口。

每个工具都返回结构化的 ToolResult, 其中 facts 携带"事实集",
供幻觉防护模块在生成回复后做二次校验。
"""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date, datetime, timedelta
from decimal import Decimal
from typing import Dict, List, Optional

from . import config, security
from .bank import Contact, Ledger, LedgerError, TODAY, D


def money(x) -> str:
    return f"{float(x):,.2f}"


@dataclass
class ToolResult:
    ok: bool
    title: str
    detail: str
    data: dict = field(default_factory=dict)
    facts: dict = field(default_factory=dict)
    compensate: Optional[dict] = None


# ------------------------------------------------------------------ 解析助手
def _contact(ledger: Ledger, args: dict) -> Contact:
    name = args.get("contact_name") or ""
    c = ledger.find_contact(name)
    if not c:
        raise LedgerError(f"通讯录里没有找到「{name}」, 请确认收款人姓名或先添加收款人")
    return c


def _card(ledger: Ledger, args: dict):
    hint = args.get("card_hint") or ""
    cards = list(ledger.cards.values())
    if not hint:
        cards = [c for c in cards if not c.virtual]
        return cards[0]
    for c in cards:
        if hint in c.kind:
            return c
    raise LedgerError(f"没有找到匹配「{hint}」的卡片")


def _sub(ledger: Ledger, args: dict):
    ref = args.get("reference")
    if ref:
        for s in ledger.subscriptions.values():
            if ref in s.merchant or ref in s.category:
                return s
    if args.get("auto_pick_risky"):
        risky = [s for s in ledger.subscriptions.values() if s.risk == "可疑" and s.status == "生效中"]
        if risky:
            return sorted(risky, key=lambda s: s.amount, reverse=True)[0]
    raise LedgerError("无法确定要取消哪个订阅, 请告诉我订阅名称")


def _product(ledger: Ledger, args: dict):
    hint = args.get("product_hint") or ""
    if hint:
        for p in ledger.products.values():
            if hint in p.name:
                return p
    if args.get("product_id") and args["product_id"] in ledger.products:
        return ledger.products[args["product_id"]]
    raise LedgerError("无法确定要申购的产品, 请先让我做产品推荐")


# ================================================================== 各工具实现
def t_query_balance(ledger: Ledger, args: dict, ctx: dict) -> ToolResult:
    accs = list(ledger.accounts.values())
    main = ledger.main_account()
    total = sum((a.balance for a in accs if a.kind != "信用卡"), D(0))
    lines = [f"{a.name}(尾号 {a.tail}): {money(a.balance)} 元" for a in accs]
    return ToolResult(
        True, "查询余额",
        "  · " + "\n  · ".join(lines) + f"\n你的总资产(不含信用卡欠款)约 {money(total)} 元。",
        data={"accounts": [{"name": a.name, "tail": a.tail, "balance": money(a.balance), "currency": a.currency}
                           for a in accs]},
        facts={"amounts": [float(a.balance) for a in accs] + [float(total)],
               "tails": [a.tail for a in accs],
               "verified_lines": lines + [f"总资产约 {money(total)} 元"]},
    )


def t_query_txn(ledger: Ledger, args: dict, ctx: dict) -> ToolResult:
    days = int(args.get("days") or 30)
    txns = ledger.recent_txns(days)[-10:]
    lines = [f"{t.ts.strftime('%m-%d %H:%M')} {t.merchant} {'-' if t.direction=='out' else '+'}{money(t.amount)} 元 [{t.category}]"
             for t in txns]
    return ToolResult(True, "查询交易记录", "最近几笔流水:\n  · " + "\n  · ".join(lines) if lines else "暂无交易记录",
                      data={"count": len(txns)},
                      facts={"amounts": [float(t.amount) for t in txns], "verified_lines": lines})


def t_analyze_bills(ledger: Ledger, args: dict, ctx: dict) -> ToolResult:
    days = int(args.get("days") or 30)
    s = ledger.bill_summary(days)
    breakdown = s["breakdown"]
    top = breakdown[0] if breakdown else None
    lines = [f"近 {days} 天支出合计 {s['total_out']} 元, 共 {s['count']} 笔, 笔均 {s['avg']} 元"]
    lines += [f"{b['category']} {b['amount']} 元 占 {b['ratio']}%" for b in breakdown[:5]]
    trend = "上升" if s["mom_change_pct"] > 0 else "下降"
    lines.append(f"相比上一个 {days} 天区间, 支出{trend} {abs(s['mom_change_pct'])}%")
    if top:
        lines.append(f"最大支出类别是{top['category']}, 建议优先从这里优化")
    return ToolResult(True, f"账单分析(近 {days} 天)", "\n  · " + "\n  · ".join(lines),
                      data=s,
                      facts={"amounts": [float(b["amount"]) for b in breakdown]
                                        + [float(s["total_out"]), float(s["prev_total"]),
                                           float(s["avg"]), float(s["income"])]
                                        + [float(t["amount"]) for t in s["top_merchants"]],
                             "verified_lines": lines})


def t_detect_anomaly(ledger: Ledger, args: dict, ctx: dict) -> ToolResult:
    days = int(args.get("days") or 30)
    items = ledger.detect_anomalies(days)
    if not items:
        return ToolResult(True, "异常交易识别", f"近 {days} 天没有发现明显异常交易。", data={"items": []},
                          facts={"amounts": [], "verified_lines": [f"近 {days} 天无异常交易"]})
    lines = [f"[{i['level']}风险] {i['merchant']} {i['amount']} 元: {i['reason']}" for i in items]
    return ToolResult(True, "异常交易识别", f"发现 {len(items)} 处异常:\n  · " + "\n  · ".join(lines),
                      data={"items": items},
                      facts={"amounts": [float(i["amount"]) for i in items], "verified_lines": lines})


def t_resolve_contact(ledger: Ledger, args: dict, ctx: dict) -> ToolResult:
    c = _contact(ledger, args)
    return ToolResult(True, "确认收款人",
                      f"收款人: {c.name} ({c.relation}), 手机号 {c.phone}, {c.bank}",
                      data={"contact_id": c.id, "name": c.name, "relation": c.relation,
                            "phone": c.phone, "bank": c.bank},
                      facts={"verified_lines": [f"收款人 {c.name} {c.phone} {c.bank}"], "amounts": []})


def t_transfer(ledger: Ledger, args: dict, ctx: dict) -> ToolResult:
    c = _contact(ledger, args)
    amount = D(args.get("amount") or 0)
    when_txt = args.get("when")
    when = _parse_when(when_txt) if when_txt else None
    note = args.get("note") or ""
    txn = ledger.transfer(ledger.main_account().id, c, amount, note, when)
    if when and when > TODAY:
        detail = (f"已预约 {when.isoformat()} 向 {c.name}({c.phone}) 转账 {money(amount)} 元"
                  + (f", 备注「{note}」" if note else ""))
    else:
        detail = (f"已向 {c.name}({c.phone}) 转账 {money(amount)} 元" + (f", 备注「{note}」" if note else "")
                  + f"; 交易号 {txn.id}, 当前活期余额 {money(ledger.main_account().balance)} 元")
    return ToolResult(True, "转账", detail,
                      data={"txn_id": txn.id, "contact": c.name, "amount": money(amount),
                            "balance": money(ledger.main_account().balance)},
                      facts={"amounts": [float(amount), float(ledger.main_account().balance)],
                             "verified_lines": [detail]},
                      compensate={"action": "reverse_transfer", "args": {"txn_id": txn.id}})


def t_reverse_transfer(ledger: Ledger, args: dict, ctx: dict) -> ToolResult:
    rev = ledger.reverse_transfer(args["txn_id"])
    detail = f"已冲正, 资金 {money(rev.amount)} 元退回活期账户, 当前余额 {money(ledger.main_account().balance)} 元"
    return ToolResult(True, "撤销转账", detail,
                      data={"txn_id": rev.id},
                      facts={"amounts": [float(rev.amount), float(ledger.main_account().balance)],
                             "verified_lines": [detail]})


def t_split_aa(ledger: Ledger, args: dict, ctx: dict) -> ToolResult:
    c = _contact(ledger, args)
    total = D(args.get("total") or 0)
    n = int(args.get("payee_count") or 2)
    if total <= 0 or n < 2:
        raise LedgerError("AA 收款需要总金额大于 0 且人数不少于 2 人")
    each = (total / n).quantize(Decimal("0.01"))
    req_id = f"aa_{int(datetime.now().timestamp())}"
    detail = (f"已向 {c.name} 发起 AA 收款 {money(each)} 元 (总额 {money(total)} 元 / {n} 人), "
              f"收款单号 {req_id}; 对方确认后资金才会入账, 你现在没有实际支出。")
    return ToolResult(True, "AA 拆分收款", detail,
                      data={"request_id": req_id, "each": money(each), "total": money(total), "count": n},
                      facts={"amounts": [float(each), float(total)], "verified_lines": [detail]},
                      compensate={"action": "cancel_aa", "args": {"request_id": req_id}})


def t_cancel_aa(ledger: Ledger, args: dict, ctx: dict) -> ToolResult:
    detail = f"已撤销 AA 收款请求 {args['request_id']}, 该请求不再有效。"
    return ToolResult(True, "撤销 AA 收款", detail, data={}, facts={"verified_lines": [detail], "amounts": []})


def t_list_subscriptions(ledger: Ledger, args: dict, ctx: dict) -> ToolResult:
    subs = list(ledger.subscriptions.values())
    active = [s for s in subs if s.status == "生效中"]
    monthly = sum((s.amount if s.cycle == "月" else s.amount / 12 for s in active), D(0))

    def due_note(s) -> str:
        left = (s.next_charge - TODAY).days
        return f" ⏰{left} 天后扣款" if 0 <= left <= 3 else ""

    lines = [f"{s.merchant} {money(s.amount)} 元/{s.cycle} 下次 {s.next_charge.isoformat()}"
             + (" [可疑]" if s.risk == "可疑" else "") + due_note(s) for s in active]
    soon = [s for s in active if 0 <= (s.next_charge - TODAY).days <= 3]
    detail = (f"你有 {len(active)} 个生效中的订阅, 折算每月约 {money(monthly)} 元:\n  · "
              + "\n  · ".join(lines))
    if soon:
        soon_total = sum((s.amount for s in soon), D(0))
        detail += (f"\n  · 提醒: 3 天内将有 {len(soon)} 笔自动扣费, 合计 {money(soon_total)} 元, "
                   f"不想续费的现在说一声就能关")
    return ToolResult(True, "订阅与自动扣费", detail,
                      data={"items": [{"id": s.id, "merchant": s.merchant, "amount": money(s.amount),
                                       "cycle": s.cycle, "next": s.next_charge.isoformat(),
                                       "risk": s.risk, "status": s.status} for s in subs],
                            "monthly_total": money(monthly),
                            "due_soon": [s.id for s in soon]},
                      facts={"amounts": [float(s.amount) for s in active] + [float(monthly)]
                                        + [float(s.amount) for s in soon]
                                        + ([float(sum((x.amount for x in soon), D(0)))] if soon else []),
                             "verified_lines": lines})


def t_cancel_subscription(ledger: Ledger, args: dict, ctx: dict) -> ToolResult:
    s = _sub(ledger, args)
    ledger.cancel_subscription(s.id)
    detail = f"已取消 {s.merchant} 的自动续费 ({money(s.amount)} 元/{s.cycle}), 本期服务到期后不再扣款。"
    return ToolResult(True, "取消订阅", detail,
                      data={"id": s.id, "merchant": s.merchant},
                      facts={"amounts": [float(s.amount)], "verified_lines": [detail]},
                      compensate={"action": "restore_subscription", "args": {"sub_id": s.id}})


def t_restore_subscription(ledger: Ledger, args: dict, ctx: dict) -> ToolResult:
    s = ledger.subscriptions[args["sub_id"]]
    s.status, s.auto_renew = "生效中", True
    detail = f"已恢复 {s.merchant} 的自动续费。"
    return ToolResult(True, "恢复订阅", detail, data={}, facts={"verified_lines": [detail], "amounts": []})


def t_query_cards(ledger: Ledger, args: dict, ctx: dict) -> ToolResult:
    lines = [f"{c.kind}(尾号 {c.tail}) 状态 {c.status}"
             + (f", 额度 {money(c.credit_limit)} 元, 可用 {money(c.available)} 元" if c.kind == "信用卡" else
                f", 单日限额 {money(c.daily_limit)} 元")
             for c in ledger.cards.values()]
    return ToolResult(True, "卡片信息", "  · " + "\n  · ".join(lines),
                      data={"cards": [{"id": c.id, "kind": c.kind, "tail": c.tail, "status": c.status,
                                       "limit": money(c.credit_limit), "available": money(c.available),
                                       "daily_limit": money(c.daily_limit)} for c in ledger.cards.values()]},
                      facts={"amounts": [float(c.credit_limit) for c in ledger.cards.values()]
                                        + [float(c.daily_limit) for c in ledger.cards.values()]
                                        + [float(c.available) for c in ledger.cards.values()],
                             "tails": [c.tail for c in ledger.cards.values()],
                             "verified_lines": lines})


def t_freeze_card(ledger: Ledger, args: dict, ctx: dict) -> ToolResult:
    card = _card(ledger, args)
    ledger.set_card(card.id, status="已挂失")
    detail = f"已对 {card.kind}(尾号 {card.tail}) 办理挂失, 该卡立即停止支付与取现, 补卡可在 3 个工作日内完成。"
    return ToolResult(True, "卡片挂失", detail, data={"card_id": card.id},
                      facts={"tails": [card.tail], "verified_lines": [detail], "amounts": []},
                      compensate={"action": "unfreeze_card_inner", "args": {"card_id": card.id}})


def t_unfreeze_card(ledger: Ledger, args: dict, ctx: dict) -> ToolResult:
    card = _card(ledger, args)
    if card.status == "正常":
        raise LedgerError(f"{card.kind}(尾号 {card.tail}) 当前状态正常, 无需解挂")
    ledger.set_card(card.id, status="正常")
    detail = f"已解除 {card.kind}(尾号 {card.tail}) 的挂失, 卡片恢复正常使用。"
    return ToolResult(True, "卡片解挂", detail, data={"card_id": card.id},
                      facts={"tails": [card.tail], "verified_lines": [detail], "amounts": []},
                      compensate={"action": "unfreeze_card_inner", "args": {"card_id": card.id}})


def t_unfreeze_card_inner(ledger: Ledger, args: dict, ctx: dict) -> ToolResult:
    card = ledger.cards[args["card_id"]]
    ledger.set_card(card.id, status="正常")
    detail = f"已回退: {card.kind}(尾号 {card.tail}) 状态恢复为正常。"
    return ToolResult(True, "回退卡片状态", detail, data={}, facts={"verified_lines": [detail], "amounts": []})


def t_adjust_card_limit(ledger: Ledger, args: dict, ctx: dict) -> ToolResult:
    card = _card(ledger, args)
    card = [c for c in ledger.cards.values() if c.kind == "信用卡"][0]
    amount = D(args.get("amount") or 0)
    if amount <= 0:
        raise LedgerError("额度调整需要明确的目标额度")
    if amount > D(50000):
        raise LedgerError("单次调额上限为 50000 元")
    old = card.credit_limit
    ledger.set_card(card.id, credit_limit=amount,
                    available=card.available + (amount - old))
    detail = f"信用卡(尾号 {card.tail}) 额度已从 {money(old)} 元调整为 {money(amount)} 元。"
    return ToolResult(True, "额度调整", detail, data={"card_id": card.id, "limit": money(amount)},
                      facts={"amounts": [float(old), float(amount)], "tails": [card.tail],
                             "verified_lines": [detail]},
                      compensate={"action": "restore_limit", "args": {"card_id": card.id, "limit": float(old)}})


def t_restore_limit(ledger: Ledger, args: dict, ctx: dict) -> ToolResult:
    card = ledger.cards[args["card_id"]]
    ledger.set_card(card.id, credit_limit=D(args["limit"]))
    detail = f"已回退信用卡额度至 {money(args['limit'])} 元。"
    return ToolResult(True, "回退额度", detail, data={}, facts={"verified_lines": [detail], "amounts": []})


def t_apply_virtual_card(ledger: Ledger, args: dict, ctx: dict) -> ToolResult:
    card = ledger.apply_virtual_card()
    detail = f"已为你开通虚拟卡(尾号 {card.tail}), 单日限额 {money(card.daily_limit)} 元, 可在 App 卡片管理中查看。"
    return ToolResult(True, "申请虚拟卡", detail, data={"card_id": card.id, "tail": card.tail},
                      facts={"tails": [card.tail], "amounts": [float(card.daily_limit)],
                             "verified_lines": [detail]})


def t_set_txn_limit(ledger: Ledger, args: dict, ctx: dict) -> ToolResult:
    card = _card(ledger, args)
    amount = D(args.get("amount") or 0)
    if amount <= 0:
        raise LedgerError("交易限额需要明确金额")
    old = card.daily_limit
    ledger.set_card(card.id, daily_limit=amount)
    detail = f"{card.kind}(尾号 {card.tail}) 单日交易限额已从 {money(old)} 元调整为 {money(amount)} 元。"
    return ToolResult(True, "交易限额", detail, data={"card_id": card.id},
                      facts={"amounts": [float(old), float(amount)], "tails": [card.tail],
                             "verified_lines": [detail]},
                      compensate={"action": "restore_daily_limit",
                                  "args": {"card_id": card.id, "limit": float(old)}})


def t_restore_daily_limit(ledger: Ledger, args: dict, ctx: dict) -> ToolResult:
    card = ledger.cards[args["card_id"]]
    ledger.set_card(card.id, daily_limit=D(args["limit"]))
    detail = f"已回退单日限额至 {money(args['limit'])} 元。"
    return ToolResult(True, "回退限额", detail, data={}, facts={"verified_lines": [detail], "amounts": []})


def t_change_password(ledger: Ledger, args: dict, ctx: dict) -> ToolResult:
    r = ledger.change_password()
    detail = f"{args.get('target', '登录密码')}已修改成功 ({r['changed_at']}), 请使用新密码重新登录其他设备。"
    return ToolResult(True, "修改密码", detail, data=r, facts={"verified_lines": [detail], "amounts": []})


def t_query_wealth(ledger: Ledger, args: dict, ctx: dict) -> ToolResult:
    lines = [f"{p.name} [{p.risk}风险] 预期年化 {p.annual_rate}% 起投 {money(p.min_amount)} 元"
             + (f" 期限 {p.term_days} 天" if p.term_days else " 灵活申赎")
             for p in ledger.products.values()]
    holdings = [f"{ledger.products[h.product_id].name} 持有 {money(h.amount)} 元" for h in ledger.holdings.values()
                if h.status == "持有中"]
    detail = "在售产品:\n  · " + "\n  · ".join(lines)
    if holdings:
        detail += "\n你当前持有:\n  · " + "\n  · ".join(holdings)
    return ToolResult(True, "理财产品", detail,
                      data={"products": [{"id": p.id, "name": p.name, "risk": p.risk,
                                          "rate": p.annual_rate, "min": money(p.min_amount),
                                          "term": p.term_days} for p in ledger.products.values()],
                            "holdings": [{"id": h.id, "product": ledger.products[h.product_id].name,
                                          "amount": money(h.amount)} for h in ledger.holdings.values()
                                         if h.status == "持有中"]},
                      facts={"amounts": [float(p.min_amount) for p in ledger.products.values()]
                                        + [float(h.amount) for h in ledger.holdings.values()],
                             "verified_lines": lines})


def t_recommend_wealth(ledger: Ledger, args: dict, ctx: dict) -> ToolResult:
    hint = args.get("product_hint") or "稳"
    pref = "R1/R2" if hint == "稳" else "R3/R4"
    picks = [p for p in ledger.products.values() if p.risk in pref.split("/")]
    if not picks:
        picks = list(ledger.products.values())[:2]
    lines = [f"{p.name} [{p.risk}] 预期年化 {p.annual_rate}% — {p.desc}" for p in picks]
    detail = ("按你「" + ("稳健" if hint == "稳" else "收益优先") + "」的偏好, 建议关注:\n  · "
              + "\n  · ".join(lines) + "\n风险等级 R3 以上不保本, 请确认可承受本金波动。")
    return ToolResult(True, "产品推荐", detail, data={"picks": [p.id for p in picks]},
                      facts={"amounts": [float(p.min_amount) for p in picks], "verified_lines": lines})


def t_quote_wealth(ledger: Ledger, args: dict, ctx: dict) -> ToolResult:
    p = _product(ledger, args) if args.get("product_hint") else list(ledger.products.values())[0]
    amount = float(args.get("amount") or float(p.min_amount))
    term = p.term_days or 365
    expr = f"{amount} * {p.annual_rate} / 100 * {term} / 365"
    try:
        gain = security.sandbox.run(expr, {"amount": amount})
    except security.SandboxError as exc:
        raise LedgerError(f"收益试算脚本执行被沙箱拒绝: {exc}") from exc
    detail = (f"按 {money(amount)} 元买入 {p.name}, 持有 {term} 天, 按当前年化 {p.annual_rate}% 试算, "
              f"预期收益约 {money(gain)} 元 (计算公式 {expr}, 已在沙箱内计算, 不代表承诺收益)。")
    return ToolResult(True, "收益试算", detail,
                      data={"expr": expr, "gain": money(gain), "product": p.name},
                      facts={"amounts": [float(amount), round(float(gain), 2)],
                             "verified_lines": [detail]})


def t_subscribe_wealth(ledger: Ledger, args: dict, ctx: dict) -> ToolResult:
    p = _product(ledger, args)
    amount = D(args.get("amount") or 0)
    holding = ledger.subscribe_wealth(p.id, amount)
    detail = (f"已申购 {p.name}({p.risk}风险) {money(amount)} 元, 持仓编号 {holding.id}, "
              f"活期余额 {money(ledger.main_account().balance)} 元。")
    return ToolResult(True, "理财申购", detail, data={"holding_id": holding.id},
                      facts={"amounts": [float(amount), float(ledger.main_account().balance)],
                             "verified_lines": [detail]},
                      compensate={"action": "revert_subscribe", "args": {"holding_id": holding.id}})


def t_revert_subscribe(ledger: Ledger, args: dict, ctx: dict) -> ToolResult:
    h = ledger.holdings[args["holding_id"]]
    ledger.main_account().balance += h.amount
    h.status = "已撤销"
    detail = f"已撤销申购, {money(h.amount)} 元退回活期账户。"
    return ToolResult(True, "撤销申购", detail, data={},
                      facts={"amounts": [float(h.amount)], "verified_lines": [detail]})


def t_redeem_wealth(ledger: Ledger, args: dict, ctx: dict) -> ToolResult:
    holdings = [h for h in ledger.holdings.values() if h.status == "持有中"]
    if not holdings:
        raise LedgerError("你当前没有可赎回的持仓")
    def open_now(x) -> bool:
        p = ledger.products[x.product_id]
        return p.term_days == 0 or (TODAY - x.buy_date).days >= p.term_days

    # 优先赎回"随时可取"的持仓, 避免撞上封闭期
    h = next((x for x in holdings if open_now(x)), holdings[0])
    if args.get("product_hint"):
        cand = [x for x in holdings if args["product_hint"] in ledger.products[x.product_id].name]
        if cand:
            h = next((x for x in cand if open_now(x)), cand[0])
    if not open_now(h):
        p = ledger.products[h.product_id]
        left = p.term_days - (TODAY - h.buy_date).days
        raise LedgerError(
            f"{p.name} 处于封闭期，还需 {left} 天到期，到期后才能赎回；"
            f"如果急用钱，我可以帮你看看别的随时可取的持仓或可用额度")
    amount = None if args.get("all") else (D(args["amount"]) if args.get("amount") else None)
    r = ledger.redeem_wealth(h.id, amount)
    detail = f"已赎回 {r['product']} {r['amount']} 元, 资金已到活期账户, 当前余额 {money(ledger.main_account().balance)} 元。"
    return ToolResult(True, "理财赎回", detail, data=r,
                      facts={"amounts": [float(r["amount"]), float(ledger.main_account().balance)],
                             "verified_lines": [detail]})


def t_lock_savings(ledger: Ledger, args: dict, ctx: dict) -> ToolResult:
    amount = D(args.get("amount") or 1000)
    r = ledger.lock_savings(amount, int(args.get("days") or 30))
    detail = (f"已从活期锁定 {money(amount)} 元到储蓄账户, 锁定期 {r['days']} 天 "
              f"(至 {r['unlock_date']}), 活期余额 {money(ledger.main_account().balance)} 元。")
    return ToolResult(True, "锁定活期资金", detail, data=r,
                      facts={"amounts": [float(amount), float(ledger.main_account().balance)],
                             "verified_lines": [detail]},
                      compensate={"action": "unlock_savings", "args": {"amount": float(amount)}})


def t_unlock_savings(ledger: Ledger, args: dict, ctx: dict) -> ToolResult:
    amount = D(args["amount"])
    ledger.accounts["acc_sav"].balance -= amount
    ledger.main_account().balance += amount
    detail = f"已解除锁定, {money(amount)} 元退回活期账户。"
    return ToolResult(True, "解除锁定", detail, data={},
                      facts={"amounts": [float(amount)], "verified_lines": [detail]})


def t_query_calendar(ledger: Ledger, args: dict, ctx: dict) -> ToolResult:
    events = ledger.upcoming_events(int(args.get("days") or 60))
    if not events:
        return ToolResult(True, "日程", "近 60 天没有设置提醒的重要日期。", data={"events": []},
                          facts={"amounts": [], "verified_lines": ["近 60 天无重要日期"]})
    lines = [f"{e.day.isoformat()} {e.title} (还有 {(e.day - TODAY).days} 天)" for e in events]
    return ToolResult(True, "重要日期", "  · " + "\n  · ".join(lines),
                      data={"events": [{"id": e.id, "title": e.title, "day": e.day.isoformat(),
                                        "kind": e.kind, "contact_id": e.contact_id} for e in events]},
                      facts={"amounts": [], "verified_lines": lines})


def t_schedule_order(ledger: Ledger, args: dict, ctx: dict) -> ToolResult:
    kind = args.get("kind") or "鲜花"
    amount = D(args.get("amount") or 300)
    day = _parse_when(args.get("deliver_on")) or (TODAY + timedelta(days=16))
    order = ledger.schedule_order(kind, amount, day, args.get("address") or "家庭地址")
    detail = f"已预约 {day.isoformat()} 配送的{kind} ({money(amount)} 元), 订单号 {order.id}。"
    return ToolResult(True, f"预约{kind}", detail,
                      data={"order_id": order.id, "kind": kind, "deliver_on": day.isoformat(),
                            "amount": money(amount)},
                      facts={"amounts": [float(amount)], "verified_lines": [detail]},
                      compensate={"action": "cancel_order", "args": {"order_id": order.id}})


def t_cancel_order(ledger: Ledger, args: dict, ctx: dict) -> ToolResult:
    for o in ledger.orders:
        if o.id == args["order_id"]:
            o.status = "已取消"
            detail = f"已取消订单 {o.id} ({o.kind})。"
            return ToolResult(True, "取消订单", detail, data={},
                              facts={"verified_lines": [detail], "amounts": []})
    raise LedgerError("订单不存在")


# ------------------------------------------------------------------ 目标与购买力
def t_plan_budget(ledger: Ledger, args: dict, ctx: dict) -> ToolResult:
    """把"我能拿出多少钱 / 买得起吗"算成一个确定、可解释的答案。"""
    s = ledger.bill_summary(30)
    spend = float(s["total_out"])
    income = float(s["income"])
    surplus = round(income - spend, 2)
    main_bal = float(ledger.main_account().balance)
    redeemable = float(ledger.redeemable_amount())
    fixed = float(ledger.accounts["acc_sav"].balance)
    liquid = main_bal + redeemable
    reserve = round(spend * 3, 2)                 # 3 个月应急金
    cash_available = round(max(liquid - reserve, 0.0), 2)
    with_fixed = round(max(liquid + fixed - reserve, 0.0), 2)
    target = float(args.get("target_amount") or 0)
    months = int(args.get("months") or 0)
    label = str(args.get("target") or "这笔大额支出")

    lines = [
        f"可立即动用: 活期 {money(main_bal)} 元 + 随时可取理财 {money(redeemable)} 元 = {money(liquid)} 元",
        f"另有定期储蓄 {money(fixed)} 元, 可提前支取但按活期计息",
        f"近 30 天支出 {money(spend)} 元、收入 {money(income)} 元, 每月结余约 {money(surplus)} 元; "
        f"建议留 3 个月应急金 {money(reserve)} 元",
        f"不动定期时, 现在能直接用于{label}的钱约 {money(cash_available)} 元; "
        f"愿意动用定期的话约 {money(with_fixed)} 元",
    ]
    gap = 0.0
    need = 0.0
    shortfall = 0.0
    if target > 0:
        gap = round(max(target - with_fixed, 0.0), 2)
        lines.append(f"目标 {money(target)} 元, 缺口 {money(gap)} 元")
        if gap > 0 and months > 0:
            need = round(gap / months, 2)
            tail = (f"按 {months} 个月准备, 每月需要额外存 {money(need)} 元")
            if surplus < need:
                shortfall = round(need - surplus, 2)
                tail += f"; 当前月结余 {money(surplus)} 元, 每月还差 {money(shortfall)} 元"
            lines.append(tail)
    elif surplus > 0:
        lines.append(f"按每月结余 {money(surplus)} 元算, 12 个月可再攒 {money(round(surplus * 12, 2))} 元")

    year_saving = round(surplus * 12, 2) if surplus > 0 else 0.0
    return ToolResult(True, f"可支配资金测算 · {label}", "  · " + "\n  · ".join(lines),
                      data={"liquid": money(liquid), "cash_available": money(cash_available),
                            "with_fixed": money(with_fixed), "reserve": money(reserve),
                            "monthly_spend": money(spend), "monthly_income": money(income),
                            "surplus": money(surplus), "year_saving": money(year_saving),
                            "gap": money(gap), "target": money(target) if target else "0.00"},
                      facts={"amounts": [main_bal, redeemable, fixed, liquid, reserve,
                                         cash_available, with_fixed, spend, income, surplus,
                                         year_saving]
                                        + ([target, gap, need, shortfall] if target else []),
                             "verified_lines": lines})


def t_compare_wealth(ledger: Ledger, args: dict, ctx: dict) -> ToolResult:
    hint = args.get("product_hint") or ""
    picks = [p for p in ledger.products.values() if hint and hint in p.name]
    picks = (picks or list(ledger.products.values()))[:3]
    lines = []
    for p in picks:
        term = f"封闭 {p.term_days} 天" if p.term_days else "随时可赎"
        lines.append(f"{p.name}: {p.risk} 风险, 预期年化 {p.annual_rate}%, 起投 {money(p.min_amount)} 元, {term}")
    detail = ("横向对比:\n  · " + "\n  · ".join(lines)
              + "\n  · 短期要用的钱优先随时可赎; 能放一年以上再考虑 R3/R4, R3 以上不保本。")
    return ToolResult(True, "理财产品横向对比", detail,
                      data={"picks": [p.id for p in picks]},
                      facts={"amounts": [float(p.min_amount) for p in picks], "verified_lines": lines})


def t_apply_physical_card(ledger: Ledger, args: dict, ctx: dict) -> ToolResult:
    kind = str(args.get("card_kind") or "储蓄卡")
    app = ledger.apply_physical_card(kind)
    detail = (f"已提交{kind}申请, 申请编号 {app['id']}, 制卡完成后预计 {app['deliver_date']} 前"
              f"通过{app['channel']}寄到你的预留地址。")
    return ToolResult(True, "申请实体卡", detail, data=app,
                      facts={"verified_lines": [detail], "amounts": []},
                      compensate={"action": "cancel_card_application", "args": {"app_id": app["id"]}})


def t_cancel_card_application(ledger: Ledger, args: dict, ctx: dict) -> ToolResult:
    for a in ledger.card_applications:
        if a["id"] == args["app_id"]:
            a["status"] = "已撤销"
            detail = f"已撤销卡申请 {a['id']}。"
            return ToolResult(True, "撤销卡申请", detail, data={},
                              facts={"verified_lines": [detail], "amounts": []})
    raise LedgerError("申请记录不存在")


# ------------------------------------------------------------------ 时间解析
def _parse_when(text: Optional[str]) -> Optional[date]:
    if not text:
        return None
    text = str(text)
    if text in ("明天",):
        return TODAY + timedelta(days=1)
    if text in ("后天",):
        return TODAY + timedelta(days=2)
    if text == "大后天":
        return TODAY + timedelta(days=3)
    if text.startswith("下周"):
        idx = "一二三四五六日天".find(text[-1])
        target = (idx + 1) if idx >= 0 else 1
        days_ahead = (7 - TODAY.weekday()) + (target - 1)
        return TODAY + timedelta(days=days_ahead)
    import re as _re
    m = _re.match(r"(\d{4})-(\d{2})-(\d{2})$", text)
    if m:
        return date(int(m.group(1)), int(m.group(2)), int(m.group(3)))
    m = _re.match(r"(\d{1,2})月(\d{1,2})[号日]", text)
    if m:
        month, day = int(m.group(1)), int(m.group(2))
        year = TODAY.year + (1 if month < TODAY.month else 0)
        return date(year, month, day)
    return None


# ================================================================== 注册表
TOOLS = {
    "query_balance": t_query_balance,
    "query_txn": t_query_txn,
    "analyze_bills": t_analyze_bills,
    "detect_anomaly": t_detect_anomaly,
    "resolve_contact": t_resolve_contact,
    "transfer": t_transfer,
    "reverse_transfer": t_reverse_transfer,
    "split_aa": t_split_aa,
    "cancel_aa": t_cancel_aa,
    "list_subscriptions": t_list_subscriptions,
    "cancel_subscription": t_cancel_subscription,
    "restore_subscription": t_restore_subscription,
    "query_cards": t_query_cards,
    "freeze_card": t_freeze_card,
    "unfreeze_card": t_unfreeze_card,
    "unfreeze_card_inner": t_unfreeze_card_inner,
    "adjust_card_limit": t_adjust_card_limit,
    "restore_limit": t_restore_limit,
    "apply_virtual_card": t_apply_virtual_card,
    "set_txn_limit": t_set_txn_limit,
    "restore_daily_limit": t_restore_daily_limit,
    "change_password": t_change_password,
    "query_wealth": t_query_wealth,
    "recommend_wealth": t_recommend_wealth,
    "compare_wealth": t_compare_wealth,
    "quote_wealth": t_quote_wealth,
    "plan_budget": t_plan_budget,
    "apply_physical_card": t_apply_physical_card,
    "cancel_card_application": t_cancel_card_application,
    "subscribe_wealth": t_subscribe_wealth,
    "revert_subscribe": t_revert_subscribe,
    "redeem_wealth": t_redeem_wealth,
    "lock_savings": t_lock_savings,
    "unlock_savings": t_unlock_savings,
    "query_calendar": t_query_calendar,
    "schedule_order": t_schedule_order,
    "cancel_order": t_cancel_order,
}


def run_tool(action: str, args: dict, ctx: dict) -> ToolResult:
    fn = TOOLS.get(action)
    if not fn:
        return ToolResult(False, "未知动作", f"未登记的工具: {action}", facts={})
    ledger: Ledger = ctx["ledger"]
    try:
        return fn(ledger, args, ctx)
    except LedgerError as exc:
        return ToolResult(False, "操作未完成", str(exc), data={"error": str(exc)}, facts={"amounts": []})
    except Exception as exc:  # noqa: BLE001
        return ToolResult(False, "操作异常", f"系统异常: {exc}", data={"error": str(exc)}, facts={"amounts": []})
