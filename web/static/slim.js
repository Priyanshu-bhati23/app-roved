/*
 * Slim an .ipa in the browser before it is uploaded.
 *
 * The checks only read Info.plist, privacy manifests, and four things inside each Mach-O:
 * the header and load commands, the symbol string table and the code signature.
 * Everything else (compiled code, images, assets) stays on the user's machine.
 * A 150 MB build typically becomes a few hundred KB, so it fits the hosting upload limit,
 * and the app's code is never sent anywhere.
 *
 * The output is still a valid IPA: the same server-side parser reads it unchanged.
 */
(function (root) {
  "use strict";

  const LC_SYMTAB = 0x2;
  const LC_CODE_SIGNATURE = 0x1d;
  const MH_MAGIC = 0xfeedface;
  const MH_MAGIC_64 = 0xfeedfacf;
  const FAT_MAGIC = 0xcafebabe;
  const FAT_MAGIC_64 = 0xcafebabf;
  const MAX_STRTAB = 64 * 1024 * 1024;
  const MAX_SIGNATURE = 16 * 1024 * 1024;
  const UNREACHABLE = 0xfffffff0; // an offset the parser will treat as out of range

  function concat(parts) {
    let total = 0;
    for (const p of parts) total += p.length;
    const out = new Uint8Array(total);
    let at = 0;
    for (const p of parts) {
      out.set(p, at);
      at += p.length;
    }
    return out;
  }

  /** Rebuild one thin Mach-O as [header + load commands][string table][code signature]. */
  function slimThin(u8, base, size) {
    const end = base + size;
    if (size < 32 || end > u8.length) return null;
    const dv = new DataView(u8.buffer, u8.byteOffset, u8.byteLength);
    const magic = dv.getUint32(base, true);
    const headerSize = magic === MH_MAGIC_64 ? 32 : magic === MH_MAGIC ? 28 : 0;
    if (!headerSize) return null;
    const ncmds = dv.getUint32(base + 16, true);
    const commandsEnd = headerSize + dv.getUint32(base + 20, true);
    if (base + commandsEnd > end) return null;

    const head = u8.slice(base, base + commandsEnd);
    const hv = new DataView(head.buffer);
    const parts = [head];
    let cursor = commandsEnd;
    let off = headerSize;
    for (let i = 0; i < ncmds && off + 8 <= commandsEnd; i++) {
      const cmd = hv.getUint32(off, true);
      const cmdsize = hv.getUint32(off + 4, true);
      if (cmdsize < 8 || off + cmdsize > commandsEnd) break;
      if (cmd === LC_SYMTAB && cmdsize >= 24) {
        const stroff = hv.getUint32(off + 16, true);
        const strsize = hv.getUint32(off + 20, true);
        hv.setUint32(off + 8, 0, true); // symoff: the nlist entries are not needed
        hv.setUint32(off + 12, 0, true); // nsyms
        if (strsize > 0 && strsize <= MAX_STRTAB && stroff + strsize <= size) {
          parts.push(u8.subarray(base + stroff, base + stroff + strsize));
          hv.setUint32(off + 16, cursor, true);
          cursor += strsize;
        } else {
          hv.setUint32(off + 16, UNREACHABLE, true);
        }
      } else if (cmd === LC_CODE_SIGNATURE && cmdsize >= 16) {
        const dataoff = hv.getUint32(off + 8, true);
        const datasize = hv.getUint32(off + 12, true);
        if (datasize > 0 && datasize <= MAX_SIGNATURE && dataoff + datasize <= size) {
          parts.push(u8.subarray(base + dataoff, base + dataoff + datasize));
          hv.setUint32(off + 8, cursor, true);
          cursor += datasize;
        } else if (datasize > 0) {
          hv.setUint32(off + 8, UNREACHABLE, true); // still "signed", entitlements unreadable as before
        }
      }
      off += cmdsize;
    }
    return concat(parts);
  }

  /** Slim a thin or fat Mach-O. Returns the input unchanged if it cannot be read safely. */
  function slimMachO(u8) {
    if (u8.length < 8) return u8;
    const dv = new DataView(u8.buffer, u8.byteOffset, u8.byteLength);
    const be = dv.getUint32(0, false);
    if (be !== FAT_MAGIC && be !== FAT_MAGIC_64) return slimThin(u8, 0, u8.length) || u8;

    const is64 = be === FAT_MAGIC_64;
    const count = dv.getUint32(4, false);
    const entry = is64 ? 32 : 20;
    if (count === 0 || count > 16 || 8 + count * entry > u8.length) return u8;
    const slices = [];
    for (let i = 0; i < count; i++) {
      const at = 8 + i * entry;
      const cpu = dv.getUint32(at, false);
      const sub = dv.getUint32(at + 4, false);
      const offset = is64 ? Number(dv.getBigUint64(at + 8, false)) : dv.getUint32(at + 8, false);
      const size = is64 ? Number(dv.getBigUint64(at + 16, false)) : dv.getUint32(at + 12, false);
      if (offset + size > u8.length) return u8;
      const data = slimThin(u8, offset, size);
      if (!data) return u8;
      slices.push({ cpu, sub, data });
    }

    let offset = 8 + count * entry;
    const header = new Uint8Array(offset);
    const hv = new DataView(header.buffer);
    hv.setUint32(0, be, false);
    hv.setUint32(4, count, false);
    const parts = [header];
    slices.forEach((s, i) => {
      const pad = (8 - (offset % 8)) % 8;
      if (pad) parts.push(new Uint8Array(pad));
      offset += pad;
      const at = 8 + i * entry;
      hv.setUint32(at, s.cpu, false);
      hv.setUint32(at + 4, s.sub, false);
      if (is64) {
        hv.setBigUint64(at + 8, BigInt(offset), false);
        hv.setBigUint64(at + 16, BigInt(s.data.length), false);
        hv.setUint32(at + 24, 3, false);
      } else {
        hv.setUint32(at + 8, offset, false);
        hv.setUint32(at + 12, s.data.length, false);
        hv.setUint32(at + 16, 3, false);
      }
      parts.push(s.data);
      offset += s.data.length;
    });
    return concat(parts);
  }

  function isMachO(u8) {
    if (u8.length < 4) return false;
    const dv = new DataView(u8.buffer, u8.byteOffset, u8.byteLength);
    const le = dv.getUint32(0, true);
    const be = dv.getUint32(0, false);
    return le === MH_MAGIC || le === MH_MAGIC_64 || be === FAT_MAGIC || be === FAT_MAGIC_64;
  }

  /**
   * Read an .ipa (File/Blob/ArrayBuffer) with JSZip and build the slim IPA.
   * Resolves to { blob, appName, originalBytes, slimBytes, kept }. outputType is a JSZip type (default "blob").
   */
  async function slimIPA(input, JSZip, onProgress, outputType) {
    const say = onProgress || function () {};
    const zip = await JSZip.loadAsync(input);
    const names = Object.keys(zip.files);
    let appRoot = null;
    for (const n of names) {
      const m = /^Payload\/[^/]+\.app\//.exec(n);
      if (m) {
        appRoot = m[0];
        break;
      }
    }
    if (!appRoot) throw new Error("This doesn't look like an .ipa: there is no Payload/<Name>.app folder inside.");

    const out = new JSZip();
    const fwRe = new RegExp("^" + appRoot.replace(/[.*+?^${}()|[\]\\]/g, "\\$&") + "Frameworks/([^/]+)\\.framework/([^/]+)$");
    let kept = 0;
    for (const name of names) {
      const entry = zip.files[name];
      if (entry.dir || !name.startsWith(appRoot)) continue;
      const rest = name.slice(appRoot.length);
      const fw = fwRe.exec(name);
      if (rest === "Info.plist" || name.endsWith("PrivacyInfo.xcprivacy")) {
        out.file(name, await entry.async("uint8array"));
        kept++;
      } else if (rest === "embedded.mobileprovision") {
        out.file(name, new Uint8Array(0)); // only its presence matters; the profile itself stays private
        kept++;
      } else if ((fw && fw[1] === fw[2]) || (!rest.includes("/") && !rest.includes("."))) {
        // Embedded framework binaries, and extensionless top-level files (the main executable).
        say("Reading " + rest);
        const bytes = await entry.async("uint8array");
        if (!isMachO(bytes)) continue;
        out.file(name, slimMachO(bytes));
        kept++;
      }
    }
    say("Packing");
    const blob = await out.generateAsync({ type: outputType || "blob", compression: "DEFLATE", compressionOptions: { level: 6 } });
    const originalBytes = input.size != null ? input.size : input.byteLength;
    return { blob, appName: appRoot.slice(8, -5), originalBytes, slimBytes: blob.size != null ? blob.size : blob.length, kept };
  }

  const api = { slimMachO, slimIPA, isMachO };
  if (typeof module === "object" && module.exports) module.exports = api;
  else root.AppRovedSlim = api;
})(typeof self !== "undefined" ? self : this);
