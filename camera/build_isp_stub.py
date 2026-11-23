#!/usr/bin/env python3
"""Generate a minimal AArch64 ELF shared object that stubs Xiaomi IspInterface JNI.

Night-mode capture loads libcamera_ispinterface_jni.xiaomi.so and calls
nativeClassInit().  That library is Qualcomm-specific and absent on tanzanite,
so MiuiCamera dies with UnsatisfiedLinkError before saving the photo.

Every exported function is `mov w0, #0; ret`:
  * void methods -> no-op
  * int methods  -> 0
  * nativeQueryFeatureSetting -> null (its caller ignores the result)

Section headers are included because Android's linker rejects ET_DYN files with
e_shentsize == 0.
"""
import hashlib
import os
import struct
from pathlib import Path

OUT = Path(__file__).resolve().parent / 'patched' / 'libcamera_ispinterface_jni.xiaomi.so'

SYMBOLS = [
    'Java_com_xiaomi_camera_isp_IspInterface_nativeClassInit',
    'Java_com_xiaomi_camera_isp_IspInterface_nativeCreate',
    'Java_com_xiaomi_camera_isp_IspInterface_nativeDestroy',
    'Java_com_xiaomi_camera_isp_IspInterface_nativeGetVersionCode',
    'Java_com_xiaomi_camera_isp_IspInterface_nativeQueryFeatureSetting',
    'Java_com_xiaomi_camera_isp_IspInterface_nativeRawToJpeg',
    'Java_com_xiaomi_camera_isp_IspInterface_nativeRawToYuv',
    'Java_com_xiaomi_camera_isp_IspInterface_nativeSetFlipFlag',
    'Java_com_xiaomi_camera_isp_IspInterface_nativeYuvToHeif',
    'Java_com_xiaomi_camera_isp_IspInterface_nativeYuvToJpeg',
    'Java_com_xiaomi_camera_isp_IspInterface_nativeYuvToYuv',
]


def build_stub():
    text_off = 0x200
    stub = struct.pack('<II', 0x52800000, 0xd65f03c0)  # mov w0,#0 ; ret
    text = stub * len(SYMBOLS)

    strtab = b'\x00'
    name_off = {}
    for s in SYMBOLS:
        name_off[s] = len(strtab)
        strtab += s.encode() + b'\x00'
    soname_off = len(strtab)
    strtab += b'libcamera_ispinterface_jni.xiaomi.so\x00'

    dynstr_off = text_off + len(text)
    dynsym_off = (dynstr_off + len(strtab) + 7) & ~7
    hash_off = (dynsym_off + (len(SYMBOLS) + 1) * 24 + 3) & ~3
    nsyms = len(SYMBOLS) + 1
    hash_size = 8 + 4 * (1 + nsyms)
    dynamic_off = (hash_off + hash_size + 7) & ~7

    dynsym = bytearray(24 * nsyms)
    for i, s in enumerate(SYMBOLS, 1):
        struct.pack_into('<IBBHQQ', dynsym, i * 24,
                         name_off[s], 0x12, 0, 1, text_off + (i - 1) * 8, 0)

    # SysV hash: one bucket, all symbols chained from index 1.
    hashdata = struct.pack('<II', 1, nsyms) + struct.pack('<I', 1)
    for i in range(nsyms):
        hashdata += struct.pack('<I', i + 1 if i < nsyms - 1 else 0)

    dynamic = b''.join([
        struct.pack('<qQ', 4, hash_off),
        struct.pack('<qQ', 5, dynstr_off),
        struct.pack('<qQ', 6, dynsym_off),
        struct.pack('<qQ', 10, len(strtab)),
        struct.pack('<qQ', 11, 24),
        struct.pack('<qQ', 14, soname_off),
        struct.pack('<qQ', 0, 0),
    ])

    shstr = b'\x00'
    shnames = {}
    for nm in ('.text', '.dynstr', '.dynsym', '.hash', '.dynamic', '.shstrtab'):
        shnames[nm] = len(shstr)
        shstr += nm.encode() + b'\x00'
    shstr_off = dynamic_off + len(dynamic)
    shoff = (shstr_off + len(shstr) + 7) & ~7
    shnum = 7
    total = shoff + shnum * 64

    out = bytearray(total)
    out[0:4] = b'\x7fELF'
    out[4], out[5], out[6] = 2, 1, 1
    struct.pack_into('<HHIQQQIHHHHHH', out, 16,
                     3, 183, 1, 0, 64, shoff, 0, 64, 56, 2, 64, shnum, 6)
    struct.pack_into('<IIQQQQQQ', out, 64, 1, 5, 0, 0, 0, total, total, 0x1000)
    struct.pack_into('<IIQQQQQQ', out, 64 + 56, 2, 4, dynamic_off,
                     dynamic_off, dynamic_off, len(dynamic), len(dynamic), 8)

    out[text_off:text_off + len(text)] = text
    out[dynstr_off:dynstr_off + len(strtab)] = strtab
    out[dynsym_off:dynsym_off + len(dynsym)] = dynsym
    out[hash_off:hash_off + len(hashdata)] = hashdata
    out[dynamic_off:dynamic_off + len(dynamic)] = dynamic
    out[shstr_off:shstr_off + len(shstr)] = shstr

    def sh(idx, name, typ, flags, addr, off, size, link, info, align, entsize):
        struct.pack_into('<IIQQQQIIQQ', out, shoff + idx * 64,
                         shnames[name], typ, flags, addr, off, size,
                         link, info, align, entsize)

    sh(1, '.text', 1, 0x6, text_off, text_off, len(text), 0, 0, 4, 0)
    sh(2, '.dynstr', 3, 0x2, dynstr_off, dynstr_off, len(strtab), 0, 0, 1, 0)
    sh(3, '.dynsym', 11, 0x2, dynsym_off, dynsym_off, len(dynsym), 2, 1, 8, 24)
    sh(4, '.hash', 5, 0x2, hash_off, hash_off, len(hashdata), 3, 0, 4, 4)
    sh(5, '.dynamic', 6, 0x3, dynamic_off, dynamic_off, len(dynamic), 2, 0, 8, 16)
    sh(6, '.shstrtab', 3, 0, 0, shstr_off, len(shstr), 0, 0, 1, 0)
    return bytes(out)


def main():
    data = build_stub()
    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_bytes(data)
    print('wrote', OUT, len(data), 'bytes')
    print('sha256', hashlib.sha256(data).hexdigest())


if __name__ == '__main__':
    main()
