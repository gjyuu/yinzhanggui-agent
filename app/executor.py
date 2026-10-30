"""执行引擎: 会话编排 + DAG 执行 + 中断/回退/人工接管。

执行顺序严格遵循:
  注入检测 → 意图理解 → 任务规划 → 权限分级 → 逐节点执行 → 事实校验 → 审计落盘
"""
from __future__ import annotations

import random
import time
import uuid
from dataclasses import dataclass, field
from datetime import datetime
from typing import Dict, List, Optional, Tuple

from . import config, eventplan, nlu, planner, policy, security, tools
from .bank import Ledger
from .policy import Tier


def _new_id(prefix: str) -> str:
    return f"{prefix}_{uuid.uuid4().hex[:8]}"


# ==================================================================== 会话
@dataclass
class Session:
    id: str
    ledger: Ledger = field(default_factory=Ledger)
    context: Dict[str, object] = field(default_factory=dict)
    plan: Optional[planner.Plan] = None
    pending_ids: List[str] = field(default_factory=list)
    approved: set = field(default_factory=set)
    mfa: Optional[dict] = None
    status: str = "idle"          # idle / awaiting_confirm / awaiting_mfa / locked / takeover
    history: List[dict] = field(default_factory=list)
    turn: int = 0
    takeover: bool = False         # 人工接管: 所有动作都需坐席确认
    created: float = field(default_factory=time.time)

    def reset_plan(self) -> None:
        self.plan = None
        self.pending_ids = []
        self.approved = set()
        self.mfa = None
        if self.status != "locked":
            self.status = "idle"


class SessionStore:
    def __init__(self) -> None:
        self.sessions: Dict[str, Session] = {}

    def get(self, session_id: Optional[str]) -> Session:
        if not session_id:
            session_id = _new_id("s")
        if session_id not in self.sessions:
            self.sessions[session_id] = Session(session_id)
        return self.sessions[session_id]

    def reset(self, session_id: str) -> Session:
        s = Session(session_id)
        self.sessions[session_id] = s
        return s


store = SessionStore()


# ==================================================================== 基础响应
def _payload(session: Session, trace_id: str, latency: float = 0.0) -> dict:
    return {
        "session_id": session.id,
        "trace_id": trace_id,
        "status": session.status,
        "reply": "",
        "intent": None,
        "policy": None,
        "plan": None,
        "pending": [],
        "mfa": None,
        "facts": {},
        "audit": security.audit_log.for_session(session.id, limit=40),
        "snapshot": session.ledger.snapshot(),
        "latency_ms": round(latency * 1000, 1),
        "mode": "llm+rule" if nlu.llm.enabled() else "rule",
    }


def _ctx(session: Session) -> dict:
    return {"ledger": session.ledger, "session": session,
            "daily_transfer_total": float(session.ledger.transfer_total_today())}


# ==================================================================== 主入口
def chat(session_id: str, text: str) -> dict:
    t0 = time.time()
    session = store.get(session_id)
    trace_id = _new_id("tr")
    payload = _payload(session, trace_id)
    session.turn += 1

    locked, remain, reason = security.breaker.is_locked(session.id)
    if locked:
        payload["status"] = "locked"
        payload["reply"] = (f"你的账户已触发安全保护, 暂时无法办理业务 (剩余 {remain} 秒)。\n"
                            f"原因: {reason}\n如需紧急处理请拨打 95588 或前往柜台。")
        payload["latency_ms"] = round((time.time() - t0) * 1000, 1)
        return payload

    # ---- 1. 注入防御 (先于任何模型调用)
    inj = security.injection_guard.scan(text)
    if inj.blocked:
        security.audit_log.record(trace_id, session.id, "injection",
                                  "拦截疑似提示注入", input=text, hits=inj.categories)
        now_locked = security.breaker.record_injection(session.id)
        payload["status"] = "blocked"
        payload["reply"] = ("这句话里包含试图绕过风控的指令, 我不会执行, 也不会改变任何权限设置。\n"
                            "权限分级由系统代码判定, 对话内容无法修改它。\n"
                            "如果你确实要办业务, 直接告诉我要做什么(例如「给王强转 200 元」)。")
        if now_locked:
            payload["status"] = "locked"
            payload["reply"] += "\n\n⚠ 多次尝试绕过风控, 已触发安全锁定 5 分钟。"
        payload["audit"] = security.audit_log.for_session(session.id, limit=40)
        payload["latency_ms"] = round((time.time() - t0) * 1000, 1)
        return payload

    security.audit_log.record(trace_id, session.id, "input", "收到用户消息", input=text)

    # ---- 2. 意图理解
    intent = nlu.understand(text, session.context)
    payload["intent"] = intent.to_dict()
    security.audit_log.record(trace_id, session.id, "nlu", f"意图={intent.name} 置信度={intent.confidence}",
                              slots={k: str(v) for k, v in intent.slots.items() if v not in (None, "", [])},
                              source=intent.source, hint=intent.hint)

    # ---- 3. 控制类意图
    # ---- 2.5 承接上一轮的提议 (如"需要我现在处理吗" -> "需要")
    offer = session.context.get("offer")
    if offer and intent.name in ("unknown", "help") and any(
            w in text for w in ("需要", "要", "好", "可以", "行", "嗯", "确认", "帮我", "处理", "麻烦")):
        security.audit_log.record(trace_id, session.id, "nlu", "承接上一轮提议: " + offer["intent"])
        intent = nlu.Intent(name=offer["intent"], slots=dict(offer.get("slots") or {}),
                            confidence=0.85, source="context", hint="上一轮提议的确认")
        payload["intent"] = intent.to_dict()

    # ---- 2.6 跨场景三步对话的后续输入 (选完 -> 地址 -> 下单)
    fu = eventplan.followup(session.ledger, session, text)
    if fu is not None:
        payload["reply"] = fu[0]
        payload["status"] = "done"
        payload["snapshot"] = session.ledger.snapshot()
        payload["latency_ms"] = round((time.time() - t0) * 1000, 1)
        security.audit_log.record(trace_id, session.id, "event", "跨场景联动对话", input=text)
        return payload

    if intent.name == "pause":
        session.status = "paused"
        session.pending_ids = session.pending_ids
        payload["status"] = "paused"
        payload["reply"] = ("已暂停当前任务, 你可以说「继续」恢复, 或说「取消」放弃这次操作。\n"
                            "已执行完成的绿色查询不会回滚, 涉及资金的动作尚未执行。")
        payload["plan"] = session.plan.to_dict() if session.plan else None
        payload["latency_ms"] = round((time.time() - t0) * 1000, 1)
        return payload

    if intent.name == "takeover":
        session.status = "takeover"
        session.takeover = True
        security.audit_log.record(trace_id, session.id, "takeover", "用户请求人工接管")
        payload["status"] = "takeover"
        payload["reply"] = ("已为你转接人工客服(工号 A208), 请稍候。\n"
                            "在人工接管期间, 任何自动化动作都需要坐席逐笔确认, Agent 不会自行执行。")
        payload["latency_ms"] = round((time.time() - t0) * 1000, 1)
        return payload

    if "继续" in text and session.status == "paused" and session.plan:
        session.status = "awaiting_confirm" if session.pending_ids else "idle"
        payload["reply"] = "继续执行。"
        result = _advance(session, trace_id, payload)
        result["latency_ms"] = round((time.time() - t0) * 1000, 1)
        return result

    if intent.name == "help":
        payload["reply"] = _help_text()
        payload["status"] = "done"
        payload["latency_ms"] = round((time.time() - t0) * 1000, 1)
        return payload

    if intent.name == "unknown":
        payload["status"] = "clarify"
        payload["reply"] = ("这句话我没把握理解对, 为了不误操作, 我先不动手。\n"
                            "你可以说得具体一点, 比如「给王强转 200 元」「这个月花了多少」「我订了哪些会员」。\n\n"
                            + _help_text())
        payload["latency_ms"] = round((time.time() - t0) * 1000, 1)
        return payload


    # ---- 3.8 跨场景: 先给方案, 不替用户做决定
    if intent.name == "cross_birthday":
        payload["reply"] = eventplan.propose(session.ledger, session, intent)
        payload["status"] = "awaiting_choice"
        payload["snapshot"] = session.ledger.snapshot()
        payload["latency_ms"] = round((time.time() - t0) * 1000, 1)
        security.audit_log.record(trace_id, session.id, "event", "给出跨场景方案选项", input=text)
        return payload

    # ---- 4. 纠正上一轮的待确认计划 (用户直接说了新指令)
    if session.status in ("awaiting_confirm", "awaiting_mfa") and session.plan:
        security.audit_log.record(trace_id, session.id, "plan", "用户放弃原计划, 重新规划",
                                  old_intent=session.plan.intent, new_intent=intent.name)
        session.reset_plan()

    # ---- 5. 缺槽位 → 澄清 (支持多轮补全)
    if intent.missing:
        payload["reply"] = _clarify(intent)
        payload["status"] = "clarify"
        session.context["pending_intent"] = intent.to_dict()
        payload["latency_ms"] = round((time.time() - t0) * 1000, 1)
        return payload

    # ---- 6. 规划
    plan = planner.build(intent, session.ledger)
    if not plan.nodes:
        payload["reply"] = _help_text()
        payload["status"] = "done"
        payload["latency_ms"] = round((time.time() - t0) * 1000, 1)
        return payload
    session.plan = plan
    session.status = "running"
    session.approved = set()
    payload["plan"] = plan.to_dict()
    security.audit_log.record(trace_id, session.id, "plan", f"生成任务 DAG: {plan.summary}",
                              nodes=[n.to_dict() for n in plan.nodes])

    # 记录上下文, 供省略表达复用
    if intent.name == "transfer":
        session.context["last_contact"] = intent.slots.get("contact_name")
        session.context["last_amount"] = intent.slots.get("amount")
        session.context["last_note"] = intent.slots.get("note")

    result = _advance(session, trace_id, payload)
    result["latency_ms"] = round((time.time() - t0) * 1000, 1)
    return result


# ==================================================================== DAG 推进
def _advance(session: Session, trace_id: str, payload: dict) -> dict:
    plan = session.plan
    assert plan is not None
    facts: Dict[str, list] = {"amounts": [], "tails": [], "verified_lines": []}
    executed_lines: List[str] = []
    local_comps: List[dict] = []      # 本轮计划内产生的可回退动作

    while True:
        node = _next_node(plan)
        if node is None:
            break

        decision = policy.classify(node.action, node.args, _ctx(session))
        node.tier = decision.tier.value
        node.detail = decision.reason
        payload["policy"] = decision.to_dict()
        security.audit_log.record(trace_id, session.id, "policy", f"{node.title}: {decision.tier.value}",
                                  node=node.id, action=node.action, tier=decision.tier.value,
                                  reason=decision.reason, detail=decision.detail)

        needs_gate = decision.tier is not Tier.GREEN
        if session.takeover and decision.tier is Tier.GREEN:
            needs_gate = True       # 人工接管期间, 全部分级都要人确认
        if needs_gate and node.id not in session.approved:
            session.pending_ids = [n.id for n in plan.topological()
                                   if n.status == "pending" and n.id not in session.approved]
            session.status = "awaiting_confirm"
            payload["plan"] = plan.to_dict()
            payload["pending"] = _pending_cards(plan, session)
            payload["status"] = "awaiting_confirm"
            head = ("\n\n".join(executed_lines) + "\n\n" if executed_lines else "")
            payload["reply"] = (head + _confirm_text(plan, session))
            payload["facts"] = facts
            return payload

        # 执行
        node.status = "running"
        args = _prepare_args(node, session)
        res = tools.run_tool(node.action, args, _ctx(session))
        ok = res.ok
        security.audit_log.record(trace_id, session.id, "tool",
                                  f"{node.action} {'成功' if ok else '失败'}",
                                  node=node.id, ok=ok, args={k: str(v) for k, v in args.items()},
                                  result=res.data, compensate=res.compensate)

        if not ok:
            node.status = "failed"
            node.detail = res.detail
            rolled = _rollback(session, trace_id, local_comps)
            locked = security.breaker.record_failure(session.id, res.detail)
            session.status = "locked" if locked else "idle"
            payload["plan"] = plan.to_dict()
            payload["status"] = session.status
            msg = f"这一步没有办成: {res.detail}\n"
            if executed_lines:
                msg += f"\n我先把已经执行的 {len(executed_lines)} 步做了回退:\n" + "\n".join(
                    f"  · {x}" for x in rolled)
            msg += "\n没有产生任何未经你确认的扣款。"
            if locked:
                msg += "\n\n⚠ 连续失败已达上限, 账户进入 5 分钟安全锁定。"
            payload["reply"] = msg
            need = _next_node(plan)
            if need is not None:
                need.status = "skipped"
            payload["facts"] = facts
            return payload

        node.status = "done"
        node.result = res.data
        node.detail = res.detail
        executed_lines.append(f"[{node.title}] {res.detail}")
        _merge_facts(facts, res.facts)
        session.history.append({"node": node.id, "action": node.action, "args": args,
                                "result": res.data, "compensate": res.compensate,
                                "detail": res.detail, "ts": datetime.now().isoformat()})
        if res.compensate:
            local_comps.append(res.compensate)
            session.context.setdefault("compensations", []).append(res.compensate)
        if node.action in ("transfer", "reverse_transfer"):
            session.context["last_txn_id"] = res.data.get("txn_id")

    # 全部完成
    if plan.intent == "bill_anomaly":
        # 按异常性质给最贴切的处置: 订阅类异常 -> 关自动续费, 否则才考虑挂失/限额
        risky = [s for s in session.ledger.subscriptions.values()
                 if s.status == "生效中" and s.risk == "可疑"]
        if risky:
            sub = sorted(risky, key=lambda x: x.amount, reverse=True)[0]
            session.context["offer"] = {"intent": "subs_cancel",
                                        "slots": {"reference": sub.merchant}}
        else:
            session.context["offer"] = {"intent": "card_freeze", "slots": {"card_hint": "信用卡"}}
    elif plan.intent in ("subs_scan", "subs_list"):
        session.context["offer"] = {"intent": "subs_cancel", "slots": {"auto_pick_risky": True}}
    session.status = "done"
    payload["status"] = "done"
    payload["plan"] = plan.to_dict()
    payload["pending"] = []
    payload["policy"] = payload.get("policy")
    body = "\n\n".join(executed_lines)
    payload["reply"] = body + "\n\n" + _closing(plan)
    payload["facts"] = facts

    # ---- 幻觉防护: 回复中的金额/尾号必须来自事实集
    guard = security.hallucination_guard.verify(payload["reply"], facts)
    security.audit_log.record(trace_id, session.id, "guard",
                              "事实校验通过" if guard.ok else "事实校验未通过, 已替换为安全模板",
                              checked=guard.checked, violations=guard.violations)
    if not guard.ok:
        payload["reply"] = security.hallucination_guard.safe_reply(facts)
        payload["guard_blocked"] = guard.violations
    security.breaker.record_success(session.id)
    return payload


def _next_node(plan: planner.Plan):
    done_ids = {n.id for n in plan.nodes if n.status in ("done", "skipped")}
    for node in plan.topological():
        if node.status != "pending":
            continue
        if all(d in done_ids for d in node.deps):
            return node
        node.status = "skipped"        # 前置失败 → 跳过
    return None


def _prepare_args(node: planner.Node, session: Session) -> dict:
    args = dict(node.args)
    if node.action == "reverse_transfer" and not args.get("txn_id"):
        for h in reversed(session.history):
            if h["action"] == "transfer" and h.get("compensate"):
                args["txn_id"] = h["compensate"]["args"]["txn_id"]
                break
    return args


def _merge_facts(acc: dict, new: dict) -> None:
    for k in ("amounts", "tails", "verified_lines"):
        acc.setdefault(k, [])
        acc[k].extend(new.get(k) or [])


def _rollback(session: Session, trace_id: str, comps: List[dict]) -> List[str]:
    """只回退本轮计划产生的事实变更, 逆序执行补偿动作。"""
    done: List[str] = []
    for comp in reversed(comps):
        res = tools.run_tool(comp["action"], comp["args"], _ctx(session))
        security.audit_log.record(trace_id, session.id, "rollback",
                                  f"回退 {comp['action']} {'成功' if res.ok else '失败'}",
                                  args=comp["args"], ok=res.ok, detail=res.detail)
        if res.ok:
            done.append(res.detail)
    return done


# ==================================================================== 确认卡
def _pending_cards(plan: planner.Plan, session: Session) -> List[dict]:
    cards = []
    for node in plan.topological():
        if node.status != "pending" or node.id in session.approved:
            continue
        decision = policy.classify(node.action, node.args, _ctx(session))
        if decision.tier is Tier.GREEN and not session.takeover:
            continue
        cards.append({
            "node_id": node.id,
            "title": node.title,
            "action": node.action,
            "tier": decision.tier.value,
            "tier_label": policy.TIER_LABEL[decision.tier],
            "reason": decision.reason,
            "mfa_methods": decision.mfa_methods,
            "review_flag": decision.review_flag,
            "details": planner.describe(node, session.ledger),
        })
    return cards


def _confirm_text(plan: planner.Plan, session: Session) -> str:
    cards = _pending_cards(plan, session)
    if not cards:
        return "计划里没有需要确认的动作。"
    reds = [c for c in cards if c["tier"] == "red"]
    lines = [f"这件事需要你先点头 ({len(cards)} 个动作):"]
    for c in cards:
        mark = "🔴 强验证" if c["tier"] == "red" else "🟡 确认"
        lines.append(f"  {mark} {c['title']}")
    if reds:
        methods = "、".join(config.MFA_LABELS[m] for m in reds[0]["mfa_methods"])
        lines.append(f"\n其中有高风险动作, 确认后还要过一道强验证({methods})才能真正执行。")
    lines.append("\n点「确认执行」继续, 点「取消」我什么都不做。")
    return "\n".join(lines)


# ==================================================================== 确认 / 强验证
def confirm(session_id: str, decision: str) -> dict:
    t0 = time.time()
    session = store.get(session_id)
    trace_id = _new_id("tr")
    payload = _payload(session, trace_id)
    if session.status not in ("awaiting_confirm", "awaiting_mfa", "takeover", "paused") or not session.plan:
        payload["reply"] = "当前没有等待确认的操作。"
        payload["status"] = session.status
        payload["latency_ms"] = round((time.time() - t0) * 1000, 1)
        return payload

    if decision != "approve":
        for nid in session.pending_ids:
            node = session.plan.get(nid)
            if node:
                node.status = "skipped"
        security.audit_log.record(trace_id, session.id, "confirm", "用户取消操作",
                                  pending=session.pending_ids)
        payload["reply"] = "好的, 已取消, 没有执行任何涉及资金的动作。"
        payload["status"] = "cancelled"
        payload["plan"] = session.plan.to_dict()
        session.status = "idle"
        session.plan = None
        payload["latency_ms"] = round((time.time() - t0) * 1000, 1)
        return payload

    need_mfa = [c for c in _pending_cards(session.plan, session) if c["tier"] == "red"]
    if need_mfa:
        methods = need_mfa[0]["mfa_methods"] or config.MFA_METHODS
        code = f"{random.randint(0, 999999):06d}"
        session.mfa = {"id": _new_id("mfa"), "methods": methods, "code": code,
                       "attempts": 0, "expires": time.time() + 180,
                       "actions": [c["title"] for c in need_mfa]}
        session.status = "awaiting_mfa"
        security.audit_log.record(trace_id, session.id, "mfa", "已下发强验证挑战",
                                  methods=methods, actions=session.mfa["actions"])
        payload["status"] = "awaiting_mfa"
        payload["mfa"] = {
            "challenge_id": session.mfa["id"],
            "methods": [{"code": m, "label": config.MFA_LABELS[m]} for m in methods],
            "actions": session.mfa["actions"],
            "expires_in": 180,
            "demo_code": code,
            "hint": "演示环境: 短信验证码直接显示在此; 人脸与 U 盾为模拟通过",
        }
        payload["reply"] = (f"确认收到。这一步属于红色高风险动作({ '、'.join(session.mfa['actions']) }), "
                            f"还需要完成强验证才能执行。\n请选择一种方式完成认证。")
        payload["plan"] = session.plan.to_dict()
        payload["latency_ms"] = round((time.time() - t0) * 1000, 1)
        return payload

    for nid in session.pending_ids:
        session.approved.add(nid)
    session.status = "running"
    security.audit_log.record(trace_id, session.id, "confirm", "用户确认执行", pending=session.pending_ids)
    payload["reply"] = "已确认, 继续执行。"
    result = _advance(session, trace_id, payload)
    result["latency_ms"] = round((time.time() - t0) * 1000, 1)
    return result


def verify_mfa(session_id: str, method: str, code: str) -> dict:
    t0 = time.time()
    session = store.get(session_id)
    trace_id = _new_id("tr")
    payload = _payload(session, trace_id)
    ch = session.mfa
    if not ch or session.status != "awaiting_mfa" or not session.plan:
        payload["reply"] = "当前没有待完成的强验证。"
        payload["status"] = session.status
        payload["latency_ms"] = round((time.time() - t0) * 1000, 1)
        return payload
    if time.time() > ch["expires"]:
        session.status = "awaiting_confirm"
        payload["status"] = "awaiting_confirm"
        payload["reply"] = "验证已超时, 请重新确认该操作。"
        payload["latency_ms"] = round((time.time() - t0) * 1000, 1)
        return payload
    if method not in ch["methods"]:
        payload["reply"] = "该操作不支持这种验证方式, 请换一种。"
        payload["status"] = "awaiting_mfa"
        payload["mfa"] = {"challenge_id": ch["id"], "methods": [{"code": m, "label": config.MFA_LABELS[m]} for m in ch["methods"]],
                          "actions": ch["actions"], "demo_code": ch["code"]}
        payload["latency_ms"] = round((time.time() - t0) * 1000, 1)
        return payload

    ok = True
    if method == "sms":
        ok = code.strip() == ch["code"]
    security.audit_log.record(trace_id, session.id, "mfa_verify",
                              f"{config.MFA_LABELS[method]} 验证{'通过' if ok else '失败'}",
                              method=method, ok=ok)
    if not ok:
        ch["attempts"] += 1
        left = config.MFA_MAX_ATTEMPTS - ch["attempts"]
        locked = security.breaker.record_failure(session.id, "强验证失败")
        if locked or left <= 0:
            session.status = "locked"
            payload["status"] = "locked"
            payload["reply"] = ("验证码连续错误, 已触发安全锁定 5 分钟。这期间不能办理任何业务, "
                                "请通过官方客服渠道解锁。")
        else:
            payload["status"] = "awaiting_mfa"
            payload["mfa"] = {"challenge_id": ch["id"],
                              "methods": [{"code": m, "label": config.MFA_LABELS[m]} for m in ch["methods"]],
                              "actions": ch["actions"], "demo_code": ch["code"]}
            payload["reply"] = f"验证码不正确, 还可以再试 {left} 次。"
        payload["latency_ms"] = round((time.time() - t0) * 1000, 1)
        return payload

    security.breaker.record_success(session.id)
    session.mfa = None
    for nid in session.pending_ids:
        session.approved.add(nid)
    session.status = "running"
    payload["reply"] = f"{config.MFA_LABELS[method]}验证通过, 正在执行。"
    result = _advance(session, trace_id, payload)
    result["latency_ms"] = round((time.time() - t0) * 1000, 1)
    return result


# ==================================================================== 文本辅助
def _clarify(intent) -> str:
    if intent.name in ("transfer", "split_aa"):
        if "contact_name" in intent.missing and "amount" in intent.missing:
            return "好的。要转给谁, 转多少? 例如「给王强转 200 元」。"
        if "amount" in intent.missing:
            who = intent.slots.get("contact_name")
            return f"要给「{who}」转多少? 另外要不要加个备注?"
        return ("能转给谁? 说个名字或称谓就行, 比如「李静」「房东」「我妈」。"
                "我也可以先帮你查一下通讯录。")
    if intent.name == "wealth_subscribe":
        return "想投多少? 比如「买 2000 元稳盈 90 天」; 如果你只说「稳健点」或「都行」, 我也能帮你选。"
    if intent.name == "help":
        return _help_text()
    return "我还需要再多一点信息才能办这件事。"


def _help_text() -> str:
    return (
        "我是银掌柜, 你的银行智能体。可以直接这样说:\n"
        "  · 转账: 「给王强转 200, 备注 饭钱」「给尾号 3382 的手机号转 100」「下周一给房东转 800」「500 块 AA, 4 个人」\n"
        "  · 账单: 「这个月钱都花哪了」「有没有异常扣费」「出个月度账单报告」\n"
        "  · 理财: 「有什么稳一点的理财」「这几款理财产品有什么区别」「1 万块稳盈 90 天能赚多少」「赎回天天利」\n"
        "  · 卡片: 「我有哪些卡」「信用卡丢了挂失」「把额度调到 3 万」「申请虚拟卡」「办张实体储蓄卡」\n"
        "  · 订阅: 「我订了哪些会员」「把那个一直扣钱的关掉」\n"
        "  · 目标规划: 「我准备给我爱人买车, 我能拿出多少钱」「明年结婚, 帮我准备 5 万」\n"
        "  · 跨场景: 「我爱人生日快到了, 帮我安排一下」「我妈生日也快到了, 一起安排」\n"
        "查询与测算类我直接办; 会动钱或改状态的, 我会先给确认卡; 高风险的还要过强验证。"
    )


def _closing(plan: planner.Plan) -> str:
    tips = {
        "transfer": "需要撤销的话, 说「撤销刚才那笔转账」就行。",
        "split_aa": "对方确认后资金才入账, 你现在没有支出。",
        "bill_report": "要我针对某一类支出做优化建议, 或者找出异常交易, 直接说。",
        "bill_anomaly": "这些异常里如果有你不认识的自动续费，我可以直接帮你关掉；需要我现在处理吗?",
        "wealth_subscribe": "冷静期内的赎回规则, 可以问我「怎么赎回」。",
        "subs_scan": "确认不要的订阅, 我可以直接帮你关掉自动续费。",
        "cross_birthday": "礼物也可以改日期、换品类, 或者取消, 告诉我就行。",
        "afford": "想要更细的方案, 告诉我目标金额和期限, 我可以按月拆出储蓄计划。",
        "plan_goal": "想调整每月金额或期限, 直接说, 我会重新算一遍。",
        "wealth_compare": "看中哪一款, 我可以直接帮你申购, 申购需要强验证。",
        "card_apply": "制卡进度可以在卡片管理里查, 需要加急也可以说。",
        "subs_list": "3 天内要扣款的订阅, 现在就能一键关掉。",
        "card_freeze": "补卡进度可在卡片管理里查看。",
    }
    return tips.get(plan.intent, "还需要我做什么, 直接说。")


def snapshot(session_id: str) -> dict:
    s = store.get(session_id)
    return {"snapshot": s.ledger.snapshot(), "status": s.status,
            "turn": s.turn,
            "plan": s.plan.to_dict() if s.plan else None}


def reset(session_id: str) -> dict:
    s = store.reset(session_id)
    security.breaker.manual_unlock(session_id)
    security.audit_log.record(_new_id("tr"), session_id, "reset", "会话重置为初始演示状态")
    return {"session_id": s.id, "snapshot": s.ledger.snapshot(), "status": s.status}
