"""演示剧本回归测试: 剧本里每一步的预期都必须成立。"""
from app import demo, executor


def test_script_is_consistent():
    steps = demo.script()
    assert len(steps) >= 10
    ids = [s["id"] for s in steps]
    assert len(ids) == len(set(ids))
    for s in steps:
        assert s["say"] and s["expect"] and s["note"]
        assert s["expect"] in ("done", "awaiting_confirm", "awaiting_choice", "blocked", "clarify")


def test_script_covers_all_six_scenes():
    scenes = " ".join(s["scene"] for s in demo.script())
    for key in ("转账", "账单", "理财", "订阅", "跨场景", "注入"):
        assert key in scenes, key


def test_full_demo_replay_passes():
    result = demo.run("demo-test")
    assert result["ok"] is True, [s for s in result["steps"] if not s["ok"]]
    assert result["passed"] == result["total"]


def test_demo_covers_every_permission_tier():
    result = demo.run("demo-test-tier")
    tiers = {s["tier"] for s in result["steps"] if s["tier"]}
    assert {"green", "yellow", "red"} <= tiers
    mfa = {s["used_mfa"] for s in result["steps"] if s["used_mfa"]}
    assert mfa, "剧本里至少要有一次强验证"


def test_demo_blocks_injection_without_moving_money():
    result = demo.run("demo-test-ajax")
    blocked = [s for s in result["steps"] if "注入" in s["scene"]][0]
    assert blocked["final_status"] == "blocked"
    snap = result["snapshot"]
    cur = [a for a in snap["accounts"] if a["name"] == "活期账户"][0]
    assert cur["balance"] != "0.00"


def test_demo_transcript_renders():
    result = demo.run("demo-test-md")
    md = demo.transcript_markdown(result)
    assert md.startswith("# 银掌柜 · 演示字幕稿")
    assert "S11" in md and "银掌柜" in md


def test_demo_is_repeatable():
    a = demo.run("demo-test-repeat")
    b = demo.run("demo-test-repeat")
    assert a["passed"] == b["passed"] == a["total"]
