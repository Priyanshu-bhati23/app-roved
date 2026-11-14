"""Retrieval-augmented explanations for findings.

The division of labour is strict: the deterministic engine decides *what* is
wrong; this layer only explains *why it matters*, grounded in the bundled
knowledge base. The model's output is rejected (and replaced by a template)
if it cites anything that was not retrieved, so it cannot invent a rule.
"""

from __future__ import annotations

import math
import re
from collections import Counter
from dataclasses import dataclass
from functools import lru_cache
from importlib import resources

from .catalog import Explanation, Finding, Report
from .llm import LLM

_TOKEN = re.compile(r"[A-Za-z][A-Za-z0-9_.]+")
_CITE = re.compile(r"[\[\u3010](kb:[a-z0-9-]+#\d+)[\]\u3011]")  # [..] or full-width 【..】
_STOP = frozenset("the a an and or of to in is are for with that this it be as on by from not no".split())


def tokenize(text: str) -> list[str]:
    return [t.lower() for t in _TOKEN.findall(text) if t.lower() not in _STOP]


@dataclass(frozen=True)
class Chunk:
    id: str
    title: str
    text: str
    source: str


class KnowledgeBase:
    """BM25 over heading-delimited chunks. Small corpus, so no vector DB needed."""

    def __init__(self, chunks: list[Chunk], k1: float = 1.5, b: float = 0.75):
        self.chunks = chunks
        self._k1, self._b = k1, b
        # Headings are the densest description of a chunk, so count them three times.
        self._docs = [Counter(tokenize((c.title + " ") * 3 + c.text)) for c in chunks]
        self._lengths = [sum(d.values()) for d in self._docs]
        self._avg = sum(self._lengths) / max(len(chunks), 1)
        df = Counter(term for d in self._docs for term in d)
        n = len(chunks)
        self._idf = {t: math.log(1 + (n - f + 0.5) / (f + 0.5)) for t, f in df.items()}

    def search(self, query: str, k: int = 3) -> list[Chunk]:
        terms = tokenize(query)
        scored = []
        for i, doc in enumerate(self._docs):
            score = 0.0
            for t in terms:
                tf = doc.get(t, 0)
                if tf:
                    norm = tf + self._k1 * (1 - self._b + self._b * self._lengths[i] / self._avg)
                    score += self._idf[t] * tf * (self._k1 + 1) / norm
            if score > 0:
                scored.append((score, i))
        scored.sort(key=lambda s: (-s[0], s[1]))
        return [self.chunks[i] for _, i in scored[:k]]


def parse_document(slug: str, raw: str) -> list[Chunk]:
    """Split a knowledge file into chunks. First line is `source: <url>`."""
    first, _, body = raw.partition("\n")
    if not first.startswith("source:"):
        raise ValueError(f"{slug}: knowledge files must start with a 'source:' line")
    source = first.split(":", 1)[1].strip()
    chunks = []
    for n, section in enumerate(re.split(r"^## ", body, flags=re.M)[1:], start=1):
        title, _, text = section.partition("\n")
        chunks.append(Chunk(f"kb:{slug}#{n}", title.strip(), " ".join(text.split()), source))
    return chunks


@lru_cache(maxsize=1)
def load_knowledge_base() -> KnowledgeBase:
    chunks: list[Chunk] = []
    folder = resources.files("approved.data").joinpath("knowledge")
    for entry in sorted(folder.iterdir(), key=lambda e: e.name):
        if entry.name.endswith(".md"):
            chunks.extend(parse_document(entry.name[:-3], entry.read_text(encoding="utf-8")))
    return KnowledgeBase(chunks)


SYSTEM_PROMPT = """You explain iOS App Store compliance findings to the developer who uploaded the build.
Rules:
- Use only the CONTEXT passages. If they do not cover something, say so; never add rules from memory.
- Do not change the finding's severity, provenance label or remediation, and do not add new findings.
- Cite every passage you rely on with its id in square brackets, e.g. [kb:privacy-manifests#1].
- 2-4 sentences, plain language, no preamble."""


def _query(finding: Finding) -> str:
    evidence = " ".join(f"{k} {v}" for k, v in finding.evidence.items())
    return f"{finding.signal.title} {finding.signal.summary} {evidence}"


def _template(finding: Finding, chunks: list[Chunk]) -> Explanation:
    signal = finding.signal
    text = f"{signal.summary} Fix: {signal.remediation}"
    return Explanation(text=text, citations=[c.id for c in chunks[:1]], generated_by="template")


def explain(finding: Finding, kb: KnowledgeBase, llm: LLM | None, k: int = 3) -> Explanation:
    chunks = kb.search(_query(finding), k=k)
    if llm is None or not chunks:
        return _template(finding, chunks)

    context = "\n\n".join(f"[{c.id}] {c.title}\n{c.text}" for c in chunks)
    user = (
        f"FINDING {finding.signal.id}: {finding.signal.title}\n"
        f"Label: {finding.signal.provenance.value} | Severity: {finding.signal.severity.value}\n"
        f"Summary: {finding.signal.summary}\nEvidence: {finding.evidence}\n\nCONTEXT\n{context}"
    )
    try:
        text = llm.complete(SYSTEM_PROMPT, user).strip()
    except Exception:
        return _template(finding, chunks)

    cited = list(dict.fromkeys(_CITE.findall(text)))
    allowed = {c.id for c in chunks}
    # Grounding gate: no citations, or a citation we never supplied, means the
    # answer is not traceable to the knowledge base - discard it.
    if not text or not cited or not set(cited) <= allowed:
        return _template(finding, chunks)
    return Explanation(text=text, citations=cited, generated_by=llm.name)


def explain_report(report: Report, llm: LLM | None, kb: KnowledgeBase | None = None) -> Report:
    kb = kb or load_knowledge_base()
    for finding in report.findings:
        finding.explanation = explain(finding, kb, llm)
    return report
