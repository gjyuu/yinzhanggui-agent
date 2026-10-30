"""全局配置与演示策略常量。

设计原则: 风控阈值写在代码里, 不交给模型 —— "能力交给模型, 权限交给框架"。
"""
from __future__ import annotations

import os

APP_NAME = "银掌柜"
APP_NAME_EN = "YinZhangGui"
APP_TAGLINE = "一句话, 把银行办了"
VERSION = "1.0.0"

# ---------------------------------------------------------------- 当前登录用户
DEMO_USER = {
    "id": "u_10086",
    "name": "张伟",
    "level": "金卡客户",
    "phone_masked": "138****6621",
}

# ---------------------------------------------------------------- 权限阈值 (元)
YELLOW_TRANSFER_LIMIT = 1000.0     # 日累计 <= 1000 走黄色(确认), > 1000 升级红色(强验证)
RED_SINGLE_AMOUNT = 5000.0         # 单笔 >= 5000, 额外标记人工复核建议

# ---------------------------------------------------------------- 异常熔断
BREAKER_MAX_FAILURES = 3           # 连续失败次数
BREAKER_LOCK_SECONDS = 300         # 锁定时长
BREAKER_MAX_INJECTIONS = 2         # 注入尝试累计阈值

# ---------------------------------------------------------------- 沙箱
SANDBOX_MAX_EXPR_LEN = 200
SANDBOX_TIMEOUT_SECONDS = 1.0

# ---------------------------------------------------------------- LLM 适配 (可选)
# 未配置时自动降级为本地确定性理解器, 演示与测试不依赖网络。
LLM_BASE_URL = os.getenv("YINZHANGGUI_LLM_BASE_URL", "").rstrip("/")
LLM_API_KEY = os.getenv("YINZHANGGUI_LLM_API_KEY", "")
LLM_MODEL = os.getenv("YINZHANGGUI_LLM_MODEL", "deepseek-chat")
LLM_TIMEOUT = float(os.getenv("YINZHANGGUI_LLM_TIMEOUT", "12"))

# ---------------------------------------------------------------- 审计
AUDIT_DIR = os.getenv("YINZHANGGUI_AUDIT_DIR", os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "runtime"))
AUDIT_FILE = os.path.join(AUDIT_DIR, "audit.jsonl")

# ---------------------------------------------------------------- MFA
MFA_METHODS = ["face", "sms", "ushield"]
MFA_LABELS = {"face": "人脸识别", "sms": "短信验证码", "ushield": "U 盾 (USB Key)"}
MFA_MAX_ATTEMPTS = 3
