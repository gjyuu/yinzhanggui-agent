"""权限分级引擎测试: 三级判定 / 日累计升级 / 未知动作 fail-closed。"""
from app import config, policy
from app.policy import Tier


def test_green_pure_queries_auto_execute():
    for action in ("query_balance", "query_txn", "analyze_bills", "query_wealth",
                   "list_subscriptions", "query_cards", "query_calendar"):
        d = policy.classify(action)
        assert d.tier is Tier.GREEN, action
        assert d.requires_confirmation is False
        assert d.requires_mfa is False


def test_yellow_small_transfer():
    d = policy.classify("transfer", {"amount": 300}, {"daily_transfer_total": 0})
    assert d.tier is Tier.YELLOW
    assert d.requires_confirmation is True
    assert d.requires_mfa is False


def test_yellow_boundary_is_inclusive():
    d = policy.classify("transfer", {"amount": 1000}, {"daily_transfer_total": 0})
    assert d.tier is Tier.YELLOW


def test_red_when_daily_cumulative_exceeds_limit():
    d = policy.classify("transfer", {"amount": 300}, {"daily_transfer_total": 800})
    assert d.tier is Tier.RED
    assert d.requires_mfa is True
    assert d.detail["daily_projected"] == 1100


def test_red_single_large_amount_gets_review_flag():
    d = policy.classify("transfer", {"amount": 6000}, {"daily_transfer_total": 0})
    assert d.tier is Tier.RED
    assert d.review_flag is True


def test_scheduled_transfer_uses_single_amount():
    assert policy.classify("transfer", {"amount": 800, "when": "明天"},
                           {"daily_transfer_total": 0}).tier is Tier.YELLOW
    assert policy.classify("transfer", {"amount": 1800, "when": "明天"},
                           {"daily_transfer_total": 0}).tier is Tier.RED


def test_split_aa_is_yellow_collection():
    d = policy.classify("split_aa", {"total": 800, "payee_count": 4})
    assert d.tier is Tier.YELLOW


def test_red_actions_require_mfa_methods():
    for action in ("freeze_card", "unfreeze_card", "change_password",
                   "subscribe_wealth", "adjust_card_limit"):
        d = policy.classify(action)
        assert d.tier is Tier.RED, action
        assert d.requires_mfa is True
        assert d.mfa_methods, action


def test_yellow_state_changes():
    for action in ("lock_savings", "apply_virtual_card", "cancel_subscription",
                   "set_txn_limit", "redeem_wealth", "schedule_order"):
        d = policy.classify(action)
        assert d.tier is Tier.YELLOW, action


def test_unknown_action_fails_closed():
    d = policy.classify("delete_all_accounts", {})
    assert d.tier is Tier.RED
    assert d.requires_mfa is True


def test_thresholds_come_from_config():
    assert config.YELLOW_TRANSFER_LIMIT == 1000
    assert config.BREAKER_MAX_FAILURES == 3


def test_max_tier_picks_strictest():
    d = policy.max_tier(["query_balance", "transfer", "freeze_card"],
                        {"transfer": {"amount": 100}},
                        {"daily_transfer_total": 0})
    assert d.tier is Tier.RED
