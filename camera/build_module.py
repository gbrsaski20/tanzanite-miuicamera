#!/usr/bin/env python3
"""Build the universal, flashable KernelSU/Magisk MiuiCamera module.

One zip for every ROM (AOSP, LineageOS, Evolution X, HyperOS).  Donor files are
NOT included in this repository - extract them from a ROM you are licensed to
use and drop them in camera/files/:

    MiuiCamera.apk
    libcamera_algoup_jni.xiaomi.so
    libcamera_mianode_jni.xiaomi.so
    libmicampostproc_client.so
    vendor.xiaomi.hardware.campostproc@1.0.so

Pipeline:
  * libmicampostproc_client.so  - session functions stubbed to `return 0`
  * libcamera_algoup_jni.xiaomi.so - MIA frame processing stubbed
  * libcamera_ispinterface_jni.xiaomi.so - generated JNI stub (night mode)
  * MiuiCamera.apk - framework compat patch (getNativeCopy), always applied

No external zip tool is required.
"""
import argparse
import hashlib
import sys
import zipfile
from pathlib import Path

from build_isp_stub import build_stub
from patch_algoup_jni import patch as patch_algoup
from patch_aosp_apk import build as patch_apk
from patch_postproc_client import patch as patch_client

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

# Everything the module ships verbatim from module/.
STATIC = [
    'module.prop',
    'customize.sh',
    'post-fs-data.sh',
    'service.sh',
    'uninstall.sh',
    'diag.sh',
    'slowmo_watch.sh',
    'system/etc/default-permissions/default-permissions-miuicamera.xml',
    'system/etc/permissions/privapp-permissions-miuicamera.xml',
    'system/etc/public.libraries-xiaomi.txt',
    'system/etc/sysconfig/miuicamera-hiddenapi-package-whitelist.xml',
]

# Copied verbatim from the donor.  The other three libraries are patched or
# generated, see below.
LIB64_VERBATIM = [
    'libcamera_mianode_jni.xiaomi.so',
    'vendor.xiaomi.hardware.campostproc@1.0.so',
]


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--files', type=Path, default=ROOT / 'files',
                    help='directory with donor binaries')
    ap.add_argument('--output', type=Path,
                    default=REPO / 'miuicamera_universal_v2.1_ksu_magisk.zip')
    ap.add_argument('--no-patch', action='store_true',
                    help='skip the framework compat patch (debug only)')
    a = ap.parse_args()

    missing = [n for n in DONOR if not (a.files / n).is_file()]
    if missing:
        sys.exit('Missing donor files: ' + ', '.join(missing))

    algoup = patch_algoup((a.files / 'libcamera_algoup_jni.xiaomi.so').read_bytes())
    client = patch_client((a.files / 'libmicampostproc_client.so').read_bytes())
    isp_stub = build_stub()

    apk = (a.files / 'MiuiCamera.apk').read_bytes()
    if not a.no_patch:
        from tempfile import TemporaryDirectory
        with TemporaryDirectory() as td:
            src = Path(td) / 'MiuiCamera.apk'
            dst = Path(td) / 'MiuiCamera_patched.apk'
            src.write_bytes(apk)
            patch_apk(src, dst)
            apk = dst.read_bytes()

    entries = [(rel, (MODULE / rel).read_bytes()) for rel in STATIC]

    for lib in LIB64_VERBATIM:
        entries.append((f'system/lib64/{lib}', (a.files / lib).read_bytes()))

    entries += [
        ('system/lib64/libcamera_algoup_jni.xiaomi.so', algoup),
        ('system/lib64/libmicampostproc_client.so', client),
        ('system/lib64/libcamera_ispinterface_jni.xiaomi.so', isp_stub),
    ]

    # Static RRO the donor ROM ships next to MiuiCamera (launcher icon overrides
    # for com.android.camera).  Optional: older donor dumps may not have it.
    overlay = a.files / 'MiuiCameraOverlayFlourite.apk'
    if overlay.is_file():
        entries.append(('product/overlay/MiuiCameraOverlayFlourite.apk',
                        overlay.read_bytes()))

    # The APK has extractNativeLibs=false, so its own lib/arm64-v8a wins for
    # anything bundled inside it.  The Xiaomi JNI libs are NOT bundled, they are
    # resolved from /system/lib64.  The lib/arm64 copies below are a fallback
    # for ROMs that force extraction; keep them in sync with /system/lib64.
    entries += [
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
