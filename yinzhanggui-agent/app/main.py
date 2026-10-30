"""银掌柜 · 银行 AI 智能体 —— FastAPI 入口。"""
from __future__ import annotations

import os
from typing import Optional

from fastapi import FastAPI, HTTPException
from fastapi.responses import FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field

from . import channels, config, demo, executor, llm, policy, security, selfcheck

app = FastAPI(
    title=f"{config.APP_NAME} · 银行 AI 智能体",
    description="自然语言办业务: 意图理解 → 任务 DAG → 三级权限 → 强验证 → 审计",
    version=config.VERSION,
)

WEB_DIR = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "web")


class ChatIn(BaseModel):
    session_id: Optional[str] = None
    text: str = Field(min_length=1, max_length=1000)


class ConfirmIn(BaseModel):
    session_id: str
    decision: str = "approve"      # approve / reject


class MfaIn(BaseModel):
    session_id: str
    method: str = "sms"            # sms / face / ushield
    code: str = ""


class ImIn(BaseModel):
    channel: str = "wechat"        # wechat / app / sms / 任意渠道标识
    user_id: str = "im-user"
    text: str = Field(min_length=1, max_length=1000)
    session_id: Optional[str] = None


@app.post("/api/chat")
def api_chat(body: ChatIn) -> dict:
    r = executor.chat(body.session_id or "", body.text)
    r["snapshot"] = executor.store.get(r["session_id"]).ledger.snapshot()
    return r


@app.post("/api/confirm")
def api_confirm(body: ConfirmIn) -> dict:
    if body.decision not in ("approve", "reject"):
        raise HTTPException(status_code=400, detail="decision 只能是 approve 或 reject")
    r = executor.confirm(body.session_id, body.decision)
    r["snapshot"] = executor.store.get(r["session_id"]).ledger.snapshot()
    return r


@app.post("/api/mfa/verify")
def api_mfa(body: MfaIn) -> dict:
    r = executor.verify_mfa(body.session_id, body.method, body.code)
    r["snapshot"] = executor.store.get(r["session_id"]).ledger.snapshot()
    return r


@app.get("/api/session/{session_id}")
def api_session(session_id: str) -> dict:
    return executor.snapshot(session_id)


@app.post("/api/im/webhook")
def api_im(body: ImIn) -> dict:
    """IM / APP 渠道入口: 纯文本交互(回复"确认""取消"或 6 位验证码)。"""
    session_id = body.session_id or f"im-{body.channel}-{body.user_id}"
    return channels.handle(session_id, body.user_id, body.channel, body.text)


@app.post("/api/session/{session_id}/reset")
def api_reset(session_id: str) -> dict:
    return executor.reset(session_id)


@app.get("/api/audit")
def api_audit(session_id: Optional[str] = None, limit: int = 60) -> dict:
    if session_id:
        items = security.audit_log.for_session(session_id, limit=limit)
    else:
        items = security.audit_log.recent(limit=limit)
    ok, length = security.audit_log.verify_chain()
    return {"ok": ok, "chain_length": length, "items": items}


@app.get("/api/policy")
def api_policy() -> dict:
    """把权限矩阵暴露给前端与审计, 阈值来自代码而非模型。"""
    rows = []
    for action, tier in policy.STATIC_TIERS.items():
        rows.append({"action": action, "tier": tier.value,
                     "tier_label": policy.TIER_LABEL[tier],
                     "reason": policy.classify(action, {}, {}).reason,
                     "mfa": policy.MFA_FOR_ACTION.get(action, [])})
    return {"static": rows,
            "dynamic": {"actions": sorted(policy.AMOUNT_ACTIONS),
                        "yellow_limit": config.YELLOW_TRANSFER_LIMIT,
                        "review_amount": config.RED_SINGLE_AMOUNT},
            "breaker": {"max_failures": config.BREAKER_MAX_FAILURES,
                        "lock_seconds": config.BREAKER_LOCK_SECONDS},
            "mfa_labels": config.MFA_LABELS}


@app.get("/api/selfcheck")
def api_selfcheck() -> dict:
    return selfcheck.run_all()


@app.get("/api/demo/script")
def api_demo_script() -> dict:
    """演示剧本: 前端一键演示与字幕稿共用同一份事实来源。"""
    return {"steps": demo.script(), "total": len(demo.script())}


@app.post("/api/demo/run")
def api_demo_run() -> dict:
    """服务端完整重放剧本, 返回逐步结果(可用于回归与生成字幕稿)。"""
    result = demo.run()
    return {k: v for k, v in result.items() if k != "snapshot"}


@app.get("/api/health")
def api_health() -> dict:
    return {"ok": True, "app": config.APP_NAME, "version": config.VERSION,
            "llm": "enabled" if llm.enabled() else "rule-only",
            "sessions": len(executor.store.sessions)}


@app.get("/")
def landing():
    """产品落地页 (hero + Dashboard)。"""
    path = os.path.join(WEB_DIR, "landing.html")
    if not os.path.exists(path):
        return JSONResponse({"detail": "landing 未构建"}, status_code=200)
    return FileResponse(path)


@app.get("/login")
def login():
    """演示登录页 (身份选择器, 无账号密码)。"""
    path = os.path.join(WEB_DIR, "login.html")
    if not os.path.exists(path):
        return JSONResponse({"detail": "login 未构建"}, status_code=200)
    return FileResponse(path)


@app.get("/register")
def register():
    """演示注册页 (界面存在, 表单禁用, 不创建账户)。"""
    path = os.path.join(WEB_DIR, "register.html")
    if not os.path.exists(path):
        return JSONResponse({"detail": "register 未构建"}, status_code=200)
    return FileResponse(path)


@app.get("/center")
def center():
    """个人中心 (未登录由前端跳回登录页)。"""
    path = os.path.join(WEB_DIR, "center.html")
    if not os.path.exists(path):
        return JSONResponse({"detail": "center 未构建"}, status_code=200)
    return FileResponse(path)


@app.get("/app")
def console():
    """可交互的智能体控制台。"""
    path = os.path.join(WEB_DIR, "index.html")
    if not os.path.exists(path):
        return JSONResponse({"detail": "前端未构建", "api": "/docs"}, status_code=200)
    return FileResponse(path)


@app.get("/api/dashboard")
def api_dashboard(scope: str = "risk") -> dict:
    """落地页 / 个人中心 Dashboard 的数据源。

    scope=customer 时只返回客户视角能看懂的内容 (不出现权限矩阵、审计链路等后台术语)。
    """
    ledger = executor.store.get("landing-dashboard").ledger
    bill = ledger.bill_summary(30)
    snap = ledger.snapshot()
    counts = {"green": 0, "yellow": 0, "red": 0}
    for tier in policy.STATIC_TIERS.values():
        counts[tier.value] += 1
    bars = [{"label": b["category"], "value": float(b["amount"]), "ratio": b["ratio"]}
            for b in bill["breakdown"][:6]]
    logs = [{"stage": e["stage"], "summary": e["summary"],
             "ts": e["ts"].replace("T", " ")[11:19]} for e in security.audit_log.recent(8)][::-1]
    if not logs:      # 冷启动时也有一条真实事件可看
        security.audit_log.record("landing", "landing-dashboard", "system",
                                  f"看板加载完成, 权限矩阵 {sum(counts.values())} 个动作就绪")
        logs = [{"stage": e["stage"], "summary": e["summary"],
                 "ts": e["ts"].replace("T", " ")[11:19]} for e in security.audit_log.recent(8)][::-1]

    if scope == "customer":
        friendly = {"transfer": "转账", "query_balance": "余额查询", "analyze_bills": "账单分析",
                    "detect_anomaly": "异常识别", "list_subscriptions": "订阅清单",
                    "quote_wealth": "收益试算", "split_aa": "AA 收款",
                    "cancel_subscription": "取消订阅", "apply_virtual_card": "虚拟卡",
                    "reverse_transfer": "撤销转账", "subscribe_wealth": "理财申购",
                    "query_cards": "卡片查询", "lock_savings": "锁定活期"}
        friendly_logs = []
        for e in security.audit_log.recent(40):
            if e["stage"] != "tool":
                continue
            action = e["summary"].split(" ")[0]
            label = friendly.get(action)
            if not label:
                continue
            ok = "失败" not in e["summary"]
            friendly_logs.append({"stage": label,
                                  "summary": "办理成功" if ok else "办理未完成",
                                  "ts": e["ts"].replace("T", " ")[11:19]})
        if not friendly_logs:
            friendly_logs = [{"stage": "账户", "summary": "账户数据已加载",
                              "ts": security.audit_log.recent(1)[0]["ts"][11:19]
                              if security.audit_log.recent(1) else ""}]
        logs = friendly_logs[:6][::-1]
    return {
        "user": {"name": "张伟", "level": "金卡客户"},
        "stats": {
            "balance": snap["accounts"][0]["balance"],
            "month_spend": bill["total_out"],
            "policy_total": sum(counts.values()),
        },
        "bars": bars,
        "logs": logs,
        "policy": counts,
        "subs_monthly": f"{sum((s.amount if s.cycle == '月' else s.amount / 12 for s in ledger.subscriptions.values() if s.status == '生效中'), __import__('decimal').Decimal(0)):.2f}",
        "thresholds": {"yellow_limit": config.YELLOW_TRANSFER_LIMIT,
                       "review_amount": config.RED_SINGLE_AMOUNT,
                       "breaker": config.BREAKER_MAX_FAILURES},
        "today": snap["events"][0]["day"] if snap["events"] else "",
    }


if os.path.isdir(WEB_DIR):
    app.mount("/static", StaticFiles(directory=WEB_DIR), name="static")
