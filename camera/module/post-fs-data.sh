#!/system/bin/sh
# Runs before system_server, so property changes here are seen by
# PackageManagerService during the very first boot scan.
#
# Why this exists
# ---------------
# 1) ro.control_privapp_permissions
#    On an "enforce" build, a priv-app that requests a signature|privileged
#    permission which is missing from its privapp-permissions whitelist is
#    REJECTED at scan time.  The package is silently skipped: no icon, no
#    error dialog, `pm path com.android.camera` returns nothing.  We ship a
#    complete whitelist, but ROMs add/rename privileged permissions, so the
#    enforcement is downgraded to "log" as a safety net.
#
# 2) debug.anc.yuvsiq.emptysdk
#    MediaTek MFNR builds an OpenCL kernel and aborts camerahalserver on
#    tanzanite.  "empty SDK" mode makes the HAL skip that path.  Setting it
#    this early means the very first camera open is already safe.

MODDIR=${0%/*}
LOG=/data/local/tmp/miuicamera_boot.log
: > "$LOG" 2>/dev/null

# Ensure overlay files are world-readable and correctly labeled for Android 15/16/17
if [ -d "$MODDIR/system" ]; then
    chmod -R u=rwX,go=rX "$MODDIR/system" 2>/dev/null || true
    chcon -R u:object_r:system_file:s0 "$MODDIR/system" 2>/dev/null || true
fi

RP=""
for c in /data/adb/magisk/resetprop /data/adb/ksu/bin/resetprop \
         /data/adb/ap/bin/resetprop resetprop; do
    if [ -x "$c" ]; then RP="$c"; break; fi
    if command -v "$c" >/dev/null 2>&1; then RP="$c"; break; fi
done

if [ -z "$RP" ]; then
    echo "resetprop not found; properties left untouched" >> "$LOG"
    exit 0
fi

"$RP" ro.control_privapp_permissions log >> "$LOG" 2>&1
"$RP" debug.anc.yuvsiq.emptysdk 1 >> "$LOG" 2>&1

echo "privapp=$(getprop ro.control_privapp_permissions) emptysdk=$(getprop debug.anc.yuvsiq.emptysdk)" >> "$LOG"

exit 0
