import pytest

from approved import macho

from .builders import build_fat, build_macho


def test_parses_header_dylibs_versions_and_symbols():
    data = build_macho(
        dylibs=("/usr/lib/libSystem.B.dylib", "/System/Library/Frameworks/UIKit.framework/UIKit"),
        weak_dylibs=("/System/Library/Frameworks/AdSupport.framework/AdSupport",),
        symbols=("_stat", "_OBJC_CLASS_$_NSUserDefaults"),
        sdk=(26, 1, 0),
        min_os=(15, 4, 0),
    )
    sl = macho.parse(data).primary
    assert sl.arch == "arm64" and sl.is_pie
    assert sl.dylibs[1].endswith("UIKit")
    assert sl.weak_dylibs == ["/System/Library/Frameworks/AdSupport.framework/AdSupport"]
    assert (sl.platform, sl.sdk, sl.min_os) == ("ios", "26.1.0", "15.4.0")
    assert {"_stat", "_OBJC_CLASS_$_NSUserDefaults"} <= sl.symbols
    assert sl.crypt_id == 0


def test_reads_entitlements_from_code_signature():
    sl = macho.parse(build_macho(entitlements={"get-task-allow": True, "application-identifier": "T.com.x"})).primary
    assert sl.has_code_signature
    assert sl.entitlements["get-task-allow"] is True


def test_unsigned_binary_has_no_signature_or_entitlements():
    sl = macho.parse(build_macho(signed=False)).primary
    assert not sl.has_code_signature and sl.entitlements is None


def test_fat_binary_prefers_arm64_slice():
    fat = build_fat((0x01000007, build_macho(cputype=0x01000007)), (0x0100000C, build_macho()))
    image = macho.parse(fat)
    assert image.archs == ["x86_64", "arm64"]
    assert image.primary.arch == "arm64"


@pytest.mark.parametrize(
    "payload",
    [b"", b"PK\x03\x04 not a binary at all", build_macho()[:40], b"\xcf\xfa\xed\xfe" + b"\xff" * 60],
)
def test_malformed_input_raises_cleanly(payload):
    with pytest.raises(macho.MachOError):
        macho.parse(payload)


def test_load_command_size_cannot_run_past_the_file():
    data = bytearray(build_macho())
    data[36:40] = (0xFFFFFF00).to_bytes(4, "little")  # first load command's cmdsize
    with pytest.raises(macho.MachOError):
        macho.parse(bytes(data))
