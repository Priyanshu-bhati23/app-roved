import pytest

from approved import ipa, rag
from approved.catalog import Provenance, Severity, Signal, load_catalog
from approved.engine import analyze

from .builders import GOOD_INFO, build_fat, build_ipa, build_macho


class FakeLLM:
    name = "fake-model"

    def __init__(self, reply):
        self.reply, self.prompts = reply, []

    def complete(self, system, user):
        self.prompts.append(user)
        if isinstance(self.reply, Exception):
            raise self.reply
        return self.reply


def finding():
    report = analyze(ipa.load(build_ipa(binary=build_macho(symbols=("_stat",)))))
    return next(f for f in report.findings if f.signal.id == "PRIV-001")


def test_catalog_labels_are_internally_consistent():
    catalog = load_catalog()
    assert {s.provenance for s in catalog} == set(Provenance)
    for s in catalog:
        assert (s.source is not None) == (s.provenance is Provenance.OFFICIAL)


def test_official_signal_requires_apple_source():
    base = dict(id="X-1", title="t", severity="info", detection="exact", summary="s", remediation="r")
    with pytest.raises(ValueError, match="must cite"):
        Signal(**base, provenance="OFFICIAL", source="https://random-blog.example/post")
    with pytest.raises(ValueError, match="only OFFICIAL"):
        Signal(**base, provenance="COMMUNITY_HEURISTIC", source="https://developer.apple.com/x")


def test_unverifiable_signal_cannot_be_a_blocker():
    with pytest.raises(ValueError, match="informational"):
        Signal(
            id="X-2",
            title="t",
            severity=Severity.BLOCKER,
            provenance="NOT_PUBLICLY_VERIFIABLE",
            detection="heuristic",
            summary="s",
            remediation="r",
        )


# Retrieval regression table: the top passage each signal's query must retrieve.
EXPECTED_TOP_PASSAGE = {
    "MACHO-001": "kb:binary-requirements#1",
    "MACHO-002": "kb:binary-requirements#2",
    "MACHO-003": "kb:binary-requirements#4",
    "PLIST-002": "kb:purpose-strings#2",
    "PLIST-003": "kb:purpose-strings#1",
    "PLIST-005": "kb:purpose-strings#5",
    "PLIST-006": "kb:binary-requirements#3",
    "PLIST-008": "kb:binary-requirements#5",
    "PRIV-001": "kb:privacy-manifests#2",
    "SIGN-001": "kb:code-signing#1",
    "REVIEW-002": "kb:binary-requirements#6",
}


def test_each_finding_retrieves_its_own_passage():
    info = dict(
        GOOD_INFO,
        NSAppTransportSecurity={"NSAllowsArbitraryLoads": True},
        UIBackgroundModes=["audio"],
        NSCameraUsageDescription="",
    )
    binary = build_macho(
        signed=False,
        sdk=(18, 0, 0),
        symbols=("_stat", "_OBJC_CLASS_$_UIWebView", "_OBJC_CLASS_$_CLLocationManager"),
        dylibs=("/System/Library/PrivateFrameworks/X.framework/X",),
    )
    fat = build_fat((0x01000007, build_macho(cputype=0x01000007)), (0x0100000C, build_macho()))
    report = analyze(ipa.load(build_ipa(info=info, binary=binary, extra={"Frameworks/Statsig.framework/Statsig": fat})))
    kb = rag.load_knowledge_base()
    top = {f.signal.id: kb.search(rag._query(f), k=1)[0].id for f in report.findings}
    assert top == EXPECTED_TOP_PASSAGE


def test_retrieval_returns_nothing_for_unrelated_queries():
    assert rag.load_knowledge_base().search("zzzz qqqq") == []


def test_offline_explanation_uses_catalog_text_and_cites_a_passage():
    explanation = rag.explain(finding(), rag.load_knowledge_base(), llm=None)
    assert explanation.generated_by == "template"
    assert "PrivacyInfo.xcprivacy" in explanation.text
    assert explanation.citations and explanation.citations[0].startswith("kb:privacy-manifests")


def test_grounded_llm_answer_is_accepted():
    llm = FakeLLM("File timestamp APIs need an approved reason in the manifest [kb:privacy-manifests#2].")
    explanation = rag.explain(finding(), rag.load_knowledge_base(), llm)
    assert explanation.generated_by == "fake-model"
    assert explanation.citations == ["kb:privacy-manifests#2"]
    assert "[kb:privacy-manifests#2]" in llm.prompts[0]  # the passage was actually supplied


@pytest.mark.parametrize(
    "reply",
    [
        "Apple rejects this under rule 9.9.9, trust me.",  # no citation
        "See the secret reviewer handbook [kb:made-up#7].",  # citation that was never retrieved
        "",
        RuntimeError("provider is down"),
    ],
)
def test_ungrounded_or_failed_llm_answer_falls_back_to_template(reply):
    explanation = rag.explain(finding(), rag.load_knowledge_base(), FakeLLM(reply))
    assert explanation.generated_by == "template"
    assert "9.9.9" not in explanation.text and "made-up" not in str(explanation.citations)


def test_full_width_citations_are_accepted():
    llm = FakeLLM("Needs an approved reason \u3010kb:privacy-manifests#2\u3011.")
    assert rag.explain(finding(), rag.load_knowledge_base(), llm).citations == ["kb:privacy-manifests#2"]
