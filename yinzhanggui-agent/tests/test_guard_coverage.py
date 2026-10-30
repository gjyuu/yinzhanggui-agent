"""幻觉防护回归: 常规场景下不允许出现"事实校验拦截"。

如果某个工具的回复里出现了没登记进 facts 的金额, 这里会立刻暴露出来
(历史上就是靠这一类断言抓到了"每月还差 32,031.43 元"这种漏登记)。
"""
import pytest

from app import executor, security

SENTENCES = [
    "我还有多少钱",
    "给王强转200元，备注饭钱",
    "给尾号3382的手机号转100",
    "这个月钱都花哪了",
    "有没有异常扣费",
    "我订了哪些会员",
    "把那个一直扣钱的关掉",
    "我有哪些卡",
    "我还剩多少额度",
    "有什么稳一点的理财",
    "这几款理财产品有什么区别",
    "1万块稳盈90天能赚多少",
    "赎回全部天天利",
    "我爱人生日快到了，帮我安排一下",
    "我妈生日快到了，帮我安排一下",
    "我准备给我爱人买车，我可以拿出多少钱",
    "我准备买套房，预算 120 万，三年能攒够吗",
    "明年结婚，帮我准备 5 万，大概需要 30 万",
    "申请虚拟卡",
    "办张实体储蓄卡",
]


@pytest.mark.parametrize("text", SENTENCES)
def test_reply_is_grounded(text):
    sid = f"guard-{abs(hash(text)) % 10000}"
    executor.store.reset(sid)
    security.breaker.manual_unlock(sid)
    r = executor.chat(sid, text)
    assert not r.get("guard_blocked"), f"{text} -> {r.get('guard_blocked')}"
    assert r["status"] != "clarify", f"{text} 不该落到澄清"
