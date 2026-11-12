"""Runs every registered check and assembles the report."""

from __future__ import annotations

from .catalog import Catalog, Finding, Report, Severity, load_catalog
from .checks import REGISTRY, Settings
from .ipa import AppBundle

_ORDER = {Severity.BLOCKER: 0, Severity.WARNING: 1, Severity.INFO: 2}


def analyze(bundle: AppBundle, settings: Settings | None = None, catalog: Catalog | None = None) -> Report:
    settings = settings or Settings()
    catalog = catalog or load_catalog()
    findings: list[Finding] = []
    for signal_id, fn in REGISTRY.items():
        # A check with no catalog entry is a programming error, not a finding.
        signal = catalog[signal_id]
        findings.extend(Finding(signal=signal, evidence=evidence) for evidence in fn(bundle, settings))
    findings.sort(key=lambda f: (_ORDER[f.signal.severity], f.signal.id))

    counts = {s.value: sum(1 for f in findings if f.signal.severity is s) for s in Severity}
    verdict = "blocked" if counts["blocker"] else "needs_review" if counts["warning"] else "clear"
    primary = bundle.executable.image.primary
    return Report(
        app_name=bundle.app_name,
        bundle_id=bundle.info.get("CFBundleIdentifier"),
        version=bundle.info.get("CFBundleShortVersionString"),
        architectures=bundle.executable.image.archs,
        sdk=primary.sdk,
        min_os=str(bundle.info.get("MinimumOSVersion") or primary.min_os or "") or None,
        verdict=verdict,
        counts=counts,
        findings=findings,
    )
