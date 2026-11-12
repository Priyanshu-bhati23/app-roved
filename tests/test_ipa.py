import io
import zipfile

import pytest

from approved import ipa

from .builders import GOOD_INFO, build_ipa, build_macho, manifest


def test_loads_bundle_with_frameworks_and_manifests():
    data = build_ipa(
        extra={
            "PrivacyInfo.xcprivacy": manifest("NSPrivacyAccessedAPICategoryUserDefaults"),
            "Frameworks/Analytics.framework/Analytics": build_macho(),
            "Frameworks/Analytics.framework/PrivacyInfo.xcprivacy": manifest(),
            "embedded.mobileprovision": b"profile",
        }
    )
    bundle = ipa.load(data)
    assert bundle.app_name == "Demo" and bundle.info["CFBundleIdentifier"] == "com.example.demo"
    assert [b.path for b in bundle.frameworks] == ["Payload/Demo.app/Frameworks/Analytics.framework/Analytics"]
    assert bundle.privacy_manifest is not None
    assert list(bundle.sdk_privacy_manifests) == ["Frameworks/Analytics.framework/PrivacyInfo.xcprivacy"]
    assert bundle.has_provisioning_profile


def test_rejects_non_zip():
    with pytest.raises(ipa.IPAError, match="not a zip"):
        ipa.load(b"definitely not a zip")


def test_rejects_archive_without_app_bundle():
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w") as zf:
        zf.writestr("README.txt", "hi")
    with pytest.raises(ipa.IPAError, match="no Payload"):
        ipa.load(buf.getvalue())


@pytest.mark.parametrize("evil", ["../../etc/passwd", "/etc/passwd", "Payload/Demo.app/../../x"])
def test_rejects_path_traversal(evil):
    with pytest.raises(ipa.IPAError, match="unsafe path"):
        ipa.load(build_ipa(extra={evil: b"x"}))


def test_rejects_zip_bomb_member():
    bomb = build_ipa(binary=b"\x00" * (8 * 1024 * 1024))
    with pytest.raises(ipa.IPAError, match="compression ratio"):
        ipa.load(bomb)


def test_missing_executable_is_reported():
    info = dict(GOOD_INFO, CFBundleExecutable="Other")
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w") as zf:
        import plistlib

        zf.writestr("Payload/Demo.app/Info.plist", plistlib.dumps(info))
    with pytest.raises(ipa.IPAError, match="missing from the bundle"):
        ipa.load(buf.getvalue())


def test_non_macho_executable_is_reported():
    with pytest.raises(ipa.IPAError, match="not a readable Mach-O"):
        ipa.load(build_ipa(binary=b"#!/bin/sh\necho hi\n"))
