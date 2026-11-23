#!/usr/bin/env python3
"""
Build an EvoX/AOSP-compatible MiuiCamera.apk.

The Xiaomi camera app calls the hidden API
    CameraCharacteristics.getNativeCopy()
while collecting vendor CaptureRequest keys.  Some custom ROMs (notably
Evolution X) ship a framework.jar without that @hide method, so the app
dies with:

    java.lang.NoSuchMethodError: No virtual method getNativeCopy()
    ... at eq.b.c -> n9.f.<init>

The caller already has a fallback that uses the public API
    CameraCharacteristics.getAvailableCaptureRequestKeys()
right after the vendor-key loop.  We redirect execution straight to that
fallback, so no hidden API is touched.  The APK is patched in place (the
dex entries are STORED, so no recompression / zipalign loss) and the dex
checksum, dex SHA-1, and ZIP CRCs are repaired afterwards.
"""

import argparse
import hashlib
import shutil
import struct
import sys
import zlib
from pathlib import Path

# Offsets inside classes4.dex (verified against androguard + raw bytes).
DEX_NAME = "classes4.dex"
CALL_OFF = 0x7AB43C          # invoke-static {v4}, Leq/b;->c(...)
CALL_BYTES = bytes.fromhex("7110b7a004000c05")  # invoke + move-result-object
FALLBACK_OFF = 0x7AB488      # invoke-virtual {v4}, getAvailableCaptureRequestKeys()
PATCH = bytes.fromhex("2826" + "0000" * 3)      # goto +0x26, then 6 nop bytes


def eocd(data: bytearray) -> int:
    for i in range(len(data) - 22, max(-1, len(data) - 66000), -1):
        if data[i:i + 4] == b"PK\x05\x06":
            return i
    raise RuntimeError("EOCD not found")


def local_data_offset(data: bytearray, hdr_off: int) -> int:
    if data[hdr_off:hdr_off + 4] != b"PK\x03\x04":
        raise RuntimeError("bad local header")
    name_len = struct.unpack_from("<H", data, hdr_off + 26)[0]
    extra_len = struct.unpack_from("<H", data, hdr_off + 28)[0]
    return hdr_off + 30 + name_len + extra_len


def build(source: Path, target: Path) -> None:
    import zipfile

    shutil.copyfile(source, target)
    buf = bytearray(target.read_bytes())

    with zipfile.ZipFile(source) as zf:
        info = zf.getinfo(DEX_NAME)
        hdr_off = info.header_offset
        comp = info.compress_type
        orig_crc = info.CRC

    if comp != 0:
        raise RuntimeError(f"{DEX_NAME} is not STORED; in-place patch unsafe")

    data_off = local_data_offset(buf, hdr_off)
    patch_at = data_off + CALL_OFF
    got = bytes(buf[patch_at:patch_at + len(CALL_BYTES)])
    if got != CALL_BYTES:
        raise RuntimeError(
            f"unexpected bytes at dex+0x{CALL_OFF:X}: {got.hex()} "
            f"(expected {CALL_BYTES.hex()}); APK version mismatch"
        )

    # goto +0x26 lands on FALLBACK_OFF.
    delta = (FALLBACK_OFF - CALL_OFF) // 2
    if PATCH[1] != delta:
        raise RuntimeError(f"goto offset mismatch: {PATCH[1]} != {delta}")
    buf[patch_at:patch_at + len(PATCH)] = PATCH

    # Repair dex header: signature = sha1(bytes[32:]), checksum = adler32(bytes[12:]).
    # Order matters: the SHA-1 occupies offsets 12..32, which the checksum covers.
    dex = bytes(buf[data_off:data_off + info.file_size])
    buf[data_off + 12:data_off + 32] = hashlib.sha1(dex[32:]).digest()
    final_dex = bytes(buf[data_off:data_off + info.file_size])
    struct.pack_into("<I", buf, data_off + 8,
                     zlib.adler32(final_dex[12:]) & 0xFFFFFFFF)
    final_dex = bytes(buf[data_off:data_off + info.file_size])
    new_crc = zlib.crc32(final_dex) & 0xFFFFFFFF

    # Local header CRC.
    struct.pack_into("<I", buf, hdr_off + 14, new_crc)

    # Central directory CRC.
    eocd_off = eocd(buf)
    cd_size = struct.unpack_from("<I", buf, eocd_off + 12)[0]
    pos = struct.unpack_from("<I", buf, eocd_off + 16)[0]
    end = pos + cd_size
    fixed_cd = False
    while pos + 46 <= end and buf[pos:pos + 4] == b"PK\x01\x02":
        nlen = struct.unpack_from("<H", buf, pos + 28)[0]
        xlen = struct.unpack_from("<H", buf, pos + 30)[0]
        clen = struct.unpack_from("<H", buf, pos + 32)[0]
        name = bytes(buf[pos + 46:pos + 46 + nlen])
        if name == DEX_NAME.encode():
            old = struct.unpack_from("<I", buf, pos + 16)[0]
            if old != orig_crc:
                raise RuntimeError(f"central CRC mismatch: {old:#x} != {orig_crc:#x}")
            struct.pack_into("<I", buf, pos + 16, new_crc)
            fixed_cd = True
        pos += 46 + nlen + xlen + clen
    if not fixed_cd:
        raise RuntimeError("central directory entry not found")

    target.write_bytes(buf)

    with zipfile.ZipFile(target) as zf:
        bad = zf.testzip()
        result = zf.read(DEX_NAME)
    if bad is not None:
        raise RuntimeError(f"zip CRC test failed at {bad}")
    if result[CALL_OFF:CALL_OFF + len(PATCH)] != PATCH:
        raise RuntimeError("patch verification failed")
    if struct.unpack_from("<I", result, 8)[0] != (zlib.adler32(result[12:]) & 0xFFFFFFFF):
        raise RuntimeError("dex checksum verification failed")
    print(f"patched {target} ({target.stat().st_size} bytes), "
          f"dex CRC {orig_crc:#x} -> {new_crc:#x}")


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("source", type=Path)
    ap.add_argument("target", type=Path)
    args = ap.parse_args()
    build(args.source, args.target)


if __name__ == "__main__":
    main()
