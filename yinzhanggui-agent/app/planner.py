"""任务规划层: 把意图编译成有向无环图 (DAG)。

· 节点 = 一次工具调用 (可被权限引擎分级)
· 边   = 数据依赖, 只有前置节点成功才执行后继节点
· 支持并行分支 (例如生日场景中"订花"和"订蛋糕"互不依赖)
"""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date, timedelta
from typing import Dict, List, Optional

from .bank import Ledger, TODAY
from .nlu import Intent


@dataclass
class Node:
    id: str
    action: str
    title: str
    args: Dict[str, object] = field(default_factory=dict)
    deps: List[str] = field(default_factory=list)
    tier: str = "green"
    status: str = "pending"       # pending / waiting_confirm / done / failed / skipped / rolled_back
    detail: str = ""
    result: Optional[dict] = None

    def to_dict(self) -> dict:
        return {"id": self.id, "action": self.action, "title": self.title, "deps": self.deps,
                "tier": self.tier, "status": self.status, "detail": self.detail,
                "args": {k: (f"{v:.2f}" if isinstance(v, float) else v) for k, v in self.args.items()}}


@dataclass
class Plan:
    intent: str
    summary: str
    nodes: List[Node] = field(default_factory=list)

    def get(self, node_id: str) -> Optional[Node]:
        return next((n for n in self.nodes if n.id == node_id), None)

    def topological(self) -> List[Node]:
        done: List[Node] = []
        ready = [n for n in self.nodes if not n.deps]
        seen = set()
        while ready or len(done) < len(self.nodes):
            if not ready:
                # 依赖成环或缺失, 兜底按原顺序补齐
                for n in self.nodes:
                    if n.id not in seen:
                        done.append(n)
                        seen.add(n.id)
                break
            node = ready.pop(0)
            if node.id in seen:
                continue
            done.append(node)
            seen.add(node.id)
            for n in self.nodes:
                if n.id not in seen and n not in ready and all(d in seen for d in n.deps):
                    ready.append(n)
        return done

    def to_dict(self) -> dict:
        return {"intent": self.intent, "summary": self.summary,
                "nodes": [n.to_dict() for n in self.nodes]}


def _n(idx: int, action: str, title: str, args: dict, deps: List[str]) -> Node:
    return Node(id=f"n{idx}", action=action, title=title, args=args, deps=deps)


def build(intent: Intent, ledger: Ledger) -> Plan:
    s = intent.slots
    name = intent.name

    if name == "transfer":
        amount = float(s.get("amount") or 0)
        contact = s.get("contact_name") or ""
        when = s.get("when")
        nodes = [
            _n(1, "resolve_contact", "校验收款人", {"contact_name": contact}, []),
            _n(2, "transfer", "执行转账", {"contact_name": contact, "amount": amount,
                                        "note": s.get("note") or "", "when": when}, ["n1"]),
        ]
        summary = f"向 {contact} 转账 {amount:,.2f} 元" + (f" ({when})" if when else "")
        return Plan("transfer", summary, nodes)

    if name == "split_aa":
        total = float(s.get("total") or 0)
        count = int(s.get("payee_count") or 2)
        contact = s.get("contact_name") or ""
        nodes = [
            _n(1, "resolve_contact", "校验收款人", {"contact_name": contact}, []),
            _n(2, "split_aa", "发起 AA 收款", {"contact_name": contact, "total": total,
                                          "payee_count": count}, ["n1"]),
        ]
        return Plan("split_aa", f"向 {contact} 发起 AA 收款, 总额 {total:,.2f} 元 / {count} 人", nodes)

    if name == "balance":
        return Plan("balance", "查询账户余额", [_n(1, "query_balance", "查询余额", {}, [])])

    if name == "bill_report":
        return Plan("bill_report", "生成账单分析报告",
                    [_n(1, "analyze_bills", "消费分类统计", {"days": s.get("days") or 30}, [])])

    if name == "bill_anomaly":
        days = s.get("days") or 30
        return Plan("bill_anomaly", "识别异常交易", [
            _n(1, "analyze_bills", "消费分类统计", {"days": days}, []),
            _n(2, "detect_anomaly", "异常交易识别", {"days": days}, ["n1"]),
        ])

    if name == "bill_category":
        return Plan("bill_category", "分析消费结构",
                    [_n(1, "analyze_bills", "消费分类统计",
                        {"days": s.get("days") or 30, "category": s.get("category")}, [])])

    if name == "wealth_recommend":
        return Plan("wealth_recommend", "按风险偏好推荐理财产品", [
            _n(1, "recommend_wealth", "风险偏好匹配", {"product_hint": s.get("product_hint") or "稳"}, []),
            _n(2, "query_wealth", "产品池与持仓核对", {}, ["n1"]),
        ])

    if name == "wealth_compare":
        return Plan("wealth_compare", "理财产品横向对比", [
            _n(1, "query_wealth", "读取产品池", {}, []),
            _n(2, "compare_wealth", "逐项对比", {"product_hint": s.get("product_hint")}, ["n1"]),
        ])

    # ---- 购买力测算: 回答"我准备给我爱人买车，我可以拿出多少钱"这类开放问题
    if name == "afford":
        target = s.get("target") or "这笔大额支出"
        return Plan("afford", f"测算「{target}」的可支配上限", [
            _n(1, "query_balance", "读取账户全貌", {}, []),
            _n(2, "plan_budget", "测算可支配上限与缺口",
               {"target": target, "target_amount": s.get("target_amount"),
                "months": s.get("months")}, ["n1"]),
        ])

    if name == "plan_goal":
        target = s.get("target") or "目标"
        amount = float(s.get("target_amount") or 0)
        months = int(s.get("months") or 0)
        nodes = [
            _n(1, "query_balance", "读取账户全貌", {}, []),
            _n(2, "plan_budget", "测算资金缺口",
               {"target": target, "target_amount": s.get("target_amount"),
                "months": months}, ["n1"]),
        ]
        if amount > 0 and months > 0:
            monthly = round(amount / months, 2)
            nodes.append(_n(3, "lock_savings", f"锁定每月 {monthly:,.0f} 元目标资金",
                            {"amount": monthly, "days": months * 30}, ["n2"]))
        summary = f"为「{target}」" + (f"分 {months} 个月准备" if months else "准备资金")
        return Plan("plan_goal", summary, nodes)

    if name == "card_apply":
        return Plan("card_apply", "申请实体卡", [
            _n(1, "apply_physical_card", "提交办卡申请",
               {"card_kind": s.get("card_kind") or "储蓄卡"}, []),
        ])

    if name == "wealth_quote":
        return Plan("wealth_quote", "收益试算 (沙箱内计算)", [
            _n(1, "query_wealth", "读取产品参数", {}, []),
            _n(2, "quote_wealth", "沙箱内试算收益",
               {"product_hint": s.get("product_hint"), "amount": s.get("amount")}, ["n1"]),
        ])

    if name == "wealth_subscribe":
        return Plan("wealth_subscribe", "申购理财产品", [
            _n(1, "query_wealth", "读取产品与持仓", {}, []),
            _n(2, "subscribe_wealth", "提交申购",
               {"product_hint": s.get("product_hint"), "amount": s.get("amount")}, ["n1"]),
        ])

    if name == "wealth_redeem":
        return Plan("wealth_redeem", "赎回理财持仓", [
            _n(1, "query_wealth", "读取持仓", {}, []),
            _n(2, "redeem_wealth", "提交赎回",
               {"product_hint": s.get("product_hint"), "amount": s.get("amount"), "all": s.get("all")}, ["n1"]),
        ])

    if name == "card_list":
        return Plan("card_list", "查询卡片信息", [_n(1, "query_cards", "卡片列表", {}, [])])

    if name == "card_freeze":
        return Plan("card_freeze", "办理卡片挂失", [
            _n(1, "query_cards", "核对卡片状态", {}, []),
            _n(2, "freeze_card", "办理挂失", {"card_hint": s.get("card_hint")}, ["n1"]),
        ])

    if name == "card_unfreeze":
        return Plan("card_unfreeze", "解除卡片挂失", [
            _n(1, "query_cards", "核对卡片状态", {}, []),
            _n(2, "unfreeze_card", "解除挂失", {"card_hint": s.get("card_hint")}, ["n1"]),
        ])

    if name == "card_limit":
        return Plan("card_limit", "调整信用卡额度", [
            _n(1, "query_cards", "核对当前额度", {}, []),
            _n(2, "adjust_card_limit", "提交调额",
               {"card_hint": s.get("card_hint") or "信用卡", "amount": s.get("amount")}, ["n1"]),
        ])

    if name == "card_virtual":
        return Plan("card_virtual", "申请虚拟卡", [_n(1, "apply_virtual_card", "开通虚拟卡", {}, [])])

    if name == "card_password":
        return Plan("card_password", "修改密码", [
            _n(1, "change_password", "修改密码", {"target": s.get("target") or "登录密码"}, []),
        ])

    if name == "txn_limit":
        return Plan("txn_limit", "调整交易限额", [
            _n(1, "query_cards", "核对当前限额", {}, []),
            _n(2, "set_txn_limit", "提交限额调整", {"amount": s.get("amount")}, ["n1"]),
        ])

    if name == "subs_list":
        return Plan("subs_list", "盘点订阅与自动扣费", [_n(1, "list_subscriptions", "订阅清单", {}, [])])

    if name == "subs_scan":
        return Plan("subs_scan", "扫描可疑扣费", [
            _n(1, "list_subscriptions", "订阅清单", {}, []),
            _n(2, "detect_anomaly", "扣费异常识别", {"days": 60}, ["n1"]),
        ])

    if name == "subs_cancel":
        return Plan("subs_cancel", "取消订阅", [
            _n(1, "list_subscriptions", "定位订阅", {}, []),
            _n(2, "cancel_subscription", "取消自动续费",
               {"reference": s.get("reference"), "auto_pick_risky": s.get("auto_pick_risky")}, ["n1"]),
        ])

    if name == "cross_birthday":
        event = _pick_event(ledger, str(s.get("text") or ""))
        day = event.day if event else TODAY + timedelta(days=18)
        title = event.title if event else "爱人生日"
        amount = float(s.get("lock_amount") or 1000)
        return Plan("cross_birthday", f"为「{title}」准备: 锁定 {amount:,.0f} 元并预约礼物", [
            _n(1, "query_calendar", "读取重要日期", {"days": 60}, []),
            _n(2, "query_balance", "确认可动用资金", {}, ["n1"]),
            _n(3, "lock_savings", f"锁定 {amount:,.0f} 元活期资金",
               {"amount": amount, "days": 30}, ["n2"]),
            _n(4, "schedule_order", "预约鲜花配送",
               {"kind": "鲜花", "amount": 300, "deliver_on": (day - timedelta(days=2)).isoformat()}, ["n3"]),
            _n(5, "schedule_order", "预约蛋糕配送",
               {"kind": "蛋糕", "amount": 200, "deliver_on": (day - timedelta(days=1)).isoformat()}, ["n3"]),
        ])

    if name == "cancel_last":
        return Plan("cancel_last", "撤销上一笔操作", [
            _n(1, "reverse_transfer", "撤销转账", {}, []),
        ])

    return Plan("help", "能力说明", [])


def _pick_event(ledger: Ledger, hint_text: str = ""):
    """按用户话里的对象(妈妈/爱人/纪念日…)匹配日历事件, 而不是只认"爱人"这一种说法。"""
    events = ledger.upcoming_events(120)
    if not events:
        return None
    text = hint_text or ""
    for e in events:
        contact = ledger.contacts.get(e.contact_id)
        if not contact:
            continue
        names = [contact.name] + list(contact.aliases)
        if any(n and n in text for n in names):
            return e
    if "纪念日" in text:
        return next((e for e in events if e.kind == "纪念日"), None)
    if "生日" in text:
        return next((e for e in events if e.kind == "生日"), None)
    return next((e for e in events if e.kind == "生日"), events[0])


def describe(node: Node, ledger: Ledger) -> List[Dict[str, str]]:
    """生成"执行前确认卡"的结构化详情, 供前端与用户共读。"""
    a = node.args
    bal = ledger.main_account().balance
    if node.action == "transfer":
        amount = float(a.get("amount") or 0)
        return [
            {"label": "收款人", "value": str(a.get("contact_name"))},
            {"label": "金额", "value": f"{amount:,.2f} 元"},
            {"label": "付款账户", "value": f"活期账户(尾号 {ledger.main_account().tail})"},
            {"label": "备注", "value": str(a.get("note") or "无")},
            {"label": "执行时间", "value": str(a.get("when") or "立即")},
            {"label": "执行后可用余额", "value": f"{float(bal) - amount:,.2f} 元 (当前 {float(bal):,.2f} 元)"},
        ]
    if node.action == "split_aa":
        total = float(a.get("total") or 0)
        n = int(a.get("payee_count") or 2)
        return [
            {"label": "收款对象", "value": str(a.get("contact_name"))},
            {"label": "总额 / 人数", "value": f"{total:,.2f} 元 / {n} 人"},
            {"label": "每人应收", "value": f"{total / n:,.2f} 元"},
            {"label": "资金影响", "value": "仅发起收款请求, 不产生扣款"},
        ]
    if node.action == "lock_savings":
        amount = float(a.get("amount") or 0)
        return [
            {"label": "锁定金额", "value": f"{amount:,.2f} 元"},
            {"label": "资金来源", "value": f"活期账户(尾号 {ledger.main_account().tail})"},
            {"label": "锁定期限", "value": f"{a.get('days')} 天"},
            {"label": "执行后可用余额", "value": f"{float(bal) - amount:,.2f} 元"},
        ]
    if node.action == "schedule_order":
        return [
            {"label": "礼物", "value": str(a.get("kind"))},
            {"label": "金额", "value": f"{float(a.get('amount') or 0):,.2f} 元"},
            {"label": "配送日期", "value": str(a.get("deliver_on"))},
            {"label": "支付方式", "value": "活期账户(免密小额支付协议)"},
        ]
    if node.action == "subscribe_wealth":
        return [
            {"label": "产品", "value": str(a.get("product_hint") or "按推荐产品")},
            {"label": "申购金额", "value": f"{float(a.get('amount') or 0):,.2f} 元"},
            {"label": "风险提示", "value": "理财非存款, R3 以上不保本"},
            {"label": "执行后可用余额", "value": f"{float(bal) - float(a.get('amount') or 0):,.2f} 元"},
        ]
    if node.action == "cancel_subscription":
        return [
            {"label": "订阅", "value": str(a.get("reference") or "自动定位可疑订阅")},
            {"label": "操作", "value": "关闭自动续费, 已付周期不退款"},
        ]
    if node.action in ("freeze_card", "unfreeze_card"):
        return [
            {"label": "卡片", "value": str(a.get("card_hint") or "默认证件下首张卡")},
            {"label": "影响", "value": "立即生效, 卡内资金不变"},
        ]
    if node.action == "adjust_card_limit":
        return [
            {"label": "卡片", "value": "信用卡"},
            {"label": "目标额度", "value": f"{float(a.get('amount') or 0):,.2f} 元"},
        ]
    if node.action == "set_txn_limit":
        return [{"label": "单日限额", "value": f"{float(a.get('amount') or 0):,.2f} 元"}]
    if node.action == "apply_physical_card":
        return [
            {"label": "卡种", "value": str(a.get("card_kind") or "储蓄卡")},
            {"label": "寄送", "value": "制卡完成后 3 个工作日内免费寄送到预留地址"},
            {"label": "费用", "value": "免工本费"},
        ]
    if node.action == "redeem_wealth":
        return [
            {"label": "持仓产品", "value": str(a.get("product_hint") or "随时可取的持仓")},
            {"label": "赎回金额", "value": "全部可赎回份额" if a.get("all") else str(a.get("amount") or "全部")},
            {"label": "资金去向", "value": "活期账户（实时到账）"},
            {"label": "到账后可用余额", "value": f"{float(bal):,.2f} 元（当前）"},
        ]
    if node.action == "change_password":
        return [{"label": "修改对象", "value": str(a.get("target") or "登录密码")},
                {"label": "影响", "value": "其他设备需重新登录"}]
    if node.action == "reverse_transfer":
        return [{"label": "操作", "value": "撤销最近一笔转账并冲正入账"}]
    return [{"label": k, "value": str(v)} for k, v in a.items() if v not in (None, "", [])]
