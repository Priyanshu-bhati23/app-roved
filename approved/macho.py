"""Pure-Python Mach-O parser.

Reads only what the compliance checks need: header flags, linked libraries,
rpaths, build/SDK versions, encryption info, the symbol string table and the
entitlements embedded in the code signature. No third-party dependencies and
no execution of the binary - this is static analysis over bytes.
"""

from __future__ import annotations

import plistlib
import struct
from dataclasses import dataclass, field

MH_MAGIC_64 = 0xFEEDFACF
MH_MAGIC_32 = 0xFEEDFACE
FAT_MAGIC = 0xCAFEBABE
FAT_MAGIC_64 = 0xCAFEBABF

CPU_TYPES = {
    0x00000007: "i386",
    0x01000007: "x86_64",
    0x0000000C: "armv7",
    0x0100000C: "arm64",
}

MH_PIE = 0x200000
MH_ALLOW_STACK_EXECUTION = 0x20000

LC_REQ_DYLD = 0x80000000
LC_SYMTAB = 0x2
LC_LOAD_DYLIB = 0xC
LC_LOAD_WEAK_DYLIB = 0x18 | LC_REQ_DYLD
LC_REEXPORT_DYLIB = 0x1F | LC_REQ_DYLD
LC_RPATH = 0x1C | LC_REQ_DYLD
LC_CODE_SIGNATURE = 0x1D
LC_ENCRYPTION_INFO = 0x21
LC_VERSION_MIN_IPHONEOS = 0x25
LC_ENCRYPTION_INFO_64 = 0x2C
LC_BUILD_VERSION = 0x32

PLATFORMS = {1: "macos", 2: "ios", 3: "tvos", 4: "watchos", 6: "maccatalyst", 7: "iossimulator"}

CSMAGIC_EMBEDDED_SIGNATURE = 0xFADE0CC0
CSMAGIC_EMBEDDED_ENTITLEMENTS = 0xFADE7171

# Guard rails: a hostile upload must not make us allocate or loop unboundedly.
MAX_LOAD_COMMANDS = 20_000
MAX_STRTAB_BYTES = 64 * 1024 * 1024


class MachOError(ValueError):
    """Raised when bytes are not a Mach-O image we can parse."""


@dataclass
class Slice:
    """One architecture inside a (possibly fat) Mach-O file."""

    arch: str
    filetype: int
    flags: int
    dylibs: list[str] = field(default_factory=list)
    weak_dylibs: list[str] = field(default_factory=list)
    rpaths: list[str] = field(default_factory=list)
    platform: str | None = None
    min_os: str | None = None
    sdk: str | None = None
    crypt_id: int | None = None
    has_code_signature: bool = False
    entitlements: dict | None = None
    symbols: set[str] = field(default_factory=set)

    @property
    def is_pie(self) -> bool:
        return bool(self.flags & MH_PIE)

    @property
    def allows_stack_execution(self) -> bool:
        return bool(self.flags & MH_ALLOW_STACK_EXECUTION)

    @property
    def all_dylibs(self) -> list[str]:
        return self.dylibs + self.weak_dylibs


@dataclass
class MachO:
    slices: list[Slice]

    @property
    def archs(self) -> list[str]:
        return [s.arch for s in self.slices]

    @property
    def primary(self) -> Slice:
        """The slice that ships to devices: arm64 if present, else the first."""
        for s in self.slices:
            if s.arch == "arm64":
                return s
        return self.slices[0]


def _version(v: int) -> str:
    return f"{v >> 16}.{(v >> 8) & 0xFF}.{v & 0xFF}"


def _cstr(buf: bytes, start: int, limit: int) -> str:
    end = buf.find(b"\x00", start, limit)
    if end == -1:
        end = limit
    return buf[start:end].decode("utf-8", errors="replace")


def is_macho(data: bytes) -> bool:
    if len(data) < 4:
        return False
    le = struct.unpack_from("<I", data)[0]
    be = struct.unpack_from(">I", data)[0]
    return le in (MH_MAGIC_64, MH_MAGIC_32) or be in (FAT_MAGIC, FAT_MAGIC_64)


def parse(data: bytes) -> MachO:
    if len(data) < 8:
        raise MachOError("file too small to be Mach-O")
    be_magic = struct.unpack_from(">I", data)[0]
    if be_magic in (FAT_MAGIC, FAT_MAGIC_64):
        return MachO(_parse_fat(data, be_magic == FAT_MAGIC_64))
    return MachO([_parse_thin(data, 0, len(data))])


def _parse_fat(data: bytes, is64: bool) -> list[Slice]:
    nfat = struct.unpack_from(">I", data, 4)[0]
    if nfat == 0 or nfat > 16:
        raise MachOError(f"implausible fat arch count: {nfat}")
    slices, off = [], 8
    for _ in range(nfat):
        if is64:
            _cpu, _sub, offset, size, _align, _res = struct.unpack_from(">IIQQII", data, off)
            off += 32
        else:
            _cpu, _sub, offset, size, _align = struct.unpack_from(">IIIII", data, off)
            off += 20
        if offset + size > len(data):
            raise MachOError("fat slice extends past end of file")
        slices.append(_parse_thin(data, offset, size))
    return slices


def _parse_thin(data: bytes, base: int, size: int) -> Slice:
    end = base + size
    if size < 32:
        raise MachOError("truncated Mach-O header")
    magic = struct.unpack_from("<I", data, base)[0]
    if magic == MH_MAGIC_32:
        header_size = 28
    elif magic == MH_MAGIC_64:
        header_size = 32
    else:
        raise MachOError(f"unsupported Mach-O magic 0x{magic:08x}")
    _, cputype, _sub, filetype, ncmds, sizeofcmds, flags = struct.unpack_from("<IIIIIII", data, base)
    if ncmds > MAX_LOAD_COMMANDS or base + header_size + sizeofcmds > end:
        raise MachOError("load commands extend past end of file")

    sl = Slice(arch=CPU_TYPES.get(cputype, f"cpu_0x{cputype:x}"), filetype=filetype, flags=flags)
    off = base + header_size
    for _ in range(ncmds):
        if off + 8 > end:
            raise MachOError("truncated load command")
        cmd, cmdsize = struct.unpack_from("<II", data, off)
        if cmdsize < 8 or off + cmdsize > end:
            raise MachOError("invalid load command size")
        _load_command(data, base, end, off, cmd, cmdsize, sl)
        off += cmdsize
    return sl


def _load_command(data: bytes, base: int, end: int, off: int, cmd: int, cmdsize: int, sl: Slice) -> None:
    if cmd in (LC_LOAD_DYLIB, LC_LOAD_WEAK_DYLIB, LC_REEXPORT_DYLIB):
        name_off = struct.unpack_from("<I", data, off + 8)[0]
        name = _cstr(data, off + name_off, off + cmdsize)
        (sl.weak_dylibs if cmd == LC_LOAD_WEAK_DYLIB else sl.dylibs).append(name)
    elif cmd == LC_RPATH:
        path_off = struct.unpack_from("<I", data, off + 8)[0]
        sl.rpaths.append(_cstr(data, off + path_off, off + cmdsize))
    elif cmd in (LC_ENCRYPTION_INFO, LC_ENCRYPTION_INFO_64):
        sl.crypt_id = struct.unpack_from("<I", data, off + 16)[0]
    elif cmd == LC_BUILD_VERSION:
        platform, minos, sdk = struct.unpack_from("<III", data, off + 8)
        sl.platform = PLATFORMS.get(platform, f"platform_{platform}")
        sl.min_os, sl.sdk = _version(minos), _version(sdk)
    elif cmd == LC_VERSION_MIN_IPHONEOS:
        minos, sdk = struct.unpack_from("<II", data, off + 8)
        sl.platform = sl.platform or "ios"
        sl.min_os, sl.sdk = _version(minos), _version(sdk)
    elif cmd == LC_SYMTAB:
        _symoff, _nsyms, stroff, strsize = struct.unpack_from("<IIII", data, off + 8)
        if strsize <= MAX_STRTAB_BYTES and base + stroff + strsize <= end:
            table = data[base + stroff : base + stroff + strsize]
            sl.symbols = {s.decode("utf-8", errors="replace") for s in table.split(b"\x00") if s}
    elif cmd == LC_CODE_SIGNATURE:
        dataoff, datasize = struct.unpack_from("<II", data, off + 8)
        sl.has_code_signature = datasize > 0
        if base + dataoff + datasize <= end:
            sl.entitlements = _entitlements(data[base + dataoff : base + dataoff + datasize])


def _entitlements(blob: bytes) -> dict | None:
    """Pull the XML entitlements plist out of an embedded-signature SuperBlob."""
    if len(blob) < 12:
        return None
    magic, _length, count = struct.unpack_from(">III", blob)
    if magic != CSMAGIC_EMBEDDED_SIGNATURE or count > 64:
        return None
    for i in range(count):
        if 12 + i * 8 + 8 > len(blob):
            return None
        _type, offset = struct.unpack_from(">II", blob, 12 + i * 8)
        if offset + 8 > len(blob):
            continue
        bmagic, blen = struct.unpack_from(">II", blob, offset)
        if bmagic == CSMAGIC_EMBEDDED_ENTITLEMENTS and 8 <= blen and offset + blen <= len(blob):
            try:
                parsed = plistlib.loads(blob[offset + 8 : offset + blen])
            except Exception:
                return None
            return parsed if isinstance(parsed, dict) else None
    return None
