"""安全体系: 注入防御 / 幻觉防护 / 异常熔断 / 代码沙箱 / 全链路审计。

这一层的核心思想: 模型的输出永远是"不可信输入"。
所有权限判定、事实校验都发生在模型之外, 且不依赖模型的配合。
"""
from __future__ import annotations

import ast
import hashlib
import json
import os
import re
import time
from collections import deque
from dataclasses import dataclass, field
from datetime import datetime
from typing import Any, Deque, Dict, List, Optional, Tuple

from . import config


# ==================================================================== 审计
class AuditLog:
    """带哈希链的审计日志: 每条记录包含前一条的哈希, 支持防篡改校验。"""

    def __init__(self, path: str = config.AUDIT_FILE, memory_limit: int = 2000) -> None:
        self.path = path
        self._memory: Deque[dict] = deque(maxlen=memory_limit)
        self._prev = "GENESIS"
        try:
            os.makedirs(os.path.dirname(path), exist_ok=True)
        except OSError:
            self.path = ""      # 只读环境下退化为内存审计

    @staticmethod
    def _digest(entry: dict, prev: str) -> str:
        payload = json.dumps(entry, ensure_ascii=False, sort_keys=True) + prev
        return hashlib.sha256(payload.encode("utf-8")).hexdigest()[:16]

    def record(self, trace_id: str, session_id: str, stage: str, summary: str, **extra: Any) -> dict:
        entry = {
            "ts": datetime.now().isoformat(timespec="milliseconds"),
            "trace_id": trace_id,
            "session_id": session_id,
            "stage": stage,
            "summary": summary,
            "prev": self._prev,
            **extra,
        }
        entry["hash"] = self._digest(entry, self._prev)
        self._prev = entry["hash"]
        self._memory.append(entry)
        if self.path:
            try:
                with open(self.path, "a", encoding="utf-8") as fh:
                    fh.write(json.dumps(entry, ensure_ascii=False) + "\n")
            except OSError:
                pass
        return entry

    def for_session(self, session_id: str, limit: int = 60) -> List[dict]:
        items = [e for e in self._memory if e["session_id"] == session_id]
        return items[-limit:]

    def recent(self, limit: int = 80) -> List[dict]:
        return list(self._memory)[-limit:]

    def verify_chain(self) -> Tuple[bool, int]:
        """校验内存中审计链是否完整。"""
        prev = "GENESIS"
        for i, e in enumerate(self._memory):
            clone = {k: v for k, v in e.items() if k != "hash"}
            if clone.get("prev") != prev:
                return False, i
            if self._digest(clone, prev) != e["hash"]:
                return False, i
            prev = e["hash"]
        return True, len(self._memory)


# ==================================================================== 注入防御
INJECTION_PATTERNS: List[Tuple[str, str]] = [
    (r"忽略(掉)?(你)?(之前|以上|上述|先前|前面)的?(所有)?(指令|提示|规则|设定)", "要求覆盖既有指令"),
    (r"(无视|绕过|跳过|不用|无需|不需要)(你的)?(权限|风控|确认|验证|审核|审批)", "要求绕过风控/确认"),
    (r"ignore\s+(all\s+)?(previous|above|prior)\s+(instructions?|prompts?|rules?)", "英文越狱指令"),
    (r"(system\s*prompt|开发者模式|developer\s*mode|DAN|jailbreak|越狱模式)", "越狱关键词"),
    (r"<\|?(im_start|im_end|system)\|?>", "特殊角色标记注入"),
    (r"(我|本用户)(就)?是(管理员|行长|开发者|超级用户|系统)", "身份伪造"),
    # 注意: 不含"额度/限额" —— 用户自己调额是合法业务, 由权限引擎按红色处理;
    # 这里只拦"要求篡改风控参数/门槛"的表达。
    (r"把[^,。;]{0,6}(权限|等级|门槛|阈值|风控|白名单)[^,。;]{0,6}(改|设|调|放)(成|为|到|宽)", "要求篡改权限参数"),
    (r"(直接|立刻|马上)(给我|帮我)?(转|付|打款|汇)\s*[0-9一二三四五六七八九十百千万]+", "诱导直接执行资金操作"),
    (r"(这条|以下|上面)(消息|内容)(不用|不要)(记录|审计|上报)", "要求关闭审计"),
    (r"(假装|模拟|扮演)(你)?(是|成为)(没有|无)(限制|约束|风控)", "角色伪装绕过"),
]


@dataclass
class InjectionResult:
    blocked: bool
    hits: List[str] = field(default_factory=list)
    categories: List[str] = field(default_factory=list)


class InjectionGuard:
    """静态规则 + 归一化处理, 在任何模型调用之前执行。"""

    def __init__(self) -> None:
        self._compiled = [(re.compile(p, re.I), label) for p, label in INJECTION_PATTERNS]

    @staticmethod
    def normalize(text: str) -> str:
        # 全角转半角 + 去零宽字符 + 折叠空白, 防止用变体绕过
        out = []
        for ch in text:
            code = ord(ch)
            if code == 0x3000:
                out.append(" ")
            elif 0xFF01 <= code <= 0xFF5E:
                out.append(chr(code - 0xFEE0))
            elif code in (0x200B, 0x200C, 0x200D, 0xFEFF):
                continue
            else:
                out.append(ch)
        return re.sub(r"\s+", " ", "".join(out)).strip()

    def scan(self, text: str) -> InjectionResult:
        normalized = self.normalize(text)
        hits, cats = [], []
        for pattern, label in self._compiled:
            if pattern.search(normalized):
                hits.append(pattern.pattern)
                cats.append(label)
        return InjectionResult(blocked=bool(hits), hits=hits, categories=cats)


# ==================================================================== 幻觉防护
MONEY_RE = re.compile(
    r"(?:¥|￥)\s*(-?[0-9][0-9,]*(?:\.[0-9]+)?)|(-?[0-9][0-9,]*(?:\.[0-9]+)?)\s*(?:元|块钱|块)"
)
TAIL_RE = re.compile(r"(?:尾号|末四位)\s*([0-9]{4})")


@dataclass
class VerifyResult:
    ok: bool
    violations: List[str] = field(default_factory=list)
    checked: int = 0


class HallucinationGuard:
    """回复后置校验: 回答中出现的金额/卡号尾号必须来自工具真实返回的事实集。"""

    @staticmethod
    def _norm(amount: str) -> float:
        try:
            return round(float(amount.replace(",", "")), 2)
        except ValueError:
            return -1.0

    def verify(self, reply: str, facts: Dict[str, Any]) -> VerifyResult:
        allowed_amounts = {round(float(a), 2) for a in facts.get("amounts", [])}
        allowed_tails = {str(t) for t in facts.get("tails", [])}
        violations: List[str] = []
        checked = 0

        for m in MONEY_RE.finditer(reply):
            raw = m.group(1) or m.group(2)
            checked += 1
            if self._norm(raw) not in allowed_amounts:
                violations.append(f"金额 {raw} 元无事实依据")

        for m in TAIL_RE.finditer(reply):
            checked += 1
            if m.group(1) not in allowed_tails:
                violations.append(f"卡号尾号 {m.group(1)} 无事实依据")

        return VerifyResult(ok=not violations, violations=violations, checked=checked)

    @staticmethod
    def safe_reply(facts: Dict[str, Any]) -> str:
        lines = facts.get("verified_lines") or []
        body = "\n".join(f"· {x}" for x in lines) if lines else "本次没有可确认的数据变更。"
        return ("为了不给你错误信息, 我把这次的真实执行结果列出来, 请以此为准:\n" + body)


# ==================================================================== 异常熔断
@dataclass
class BreakerState:
    failures: int = 0
    injections: int = 0
    locked_until: float = 0.0
    reason: str = ""


class CircuitBreaker:
    def __init__(self) -> None:
        self.states: Dict[str, BreakerState] = {}

    def state(self, session_id: str) -> BreakerState:
        return self.states.setdefault(session_id, BreakerState())

    def is_locked(self, session_id: str) -> Tuple[bool, int, str]:
        st = self.state(session_id)
        remain = int(st.locked_until - time.time())
        if remain > 0:
            return True, remain, st.reason
        return False, 0, ""

    def _lock(self, session_id: str, reason: str) -> BreakerState:
        st = self.state(session_id)
        st.locked_until = time.time() + config.BREAKER_LOCK_SECONDS
        st.reason = reason
        return st

    def record_failure(self, session_id: str, reason: str) -> bool:
        st = self.state(session_id)
        st.failures += 1
        if st.failures >= config.BREAKER_MAX_FAILURES:
            self._lock(session_id, f"连续 {st.failures} 次操作失败: {reason}")
            return True
        return False

    def record_success(self, session_id: str) -> None:
        st = self.state(session_id)
        st.failures = 0

    def record_injection(self, session_id: str) -> bool:
        st = self.state(session_id)
        st.injections += 1
        if st.injections >= config.BREAKER_MAX_INJECTIONS:
            self._lock(session_id, f"检测到 {st.injections} 次提示注入攻击尝试, 已触发安全锁定")
            return True
        return False

    def manual_unlock(self, session_id: str) -> None:
        st = self.state(session_id)
        st.failures = 0
        st.injections = 0
        st.locked_until = 0.0
        st.reason = ""


# ==================================================================== 代码沙箱
class SandboxError(Exception):
    pass


class Sandbox:
    """AST 白名单沙箱: 只允许算术/比较/内置纯函数, 禁止属性访问、导入、赋值。

    Agent 生成的任何"计算类脚本"(如收益试算)都在这里执行, 不触碰真实系统。
    """

    ALLOWED_NODES = (
        ast.Expression, ast.BinOp, ast.UnaryOp, ast.Constant, ast.Name, ast.Load,
        ast.Call, ast.Subscript, ast.List, ast.Tuple, ast.Dict, ast.Compare,
        ast.IfExp, ast.BoolOp, ast.And, ast.Or, ast.Not,
        ast.Add, ast.Sub, ast.Mult, ast.Div, ast.FloorDiv, ast.Mod, ast.Pow,
        ast.USub, ast.UAdd, ast.Lt, ast.Gt, ast.LtE, ast.GtE, ast.Eq, ast.NotEq,
        ast.Slice,
    )
    SAFE_FUNCS = {"sum", "min", "max", "len", "round", "abs", "int", "float", "sorted"}

    def __init__(self) -> None:
        self.trace: List[str] = []

    def run(self, expr: str, context: Optional[Dict[str, Any]] = None) -> Any:
        expr = (expr or "").strip()
        if not expr:
            raise SandboxError("表达式为空")
        if len(expr) > config.SANDBOX_MAX_EXPR_LEN:
            raise SandboxError("表达式过长, 已拒绝执行")
        try:
            tree = ast.parse(expr, mode="eval")
        except SyntaxError as exc:
            raise SandboxError(f"语法错误: {exc.msg}") from exc

        for node in ast.walk(tree):
            if not isinstance(node, self.ALLOWED_NODES):
                raise SandboxError(f"禁止的语法节点: {type(node).__name__}")
            if isinstance(node, ast.Name) and node.id.startswith("__"):
                raise SandboxError("禁止访问下划线名称")

        env: Dict[str, Any] = {"__builtins__": {}}
        for k, v in (context or {}).items():
            if isinstance(v, (int, float, str, list, dict, tuple)):
                env[k] = v
        import builtins as _builtins
        for fn in self.SAFE_FUNCS:
            env[fn] = getattr(_builtins, fn)
        self.trace = ["AST 白名单校验通过", f"节点数 {len(list(ast.walk(tree)))}", "受限作用域执行"]
        try:
            return eval(compile(tree, "<sandbox>", "eval"), env)  # noqa: S307 - 已做 AST 白名单
        except Exception as exc:  # noqa: BLE001
            raise SandboxError(f"执行失败: {exc}") from exc


# ==================================================================== 单例
audit_log = AuditLog()
injection_guard = InjectionGuard()
hallucination_guard = HallucinationGuard()
breaker = CircuitBreaker()
sandbox = Sandbox()
