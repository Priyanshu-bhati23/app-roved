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
    assert len(catalog) == 21
    everything = AppProfile(
        login_wall=True,
        account_needed=False,
        demo_account=True,
        demo_full_access=False,
        extra_personal_info=True,
        social_revoke=False,
        privacy_login=False,
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
    # deletion that exists but only deactivates, with Sign in with Apple tokens left alive
    partial = AppProfile(
        has_login=True,
        creates_accounts=True,
        in_app_deletion=True,
        full_deletion=False,
        privacy_login=True,
        siwa_revoke=False,
        subscriptions=True,
        deletion_billing_notice=False,
    )
    found = ids(everything) + ids(partial)
    assert ids(partial) == ["SETUP-001", "SETUP-005", "SETUP-016", "SETUP-019", "SETUP-020"]
    assert sorted(set(found)) == sorted(s.id for s in catalog)


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


def test_sign_in_rules_follow_apple_5_1_1_v():
    # Senad's case: a login wall in front of features that work without an account
    assert ids(AppProfile(has_login=True, demo_account=True, login_wall=True, account_needed=False)) == ["SETUP-015"]
    # a login wall is fine when the app is account-based, or when there is a guest mode
    assert ids(AppProfile(has_login=True, demo_account=True, login_wall=True, account_needed=True)) == []
    assert ids(AppProfile(has_login=True, demo_account=True, login_wall=False, account_needed=False)) == []
    # no in-app deletion at all is SETUP-002, not also SETUP-016
    assert ids(AppProfile(creates_accounts=True, in_app_deletion=False, full_deletion=False)) == ["SETUP-002"]
    assert ids(AppProfile(social_login=True, privacy_login=True, social_revoke=False)) == ["SETUP-018"]
    assert ids(AppProfile(has_login=True, demo_account=True, demo_full_access=False)) == ["SETUP-021"]
    assert ids(AppProfile(has_login=True, demo_full_access=False)) == ["SETUP-001"]


def test_rescue_for_a_login_wall_rejection_uses_the_sign_in_section():
    rejection = (
        "Guideline 5.1.1(v) - Legal - Privacy - Data Collection and Storage\n"
        "We noticed that your app requires users to register or log in to access features that are not account-based."
    )
    help_ = rescue(rejection, None)
    assert help_.guidelines == ["5.1.1"]
    assert "without logging in" in help_.meaning and "guest" in help_.meaning
    kb = rag.load_knowledge_base()
    deletion = rescue(
        "Guideline 5.1.1(v) - your app supports account creation"
        " but does not include an option to initiate account deletion",
        None,
        kb,
    )
    assert "delet" in deletion.meaning
    from approved.review import _chunks_for

    titles = [c.title for c in _chunks_for(["5.1.1"], "5.1.1(v) account deletion option", kb)]
    assert titles[0].startswith("5.1.1(v)") and "Account deletion in the app" in titles


def test_a_problem_found_in_build_and_answers_is_reported_once():
    scan = analyze(ipa.load(build_ipa(binary=build_macho(symbols=("_OBJC_CLASS_$_GIDSignIn",), entitlements={}))))
    review = build_review(scan, AppProfile(has_login=True, demo_account=True, social_login=True), None, None)
    ids_ = [i.id for i in review.items]
    assert "SETUP-003" in ids_ and "AUTH-001" not in ids_
    merged = next(i for i in review.items if i.id == "SETUP-003")
    assert merged.evidence["found_in_build"]["social_login_sdks"] == {"Google Sign-In": ["GIDSignIn"]}
    # answered "we offer Sign in with Apple" while the build shows none: the build finding stays
    kept = build_review(scan, AppProfile(social_login=True, privacy_login=True), None, None)
    assert "AUTH-001" in [i.id for i in kept.items]
