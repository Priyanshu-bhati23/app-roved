from fastapi.testclient import TestClient

from approved import ipa, rag
from approved.engine import analyze
from approved.review import AppProfile, build_review, guideline_numbers, load_setup_catalog, rescue, setup_findings
from web import app as web

from .builders import build_ipa, build_macho

client = TestClient(web.app)


class FakeLLM:
    name = "fake-model"

    def __init__(self, reply):
        self.reply = reply

    def complete(self, system, user):
        if isinstance(self.reply, Exception):
            raise self.reply
        return self.reply


def ids(profile):
    return [i for i, _ in setup_findings(profile)]


def test_setup_catalog_is_consistent_and_every_rule_has_an_entry():
    catalog = load_setup_catalog()
    assert len(catalog) == 14
    everything = AppProfile(
        has_login=True,
        creates_accounts=True,
        social_login=True,
        sells_digital=True,
        subscriptions=True,
        privacy_policy=False,
        user_content=True,
        kids_category=True,
        third_party_ads_analytics=True,
        tracks_users=True,
        mostly_web=True,
        review_notes=False,
        description="Beta! Also on Android and Google Play. Lorem ipsum.",
    )
    found = ids(everything)
    assert len(found) == 14 and all(i in catalog for i in found)


def test_a_well_set_up_app_has_no_setup_findings():
    good = AppProfile(
        has_login=True,
        demo_account=True,
        creates_accounts=True,
        in_app_deletion=True,
        social_login=True,
        privacy_login=True,
        sells_digital=True,
        uses_iap=True,
        subscriptions=True,
        terms_and_privacy_links=True,
        user_content=True,
        report_and_block=True,
        tracks_users=True,
        uses_att=True,
        description="Track your budget and scan receipts. Works offline.",
    )
    assert ids(good) == []


def test_description_rules_ignore_innocent_words():
    assert ids(AppProfile(description="Our betamax-style retro player plays tests of your hearing")) == []
    assert ids(AppProfile(description="Coming soon: dark mode")) == ["SETUP-012"]


def test_guideline_numbers_are_read_from_the_rejection():
    text = "Guideline 3.1.2(c) - Business - Payments - Subscriptions\nAlso Guideline 5.1.1(v)"
    assert guideline_numbers(text) == ["3.1.2", "5.1.1"]


def test_rescue_without_llm_uses_the_matching_guideline():
    help_ = rescue("Guideline 4.8 - Design - Login Services. Your app uses a third-party login service", None)
    assert help_.guidelines == ["4.8"]
    assert "Sign in with Apple" in help_.meaning
    assert "build [build number]" in help_.reply and help_.generated_by == "template"


def test_rescue_keeps_a_grounded_llm_answer_and_drops_an_ungrounded_one():
    kb = rag.load_knowledge_base()
    login = next(c.id for c in kb.chunks if c.title.startswith("4.8"))
    good = (
        f"MEANING: You need a privacy-focused login next to Google [{login}].\n"
        f"STEPS:\n- Add Sign in with Apple [{login}]\n"
        "REPLY: Hello, we added Sign in with Apple in build [x]."
    )
    help_ = rescue("Guideline 4.8 - Login Services", FakeLLM(good))
    assert help_.generated_by == "fake-model" and help_.steps == ["Add Sign in with Apple"]
    bold = good.replace("MEANING:", "**MEANING:**").replace("STEPS:", "### STEPS:").replace("REPLY:", "**REPLY:**")
    assert rescue("Guideline 4.8 - Login Services", FakeLLM(bold)).generated_by == "fake-model"
    invented = "MEANING: Apple hates Google [kb:made-up#1].\nSTEPS:\n- x\nREPLY: hi"
    assert rescue("Guideline 4.8", FakeLLM(invented)).generated_by == "template"
    assert rescue("Guideline 4.8", FakeLLM(RuntimeError("429"))).generated_by == "template"


def test_full_review_merges_build_and_setup_and_orders_by_severity():
    scan = analyze(ipa.load(build_ipa(binary=build_macho(signed=False))))
    review = build_review(scan, AppProfile(has_login=True, mostly_web=True), None, None)
    assert review.verdict == "fix_first"
    severities = [i.severity.value for i in review.items]
    assert severities == sorted(severities, key=["blocker", "warning", "info"].index)
    assert {"SIGN-001", "SETUP-001", "SETUP-010"} <= {i.id for i in review.items}
    clean = build_review(None, AppProfile(), None, None)
    assert clean.verdict == "ready" and clean.items == []


def test_review_endpoint(monkeypatch):
    for k in ("OPENAI_API_KEY", "ANTHROPIC_API_KEY", "ORDER_WEBHOOK_URL"):
        monkeypatch.delenv(k, raising=False)
    web._review_hits.clear()
    scan = client.post("/v1/demo-scan").json()
    r = client.post("/v1/review", json={"plan": "review", "profile": {"has_login": True}, "scan": scan})
    assert r.status_code == 200 and r.json()["verdict"] == "fix_first"
    r = client.post(
        "/v1/review", json={"plan": "rescue", "rejection": "Guideline 2.1 - Performance - App Completeness"}
    )
    assert r.json()["rejection"]["guidelines"] == ["2.1"]
    assert client.post("/v1/review", json={"plan": "rescue"}).status_code == 422
    assert client.post("/v1/review", json={"plan": "review"}).status_code == 422
