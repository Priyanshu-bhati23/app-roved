import httpx
import pytest
from fastapi.testclient import TestClient

from web import app as web

client = TestClient(web.app)

ORDER = {"plan": "review", "name": "Asha", "email": "asha@example.com", "app_name": "Notely", "scan_summary": "blocked"}


@pytest.fixture(autouse=True)
def clean_env(monkeypatch):
    for key in (
        "ORDER_WEBHOOK_URL",
        "CONTACT_EMAIL",
        "PAY_URL_REVIEW",
        "PAY_URL_RESCUE",
        "PRICE_REVIEW",
        "LAUNCH_NOTE",
    ):
        monkeypatch.delenv(key, raising=False)
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
    web._recent.clear()


class FakeResponse:
    def raise_for_status(self):
        return None


def capture(monkeypatch):
    sent = []
    monkeypatch.setattr(web.httpx, "post", lambda url, json, timeout: sent.append((url, json)) or FakeResponse())
    return sent


def test_page_renders_config_and_escapes_it(monkeypatch):
    monkeypatch.setenv("PRICE_REVIEW", "₹1,999")
    monkeypatch.setenv("LAUNCH_NOTE", "<script>alert(1)</script>")
    body = client.get("/").text
    assert "₹1,999" in body
    assert "<script>alert(1)</script>" not in body
    assert "{{" not in body
    assert client.get("/slim.js").headers["content-type"].startswith("text/javascript")
    assert client.get("/phone3d.js").status_code == 200
    assert client.get("/app.js").status_code == 404  # only the site's own scripts are served


def test_sample_scan_finds_the_planted_problems():
    body = client.post("/v1/demo-scan").json()
    assert body["verdict"] == "blocked"
    assert {"SIGN-002", "PLIST-005"} <= {f["signal"]["id"] for f in body["findings"]}


def test_orders_are_closed_without_a_webhook(monkeypatch):
    monkeypatch.setenv("CONTACT_EMAIL", "hi@example.com")
    r = client.post("/v1/orders", json=ORDER)
    assert r.status_code == 503
    assert "hi@example.com" in r.json()["detail"]


def test_order_goes_to_discord_and_returns_the_payment_link(monkeypatch):
    monkeypatch.setenv("ORDER_WEBHOOK_URL", "https://discord.com/api/webhooks/1/x")
    monkeypatch.setenv("PAY_URL_REVIEW", "https://pay.example/review")
    sent = capture(monkeypatch)
    r = client.post("/v1/orders", json=ORDER)
    assert r.json() == {"ok": True, "pay_url": "https://pay.example/review"}
    url, payload = sent[0]
    assert "Pre-submission review ($29)" in payload["content"] and "asha@example.com" in payload["content"]
    assert payload["allowed_mentions"] == {"parse": []}  # an order can't ping @everyone


def test_slack_webhooks_get_slack_format(monkeypatch):
    monkeypatch.setenv("ORDER_WEBHOOK_URL", "https://hooks.slack.com/services/x")
    sent = capture(monkeypatch)
    client.post("/v1/orders", json=dict(ORDER, plan="rescue", rejection="Guideline 5.1.1"))
    assert "Rejection rescue" in sent[0][1]["text"] and "Guideline 5.1.1" in sent[0][1]["text"]


def test_honeypot_bad_email_throttle_and_webhook_failure(monkeypatch):
    monkeypatch.setenv("ORDER_WEBHOOK_URL", "https://discord.com/api/webhooks/1/x")
    sent = capture(monkeypatch)
    assert client.post("/v1/orders", json=dict(ORDER, website="spam.example")).json()["ok"]
    assert sent == []
    assert client.post("/v1/orders", json=dict(ORDER, email="not-an-email")).status_code == 422
    codes = [client.post("/v1/orders", json=ORDER).status_code for _ in range(web.MAX_ORDERS_PER_HOUR + 1)]
    assert codes[-1] == 429

    web._recent.clear()

    def boom(*a, **k):
        raise httpx.ConnectError("down")

    monkeypatch.setattr(web.httpx, "post", boom)
    assert client.post("/v1/orders", json=ORDER).status_code == 502
