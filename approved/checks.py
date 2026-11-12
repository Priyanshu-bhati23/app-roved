"""Deterministic checks. Each check is registered against exactly one catalog id
and yields evidence dicts; it never produces free text of its own."""

from __future__ import annotations

import re
from collections.abc import Callable, Iterator
from dataclasses import dataclass

from .ipa import AppBundle

Evidence = dict
CheckFn = Callable[[AppBundle, "Settings"], Iterator[Evidence]]
REGISTRY: dict[str, CheckFn] = {}


@dataclass(frozen=True)
class Settings:
    """Thresholds Apple changes over time. Verify against
    https://developer.apple.com/news/upcoming-requirements/ before relying on them."""

    min_sdk: str = "26.0"
    min_deployment_target: str = "13.0"


def check(signal_id: str) -> Callable[[CheckFn], CheckFn]:
    def register(fn: CheckFn) -> CheckFn:
        if signal_id in REGISTRY:
            raise ValueError(f"duplicate check for {signal_id}")
        REGISTRY[signal_id] = fn
        return fn

    return register


def _ver(text: str) -> tuple[int, ...]:
    return tuple(int(p) for p in re.findall(r"\d+", str(text))[:3]) or (0,)


OBJC = "_OBJC_CLASS_$_"

# class symbol -> usage-description keys, any one of which satisfies the requirement
PROTECTED_CLASSES: dict[str, tuple[str, ...]] = {
    "AVCaptureDevice": ("NSCameraUsageDescription", "NSMicrophoneUsageDescription"),
    "CLLocationManager": (
        "NSLocationWhenInUseUsageDescription",
        "NSLocationAlwaysAndWhenInUseUsageDescription",
    ),
    "PHPhotoLibrary": ("NSPhotoLibraryUsageDescription", "NSPhotoLibraryAddUsageDescription"),
    "CNContactStore": ("NSContactsUsageDescription",),
    "EKEventStore": (
        "NSCalendarsUsageDescription",
        "NSCalendarsFullAccessUsageDescription",
        "NSCalendarsWriteOnlyAccessUsageDescription",
        "NSRemindersUsageDescription",
        "NSRemindersFullAccessUsageDescription",
    ),
    "CMMotionActivityManager": ("NSMotionUsageDescription",),
    "CMPedometer": ("NSMotionUsageDescription",),
    "LAContext": ("NSFaceIDUsageDescription",),
    "SFSpeechRecognizer": ("NSSpeechRecognitionUsageDescription",),
    "CBCentralManager": ("NSBluetoothAlwaysUsageDescription",),
    "HKHealthStore": ("NSHealthShareUsageDescription", "NSHealthUpdateUsageDescription"),
    "ATTrackingManager": ("NSUserTrackingUsageDescription",),
}

# Symbols that are visible in the symbol table. Selector-only APIs
# (systemUptime, activeInputModes) cannot be seen this way and are not claimed.
REQUIRED_REASON_SYMBOLS: dict[str, tuple[str, ...]] = {
    "NSPrivacyAccessedAPICategoryFileTimestamp": (
        "_stat",
        "_fstat",
        "_lstat",
        "_fstatat",
        "_getattrlist",
        "_getattrlistbulk",
        "_fgetattrlist",
        "_NSFileCreationDate",
        "_NSFileModificationDate",
        "_NSURLContentModificationDateKey",
        "_NSURLCreationDateKey",
    ),
    "NSPrivacyAccessedAPICategorySystemBootTime": ("_mach_absolute_time",),
    "NSPrivacyAccessedAPICategoryDiskSpace": (
        "_statfs",
        "_statvfs",
        "_fstatfs",
        "_fstatvfs",
        "_NSFileSystemFreeSize",
        "_NSFileSystemSize",
        "_NSURLVolumeAvailableCapacityKey",
        "_NSURLVolumeAvailableCapacityForImportantUsageKey",
        "_NSURLVolumeAvailableCapacityForOpportunisticUsageKey",
        "_NSURLVolumeTotalCapacityKey",
    ),
    "NSPrivacyAccessedAPICategoryUserDefaults": (OBJC + "NSUserDefaults",),
}

PLACEHOLDER = re.compile(r"\b(lorem ipsum|tbd|placeholder|change ?me|asdf)\b", re.I)
REMOTE_CONFIG_LIBS = ("FirebaseRemoteConfig", "LaunchDarkly", "Statsig", "Optimizely", "ConfigCat")


def _usage_keys(info: dict) -> dict[str, object]:
    return {k: v for k, v in info.items() if k.endswith("UsageDescription")}


def required_reason_usage(bundle: AppBundle) -> dict[str, list[str]]:
    symbols = bundle.executable.image.primary.symbols
    used = {}
    for category, names in REQUIRED_REASON_SYMBOLS.items():
        hits = sorted(symbols.intersection(names))
        if hits:
            used[category] = hits
    return used


@check("PLIST-001")
def required_keys(bundle, settings):
    required = ("CFBundleIdentifier", "CFBundleExecutable", "CFBundleShortVersionString", "CFBundleVersion")
    missing = [k for k in required if not str(bundle.info.get(k, "")).strip()]
    if missing:
        yield {"missing_keys": missing}


@check("PLIST-002")
def empty_purpose_strings(bundle, settings):
    for key, value in sorted(_usage_keys(bundle.info).items()):
        text = value.strip() if isinstance(value, str) else ""
        if len(text) < 10 or PLACEHOLDER.search(text):
            yield {"key": key, "value": value if isinstance(value, str) else repr(value)}


@check("PLIST-003")
def missing_purpose_strings(bundle, settings):
    symbols = bundle.executable.image.primary.symbols
    for cls, keys in PROTECTED_CLASSES.items():
        if OBJC + cls in symbols and not any(k in bundle.info for k in keys):
            yield {"symbol": OBJC + cls, "any_of_keys": list(keys)}


@check("PLIST-004")
def export_compliance(bundle, settings):
    if "ITSAppUsesNonExemptEncryption" not in bundle.info:
        yield {"missing_key": "ITSAppUsesNonExemptEncryption"}


@check("PLIST-005")
def arbitrary_loads(bundle, settings):
    ats = bundle.info.get("NSAppTransportSecurity")
    if isinstance(ats, dict) and ats.get("NSAllowsArbitraryLoads") is True:
        yield {"NSAllowsArbitraryLoads": True}


@check("PLIST-006")
def sdk_version(bundle, settings):
    primary = bundle.executable.image.primary
    sdk = primary.sdk or bundle.info.get("DTPlatformVersion")
    if sdk and _ver(sdk) < _ver(settings.min_sdk):
        yield {"built_with_sdk": str(sdk), "required_minimum": settings.min_sdk}


@check("PLIST-007")
def deployment_target(bundle, settings):
    target = bundle.info.get("MinimumOSVersion") or bundle.executable.image.primary.min_os
    if target and _ver(target) < _ver(settings.min_deployment_target):
        yield {"deployment_target": str(target), "required_minimum": settings.min_deployment_target}


@check("PLIST-008")
def background_modes(bundle, settings):
    modes = bundle.info.get("UIBackgroundModes")
    if isinstance(modes, list) and modes:
        yield {"modes": [str(m) for m in modes]}


@check("PRIV-001")
def privacy_manifest_missing(bundle, settings):
    used = required_reason_usage(bundle)
    if used and bundle.privacy_manifest is None:
        yield {"categories": used}


@check("PRIV-002")
def privacy_manifest_incomplete(bundle, settings):
    if bundle.privacy_manifest is None:
        return
    declared = {
        entry.get("NSPrivacyAccessedAPIType")
        for entry in bundle.privacy_manifest.get("NSPrivacyAccessedAPITypes") or []
        if isinstance(entry, dict)
    }
    for category, symbols in required_reason_usage(bundle).items():
        if category not in declared:
            yield {"category": category, "symbols": symbols}


@check("PRIV-003")
def tracking_declaration(bundle, settings):
    manifest = bundle.privacy_manifest
    if not manifest or manifest.get("NSPrivacyTracking") is not True:
        return
    problems = []
    if not manifest.get("NSPrivacyTrackingDomains"):
        problems.append("NSPrivacyTrackingDomains is empty")
    if "NSUserTrackingUsageDescription" not in bundle.info:
        problems.append("NSUserTrackingUsageDescription is missing")
    if problems:
        yield {"problems": problems}


@check("MACHO-001")
def private_frameworks(bundle, settings):
    for binary in bundle.binaries:
        hits = [d for d in binary.image.primary.all_dylibs if "/PrivateFrameworks/" in d]
        if hits:
            yield {"binary": binary.path, "libraries": hits}


@check("MACHO-002")
def uiwebview(bundle, settings):
    for binary in bundle.binaries:
        if OBJC + "UIWebView" in binary.image.primary.symbols:
            yield {"binary": binary.path, "symbol": OBJC + "UIWebView"}


@check("MACHO-003")
def non_device_architectures(bundle, settings):
    for binary in bundle.binaries:
        bad = [a for a in binary.image.archs if a in ("x86_64", "i386")]
        sim = [s.arch for s in binary.image.slices if s.platform == "iossimulator"]
        if bad or sim:
            yield {"binary": binary.path, "architectures": bad, "simulator_slices": sim}


@check("MACHO-004")
def not_pie(bundle, settings):
    if not bundle.executable.image.primary.is_pie:
        yield {"binary": bundle.executable.path, "MH_PIE": False}


@check("SIGN-001")
def unsigned(bundle, settings):
    if not bundle.executable.image.primary.has_code_signature:
        yield {"binary": bundle.executable.path, "LC_CODE_SIGNATURE": False}


@check("SIGN-002")
def development_signed(bundle, settings):
    entitlements = bundle.executable.image.primary.entitlements or {}
    if entitlements.get("get-task-allow") is True:
        yield {"entitlement": "get-task-allow", "value": True}


@check("REVIEW-001")
def placeholder_text(bundle, settings):
    for key in ("CFBundleDisplayName", "CFBundleName"):
        value = bundle.info.get(key)
        if isinstance(value, str) and PLACEHOLDER.search(value):
            yield {"key": key, "value": value}


@check("REVIEW-002")
def remote_config(bundle, settings):
    linked = {d.rsplit("/", 1)[-1] for b in bundle.binaries for d in b.image.primary.all_dylibs}
    embedded = {b.path.rsplit("/", 1)[-1] for b in bundle.frameworks}
    hits = sorted(n for n in linked | embedded if any(lib.lower() in n.lower() for lib in REMOTE_CONFIG_LIBS))
    if hits:
        yield {"libraries": hits}
