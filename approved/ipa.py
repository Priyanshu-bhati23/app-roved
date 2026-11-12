"""IPA ingestion: validate the archive, then read the few files the checks need.

An IPA is an attacker-controlled zip. Nothing is extracted to disk; members are
read into memory under explicit size limits, and member names are validated so
a crafted archive cannot traverse paths or exhaust memory (zip bomb).
"""

from __future__ import annotations

import io
import plistlib
import re
import zipfile
from dataclasses import dataclass, field

from . import macho

MAX_IPA_BYTES = 500 * 1024 * 1024
MAX_MEMBERS = 50_000
MAX_MEMBER_BYTES = 300 * 1024 * 1024
MAX_PLIST_BYTES = 5 * 1024 * 1024
MAX_COMPRESSION_RATIO = 200

_APP_RE = re.compile(r"^Payload/([^/]+)\.app/$")


class IPAError(ValueError):
    """The upload is not a valid, safe-to-read IPA."""


@dataclass
class Binary:
    path: str
    image: macho.MachO


@dataclass
class AppBundle:
    app_name: str
    info: dict
    executable: Binary
    frameworks: list[Binary] = field(default_factory=list)
    privacy_manifest: dict | None = None
    sdk_privacy_manifests: dict[str, dict] = field(default_factory=dict)
    has_provisioning_profile: bool = False
    file_count: int = 0

    @property
    def binaries(self) -> list[Binary]:
        return [self.executable, *self.frameworks]


def _safe_name(name: str) -> bool:
    return not (name.startswith("/") or "\\" in name or ".." in name.split("/") or "\x00" in name)


def _read(zf: zipfile.ZipFile, info: zipfile.ZipInfo, limit: int) -> bytes:
    if info.file_size > limit:
        raise IPAError(f"{info.filename} is larger than the {limit} byte limit")
    if info.compress_size and info.file_size / info.compress_size > MAX_COMPRESSION_RATIO:
        raise IPAError(f"{info.filename} has a suspicious compression ratio")
    with zf.open(info) as fh:
        data = fh.read(limit + 1)
    if len(data) > limit:
        raise IPAError(f"{info.filename} expanded past its declared size")
    return data


def load(data: bytes) -> AppBundle:
    """Parse IPA bytes into an :class:`AppBundle`. Raises :class:`IPAError`."""
    if len(data) > MAX_IPA_BYTES:
        raise IPAError("IPA exceeds the maximum upload size")
    try:
        zf = zipfile.ZipFile(io.BytesIO(data))
    except zipfile.BadZipFile as exc:
        raise IPAError("file is not a zip archive") from exc

    with zf:
        members = zf.infolist()
        if len(members) > MAX_MEMBERS:
            raise IPAError("archive has too many entries")
        by_name: dict[str, zipfile.ZipInfo] = {}
        app_root = None
        for m in members:
            if not _safe_name(m.filename):
                raise IPAError(f"unsafe path in archive: {m.filename!r}")
            by_name[m.filename] = m
            # Some tools omit directory entries, so infer the .app root from any member.
            head = "/".join(m.filename.split("/")[:2]) + "/"
            if app_root is None and _APP_RE.match(head):
                app_root = head
        if app_root is None:
            raise IPAError("no Payload/<Name>.app bundle found")

        plist_member = by_name.get(app_root + "Info.plist")
        if plist_member is None:
            raise IPAError("app bundle has no Info.plist")
        try:
            info = plistlib.loads(_read(zf, plist_member, MAX_PLIST_BYTES))
        except IPAError:
            raise
        except Exception as exc:
            raise IPAError("Info.plist is not a valid property list") from exc
        if not isinstance(info, dict):
            raise IPAError("Info.plist root is not a dictionary")

        exe_name = info.get("CFBundleExecutable") or _APP_RE.match(app_root).group(1)
        exe_member = by_name.get(app_root + str(exe_name))
        if exe_member is None:
            raise IPAError(f"main executable {exe_name!r} is missing from the bundle")
        try:
            executable = Binary(exe_member.filename, macho.parse(_read(zf, exe_member, MAX_MEMBER_BYTES)))
        except macho.MachOError as exc:
            raise IPAError(f"main executable is not a readable Mach-O: {exc}") from exc

        bundle = AppBundle(
            app_name=_APP_RE.match(app_root).group(1),
            info=info,
            executable=executable,
            has_provisioning_profile=(app_root + "embedded.mobileprovision") in by_name,
            file_count=len(members),
        )

        fw_re = re.compile(re.escape(app_root) + r"Frameworks/([^/]+)\.framework/([^/]+)$")
        for name, m in by_name.items():
            fw = fw_re.match(name)
            if fw and fw.group(1) == fw.group(2):
                try:
                    bundle.frameworks.append(Binary(name, macho.parse(_read(zf, m, MAX_MEMBER_BYTES))))
                except (macho.MachOError, IPAError):
                    continue  # an unreadable embedded framework should not sink the whole scan
            elif name.endswith("PrivacyInfo.xcprivacy"):
                manifest = _plist_or_none(zf, m)
                if manifest is None:
                    continue
                if name == app_root + "PrivacyInfo.xcprivacy":
                    bundle.privacy_manifest = manifest
                else:
                    bundle.sdk_privacy_manifests[name[len(app_root) :]] = manifest
    return bundle


def _plist_or_none(zf: zipfile.ZipFile, member: zipfile.ZipInfo) -> dict | None:
    try:
        parsed = plistlib.loads(_read(zf, member, MAX_PLIST_BYTES))
    except Exception:
        return None
    return parsed if isinstance(parsed, dict) else None
