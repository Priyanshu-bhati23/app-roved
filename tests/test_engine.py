from approved import ipa
from approved.catalog import Provenance, load_catalog
from approved.checks import REGISTRY, Settings
from approved.engine import analyze

from .builders import GOOD_INFO, build_fat, build_ipa, build_macho, manifest


def scan(**kw):
    settings = kw.pop("settings", None)
    return analyze(ipa.load(build_ipa(**kw)), settings)


def ids(report):
    return {f.signal.id for f in report.findings}


def test_clean_build_is_clear():
    report = scan()
    assert report.findings == [] and report.verdict == "clear"
    assert (report.bundle_id, report.sdk, report.architectures) == ("com.example.demo", "26.0.0", ["arm64"])


def test_every_check_has_a_catalog_entry_and_vice_versa():
    assert set(REGISTRY) == {s.id for s in load_catalog()}


def test_missing_bundle_keys():
    info = {k: v for k, v in GOOD_INFO.items() if k != "CFBundleVersion"}
    report = scan(info=info)
    finding = next(f for f in report.findings if f.signal.id == "PLIST-001")
    assert finding.evidence == {"missing_keys": ["CFBundleVersion"]}
    assert report.verdict == "blocked"


def test_protected_class_without_purpose_string_is_flagged_then_cleared():
    binary = build_macho(symbols=("_OBJC_CLASS_$_AVCaptureDevice",))
    assert "PLIST-003" in ids(scan(binary=binary))
    info = dict(GOOD_INFO, NSCameraUsageDescription="Scan receipts to add expenses automatically.")
    assert "PLIST-003" not in ids(scan(binary=binary, info=info))


def test_placeholder_and_empty_purpose_strings():
    info = dict(GOOD_INFO, NSCameraUsageDescription="", NSContactsUsageDescription="Lorem ipsum dolor sit amet")
    keys = {f.evidence["key"] for f in scan(info=info).findings if f.signal.id == "PLIST-002"}
    assert keys == {"NSCameraUsageDescription", "NSContactsUsageDescription"}


def test_required_reason_api_without_manifest_then_incomplete_then_complete():
    binary = build_macho(symbols=("_stat", "_OBJC_CLASS_$_NSUserDefaults"))
    assert "PRIV-001" in ids(scan(binary=binary))

    partial = scan(binary=binary, extra={"PrivacyInfo.xcprivacy": manifest("NSPrivacyAccessedAPICategoryUserDefaults")})
    missing = [f.evidence["category"] for f in partial.findings if f.signal.id == "PRIV-002"]
    assert missing == ["NSPrivacyAccessedAPICategoryFileTimestamp"] and "PRIV-001" not in ids(partial)

    full = scan(
        binary=binary,
        extra={
            "PrivacyInfo.xcprivacy": manifest(
                "NSPrivacyAccessedAPICategoryUserDefaults", "NSPrivacyAccessedAPICategoryFileTimestamp"
            )
        },
    )
    assert not ids(full) & {"PRIV-001", "PRIV-002"}


def test_tracking_without_domains_or_purpose_string():
    report = scan(extra={"PrivacyInfo.xcprivacy": manifest(tracking=True)})
    finding = next(f for f in report.findings if f.signal.id == "PRIV-003")
    assert len(finding.evidence["problems"]) == 2


def test_private_framework_and_uiwebview():
    binary = build_macho(
        dylibs=("/System/Library/PrivateFrameworks/SpringBoardServices.framework/SpringBoardServices",),
        symbols=("_OBJC_CLASS_$_UIWebView",),
    )
    assert {"MACHO-001", "MACHO-002"} <= ids(scan(binary=binary))


def test_simulator_slice_in_embedded_framework():
    fat = build_fat((0x01000007, build_macho(cputype=0x01000007, platform=7)), (0x0100000C, build_macho()))
    report = scan(extra={"Frameworks/Old.framework/Old": fat})
    finding = next(f for f in report.findings if f.signal.id == "MACHO-003")
    assert finding.evidence["architectures"] == ["x86_64"]
    assert finding.signal.provenance is Provenance.COMMUNITY_HEURISTIC


def test_signing_checks():
    assert "SIGN-001" in ids(scan(binary=build_macho(signed=False)))
    assert "SIGN-002" in ids(scan(binary=build_macho(entitlements={"get-task-allow": True})))
    assert "SIGN-002" not in ids(scan(binary=build_macho(entitlements={"get-task-allow": False})))


def test_sdk_threshold_is_configurable():
    binary = build_macho(sdk=(18, 2, 0))
    assert "PLIST-006" in ids(scan(binary=binary))
    assert "PLIST-006" not in ids(scan(binary=binary, settings=Settings(min_sdk="18.0")))


def test_unverifiable_signal_never_blocks():
    report = scan(extra={"Frameworks/FirebaseRemoteConfig.framework/FirebaseRemoteConfig": build_macho()})
    finding = next(f for f in report.findings if f.signal.id == "REVIEW-002")
    assert finding.signal.provenance is Provenance.NOT_PUBLICLY_VERIFIABLE
    assert report.verdict == "clear"


def test_findings_are_sorted_blockers_first():
    info = dict(GOOD_INFO, NSAppTransportSecurity={"NSAllowsArbitraryLoads": True}, UIBackgroundModes=["audio"])
    report = scan(info=info, binary=build_macho(signed=False))
    assert [f.signal.severity.value for f in report.findings] == ["blocker", "warning", "info"]
