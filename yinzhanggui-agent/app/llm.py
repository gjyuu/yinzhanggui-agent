"""可选的大模型适配器 (OpenAI 兼容 /chat/completions 协议)。

定位: 只负责"理解自然语言"这一件事。
权限分级、金额校验、执行与审计全部在确定性代码里完成 —— 模型无法提权。
未配置密钥时返回 None, 系统自动使用本地规则理解器。
"""
from __future__ import annotations

import json
import urllib.error
import urllib.request
from typing import Optional

from . import config

SYSTEM_PROMPT = """你是银行智能体的"意图理解模块"。只做语义解析, 不做任何权限判断, 也不执行操作。
把用户话转成 JSON: {"intent": <意图名>, "slots": {...}, "reason": "<一句话>", "confidence": 0~1}
可选意图: transfer, split_aa, balance, bill_report, bill_anomaly, bill_category,
wealth_recommend, wealth_quote, wealth_subscribe, wealth_redeem, card_list, card_freeze,
card_unfreeze, card_limit, card_virtual, card_password, txn_limit, subs_list, subs_cancel,
subs_scan, cross_birthday, cancel_last, pause, takeover, help
常用槽位: amount(数字), contact_name(人名/称谓), note(备注), when(时间词), days(整数),
product_hint, reference, card_hint, total, payee_count
只输出 JSON, 不要解释。"""


def enabled() -> bool:
    return bool(config.LLM_BASE_URL and config.LLM_API_KEY)


def understand(text: str, context: Optional[dict] = None) -> Optional[dict]:
    if not enabled():
        return None
    payload = {
        "model": config.LLM_MODEL,
        "temperature": 0.0,
        "max_tokens": 300,
        "messages": [
            {"role": "system", "content": SYSTEM_PROMPT},
            {"role": "user", "content": json.dumps(
                {"text": text, "context": context or {}}, ensure_ascii=False)},
        ],
    }
    req = urllib.request.Request(
        f"{config.LLM_BASE_URL}/chat/completions",
        data=json.dumps(payload).encode("utf-8"),
        headers={"Content-Type": "application/json",
                 "Authorization": f"Bearer {config.LLM_API_KEY}"},
        method="POST",
    )
    try:
        with urllib.request.urlopen(req, timeout=config.LLM_TIMEOUT) as resp:
            body = json.loads(resp.read().decode("utf-8"))
        content = body["choices"][0]["message"]["content"].strip()
        content = content.removeprefix("```json").removeprefix("```").removesuffix("```").strip()
        parsed = json.loads(content)
        if not isinstance(parsed, dict) or "intent" not in parsed:
            return None
        return parsed
    except (urllib.error.URLError, KeyError, json.JSONDecodeError, TimeoutError, OSError, IndexError):
        return None      # 任何异常都静默降级到规则理解器
