"""The automated review: build scan + App Store Connect setup + (optionally) a rejection.

Same division of labour as the rest of App-roved:
- deterministic rules decide what is wrong (setup answers, description text, build findings);
- the knowledge base supplies the explanation;
- an LLM may only rephrase grounded material, and its answer is dropped if it cites anything
  that was not retrieved. Without an LLM every part still works from templates.
"""

from __future__ import annotations

import re
from functools import lru_cache
from importlib import resources

import yaml
from pydantic import BaseModel, Field

from .catalog import Catalog, Report, Severity, Signal
from .llm import LLM
from .rag import _CITE, KnowledgeBase, load_knowledge_base

GUIDELINES_URL = "https://developer.apple.com/app-store/review/guidelines/"


@lru_cache(maxsize=1)
def load_setup_catalog() -> Catalog:
    raw = resources.files("approved.data").joinpath("setup_signals.yaml").read_text(encoding="utf-8")
    return Catalog([Signal(**entry) for entry in yaml.safe_load(raw)])


class AppProfile(BaseModel):
    """What the developer tells us about the app. Every answer defaults to the safe side."""

    has_login: bool = False
    demo_account: bool = False
    creates_accounts: bool = False
    in_app_deletion: bool = False
    social_login: bool = False
    privacy_login: bool = False  # Sign in with Apple or an equivalent
    sells_digital: bool = False
    uses_iap: bool = False
    subscriptions: bool = False
    terms_and_privacy_links: bool = False
    privacy_policy: bool = True
    user_content: bool = False
    report_and_block: bool = False
    kids_category: bool = False
    third_party_ads_analytics: bool = False
    tracks_users: bool = False
    uses_att: bool = False
    mostly_web: bool = False
    review_notes: bool = True
    description: str = Field(default="", max_length=8000)


class Item(BaseModel):
    source: str  # "build", "setup" or "description"
    id: str
    title: str
    severity: Severity
    provenance: str
    why: str
    fix: str
    link: str | None = None
    evidence: dict = Field(default_factory=dict)


class RejectionHelp(BaseModel):
    guidelines: list[str]
    meaning: str
    steps: list[str]
    reply: str
    citations: list[str] = Field(default_factory=list)
    generated_by: str = "template"


class Review(BaseModel):
    verdict: str  # "ready" or "fix_first" or "check"
    headline: str
    counts: dict[str, int]
    items: list[Item]
    rejection: RejectionHelp | None = None
    disclaimer: str = (
        "Automated review based on Apple's published guidelines and your answers. "
        "Only Apple approves apps, so treat this as a checklist, not a guarantee."
    )


# ---------- setup rules ----------

OTHER_PLATFORMS = re.compile(r"\b(android|google play|play store|windows phone|huawei appgallery)\b", re.I)
UNFINISHED = re.compile(r"\b(beta|test version|demo version|coming soon|work in progress|early access)\b", re.I)
PLACEHOLDER = re.compile(r"\b(lorem ipsum|tbd|placeholder|change ?me|asdf)\b", re.I)


def setup_findings(p: AppProfile) -> list[tuple[str, dict]]:
    out: list[tuple[str, dict]] = []
    if p.has_login and not p.demo_account:
        out.append(("SETUP-001", {"login": True, "demo_account": False}))
    if p.creates_accounts and not p.in_app_deletion:
        out.append(("SETUP-002", {"creates_accounts": True, "in_app_deletion": False}))
    if p.social_login and not p.privacy_login:
        out.append(("SETUP-003", {"social_login": True, "privacy_login": False}))
    if p.sells_digital and not p.uses_iap:
        out.append(("SETUP-004", {"sells_digital": True, "uses_iap": False}))
    if p.subscriptions and not p.terms_and_privacy_links:
        out.append(("SETUP-005", {"subscriptions": True, "terms_and_privacy_links": False}))
    if not p.privacy_policy:
        out.append(("SETUP-006", {"privacy_policy": False}))
    if p.user_content and not p.report_and_block:
        out.append(("SETUP-007", {"user_content": True, "report_and_block": False}))
    if p.kids_category and p.third_party_ads_analytics:
        out.append(("SETUP-008", {"kids_category": True, "third_party_ads_analytics": True}))
    if p.tracks_users and not p.uses_att:
        out.append(("SETUP-009", {"tracks_users": True, "uses_att": False}))
    if p.mostly_web:
        out.append(("SETUP-010", {"mostly_web": True}))
    text = p.description or ""
    if m := sorted({x.lower() for x in OTHER_PLATFORMS.findall(text)}):
        out.append(("SETUP-011", {"mentions": m}))
    if m := sorted({x.lower() for x in UNFINISHED.findall(text)}):
        out.append(("SETUP-012", {"words": m}))
    if m := sorted({x.lower() for x in PLACEHOLDER.findall(text)}):
        out.append(("SETUP-013", {"words": m}))
    if not p.review_notes:
        out.append(("SETUP-014", {"review_notes": False}))
    return out


_ORDER = {Severity.BLOCKER: 0, Severity.WARNING: 1, Severity.INFO: 2}


def _items(scan: Report | None, profile: AppProfile | None) -> list[Item]:
    items: list[Item] = []
    if scan:
        seen = set()
        for f in scan.findings:
            key = (f.signal.id, str(f.evidence))
            if key in seen:
                continue
            seen.add(key)
            ai = f.explanation and f.explanation.generated_by != "template"
            why = f.explanation.text if ai else f.signal.summary
            items.append(
                Item(
                    source="build",
                    id=f.signal.id,
                    title=f.signal.title,
                    severity=f.signal.severity,
                    provenance=f.signal.provenance.value,
                    why=why,
                    fix=f.signal.remediation,
                    link=f.signal.source,
                    evidence=f.evidence,
                )
            )
    if profile:
        catalog = load_setup_catalog()
        for signal_id, evidence in setup_findings(profile):
            s = catalog[signal_id]
            items.append(
                Item(
                    source="description" if signal_id in ("SETUP-011", "SETUP-012", "SETUP-013") else "setup",
                    id=s.id,
                    title=s.title,
                    severity=s.severity,
                    provenance=s.provenance.value,
                    why=s.summary,
                    fix=s.remediation,
                    link=s.source,
                    evidence=evidence,
                )
            )
    items.sort(key=lambda i: (_ORDER[i.severity], i.source != "build", i.id))
    return items


# ---------- rejection help ----------

_GUIDELINE = re.compile(r"\b(?:guideline|guidelines)\s*(\d\.\d+(?:\.\d+)?)", re.I)
_BARE = re.compile(r"\b([1-5]\.\d{1,2}(?:\.\d{1,2})?)\b")


def guideline_numbers(text: str) -> list[str]:
    found = _GUIDELINE.findall(text) or _BARE.findall(text)
    return list(dict.fromkeys(found))[:4]


def _chunks_for(numbers: list[str], text: str, kb: KnowledgeBase):
    picked = []
    by_title = {c.title.split(" ")[0]: c for c in kb.chunks if c.id.startswith("kb:guidelines#")}
    for n in numbers:
        # 3.1.2(c) -> 3.1.2, 2.3.10 -> 2.3 if there is no exact section
        parts = n.split(".")
        for k in range(len(parts), 1, -1):
            c = by_title.get(".".join(parts[:k]))
            if c and c not in picked:
                picked.append(c)
                break
    for c in kb.search(text, k=3):
        if c not in picked and len(picked) < 4:
            picked.append(c)
    reply = next((c for c in kb.chunks if c.title == "Replying to App Review"), None)
    if reply and reply not in picked:
        picked.append(reply)
    return picked


RESCUE_PROMPT = """You help an iOS developer respond to an App Store rejection.
Use only the CONTEXT passages for rules; never add rules from memory. Do not promise approval.
Write exactly three sections, each starting on its own line with the label:
MEANING: 2-3 sentences in plain language on what Apple is objecting to and why. Cite passages like [kb:guidelines#3].
STEPS: 2-5 lines, each starting with "- ", concrete changes to make.
REPLY: a short, polite reply to App Review (4-7 sentences) the developer can paste, with [brackets]
where they must fill in details such as the build number. No citations in REPLY."""


def _template_rescue(numbers: list[str], chunks) -> RejectionHelp:
    main = [c for c in chunks if c.title != "Replying to App Review"]
    if main:
        meaning = main[0].text
        title = main[0].title
    else:
        meaning, title = (
            "We could not match this message to a specific guideline. Read it for the guideline number Apple quotes.",
            "the guideline",
        )
    steps = [
        f"Read the {title} section of the App Review Guidelines and compare it with what the reviewer describes.",
        "Fix the exact behaviour or metadata the message mentions, then check the rest of the app for it too.",
        "Upload a new build if you changed the app, and note its build number.",
        "Reply to App Review in App Store Connect explaining what you changed.",
    ]
    g = ", ".join(numbers) if numbers else "[guideline]"
    reply = (
        f"Hello App Review team,\n\nThank you for the feedback on guideline {g}. "
        "We have [describe the change you made] and uploaded build [build number]. "
        "You can see the change by [steps to reach the screen]. "
        "If you need a demo account, the details are in App Review Information. "
        "Please let us know if anything else needs attention.\n\nThank you,\n[Your name]"
    )
    return RejectionHelp(
        guidelines=numbers,
        meaning=meaning,
        steps=steps,
        reply=reply,
        citations=[c.id for c in main[:1]],
        generated_by="template",
    )


def _parse_sections(text: str) -> dict[str, str]:
    parts = re.split(r"^\s*[*#_ ]*(MEANING|STEPS|REPLY)[*_ ]*:[*_ ]*", text, flags=re.M)
    out = {}
    for i in range(1, len(parts) - 1, 2):
        out[parts[i]] = parts[i + 1].strip()
    return out


def rescue(rejection: str, llm: LLM | None, kb: KnowledgeBase | None = None) -> RejectionHelp:
    kb = kb or load_knowledge_base()
    numbers = guideline_numbers(rejection)
    chunks = _chunks_for(numbers, rejection, kb)
    if llm is None or not chunks:
        return _template_rescue(numbers, chunks)
    context = "\n\n".join(f"[{c.id}] {c.title}\n{c.text}" for c in chunks)
    user = f"REJECTION MESSAGE (written by Apple, quoted by the developer):\n{rejection[:4000]}\n\nCONTEXT\n{context}"
    try:
        text = llm.complete(RESCUE_PROMPT, user).strip()
    except Exception:
        return _template_rescue(numbers, chunks)
    s = _parse_sections(text)
    meaning, steps_raw, reply = s.get("MEANING", ""), s.get("STEPS", ""), s.get("REPLY", "")
    cited = list(dict.fromkeys(_CITE.findall(meaning)))
    allowed = {c.id for c in chunks}
    steps = [ln.lstrip("-•* ").strip() for ln in steps_raw.splitlines() if ln.strip().lstrip("-•* ")]
    if not meaning or not cited or not set(cited) <= allowed or not steps or not reply or _CITE.search(reply):
        return _template_rescue(numbers, chunks)
    return RejectionHelp(
        guidelines=numbers, meaning=meaning, steps=steps[:6], reply=reply, citations=cited, generated_by=llm.name
    )


# ---------- the whole review ----------


def build_review(scan: Report | None, profile: AppProfile | None, rejection: str | None, llm: LLM | None) -> Review:
    items = _items(scan, profile)
    counts = {s.value: sum(1 for i in items if i.severity is s) for s in Severity}
    help_ = rescue(rejection, llm) if rejection and rejection.strip() else None
    b = counts["blocker"]
    plural = "s" if b != 1 else ""
    if help_:
        verdict = "fix_first"
        headline = (
            f"Fix the rejection and {b} blocker{plural} before you resubmit"
            if b
            else "Address the rejection, then resubmit"
        )
    elif b:
        verdict, headline = "fix_first", f"Fix {b} blocker{plural} before you submit"
    elif counts["warning"]:
        verdict, headline = (
            "check",
            f"No blockers found. Check {counts['warning']} warning{'s' if counts['warning'] != 1 else ''}",
        )
    else:
        verdict, headline = "ready", "Nothing found that would block review"
    return Review(verdict=verdict, headline=headline, counts=counts, items=items, rejection=help_)
