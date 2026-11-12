"""Builds synthetic Mach-O binaries and IPAs so tests need no real app."""

from __future__ import annotations

import io
import plistlib
import struct
import zipfile

from approved import macho


def _pad(b: bytes, multiple: int = 8) -> bytes:
    return b + b"\x00" * (-len(b) % multiple)


def _dylib_cmd(cmd: int, name: str) -> bytes:
    body = _pad(name.encode() + b"\x00")
    return struct.pack("<IIIIII", cmd, 24 + len(body), 24, 0, 0, 0) + body


def build_macho(
    *,
    cputype: int = 0x0100000C,
    pie: bool = True,
    dylibs: tuple[str, ...] = ("/usr/lib/libSystem.B.dylib",),
    weak_dylibs: tuple[str, ...] = (),
    symbols: tuple[str, ...] = (),
    sdk: tuple[int, int, int] = (26, 0, 0),
    min_os: tuple[int, int, int] = (16, 0, 0),
    platform: int = 2,
    signed: bool = True,
    entitlements: dict | None = None,
    crypt_id: int | None = 0,
) -> bytes:
    def ver(v):
        return (v[0] << 16) | (v[1] << 8) | v[2]

    cmds = [_dylib_cmd(macho.LC_LOAD_DYLIB, d) for d in dylibs]
    cmds += [_dylib_cmd(macho.LC_LOAD_WEAK_DYLIB, d) for d in weak_dylibs]
    cmds.append(struct.pack("<IIIIII", macho.LC_BUILD_VERSION, 24, platform, ver(min_os), ver(sdk), 0))
    if crypt_id is not None:
        cmds.append(struct.pack("<IIIIII", macho.LC_ENCRYPTION_INFO_64, 24, 0, 0, crypt_id, 0))

    strtab = b"\x00" + b"".join(s.encode() + b"\x00" for s in symbols)
    signature = b""
    if signed:
        blobs = b""
        if entitlements is not None:
            xml = plistlib.dumps(entitlements)
            blobs = struct.pack(">II", macho.CSMAGIC_EMBEDDED_ENTITLEMENTS, 8 + len(xml)) + xml
        count = 1 if blobs else 0
        index = struct.pack(">II", 5, 12 + 8 * count) if blobs else b""
        signature = (
            struct.pack(">III", macho.CSMAGIC_EMBEDDED_SIGNATURE, 12 + len(index) + len(blobs), count) + index + blobs
        )

    # Two more commands (symtab, code signature) whose offsets depend on the total header size.
    fixed = sum(len(c) for c in cmds) + 24 + (16 if signed else 0)
    stroff = 32 + fixed
    sigoff = stroff + len(strtab)
    cmds.append(struct.pack("<IIIIII", macho.LC_SYMTAB, 24, 0, 0, stroff, len(strtab)))
    if signed:
        cmds.append(struct.pack("<IIII", macho.LC_CODE_SIGNATURE, 16, sigoff, len(signature)))

    body = b"".join(cmds)
    flags = macho.MH_PIE if pie else 0
    header = struct.pack("<IIIIIIII", macho.MH_MAGIC_64, cputype, 0, 2, len(cmds), len(body), flags, 0)
    return header + body + strtab + signature


def build_fat(*slices: tuple[int, bytes]) -> bytes:
    header = struct.pack(">II", macho.FAT_MAGIC, len(slices))
    offset = 8 + 20 * len(slices)
    table, payload = b"", b""
    for cputype, data in slices:
        table += struct.pack(">IIIII", cputype, 0, offset + len(payload), len(data), 0)
        payload += data
    return header + table + payload


GOOD_INFO = {
    "CFBundleIdentifier": "com.example.demo",
    "CFBundleExecutable": "Demo",
    "CFBundleShortVersionString": "1.2.0",
    "CFBundleVersion": "42",
    "CFBundleDisplayName": "Demo",
    "MinimumOSVersion": "16.0",
    "ITSAppUsesNonExemptEncryption": False,
}


def build_ipa(
    info: dict | None = None,
    binary: bytes | None = None,
    extra: dict[str, bytes] | None = None,
    app: str = "Demo",
) -> bytes:
    info = GOOD_INFO if info is None else info
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as zf:
        root = f"Payload/{app}.app/"
        zf.writestr(root + "Info.plist", plistlib.dumps(info))
        zf.writestr(root + str(info.get("CFBundleExecutable", app)), build_macho() if binary is None else binary)
        for name, data in (extra or {}).items():
            zf.writestr(
                name if name.startswith("Payload/") or name.startswith("..") or name.startswith("/") else root + name,
                data,
            )
    return buf.getvalue()


def manifest(*categories: str, tracking: bool = False, domains: tuple[str, ...] = ()) -> bytes:
    return plistlib.dumps(
        {
            "NSPrivacyTracking": tracking,
            "NSPrivacyTrackingDomains": list(domains),
            "NSPrivacyAccessedAPITypes": [
                {"NSPrivacyAccessedAPIType": c, "NSPrivacyAccessedAPITypeReasons": ["CA92.1"]} for c in categories
            ],
        }
    )
