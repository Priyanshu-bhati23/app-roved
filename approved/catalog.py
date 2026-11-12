"""The deterministic signal catalog and the models built on it."""

from __future__ import annotations

from enum import StrEnum
from functools import lru_cache
from importlib import resources

import yaml
from pydantic import BaseModel, Field, model_validator


class Provenance(StrEnum):
    OFFICIAL = "OFFICIAL"
    COMMUNITY_HEURISTIC = "COMMUNITY_HEURISTIC"
    NOT_PUBLICLY_VERIFIABLE = "NOT_PUBLICLY_VERIFIABLE"


class Severity(StrEnum):
    BLOCKER = "blocker"
    WARNING = "warning"
    INFO = "info"


class Detection(StrEnum):
    EXACT = "exact"
    HEURISTIC = "heuristic"


class Signal(BaseModel):
    id: str
    title: str
    severity: Severity
    provenance: Provenance
    detection: Detection
    source: str | None = None
    summary: str
    remediation: str

    @model_validator(mode="after")
    def _provenance_rules(self) -> Signal:
        # These invariants are what keep the labels honest.
        if self.provenance is Provenance.OFFICIAL:
            if not (self.source or "").startswith("https://developer.apple.com/"):
                raise ValueError(f"{self.id}: OFFICIAL signals must cite a developer.apple.com source")
        elif self.source is not None:
            raise ValueError(f"{self.id}: only OFFICIAL signals may carry a source URL")
        if self.provenance is Provenance.NOT_PUBLICLY_VERIFIABLE and self.severity is not Severity.INFO:
            raise ValueError(f"{self.id}: unverifiable signals can only be informational")
        return self


class Explanation(BaseModel):
    text: str
    citations: list[str] = Field(default_factory=list, description="Knowledge-base chunk ids used")
    generated_by: str = "template"


class Finding(BaseModel):
    signal: Signal
    evidence: dict
    explanation: Explanation | None = None


class Report(BaseModel):
    app_name: str
    bundle_id: str | None
    version: str | None
    architectures: list[str]
    sdk: str | None
    min_os: str | None
    verdict: str
    counts: dict[str, int]
    findings: list[Finding]


class Catalog:
    def __init__(self, signals: list[Signal]):
        ids = [s.id for s in signals]
        if len(ids) != len(set(ids)):
            raise ValueError("duplicate signal ids in catalog")
        self._by_id = {s.id: s for s in signals}

    def __getitem__(self, signal_id: str) -> Signal:
        return self._by_id[signal_id]

    def __contains__(self, signal_id: str) -> bool:
        return signal_id in self._by_id

    def __iter__(self):
        return iter(self._by_id.values())

    def __len__(self) -> int:
        return len(self._by_id)


@lru_cache(maxsize=1)
def load_catalog() -> Catalog:
    raw = resources.files("approved.data").joinpath("signals.yaml").read_text(encoding="utf-8")
    return Catalog([Signal(**entry) for entry in yaml.safe_load(raw)])
