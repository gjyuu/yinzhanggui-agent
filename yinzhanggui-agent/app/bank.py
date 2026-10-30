"""模拟银行核心账本 (Ledger)。

全部数据为虚构演示数据, 不连接任何真实银行系统。
提供: 账户/联系人/流水/卡片/订阅/理财/日历事件 的查询与变更能力,
以及撤销(冲正)能力 —— 供 Agent 的"回退"特性使用。
"""
from __future__ import annotations

import itertools
import random
import re
from dataclasses import dataclass, field
from datetime import date, datetime, timedelta
from decimal import ROUND_HALF_UP, Decimal
from typing import Dict, List, Optional

CENT = Decimal("0.01")
TODAY = date.today()


def D(x) -> Decimal:
    return Decimal(str(x)).quantize(CENT, rounding=ROUND_HALF_UP)


def f(x) -> float:
    return float(D(x))


class LedgerError(Exception):
    """业务规则拒绝执行 (余额不足、状态非法等)。"""


# ==================================================================== 数据模型
@dataclass
class Account:
    id: str
    name: str
    kind: str          # 活期 / 定期 / 信用卡
    tail: str
    balance: Decimal
    currency: str = "CNY"


@dataclass
class Contact:
    id: str
    name: str
    aliases: List[str]
    phone: str
    bank: str
    relation: str
    limit_daily: Decimal = D(20000)


@dataclass
class Txn:
    id: str
    account_id: str
    ts: datetime
    amount: Decimal          # 正数金额, 方向由 direction 决定
    direction: str           # in / out
    category: str
    merchant: str
    channel: str
    note: str = ""
    reversed_by: Optional[str] = None

    @property
    def signed(self) -> Decimal:
        return self.amount if self.direction == "in" else -self.amount


@dataclass
class Card:
    id: str
    account_id: str
    kind: str                # 借记卡 / 信用卡 / 虚拟卡
    tail: str
    status: str              # 正常 / 已挂失 / 已冻结
    credit_limit: Decimal
    available: Decimal
    daily_limit: Decimal
    virtual: bool = False


@dataclass
class Subscription:
    id: str
    merchant: str
    amount: Decimal
    cycle: str               # 月 / 年
    next_charge: date
    account_id: str
    status: str              # 生效中 / 已取消
    auto_renew: bool
    risk: str                # 正常 / 可疑
    category: str


@dataclass
class WealthProduct:
    id: str
    name: str
    risk: str                # R1..R5
    annual_rate: float
    min_amount: Decimal
    term_days: int           # 0 = 灵活申赎
    desc: str


@dataclass
class Holding:
    id: str
    product_id: str
    amount: Decimal
    buy_date: date
    status: str = "持有中"


@dataclass
class CalendarEvent:
    id: str
    title: str
    day: date
    kind: str                # 生日 / 纪念日 / 还款日
    contact_id: str = ""


@dataclass
class Order:
    id: str
    kind: str                # 鲜花 / 蛋糕
    amount: Decimal
    deliver_on: date
    address: str
    status: str = "已预约"


# ==================================================================== 账本
class Ledger:
    def __init__(self) -> None:
        self._seq = itertools.count(1)
        self.accounts: Dict[str, Account] = {}
        self.contacts: Dict[str, Contact] = {}
        self.txns: List[Txn] = []
        self.cards: Dict[str, Card] = {}
        self.subscriptions: Dict[str, Subscription] = {}
        self.products: Dict[str, WealthProduct] = {}
        self.holdings: Dict[str, Holding] = {}
        self.events: List[CalendarEvent] = []
        self.orders: List[Order] = []
        self.card_applications: List[dict] = []
        self.scheduled_transfers: List[dict] = []
        self.transfer_log: List[dict] = []       # 用于日累计风控与冲正
        self.password_last_change = TODAY - timedelta(days=180)
        self._seed()

    # ---------------------------------------------------------- 工具方法
    def _id(self, prefix: str) -> str:
        return f"{prefix}_{next(self._seq):05d}"

    def account(self, account_id: str) -> Account:
        if account_id not in self.accounts:
            raise LedgerError(f"账户不存在: {account_id}")
        return self.accounts[account_id]

    def main_account(self) -> Account:
        return self.accounts["acc_cur"]

    # ---------------------------------------------------------- 种子数据
    def _seed(self) -> None:
        rnd = random.Random(20250520)

        self.accounts["acc_cur"] = Account("acc_cur", "活期账户", "活期", "8823", D(12846.50))
        self.accounts["acc_sav"] = Account("acc_sav", "储蓄账户", "定期", "1179", D(50000.00))
        self.accounts["acc_cc"] = Account("acc_cc", "信用卡账户", "信用卡", "6008", D(-3260.40))

        self.contacts = {
            "c_lijing": Contact("c_lijing", "李静", ["爱人", "老婆", "我老婆", "媳妇", "太太"], "138****6621", "招商银行", "配偶"),
            "c_wangqiang": Contact("c_wangqiang", "王强", ["老王", "强哥", "同事"], "139****3382", "工商银行", "同事"),
            "c_chen": Contact("c_chen", "陈先生", ["房东", "陈房东"], "137****9012", "建设银行", "房东"),
            "c_mama": Contact("c_mama", "张秀兰", ["妈妈", "妈", "我妈"], "136****7745", "农业银行", "母亲"),
            "c_liuting": Contact("c_liuting", "刘婷", ["小刘", "朋友", "闺蜜"], "135****2208", "中国银行", "朋友"),
        }

        self.cards = {
            "card_debit": Card("card_debit", "acc_cur", "借记卡", "8823", "正常", D(0), D(12846.50), D(20000)),
            "card_credit": Card("card_credit", "acc_cc", "信用卡", "6008", "正常", D(20000), D(16739.60), D(20000)),
        }

        self.products = {
            "p_steady": WealthProduct("p_steady", "稳盈 90 天", "R2", 2.85, D(1000), 90, "中低风险, 封闭 90 天, 到期自动回款"),
            "p_daily": WealthProduct("p_daily", "天天利活期+", "R1", 1.95, D(1), 0, "低风险, 随时申赎, T+0 到账"),
            "p_bond": WealthProduct("p_bond", "安享纯债 180 天", "R2", 3.20, D(5000), 180, "中低风险, 主投利率债"),
            "p_mix": WealthProduct("p_mix", "进取混合策略", "R4", 4.60, D(10000), 365, "中高风险, 含权益仓位, 可能亏损本金"),
        }

        self.holdings["h_1"] = Holding("h_1", "p_daily", D(3000), TODAY - timedelta(days=40))

        # 联系人日历事件 (相对今天, 保证演示随时可用)
        self.events = [
            CalendarEvent("e_birthday_wife", "李静的生日", TODAY + timedelta(days=18), "生日", "c_lijing"),
            CalendarEvent("e_birthday_mama", "妈妈的生日", TODAY + timedelta(days=95), "生日", "c_mama"),
            CalendarEvent("e_anniv", "结婚纪念日", TODAY + timedelta(days=140), "纪念日", "c_lijing"),
            CalendarEvent("e_cc_bill", "信用卡还款日", TODAY + timedelta(days=6), "还款日", ""),
        ]

        self.subscriptions = {
            "s_iqiyi": Subscription("s_iqiyi", "爱奇艺 VIP", D(25), "月", TODAY + timedelta(days=9), "acc_cur", "生效中", True, "正常", "影音娱乐"),
            "s_netease": Subscription("s_netease", "网易云音乐黑胶", D(15), "月", TODAY + timedelta(days=14), "acc_cur", "生效中", True, "正常", "影音娱乐"),
            "s_icloud": Subscription("s_icloud", "iCloud 云存储 50G", D(6), "月", TODAY + timedelta(days=3), "acc_cur", "生效中", True, "正常", "工具"),
            "s_keep": Subscription("s_keep", "Keep 会员", D(28), "月", TODAY + timedelta(days=21), "acc_cur", "生效中", True, "正常", "运动健康"),
            "s_junk": Subscription("s_junk", "极速清理大师 Pro", D(199), "年", TODAY + timedelta(days=2), "acc_cur", "生效中", True, "可疑", "工具"),
        }

        # 近 60 天流水
        cat_merchants = {
            "餐饮": [("星巴克", 18, 58), ("瑞幸咖啡", 9, 39), ("海底捞", 120, 460), ("全家便利店", 8, 45), ("麦当劳", 22, 66)],
            "交通": [("滴滴出行", 12, 88), ("地铁出行", 3, 12), ("中国石化", 200, 420), ("12306", 120, 680)],
            "购物": [("淘宝", 39, 680), ("京东", 60, 1200), ("优衣库", 129, 599), ("盒马鲜生", 45, 320)],
            "生活缴费": [("国家电网", 60, 180), ("中国移动", 58, 128), ("物业费", 180, 420)],
            "娱乐": [("猫眼电影", 39, 120), ("Steam", 30, 300), ("爱奇艺", 25, 25)],
            "医疗健康": [("老百姓大药房", 25, 160)],
            "数码": [("Apple Store", 68, 400)],
        }
        for back in range(60, -1, -1):
            day = TODAY - timedelta(days=back)
            for _ in range(rnd.randint(1, 3)):
                cat = rnd.choices(
                    list(cat_merchants), weights=[30, 22, 18, 10, 9, 6, 5], k=1
                )[0]
                merchant, lo, hi = rnd.choice(cat_merchants[cat])
                amount = D(round(rnd.uniform(lo, hi), 2))
                ts = datetime(day.year, day.month, day.day, rnd.randint(7, 22), rnd.randint(0, 59))
                self.txns.append(Txn(self._id("t"), "acc_cur", ts, amount, "out", cat, merchant, "手机银行"))

            # 每月 10 号工资
            if day.day == 10:
                self.txns.append(Txn(self._id("t"), "acc_cur",
                                     datetime(day.year, day.month, day.day, 9, 30),
                                     D(18500), "in", "工资", "某科技有限公司", "代发"))

        # 植入异常: 凌晨小额反复扣费 + 境外消费
        for k in (12, 7, 2):
            ts = datetime.combine(TODAY - timedelta(days=k), datetime.min.time()) + timedelta(hours=2, minutes=47)
            self.txns.append(Txn(self._id("t"), "acc_cur", ts, D(999.00), "out", "购物",
                                 "极速清理大师", "快捷支付", note="凌晨自动扣款"))
        self.txns.append(Txn(self._id("t"), "acc_cur",
                             datetime.combine(TODAY - timedelta(days=5), datetime.min.time()) + timedelta(hours=3, minutes=12),
                             D(288.00), "out", "购物", "AMAZON US", "境外线上", note="境外交易"))
        self.txns.append(Txn(self._id("t"), "acc_cur",
                             datetime.combine(TODAY - timedelta(days=20), datetime.min.time()) + timedelta(hours=15, minutes=5),
                             D(3280.00), "out", "医疗健康", "瑞尔齿科", "刷卡"))

        self.txns.sort(key=lambda t: t.ts)

    # ---------------------------------------------------------- 查询
    def recent_txns(self, days: int = 30, account_id: Optional[str] = None,
                    category: Optional[str] = None) -> List[Txn]:
        since = datetime.combine(TODAY - timedelta(days=days), datetime.min.time())
        out = [t for t in self.txns if t.ts >= since and not t.reversed_by]
        if account_id:
            out = [t for t in out if t.account_id == account_id]
        if category:
            out = [t for t in out if t.category == category]
        return out

    def find_contact(self, query: str) -> Optional[Contact]:
        """按姓名 / 称谓 / 手机号(支持掩码与尾号) 找人。"""
        q = (query or "").strip()
        if not q:
            return None
        for c in self.contacts.values():
            if q == c.name or q in c.aliases:
                return c
        # 手机号: 允许 139****3382 / 尾号3382 / 完整号码
        digits = re.sub(r"\D", "", q)
        if len(digits) >= 4:
            tail = digits[-4:]
            for c in self.contacts.values():
                cd = re.sub(r"\D", "", c.phone)
                if cd.endswith(tail):
                    return c
        for c in self.contacts.values():
            if q in c.name or any(q in a or a in q for a in c.aliases):
                return c
        return None

    def transfer_total_today(self) -> Decimal:
        total = D(0)
        for item in self.transfer_log:
            if item["date"] == TODAY and not item.get("reversed"):
                total += item["amount"]
        return total

    # ---------------------------------------------------------- 账单分析
    def bill_summary(self, days: int = 30) -> dict:
        txns = self.recent_txns(days)
        out = [t for t in txns if t.direction == "out"]
        cats: Dict[str, Decimal] = {}
        merchants: Dict[str, Decimal] = {}
        for t in out:
            cats[t.category] = cats.get(t.category, D(0)) + t.amount
            merchants[t.merchant] = merchants.get(t.merchant, D(0)) + t.amount
        total = sum(cats.values(), D(0))
        breakdown = [
            {"category": k, "amount": f(v), "ratio": round(float(v / total * 100), 1) if total else 0.0}
            for k, v in sorted(cats.items(), key=lambda kv: -kv[1])
        ]
        top = [
            {"merchant": k, "amount": f(v)}
            for k, v in sorted(merchants.items(), key=lambda kv: -kv[1])[:5]
        ]
        prev = [t for t in self.txns
                if t.direction == "out" and not t.reversed_by
                and datetime.combine(TODAY - timedelta(days=2 * days), datetime.min.time()) <= t.ts
                < datetime.combine(TODAY - timedelta(days=days), datetime.min.time())]
        prev_total = sum((t.amount for t in prev), D(0))
        mom = round(float((total - prev_total) / prev_total * 100), 1) if prev_total else 0.0
        return {
            "range_days": days,
            "total_out": f(total),
            "count": len(out),
            "avg": f(total / len(out)) if out else 0.0,
            "breakdown": breakdown,
            "top_merchants": top,
            "prev_total": f(prev_total),
            "mom_change_pct": mom,
            "income": f(sum((t.amount for t in txns if t.direction == "in"), D(0))),
        }

    def detect_anomalies(self, days: int = 30) -> List[dict]:
        txns = [t for t in self.recent_txns(days) if t.direction == "out"]
        found: List[dict] = []
        seen: Dict[tuple, List[Txn]] = {}
        for t in txns:
            seen.setdefault((t.merchant, t.amount), []).append(t)
        for (merchant, amount), items in seen.items():
            if len(items) >= 2 and float(amount) >= 500:
                found.append({
                    "level": "高",
                    "merchant": merchant,
                    "amount": f(amount),
                    "count": len(items),
                    "reason": f"同一商户在 {len(items)} 天内重复扣款 {len(items)} 次, 金额完全一致, 疑似自动续费或盗刷",
                    "txn_ids": [t.id for t in items],
                })
        for t in txns:
            if "境外" in t.channel or "AMAZON" in t.merchant.upper():
                found.append({
                    "level": "中",
                    "merchant": t.merchant,
                    "amount": f(t.amount),
                    "count": 1,
                    "reason": "非境内常规消费商户, 且发生在凌晨时段, 建议核实",
                    "txn_ids": [t.id],
                })
            if t.ts.hour in (1, 2, 3, 4, 5) and float(t.amount) >= 300:
                found.append({
                    "level": "中",
                    "merchant": t.merchant,
                    "amount": f(t.amount),
                    "count": 1,
                    "reason": f"交易时间异常 ({t.ts.strftime('%H:%M')})",
                    "txn_ids": [t.id],
                })
        return found

    # ---------------------------------------------------------- 变更操作
    def transfer(self, account_id: str, contact: Contact, amount: Decimal,
                 note: str = "", when: Optional[date] = None) -> Txn:
        amount = D(amount)
        if amount <= 0:
            raise LedgerError("转账金额必须大于 0")
        acc = self.account(account_id)
        if acc.balance < amount:
            raise LedgerError(f"活期账户余额不足: 可用 {acc.balance} 元, 本次需要 {amount} 元")
        if when and when > TODAY:
            self.scheduled_transfers.append({
                "id": self._id("st"), "contact": contact.name, "amount": f(amount),
                "when": when.isoformat(), "note": note, "status": "已预约",
            })
            return Txn(self._id("t"), account_id, datetime.now(), amount, "out",
                       "转账", f"预约转账-{contact.name}", "预约", note=note)
        acc.balance -= amount
        txn = Txn(self._id("t"), account_id, datetime.now(), amount, "out",
                  "转账", f"转账给{contact.name}", "手机银行", note=note)
        self.txns.append(txn)
        self.transfer_log.append({"txn_id": txn.id, "date": TODAY, "amount": amount,
                                  "contact": contact.name, "reversed": False})
        return txn

    def reverse_transfer(self, txn_id: str) -> Txn:
        for item in self.transfer_log:
            if item["txn_id"] == txn_id and not item["reversed"]:
                acc = self.main_account()
                acc.balance += item["amount"]
                item["reversed"] = True
                rev = Txn(self._id("t"), acc.id, datetime.now(), item["amount"], "in",
                          "冲正", f"冲正-{item['contact']}", "手机银行", note="撤销转账")
                self.txns.append(rev)
                return rev
        raise LedgerError("该笔交易不可撤销或已撤销")

    def lock_savings(self, amount: Decimal, days: int = 30) -> dict:
        amount = D(amount)
        acc = self.main_account()
        if acc.balance < amount:
            raise LedgerError(f"活期余额不足: 可用 {acc.balance} 元")
        acc.balance -= amount
        self.accounts["acc_sav"].balance += amount
        self.txns.append(Txn(self._id("t"), acc.id, datetime.now(), amount, "out",
                             "理财", "锁定活期资金", "智能规划", note=f"锁定 {days} 天"))
        return {"amount": f(amount), "days": days,
                "unlock_date": (TODAY + timedelta(days=days)).isoformat()}

    def set_card(self, card_id: str, **kwargs) -> Card:
        if card_id not in self.cards:
            raise LedgerError(f"卡片不存在: {card_id}")
        card = self.cards[card_id]
        for k, v in kwargs.items():
            setattr(card, k, v)
        return card

    def apply_virtual_card(self) -> Card:
        tail = str(1000 + len(self.cards) * 37)[-4:]
        card = Card(self._id("card"), "acc_cur", "虚拟卡", tail, "正常", D(0), D(0), D(2000), virtual=True)
        self.cards[card.id] = card
        return card

    def apply_physical_card(self, kind: str = "储蓄卡") -> dict:
        app = {
            "id": self._id("ca"),
            "kind": kind,
            "status": "制卡中",
            "apply_date": TODAY.isoformat(),
            "deliver_date": (TODAY + timedelta(days=3)).isoformat(),
            "channel": "免费顺丰寄送",
        }
        self.card_applications.append(app)
        return app

    def redeemable_amount(self) -> Decimal:
        """随时可取的理财金额 (灵活产品或已过封闭期)。"""
        total = D(0)
        for h in self.holdings.values():
            if h.status != "持有中":
                continue
            p = self.products[h.product_id]
            if p.term_days == 0 or (TODAY - h.buy_date).days >= p.term_days:
                total += h.amount
        return total

    def cancel_subscription(self, sub_id: str) -> Subscription:
        sub = self.subscriptions.get(sub_id)
        if not sub:
            raise LedgerError("订阅不存在")
        if sub.status == "已取消":
            raise LedgerError("该订阅已取消, 无需重复操作")
        sub.status = "已取消"
        sub.auto_renew = False
        return sub

    def subscribe_wealth(self, product_id: str, amount: Decimal) -> Holding:
        amount = D(amount)
        product = self.products.get(product_id)
        if not product:
            raise LedgerError("理财产品不存在")
        if amount < product.min_amount:
            raise LedgerError(f"低于起投金额 {product.min_amount} 元")
        acc = self.main_account()
        if acc.balance < amount:
            raise LedgerError(f"活期余额不足: 可用 {acc.balance} 元")
        acc.balance -= amount
        holding = Holding(self._id("h"), product_id, amount, TODAY)
        self.holdings[holding.id] = holding
        self.txns.append(Txn(self._id("t"), acc.id, datetime.now(), amount, "out",
                             "理财", f"申购-{product.name}", "手机银行"))
        return holding

    def redeem_wealth(self, holding_id: str, amount: Optional[Decimal] = None) -> dict:
        holding = self.holdings.get(holding_id)
        if not holding or holding.status != "持有中":
            raise LedgerError("持仓不存在或已赎回")
        product = self.products[holding.product_id]
        if product.term_days and (TODAY - holding.buy_date).days < product.term_days:
            raise LedgerError(f"{product.name} 处于封闭期, 剩余 {product.term_days - (TODAY - holding.buy_date).days} 天")
        amt = D(amount) if amount else holding.amount
        if amt > holding.amount:
            raise LedgerError("赎回金额超过持仓")
        holding.amount -= amt
        if holding.amount <= 0:
            holding.status = "已赎回"
        acc = self.main_account()
        acc.balance += amt
        self.txns.append(Txn(self._id("t"), acc.id, datetime.now(), amt, "in",
                             "理财", f"赎回-{product.name}", "手机银行"))
        return {"product": product.name, "amount": f(amt), "credited": True}

    def schedule_order(self, kind: str, amount: Decimal, deliver_on: date, address: str) -> Order:
        order = Order(self._id("o"), kind, D(amount), deliver_on, address)
        self.orders.append(order)
        return order

    def change_password(self) -> dict:
        self.password_last_change = TODAY
        return {"changed_at": TODAY.isoformat(), "method": "强验证后修改"}

    def upcoming_events(self, days: int = 60) -> List[CalendarEvent]:
        return sorted([e for e in self.events if 0 <= (e.day - TODAY).days <= days], key=lambda e: e.day)

    # ---------------------------------------------------------- 快照
    def snapshot(self) -> dict:
        m = lambda x: f"{Decimal(x):.2f}"      # noqa: E731  固定两位小数
        return {
            "user": {"name": "张伟", "level": "金卡客户"},
            "accounts": [
                {"id": a.id, "name": a.name, "kind": a.kind, "tail": a.tail, "balance": m(a.balance)}
                for a in self.accounts.values()
            ],
            "cards": [
                {"id": c.id, "kind": c.kind, "tail": c.tail, "status": c.status,
                 "limit": m(c.credit_limit), "available": m(c.available), "daily_limit": m(c.daily_limit)}
                for c in self.cards.values()
            ],
            "subscriptions": [
                {"id": s.id, "merchant": s.merchant, "amount": m(s.amount), "cycle": s.cycle,
                 "next": s.next_charge.isoformat(), "status": s.status, "risk": s.risk}
                for s in self.subscriptions.values()
            ],
            "holdings": [
                {"id": h.id, "product": self.products[h.product_id].name, "amount": m(h.amount),
                 "status": h.status}
                for h in self.holdings.values()
            ],
            "events": [{"id": e.id, "title": e.title, "day": e.day.isoformat(), "kind": e.kind}
                       for e in self.upcoming_events(120)],
            "transfer_today": m(self.transfer_total_today()),
        }
