"""HTTP 接口测试 (FastAPI TestClient)。"""
import pytest
from fastapi.testclient import TestClient

from app.main import app


@pytest.fixture(scope="module")
def client():
    return TestClient(app)


def test_health(client):
    r = client.get("/api/health")
    assert r.status_code == 200
    body = r.json()
    assert body["ok"] is True
    assert body["version"]


def test_policy_matrix(client):
    r = client.get("/api/policy")
    body = r.json()
    assert len(body["static"]) >= 20
    assert body["dynamic"]["yellow_limit"] == 1000
    tiers = {row["tier"] for row in body["static"]}
    assert tiers == {"green", "yellow", "red"}


def test_index_served(client):
    r = client.get("/")
    assert r.status_code == 200
    assert "银掌柜" in r.text


def test_chat_confirm_roundtrip(client):
    r = client.post("/api/chat", json={"session_id": "api-1", "text": "给王强转200元"})
    body = r.json()
    assert body["status"] == "awaiting_confirm"
    assert body["pending"][0]["tier"] == "yellow"

    r2 = client.post("/api/confirm", json={"session_id": "api-1", "decision": "approve"})
    assert r2.json()["status"] == "done"


def test_confirm_without_pending(client):
    r = client.post("/api/confirm", json={"session_id": "api-empty", "decision": "approve"})
    assert r.json()["status"] in ("idle", "done")


def test_bad_decision_rejected(client):
    r = client.post("/api/confirm", json={"session_id": "api-1", "decision": "maybe"})
    assert r.status_code == 400


def test_selfcheck_all_pass(client):
    r = client.get("/api/selfcheck")
    body = r.json()
    assert body["total"] >= 8
    assert body["failed"] == 0, [c for c in body["cases"] if not c["passed"]]


def test_audit_endpoint_verifies_chain(client):
    client.post("/api/chat", json={"session_id": "api-audit", "text": "我还有多少钱"})
    r = client.get("/api/audit?session_id=api-audit")
    body = r.json()
    assert body["ok"] is True
    assert body["chain_length"] > 0
    assert body["items"]
    assert all("hash" in item for item in body["items"])


def test_session_reset(client):
    client.post("/api/chat", json={"session_id": "api-reset", "text": "给王强转200元"})
    client.post("/api/confirm", json={"session_id": "api-reset", "decision": "approve"})
    r = client.post("/api/session/api-reset/reset")
    body = r.json()
    balances = {a["name"]: a["balance"] for a in body["snapshot"]["accounts"]}
    assert balances["活期账户"] == "12846.50"


def test_mfa_flow_via_api(client):
    client.post("/api/chat", json={"session_id": "api-mfa", "text": "给王强转1500元"})
    r = client.post("/api/confirm", json={"session_id": "api-mfa", "decision": "approve"})
    mfa = r.json()["mfa"]
    r2 = client.post("/api/mfa/verify",
                     json={"session_id": "api-mfa", "method": "sms", "code": mfa["demo_code"]})
    assert r2.json()["status"] == "done"
