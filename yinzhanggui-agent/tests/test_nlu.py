"""意图理解层测试: 金额解析 / 模糊表达 / 省略上下文。"""
from app import nlu


def test_parse_amount_digits():
    assert nlu.parse_amount("给王强转500元") == 500
    assert nlu.parse_amount("转 128.50 块") == 128.5


def test_parse_amount_units():
    assert nlu.parse_amount("转1.5万") == 15000
    assert nlu.parse_amount("转3千") == 3000


def test_parse_amount_chinese():
    assert nlu.parse_amount("转五百") == 500
    assert nlu.parse_amount("转一千五") is not None


def test_parse_amount_ignores_long_numbers():
    assert nlu.parse_amount("卡号 6222020200112345678") is None


def test_intent_transfer():
    it = nlu.understand("给王强转200元")
    assert it.name == "transfer"
    assert it.slots["amount"] == 200
    assert it.slots["contact_name"] == "王强"
    assert it.missing == []


def test_intent_transfer_note():
    it = nlu.understand("给王强转200元，备注饭钱")
    assert "饭钱" in str(it.slots.get("note"))


def test_intent_transfer_scheduled():
    it = nlu.understand("下周给房东转800元")
    assert it.name == "transfer"
    assert it.slots.get("when")


def test_intent_aa():
    it = nlu.understand("我们4个人AA，总共800元")
    assert it.name == "split_aa"
    assert it.slots["payee_count"] == 4
    assert it.slots["total"] == 800


def test_intent_bill_colloquial():
    assert nlu.understand("这个月钱都花哪了").name == "bill_report"


def test_intent_anomaly():
    assert nlu.understand("有没有异常扣费").name == "bill_anomaly"


def test_intent_subscription_ellipsis():
    it = nlu.understand("把那个一直扣钱的关掉")
    assert it.name == "subs_cancel"
    assert it.slots.get("auto_pick_risky") is True


def test_intent_cross_scene():
    assert nlu.understand("我爱人生日快到了，帮我安排一下").name == "cross_birthday"


def test_intent_wealth_quote():
    it = nlu.understand("1万块稳盈90天能赚多少")
    assert it.name == "wealth_quote"
    assert it.slots["amount"] == 10000
    assert it.slots["product_hint"] == "稳盈"


def test_intent_unknown_is_not_guessed():
    assert nlu.understand("今天天气怎么样").name == "unknown"


def test_pronoun_resolution_from_context():
    it = nlu.understand("转500给他", {"last_contact": "王强"})
    assert it.name == "transfer"
    assert it.slots["contact_name"] == "王强"
    assert "代词" in it.hint


def test_missing_amount_asks_back():
    it = nlu.understand("给王强转点钱")
    assert it.name == "transfer"
    assert "amount" in it.missing


def test_greeting_is_help():
    assert nlu.understand("你好，你能做什么").name == "help"


def test_full_width_text_still_parsed():
    it = nlu.understand("给李静转３００元")
    assert it.name == "transfer"
    assert it.slots["amount"] == 300
