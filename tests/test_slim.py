"""The browser-side slimmer (web/static/slim.js) must not change what the checks see."""

import json
import shutil
import struct
import subprocess
from pathlib import Path

import pytest

from approved import macho

from .builders import build_fat, build_macho

SLIM_JS = Path(__file__).resolve().parents[1] / "web" / "static" / "slim.js"
NODE = shutil.which("node")
pytestmark = pytest.mark.skipif(NODE is None, reason="node is needed to run the browser slimmer")


def with_code(binary: bytes, code_bytes: int) -> bytes:
    """Insert fake compiled code after the load commands and move the tables behind it, like a real binary."""
    sizeofcmds = struct.unpack_from("<I", binary, 20)[0]
    ncmds = struct.unpack_from("<I", binary, 16)[0]
    head = bytearray(binary[: 32 + sizeofcmds])
    off = 32
    for _ in range(ncmds):
        cmd, size = struct.unpack_from("<II", head, off)
        if cmd == macho.LC_SYMTAB:
            struct.pack_into("<I", head, off + 16, struct.unpack_from("<I", head, off + 16)[0] + code_bytes)
        elif cmd == macho.LC_CODE_SIGNATURE:
            struct.pack_into("<I", head, off + 8, struct.unpack_from("<I", head, off + 8)[0] + code_bytes)
        off += size
    junk = bytes((i * 131 + 7) % 251 for i in range(code_bytes))
    return bytes(head) + junk + binary[32 + sizeofcmds :]


def slim(data: bytes, tmp_path: Path) -> bytes:
    src, dst = tmp_path / "in.bin", tmp_path / "out.bin"
    src.write_bytes(data)
    script = (
        f"const s=require({json.dumps(str(SLIM_JS))});const fs=require('fs');"
        f"const input=new Uint8Array(fs.readFileSync({json.dumps(str(src))}));"
        f"fs.writeFileSync({json.dumps(str(dst))},s.slimMachO(input));"
    )
    subprocess.run([NODE, "-e", script], check=True)
    return dst.read_bytes()


def view(image: macho.MachO) -> list[dict]:
    return [
        {
            "arch": s.arch,
            "flags": s.flags,
            "dylibs": s.dylibs,
            "weak": s.weak_dylibs,
            "platform": s.platform,
            "min_os": s.min_os,
            "sdk": s.sdk,
            "crypt_id": s.crypt_id,
            "signed": s.has_code_signature,
            "entitlements": s.entitlements,
            "symbols": sorted(s.symbols),
        }
        for s in image.slices
    ]


SYMBOLS = ("_stat", "_OBJC_CLASS_$_UIWebView", "_OBJC_CLASS_$_CLLocationManager", "_mach_absolute_time")


def test_thin_binary_keeps_everything_the_checks_read_and_drops_the_code(tmp_path):
    original = with_code(
        build_macho(
            symbols=SYMBOLS,
            entitlements={"get-task-allow": True, "aps-environment": "development"},
            dylibs=("/usr/lib/libSystem.B.dylib", "/System/Library/PrivateFrameworks/X.framework/X"),
            weak_dylibs=("@rpath/FirebaseRemoteConfig.framework/FirebaseRemoteConfig",),
        ),
        2_000_000,
    )
    slimmed = slim(original, tmp_path)
    assert len(slimmed) < 2_000
    assert view(macho.parse(slimmed)) == view(macho.parse(original))


def test_unsigned_and_symbol_less_binaries(tmp_path):
    original = with_code(build_macho(signed=False), 50_000)
    assert view(macho.parse(slim(original, tmp_path))) == view(macho.parse(original))


def test_fat_binary_keeps_every_slice(tmp_path):
    arm = with_code(build_macho(symbols=SYMBOLS, entitlements={"get-task-allow": False}), 300_000)
    intel = with_code(build_macho(cputype=0x01000007, platform=7), 300_000)
    original = build_fat((0x0100000C, arm), (0x01000007, intel))
    slimmed = slim(original, tmp_path)
    assert len(slimmed) < 4_000
    assert view(macho.parse(slimmed)) == view(macho.parse(original))


def test_unreadable_input_is_passed_through(tmp_path):
    assert slim(b"definitely not mach-o", tmp_path) == b"definitely not mach-o"
