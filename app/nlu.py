"""意图理解层 (NLU)。

两层结构:
1. 本地确定性理解器 —— 规则 + 槽位抽取, 离线可用, 保证演示与测试稳定;
2. LLM 增强器 (可选) —— 配置 YINZHANGGUI_LLM_API_KEY 后, 用大模型增强模糊表达理解,
   但模型的输出只用于"选意图 + 抽槽位", 绝不参与权限判定。

支持: 模糊表达、省略上下文(代词/零指代)、隐含意图、中文数字金额。
"""
from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Dict, List, Optional, Tuple

from . import llm

# ---------------------------------------------------------------- 中文数字
CN_DIGITS = {"零": 0, "一": 1, "两": 2, "二": 2, "三": 3, "四": 4, "五": 5, "六": 6, "七": 7, "八": 8, "九": 9}
CN_UNITS = {"十": 10, "百": 100, "千": 1000, "万": 10000}


def cn_to_number(text: str) -> Optional[float]:
    total = section = num = 0.0
    last_unit = 0.0
    hit = False
    for ch in text:
        if ch in CN_DIGITS:
            num = float(CN_DIGITS[ch])
            hit = True
        elif ch in CN_UNITS:
            unit = CN_UNITS[ch]
            hit = True
            if unit == 10000:
                section = (section + max(num, 1.0)) * unit
                total += section
                section = 0.0
            else:
                section += max(num, 1.0) * unit
            num = 0.0
            last_unit = unit
    if not hit:
        return None
    if num and last_unit >= 100:
        # "一千五" = 1500, "两百五" = 250 (口语省略末位单位)
        return total + section + num * last_unit / 10
    return total + section + num


AMOUNT_RE = re.compile(r"(?P<num>\d+(?:\.\d+)?)\s*(?P<unit>万|千|w|k)?", re.I)
CN_AMOUNT_RE = re.compile(r"[零一二两三四五六七八九十百千万]{1,6}(?=\s*(?:元|块|钱|$|[，,。；;！!？?]))")


def parse_amount(text: str) -> Optional[float]:
    """从文本中抽取金额, 支持 500 / 1000元 / 1.5万 / 五百 等写法。"""
    for m in AMOUNT_RE.finditer(text):
        unit = (m.group("unit") or "").lower()
        # 银行卡号/手机号/日期等长数字不算金额
        if len(m.group("num").split(".")[0]) >= 8:
            continue
        value = float(m.group("num"))
        if unit in ("万", "w"):
            value *= 10000
        elif unit in ("千", "k"):
            value *= 1000
        return value
    cm = CN_AMOUNT_RE.search(text)
    if cm:
        return cn_to_number(cm.group(0))
    return None


# ---------------------------------------------------------------- 意图定义
KNOWN_INTENTS = [
    "transfer", "split_aa", "balance", "bill_report", "bill_anomaly", "bill_category",
    "wealth_recommend", "wealth_quote", "wealth_subscribe", "wealth_redeem",
    "card_list", "card_freeze", "card_unfreeze", "card_limit", "card_virtual",
    "card_password", "txn_limit", "subs_list", "subs_cancel", "subs_scan",
    "cross_birthday", "cancel_last", "pause", "takeover", "help", "unknown",
]

KEYWORDS: Dict[str, List[str]] = {
    "balance": ["余额", "还剩多少", "账上", "存款有多少", "卡里有多少"],
    "bill_anomaly": ["异常", "可疑", "盗刷", "不对的账", "乱扣", "被扣"],
    "bill_category": ["分类", "占比", "哪类", "花在", "消费结构", "都花哪"],
    "bill_report": ["账单", "花了多少", "支出", "流水", "开销", "消费报告", "月报", "年报"],
    "wealth_recommend": ["推荐", "买什么", "哪个产品", "理财产品", "配置", "风险测评"],
    "wealth_quote": ["能赚", "收益多少", "试算", "算一下收益", "利息"],
    "wealth_subscribe": ["申购", "买", "买入", "投"],
    "wealth_redeem": ["赎回", "卖掉", "取出来", "退出"],
    "card_freeze": ["挂失", "冻结", "丢卡", "丢了", "被盗刷"],
    "card_unfreeze": ["解挂", "解冻", "恢复使用", "找到了"],
    "card_limit": ["额度", "提额", "调额", "限额"],
    "card_virtual": ["虚拟卡", "虚拟卡号", "开张卡", "办卡", "新卡"],
    "card_password": ["密码", "改密", "修改密码", "支付密码"],
    "txn_limit": ["交易限制", "单笔限额", "每日限额", "限制额度"],
    "subs_list": ["订阅", "会员", "自动续费", "代扣"],
    "subs_cancel": ["取消订阅", "关掉会员", "退订", "关掉", "取消掉", "别续费"],
    "cross_birthday": ["生日", "纪念日", "鲜花", "蛋糕", "礼物"],
    "transfer": ["转账", "转给", "汇", "打款", "转钱", "给他", "给她"],
    "split_aa": ["aa", "AA", "平分", "均摊", "拆", "各付"],
    "cancel_last": ["撤销", "取消刚才", "不要了", "算了", "退回来", "撤回"],
    "pause": ["暂停", "等一等", "先别", "停一下", "稍等"],
    "takeover": ["人工", "客服", "转人工", "人工接管"],
    "help": ["你能做什么", "帮我做什么", "有什么功能", "怎么用"],
}

# 正则版识别规则 —— 命中数越多置信度越高
INTENT_RULES: Dict[str, List[str]] = {
    "transfer": [
        r"给[^,。；;\s]{1,6}(?:转|汇|打|付)",
        r"转给[^,。；;\s]{1,6}",
        r"(?:转|汇|打)(?:账)?\s*[0-9一二两三四五六七八九十百千万]",
        r"转\s*[0-9]+\s*(?:元|块)",
        r"[0-9]+\s*(?:元|块).{0,6}(?:转|给|汇)",
        r"(?:帮|替)我?给.{1,6}(?:转|付)",
    ],
    "split_aa": [r"aa", r"平分", r"均摊", r"各付", r"拆(?:一下|分)", r"一起出钱"],
    "balance": [
        r"余额", r"还剩多少", r"还有多少", r"有多少钱", r"存款", r"总资产",
        r"卡里(?:有|还剩)", r"账上",
    ],
    "bill_report": [r"账单", r"花了多少", r"花(?:了|哪|费)", r"支出", r"流水", r"开销",
                    r"消费报告", r"月报", r"年报", r"这个月.{0,4}花",
                    r"交易记录", r"交易明细", r"历史交易", r"查.{0,4}(?:记录|明细)"],
    "bill_anomaly": [r"异常", r"可疑", r"盗刷", r"乱扣", r"不对的账", r"有问题.{0,3}交易"],
    "bill_category": [r"分类", r"占比", r"哪类", r"消费结构", r"都花(?:在|哪)"],
    "wealth_recommend": [r"推荐", r"买什么", r"哪个产品", r"理财产品", r"理财", r"基金",
                         r"风险测评", r"稳一点"],
    "wealth_compare": [r"(?:理财|产品|基金|收益).{0,8}(?:对比|比较|区别|哪个好|哪个划算)",
                       r"(?:对比|比较|区别).{0,8}(?:理财|产品|基金)"],
    "wealth_quote": [r"能赚", r"收益多少", r"试算", r"算一下.{0,4}收益", r"利息", r"赚多少"],
    # 购买力 / 目标规划 —— 不依赖固定句式, 覆盖"我准备给我爱人买车，我可以拿出多少钱"
    "afford": [r"(?:能|可以|可)(?:拿|出|凑|挤)(?:出|来)?多少",
               r"能拿出多少", r"可以动用多少", r"最多能.{0,4}(?:花|拿|用)多少",
               r"(?:预算|手头|资金|钱).{0,6}(?:够不够|够吗|够不|多少够|够用吗)",
               r"(?:买得起|够不够|差多少钱|钱够吗)",
               r"(?:准备|打算|想|要).{0,12}(?:买|换|装修|建房|结婚|留学)"],
    "plan_goal": [r"(?:帮我|替我|给我|帮忙).{0,12}(?:存|攒|准备|规划).{0,10}(?:\d|[一二三四五六七八九十]|钱|资金|预算)",
                  r"(?:每月|每个月).{0,8}(?:存|攒|定投).{0,6}(?:\d|[一二三四五六七八九十])",
                  r"(?:明年|后年|下个月|半年后|\d+个月后).{0,14}(?:结婚|婚礼|留学|旅行|旅游|装修|买房|买车)"],
    "wealth_subscribe": [r"申购", r"买入", r"买.{0,4}元", r"投.{0,4}元", r"买点"],
    "wealth_redeem": [r"赎回", r"卖掉", r"取出来", r"退出"],
    "card_list": [r"有哪些卡", r"我的卡", r"几张卡", r"卡片", r"卡号", r"看看卡"],
    "card_freeze": [r"挂失", r"冻结", r"丢卡", r"卡丢", r"被盗刷"],
    "card_unfreeze": [r"解挂", r"解冻", r"恢复使用", r"找到了"],
    "card_limit": [r"额度", r"提额", r"调额"],
    "card_virtual": [r"虚拟卡", r"开张卡", r"办卡", r"新卡"],
    "card_apply": [r"(?:申请|办|开|来)(?:一)?张.{0,6}(?:储蓄卡|借记卡|实体卡|信用卡)",
                   r"实体卡", r"补卡", r"新办.{0,4}卡", r"要一张.{0,4}卡"],
    "card_password": [r"密码", r"改密"],
    "txn_limit": [r"交易限制", r"单笔限额", r"每日限额", r"限额"],
    "subs_list": [r"订阅", r"会员", r"自动续费", r"代扣"],
    "subs_cancel": [r"取消.{0,4}(?:订阅|会员|续费)", r"退订", r"关掉", r"取消掉", r"别续费", r"不要了"],
    "subs_scan": [r"一直扣", r"乱扣", r"可疑扣", r"乱七八糟", r"扣费(?:异常|检查)"],
    "cross_birthday": [r"生日", r"纪念日", r"鲜花", r"蛋糕", r"礼物"],
    "cancel_last": [r"撤销", r"撤回", r"取消刚才", r"退回来", r"算了"],
    "pause": [r"暂停", r"等一等", r"等一下", r"等会", r"先别", r"停一下", r"稍等", r"稍候", r"别急"],
    "takeover": [r"人工", r"客服", r"转人工"],
    "help": [r"你能做什么", r"能做什么", r"有什么功能", r"怎么用", r"你是谁",
             r"你好", r"在吗", r"hi", r"hello", r"帮助"],
}

PRIORITY = [
    "cancel_last", "pause", "takeover", "card_freeze", "card_unfreeze", "card_password",
    "afford", "plan_goal",
    "subs_cancel", "wealth_redeem", "wealth_subscribe", "wealth_compare", "wealth_quote",
    "wealth_recommend", "split_aa", "transfer", "bill_anomaly", "bill_category", "bill_report",
    "txn_limit", "card_limit", "card_virtual", "card_apply", "card_list", "subs_scan", "subs_list",
    "cross_birthday", "balance", "help",
]


@dataclass
class Intent:
    name: str
    slots: Dict[str, object] = field(default_factory=dict)
    confidence: float = 0.0
    missing: List[str] = field(default_factory=list)
    source: str = "rule"
    hint: str = ""

    def to_dict(self) -> dict:
        return {"name": self.name, "slots": self.slots, "confidence": self.confidence,
                "missing": self.missing, "source": self.source}


MONEY_HINT = ("转账", "汇", "打款", "转点", "转笔")


def _guess_intent(text: str) -> Tuple[str, float]:
    low = text.lower()
    scores: Dict[str, int] = {}
    for name, patterns in INTENT_RULES.items():
        hits = sum(1 for p in patterns if re.search(p, low))
        if hits:
            scores[name] = hits

    # ---- 语境修正
    if re.search(r"(转账记录|转账流水|交易明细|转账历史|查.*转账)", low) and parse_amount(text) is None:
        scores.pop("transfer", None)
        scores["bill_report"] = max(scores.get("bill_report", 0), 2)
    if "取消" in low and any(k in low for k in ("订阅", "会员", "续费", "扣费")):
        scores["subs_cancel"] = max(scores.get("subs_cancel", 0), 2)
    if re.search(r"(怎么|如何).{0,3}(撤销|撤回)", low):
        scores["cancel_last"] = max(scores.get("cancel_last", 0), 2)
    if "限额" in low and "额度" not in low:
        scores["txn_limit"] = max(scores.get("txn_limit", 0), 2)
    if re.search(r"(理财|产品).{0,4}(买|投).{0,8}(元|万)", low):
        scores["wealth_subscribe"] = max(scores.get("wealth_subscribe", 0), 3)
        scores.pop("wealth_recommend", None)
    if "赎回" in low:
        scores["wealth_redeem"] = max(scores.get("wealth_redeem", 0), 3)
    if parse_amount(text) and re.search(r"能赚|收益多少|试算|赚多少", low):
        scores["wealth_quote"] = max(scores.get("wealth_quote", 0), 3)
    # 明确要"对比/区别"时, 不能被泛化的推荐意图压过去
    if re.search(r"(对比|比较|区别|哪个好|哪个划算)", low) and re.search(r"(理财|产品|基金|收益)", low):
        scores["wealth_compare"] = max(scores.get("wealth_compare", 0), 4)
        scores.pop("wealth_recommend", None)
    # 生日/纪念日/礼物 属于"事件安排", 不是资金规划
    if re.search(r"(生日|纪念日|礼物|鲜花|蛋糕)", low):
        scores["cross_birthday"] = max(scores.get("cross_birthday", 0), 4)
        scores.pop("plan_goal", None)

    if not scores:
        return "unknown", 0.0

    best = max(scores.items(), key=lambda kv: (kv[1], -PRIORITY.index(kv[0]) if kv[0] in PRIORITY else 0))
    conf = min(0.95, 0.5 + 0.15 * best[1])
    return best[0], conf


def _extract_contact_name(text: str) -> Optional[str]:
    patterns = [
        # 手机号: 完整号码 / 掩码 139****3382 / 尾号3382
        r"(?:给|向|转给)\s*(?P<who>(?:1\d{2}\*{2,4}\d{4}|\d{11}|尾号\d{4}))的?(?:手机号|号码|卡|账户|账号)?\s*(?:转|汇|付|打)",
        r"给\s*(?P<who>[\u4e00-\u9fa5A-Za-z]{1,6})\s*(?:转|汇|打|付)",
        r"(?:转给|汇给|打给)\s*(?P<who>[\u4e00-\u9fa5A-Za-z]{1,6})",
        r"向\s*(?P<who>[\u4e00-\u9fa5A-Za-z]{1,6})\s*(?:转|付)",
        r"(?:帮|替)\s*(?P<who>[\u4e00-\u9fa5A-Za-z]{1,6})\s*(?:转|付|交)",
        r"找\s*(?P<who>[\u4e00-\u9fa5A-Za-z]{1,6})\s*(?:收|要|还|拿)",
        r"(?P<who>[\u4e00-\u9fa5A-Za-z]{1,6})\s*(?:的)?\s*(?:那)?(?:笔)?(?:钱|账)",
    ]
    for p in patterns:
        m = re.search(p, text)
        if not m:
            continue
        who = m.group("who")
        who = re.sub(r"^(帮我|给我|给|向|替|帮|把)$", "", who).strip()
        who = re.sub(r"(转|打|汇|付)$", "", who).strip()
        if who and who not in ("他", "她", "它", "我", "自己", "点钱", "一笔"):
            return who
    return None


def _extract_note(text: str) -> Optional[str]:
    m = re.search(r"(?:备注|注明|写上|标注)[:：]?\s*(?P<note>[^,。；;\n]{1,20})", text)
    return m.group("note").strip() if m else None


def _extract_when(text: str) -> Optional[str]:
    m = re.search(r"(明天|后天|大后天|下周[一二三四五六日天]?|下个?月\d{1,2}[号日]|每月\d{1,2}[号日]|\d{1,2}月\d{1,2}[号日])", text)
    return m.group(1) if m else None


def _extract_total(text: str) -> Optional[float]:
    """AA 场景: 总额可能和"N 个人"混在一起, 优先取"总共/一共"后的数字。"""
    m = re.search(r"(?:总共|一共|总计|合计|总额|总金额)\s*([\d.]+)\s*(万|千)?", text)
    if m:
        value = float(m.group(1))
        if m.group(2) == "万":
            value *= 10000
        elif m.group(2) == "千":
            value *= 1000
        return value
    stripped = re.sub(r"\d{1,2}\s*(?:个)?人", " ", text)
    return parse_amount(stripped)


def _extract_count(text: str) -> Optional[int]:
    m = re.search(r"(?P<n>\d{1,2})\s*(?:个)?人", text)
    if m:
        return int(m.group("n"))
    m = re.search(r"([一二两三四五六七八九十])\s*(?:个)?人", text)
    if m:
        v = cn_to_number(m.group(1))
        return int(v) if v else None
    return None


def _days_hint(text: str) -> int:
    if "今天" in text or "今日" in text:
        return 1
    if "本周" in text or "这周" in text:
        return 7
    if "这个月" in text or "本月" in text or "当月" in text:
        return 30
    if "上个月" in text or "上月" in text:
        return 60
    if "半年" in text:
        return 180
    if "一年" in text or "全年" in text or "年度" in text:
        return 365
    if "最近" in text or "近期" in text:
        return 15
    return 30


# ---------------------------------------------------------------- 省略与上下文
def _apply_context(intent: Intent, text: str, context: dict) -> Intent:
    """处理省略表达: "转 500 给他"、"再来一笔"、"那个一直扣钱的"。"""
    name = intent.name
    low = text.lower()

    if name == "transfer":
        has_who = bool(intent.slots.get("contact_name"))
        has_amount = intent.slots.get("amount") is not None
        pronoun = any(p in text for p in ("他", "她", "还是那个", "老样子", "上次那个"))
        if not has_who and pronoun and context.get("last_contact"):
            intent.slots["contact_name"] = context["last_contact"]
            intent.hint = "代词指代 → 上文联系人"
        elif not has_who and context.get("last_contact") and has_amount:
            intent.slots["contact_name"] = context["last_contact"]
            intent.hint = "省略收款人 → 沿用上文联系人"
        if not has_amount and any(k in low for k in ("老样子", "上次那个数", "还是那个数")) and context.get("last_amount"):
            intent.slots["amount"] = context["last_amount"]
            intent.hint = (intent.hint + " + 金额沿用上文").strip(" +")
        if not intent.slots.get("note") and context.get("last_note") and any(k in low for k in ("老样子", "还是那个")):
            intent.slots["note"] = context["last_note"]

    if name == "subs_cancel" and not intent.slots.get("sub_id"):
        ref = intent.slots.get("reference")
        if not ref and any(k in text for k in ("一直扣钱", "乱扣", "那个", "乱七八糟", "可疑")):
            intent.slots["auto_pick_risky"] = True
            intent.hint = "模糊指代 → 自动定位高风险订阅"

    if name == "wealth_subscribe" and not intent.slots.get("product_hint"):
        if "稳健" in text or "保本" in text or "稳一点" in text:
            intent.slots["product_hint"] = "稳"
        elif "高收益" in text or "激进" in text:
            intent.slots["product_hint"] = "进取"

    if name in ("wealth_redeem",) and "全部" in text:
        intent.slots["all"] = True
    return intent


# ---------------------------------------------------------------- 主入口
def understand(text: str, context: Optional[dict] = None) -> Intent:
    context = context or {}
    raw = (text or "").strip()
    if not raw:
        return Intent("help", {}, 0.0, ["query"], "rule")

    name, conf = _guess_intent(raw)

    slots: Dict[str, object] = {"text": raw}
    # 手机号/尾号里的数字不能当金额 (给尾号3382的手机号转200 -> 金额是 200, 不是 3382)
    amount_text = re.sub(r"(?:1\d{2}\*{2,4}\d{4}|\d{11}|尾号\s*\d{4})", " ", raw)
    amount = parse_amount(amount_text)
    contact = _extract_contact_name(raw)
    note = _extract_note(raw)
    when = _extract_when(raw)

    if name == "transfer":
        slots.update({"amount": amount, "contact_name": contact, "note": note, "when": when})
    elif name == "split_aa":
        slots.update({"total": _extract_total(raw), "payee_count": _extract_count(raw) or 2,
                      "contact_name": contact, "note": note})
    elif name in ("bill_report", "bill_anomaly", "bill_category"):
        slots.update({"days": _days_hint(raw), "category": _extract_category(raw)})
    elif name == "wealth_recommend":
        slots.update({"product_hint": _risk_hint(raw)})
    elif name == "wealth_compare":
        slots.update({"product_hint": _extract_product(raw)})
    elif name in ("afford", "plan_goal"):
        slots.update({"target": _extract_target(raw), "target_amount": _extract_budget(raw),
                      "months": _extract_months(raw), "spend_hint": _extract_spend(raw)})
    elif name == "wealth_subscribe":
        slots.update({"amount": amount, "product_hint": _extract_product(raw) or _risk_hint(raw)})
    elif name == "wealth_quote":
        slots.update({"amount": amount, "product_hint": _extract_product(raw)})
    elif name == "wealth_redeem":
        slots.update({"amount": amount, "all": "全部" in raw,
                      "product_hint": _extract_product(raw)})
    elif name == "card_apply":
        slots.update({"card_kind": _extract_card_kind(raw)})
    elif name in ("card_limit", "txn_limit") and amount is None:
        # "我还剩多少额度" 这类是查询, 不是调额申请
        name = "card_list"
        slots.update({"card_hint": _extract_card(raw)})
    elif name in ("card_freeze", "card_unfreeze", "card_limit"):
        slots.update({"card_hint": _extract_card(raw), "amount": amount if name == "card_limit" else None})
    elif name in ("card_limit", "txn_limit"):
        slots.update({"card_hint": _extract_card(raw), "amount": amount})
    elif name == "card_password":
        slots.update({"target": "支付密码" if "支付" in raw else "登录密码"})
    elif name == "txn_limit":
        slots.update({"amount": amount})
    elif name == "subs_cancel":
        slots.update({"reference": _extract_sub_reference(raw)})
    elif name == "cross_birthday":
        slots.update({"contact_name": contact, "days_hint": _days_hint(raw)})

    intent = Intent(name=name, slots=slots, confidence=round(conf, 2), source="rule")

    # ---- LLM 增强 (可选, 失败静默降级)
    enhanced = llm.understand(raw, context)
    if enhanced:
        llm_intent = enhanced.get("intent")
        if llm_intent in KNOWN_INTENTS:
            intent.source = "llm+rule"
            if intent.confidence < 0.6:
                intent.name, intent.confidence = llm_intent, 0.75
            for k, v in (enhanced.get("slots") or {}).items():
                if v not in (None, "", []) and intent.slots.get(k) in (None, "", []):
                    intent.slots[k] = v
            if enhanced.get("reason"):
                intent.hint = (intent.hint + " | LLM: " + str(enhanced["reason"])).strip(" |")

    intent = _apply_context(intent, raw, context)
    intent.missing = _missing_slots(intent)
    return intent


def _missing_slots(intent: Intent) -> List[str]:
    missing: List[str] = []
    if intent.name == "transfer":
        if intent.slots.get("amount") is None:
            missing.append("amount")
        if not intent.slots.get("contact_name"):
            missing.append("contact_name")
    elif intent.name == "split_aa":
        if not intent.slots.get("total"):
            missing.append("total")
        if not intent.slots.get("contact_name"):
            missing.append("contact_name")
    elif intent.name == "wealth_subscribe":
        if intent.slots.get("amount") is None:
            missing.append("amount")
    elif intent.name == "cancel_last":
        pass
    elif intent.name == "help":
        missing.append("query")
    return missing


CATEGORY_WORDS = ["餐饮", "交通", "购物", "生活缴费", "娱乐", "医疗健康", "数码", "转账", "工资", "理财"]


def _extract_category(text: str) -> Optional[str]:
    for c in CATEGORY_WORDS:
        if c in text:
            return c
    alias = {"吃饭": "餐饮", "外卖": "餐饮", "打车": "交通", "加油": "交通",
             "网购": "购物", "看病": "医疗健康", "会员": "娱乐"}
    for k, v in alias.items():
        if k in text:
            return v
    return None


def _extract_product(text: str) -> Optional[str]:
    for name in ("稳盈", "天天利", "安享", "进取"):
        if name in text:
            return name
    return None


def _risk_hint(text: str) -> Optional[str]:
    """风险偏好: 稳 → R1/R2; 收益优先 → R3/R4。"""
    if any(k in text for k in ("稳", "保本", "保守", "低风险", "安全")):
        return "稳"
    if any(k in text for k in ("高收益", "收益高", "进取", "激进", "高风险", "搏一把")):
        return "进取"
    return None


TARGET_WORDS = ["买车", "换车", "买房", "还房贷", "装修", "结婚", "婚礼", "旅行", "旅游",
                "留学", "生娃", "育儿", "换手机", "买电脑", "创业"]


def _extract_target(text: str) -> Optional[str]:
    """用户想花这笔钱干什么 —— 不限官网举例, 常见大额支出都能识别。"""
    for word in TARGET_WORDS:
        if word in text:
            return word
    if "车" in text and any(k in text for k in ("买", "换", "首付")):
        return "买车"
    if "房" in text and any(k in text for k in ("买", "换", "首付", "贷")):
        return "买房"
    if "婚" in text:
        return "结婚"
    return None


def _extract_budget(text: str) -> Optional[float]:
    """目标金额: "预算 20 万"、"准备 5 万"、"大概 8000 元"。"""
    m = re.search(r"(?:预算|目标|大概|需要|准备|攒|存|首付)\s*([\d.]+)\s*(万|千)?", text)
    if m:
        value = float(m.group(1))
        unit = m.group(2)
        if unit == "万":
            value *= 10000
        elif unit == "千":
            value *= 1000
        return value
    m = re.search(r"([\d.]+)\s*(万|千)\s*(?:左右|上下|以内|首付)?", text)
    if m:
        value = float(m.group(1))
        return value * (10000 if m.group(2) == "万" else 1000)
    return None


def _extract_months(text: str) -> Optional[int]:
    m = re.search(r"(\d{1,2})\s*个月", text)
    if m:
        return int(m.group(1))
    if "半年" in text:
        return 6
    if "明年" in text or "一年" in text or "12个月" in text:
        return 12
    if "后年" in text or "两年" in text:
        return 24
    if "下个月" in text:
        return 1
    if "三年" in text or "3年" in text:
        return 36
    return None


def _extract_spend(text: str) -> Optional[float]:
    """口语里"拿出多少钱"不带数字时, 抽取"每月能存 X"这类数量。"""
    m = re.search(r"(?:每月|每个月).{0,6}(?:存|攒|省)\s*([\d.]+)\s*(万|千)?", text)
    if m:
        value = float(m.group(1))
        return value * (10000 if m.group(2) == "万" else 1000)
    return None


def _extract_card_kind(text: str) -> str:
    if "信用卡" in text:
        return "信用卡"
    if "借记卡" in text or "储蓄卡" in text:
        return "储蓄卡"
    return "储蓄卡"


def _extract_card(text: str) -> Optional[str]:
    if "信用" in text:
        return "信用卡"
    if "虚拟" in text:
        return "虚拟卡"
    if "借记" in text or "储蓄" in text:
        return "借记卡"
    return None


def _extract_sub_reference(text: str) -> Optional[str]:
    for name in ("爱奇艺", "网易云", "iCloud", "Keep", "清理", "视频", "音乐", "云存储", "健身"):
        if name in text:
            return name
    return None
