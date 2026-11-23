#!/system/bin/sh
# Manual diagnostic collector.
#
#   su -c "sh /data/adb/modules/miuicamera_tanzanite/diag.sh"
#
# Writes /sdcard/micam_diag.txt.  Send that file when reporting "app tidak
# muncul" or "app terhenti" - it contains everything needed to tell whether
# the overlay, the package scan, or the framework compat is the problem.

MODDIR=${0%/*}
PKG=com.android.camera
OUT=/sdcard/micam_diag.txt

{
    echo "=== MiuiCamera diagnostic ==="
    echo "time   : $(date)"
    echo "device : $(getprop ro.product.device) / $(getprop ro.product.model)"
    echo "rom    : $(getprop ro.build.display.id) (sdk $(getprop ro.build.version.sdk))"
    echo "kernel : $(uname -a)"
    echo

    echo "--- root ---"
    echo "KSU=$KSU magisk=$([ -d /data/adb/magisk ] && echo yes || echo no) apatch=$([ -d /data/adb/ap ] && echo yes || echo no)"
    ls -d /data/adb/modules/* 2>/dev/null | sed 's|.*/||' | tr '\n' ' '
    echo
    echo

    echo "--- module ---"
    cat "$MODDIR/module.prop" 2>/dev/null
    echo

    echo "--- overlay paths ---"
    ls -l /system/priv-app/MiuiCamera/ 2>&1
    ls -l /system/lib64/libcamera_*xiaomi* 2>&1
    ls -l /system/lib64/libmicampostproc_client.so 2>&1
    echo

    echo "--- package ---"
    pm path "$PKG" 2>&1
    dumpsys package "$PKG" 2>/dev/null | grep -E "versionName|codePath|flags=|privateFlags|pkgFlags|userId" | head -n 20
    echo

    echo "--- props ---"
    getprop ro.control_privapp_permissions
    getprop debug.anc.yuvsiq.emptysdk
    getprop ro.build.version.sdk
    echo

    echo "--- privapp / scan errors in logcat ---"
    logcat -b system -d 2>/dev/null | grep -i -E "privapp|com\.android\.camera" | tail -n 40
    echo

    echo "--- crash buffer ---"
    logcat -b crash -d 2>/dev/null | tail -n 200
    echo

    echo "--- SELinux denials (camera) ---"
    dmesg 2>/dev/null | grep -i -E "avc.*camera|denied.*camera" | tail -n 30
    echo

    echo "--- framework compat check ---"
    if [ -f /system/framework/framework.jar ]; then
        echo "framework.jar: $(ls -l /system/framework/framework.jar | awk '{print $5}') bytes"
        echo "(getNativeCopy presence is checked by the APK patch, not here)"
    fi
} > "$OUT" 2>&1

echo "written to $OUT"
