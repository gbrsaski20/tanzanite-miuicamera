#!/usr/bin/env python3
"""
Make MiuiCamera.apk run on a stock/AOSP framework.

The Xiaomi camera calls the hidden API

    CameraCharacteristics.getNativeCopy()

while building its vendor CaptureRequest key map:

    n9.f.<init>  ->  eq.b.c(CameraCharacteristics)

On ROMs whose framework.jar was built without that @hide method (Evolution X
and several other AOSP forks) the call dies with

    java.lang.NoSuchMethodError: No virtual method getNativeCopy()
    ... at eq.b.c -> n9.f.<init>

The same method already contains a public fallback right after the vendor-key
loop: CameraCharacteristics.getAvailableCaptureRequestKeys().  We redirect the
call straight to that fallback, so the hidden API is never touched.

The patch is byte level and applied to the STORED classes4.dex entry, so the
APK is never recompressed and the 4 KiB alignment of every native library in
lib/arm64-v8a stays intact.  Afterwards the dex signature/checksum and the ZIP
local + central directory CRCs are repaired.

Two things are verified before writing:
  * the 8 bytes at the call site are exactly invoke + move-result-object, so a
    mismatched APK version aborts instead of producing a corrupt dex;
  * the replacement covers BOTH instructions.  Leaving the move-result-object
    in place would make ART reject the method (a move-result must follow an
    invoke), which is a crash on every ROM, not just on EvoX.
"""

import argparse
import hashlib
import shutil
import struct
import zlib
from pathlib import Path

DEX_NAME = "classes4.dex"

# invoke-static {v4}, Leq/b;->c(CameraCharacteristics)  +  move-result-object v5
CALL_OFF = 0x7AB43C
CALL_BYTES = bytes.fromhex("7110b7a004000c05")

# goto +0x26 (lands on getAvailableCaptureRequestKeys) + 3 nop code units
PATCH = bytes.fromhex("2826" + "0000" * 3)


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
        orig_crc = info.CRC
        dex_size = info.file_size
        if info.compress_type != 0:
            raise RuntimeError(f"{DEX_NAME} is not STORED; in-place patch unsafe")

    data_off = local_data_offset(buf, hdr_off)
    patch_at = data_off + CALL_OFF
    got = bytes(buf[patch_at:patch_at + len(CALL_BYTES)])
    if got != CALL_BYTES:
        raise RuntimeError(
            f"unexpected bytes at dex+0x{CALL_OFF:X}: {got.hex()} "
            f"(expected {CALL_BYTES.hex()}); APK version mismatch"
        )

    buf[patch_at:patch_at + len(PATCH)] = PATCH

    # dex header: signature = sha1(bytes[32:]) at 12, checksum = adler32(bytes[12:]) at 8.
    # The order matters: the SHA-1 lives inside the range the checksum covers.
    dex = bytes(buf[data_off:data_off + dex_size])
    buf[data_off + 12:data_off + 32] = hashlib.sha1(dex[32:]).digest()
    dex = bytes(buf[data_off:data_off + dex_size])
    struct.pack_into("<I", buf, data_off + 8, zlib.adler32(dex[12:]) & 0xFFFFFFFF)
    dex = bytes(buf[data_off:data_off + dex_size])
    new_crc = zlib.crc32(dex) & 0xFFFFFFFF

    struct.pack_into("<I", buf, hdr_off + 14, new_crc)   # local header

    eocd_off = eocd(buf)                                  # central directory
    cd_size = struct.unpack_from("<I", buf, eocd_off + 12)[0]
    pos = struct.unpack_from("<I", buf, eocd_off + 16)[0]
    end = pos + cd_size
    fixed = False
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
            fixed = True
        pos += 46 + nlen + xlen + clen
    if not fixed:
        raise RuntimeError("central directory entry not found")

    target.write_bytes(buf)

    # ------------------------------------------------------------- verification
    with zipfile.ZipFile(target) as zf:
        bad = zf.testzip()
        dex = zf.read(DEX_NAME)
    if bad is not None:
        raise RuntimeError(f"zip CRC test failed at {bad}")
    if dex[CALL_OFF:CALL_OFF + len(PATCH)] != PATCH:
        raise RuntimeError("patch verification failed")
    if struct.unpack_from("<I", dex, 8)[0] != (zlib.adler32(dex[12:]) & 0xFFFFFFFF):
        raise RuntimeError("dex checksum verification failed")
    if dex[12:32] != hashlib.sha1(dex[32:]).digest():
        raise RuntimeError("dex signature verification failed")
    print(f"patched {target.name}: {target.stat().st_size:,} bytes, "
          f"dex CRC {orig_crc:#x} -> {new_crc:#x}")


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("source", type=Path)
    ap.add_argument("target", type=Path)
    args = ap.parse_args()
    build(args.source, args.target)


if __name__ == "__main__":
    main()
