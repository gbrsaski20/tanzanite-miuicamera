#!/usr/bin/env python3
"""Build a flashable KernelSU/Magisk MiuiCamera module from donor binaries.

Donor files are NOT included in this repository.  Extract them from a ROM you
are licensed to use (see README) and place them in camera/files/:

    MiuiCamera.apk
    libcamera_algoup_jni.xiaomi.so
    libcamera_mianode_jni.xiaomi.so
    libmicampostproc_client.so
    vendor.xiaomi.hardware.campostproc@1.0.so

The two incompatible MIA libraries are patched in memory, a small IspInterface
JNI stub is generated for night mode, and everything else is copied verbatim.
No external zip tool is required.
"""
import argparse
import hashlib
import sys
import zipfile
from pathlib import Path

from build_isp_stub import build_stub
from patch_algoup_jni import patch as patch_algoup
from patch_postproc_client import patch as patch_client
from patch_evox_apk import build as patch_evox

ROOT = Path(__file__).resolve().parent
MODULE = ROOT / 'module'
REPO = ROOT.parent

DONOR = [
    'MiuiCamera.apk',
    'libcamera_algoup_jni.xiaomi.so',
    'libcamera_mianode_jni.xiaomi.so',
    'libmicampostproc_client.so',
    'vendor.xiaomi.hardware.campostproc@1.0.so',
]

STATIC = [
    'slowmo_watch.sh',
    'customize.sh',
    'module.prop',
    'service.sh',
    'system/etc/default-permissions/default-permissions-miuicamera.xml',
    'system/etc/permissions/privapp-permissions-miuicamera.xml',
    'system/etc/sysconfig/miuicamera-hiddenapi-package-whitelist.xml',
]


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--files', type=Path, default=ROOT / 'files',
                    help='directory with donor binaries')
    ap.add_argument('--output', type=Path,
                    default=REPO / 'miuicamera_tanzanite_v1.9_ksu_magisk.zip')
    ap.add_argument('--evox', action='store_true',
                    help='patch MiuiCamera.apk for EvoX/AOSP framework.jar')
    a = ap.parse_args()

    missing = [n for n in DONOR if not (a.files / n).is_file()]
    if missing:
        sys.exit('Missing donor files: ' + ', '.join(missing))

    algoup = patch_algoup((a.files / 'libcamera_algoup_jni.xiaomi.so').read_bytes())
    client = patch_client((a.files / 'libmicampostproc_client.so').read_bytes())
    isp_stub = build_stub()

    module_dir = ROOT / ('module_evox' if a.evox else 'module')
    apk = (a.files / 'MiuiCamera.apk').read_bytes()
    if a.evox:
        from tempfile import TemporaryDirectory
        with TemporaryDirectory() as td:
            src = Path(td) / 'MiuiCamera.apk'
            dst = Path(td) / 'MiuiCamera_EvoX.apk'
            src.write_bytes(apk)
            patch_evox(src, dst)
            apk = dst.read_bytes()

    entries = []
    for rel in STATIC:
        entries.append((rel, (module_dir / rel).read_bytes()))

    entries += [
        ('system/lib64/libcamera_algoup_jni.xiaomi.so', algoup),
        ('system/lib64/libmicampostproc_client.so', client),
        ('system/lib64/libcamera_ispinterface_jni.xiaomi.so', isp_stub),
        ('system/lib64/libcamera_mianode_jni.xiaomi.so',
         (a.files / 'libcamera_mianode_jni.xiaomi.so').read_bytes()),
        ('system/lib64/vendor.xiaomi.hardware.campostproc@1.0.so',
         (a.files / 'vendor.xiaomi.hardware.campostproc@1.0.so').read_bytes()),
        ('system/priv-app/MiuiCamera/MiuiCamera.apk', apk),
        ('system/priv-app/MiuiCamera/lib/arm64/libcamera_algoup_jni.xiaomi.so', algoup),
        ('system/priv-app/MiuiCamera/lib/arm64/libmicampostproc_client.so', client),
        ('system/priv-app/MiuiCamera/lib/arm64/libcamera_ispinterface_jni.xiaomi.so', isp_stub),
        ('system/priv-app/MiuiCamera/lib/arm64/libcamera_mianode_jni.xiaomi.so',
         (a.files / 'libcamera_mianode_jni.xiaomi.so').read_bytes()),
    ]

    a.output.parent.mkdir(parents=True, exist_ok=True)
    with zipfile.ZipFile(a.output, 'w', zipfile.ZIP_STORED) as z:
        for name, data in entries:
            z.writestr(name, data)

    print(f'wrote {a.output} ({a.output.stat().st_size:,} bytes)')
    print('sha256', hashlib.sha256(a.output.read_bytes()).hexdigest())


if __name__ == '__main__':
    main()
