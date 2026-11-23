#!/system/bin/sh
# Post-boot tasks:
#   1. write a human readable status report to /sdcard/micam_status.txt
#   2. self-repair the "duplicate com.android.camera" case
#   3. grant runtime permissions
#   4. save the last crash log for bug reports
#   5. start the slow-motion retiming watcher

MODDIR=${0%/*}
PKG=com.android.camera
APK_REL=system/priv-app/MiuiCamera/MiuiCamera.apk
APK_ABS=/system/priv-app/MiuiCamera/MiuiCamera.apk
LOG=/data/local/tmp/miuicamera_grants.log
STATUS=/data/local/tmp/micam_status.txt
NEEDS_REBOOT=0

: > "$LOG" 2>/dev/null

# ------------------------------------------------------------ wait for boot
i=0
while [ "$(getprop sys.boot_completed)" != "1" ] && [ $i -lt 90 ]; do
    sleep 2
    i=$((i + 1))
done

# --------------------------------------------------------------- properties
RP=""
for c in /data/adb/magisk/resetprop /data/adb/ksu/bin/resetprop \
         /data/adb/ap/bin/resetprop resetprop; do
    if [ -x "$c" ]; then RP="$c"; break; fi
    if command -v "$c" >/dev/null 2>&1; then RP="$c"; break; fi
done
if [ -n "$RP" ]; then
    "$RP" debug.anc.yuvsiq.emptysdk 1 >> "$LOG" 2>&1
fi

# ------------------------------------------------------------- what is real
OVERLAY=no
[ -f "$APK_ABS" ] && OVERLAY=yes

PKGPATH=$(pm path "$PKG" 2>/dev/null | head -n 1 | sed 's/^package://')
OVERLAY_META="none"
for m in meta-overlayfs magic_mount hybrid_mount; do
    [ -d "/data/adb/modules/$m" ] && OVERLAY_META="$m"
done

# ------------------------------------- repair: another app owns the same name
# When the ROM already ships a package called com.android.camera, PackageManager
# scans the ROM copy first and silently skips ours.  Masking the loser's
# directory with a ".replace" marker makes ours the only candidate.
if [ -n "$PKGPATH" ] && [ "$PKGPATH" != "$APK_ABS" ]; then
    case "$PKGPATH" in
        /system/*)     PART=system;     REL=${PKGPATH#/system/} ;;
        /system_ext/*) PART=system_ext; REL=${PKGPATH#/system_ext/} ;;
        /product/*)    PART=product;    REL=${PKGPATH#/product/} ;;
        /vendor/*)     PART=vendor;     REL=${PKGPATH#/vendor/} ;;
        *)             PART="";         REL="" ;;
    esac
    if [ -n "$PART" ]; then
        DIR=$(dirname "$REL")
        mkdir -p "$MODDIR/$PART/$DIR" 2>/dev/null
        : > "$MODDIR/$PART/$DIR/.replace" 2>/dev/null
        if [ -f "$MODDIR/$PART/$DIR/.replace" ]; then
            NEEDS_REBOOT=1
            echo "masked conflicting package at $PKGPATH -> $PART/$DIR/.replace" >> "$LOG"
        fi
    fi
fi

# ------------------------------------------------------------------- grants
if [ -n "$PKGPATH" ]; then
    for p in \
        android.permission.CAMERA \
        android.permission.RECORD_AUDIO \
        android.permission.ACCESS_FINE_LOCATION \
        android.permission.ACCESS_COARSE_LOCATION \
        android.permission.READ_MEDIA_IMAGES \
        android.permission.READ_MEDIA_VIDEO \
        android.permission.READ_MEDIA_AUDIO \
        android.permission.POST_NOTIFICATIONS
    do
        echo "grant $p: $(pm grant $PKG $p 2>&1)" >> "$LOG"
    done
    echo "appops: $(appops set $PKG MANAGE_EXTERNAL_STORAGE allow 2>&1)" >> "$LOG"
fi

# -------------------------------------------------------------- crash report
CRASH=""
if command -v logcat >/dev/null 2>&1; then
    RAW=$(logcat -b crash -d 2>/dev/null | tail -n 400)
    case "$RAW" in
        *com.android.camera*) CRASH="$RAW" ;;
    esac
fi
if [ -n "$CRASH" ]; then
    printf '%s\n' "$CRASH" > /data/local/tmp/micam_crash.txt
fi

# --------------------------------------------------------------- slow motion
SLOWMO="$MODDIR/slowmo_watch.sh"
if [ -f "$SLOWMO" ]; then
    SU=$(command -v su 2>/dev/null || echo /system/bin/su)
    "$SU" -G 1015 -G 1028 -c "sh $SLOWMO" >> /data/local/tmp/miuicamera_slowmo_watch.log 2>&1 &
    echo "slowmo watcher started via su" >> "$LOG"
fi

# ------------------------------------------------------------------- status
{
    echo "=== MiuiCamera Universal - status report ==="
    echo "time              : $(date)"
    echo "module            : $(grep '^version=' "$MODDIR/module.prop" 2>/dev/null)"
    echo "root              : KSU=${KSU:-no} magisk=$([ -d /data/adb/magisk ] && echo yes || echo no) apatch=$([ -d /data/adb/ap ] && echo yes || echo no)"
    echo "overlay metamodule: $OVERLAY_META"
    echo "system overlay    : $OVERLAY   ($APK_ABS)"
    echo "privapp enforce   : $(getprop ro.control_privapp_permissions)"
    echo "package path      : ${PKGPATH:-<not installed>}"
    echo "public libs file  : $([ -f /system/etc/public.libraries-xiaomi.txt ] && echo present || echo MISSING) $(grep -c xiaomi /system/etc/public.libraries-xiaomi.txt 2>/dev/null)"
    echo "icon overlay      : $([ -f /product/overlay/MiuiCameraOverlayFlourite.apk ] && echo present || echo missing)"
    echo "sdk               : $(getprop ro.build.version.sdk)  rom: $(getprop ro.build.display.id)"
    echo
    if [ -z "$PKGPATH" ]; then
        if [ "$OVERLAY" = "no" ]; then
            echo "DIAGNOSA: /system/priv-app/MiuiCamera tidak ada."
            echo "  -> Overlay /system tidak jalan. Di KernelSU ini terjadi kalau"
            echo "     metamodule (meta-overlayfs) belum dipasang. Pasang, reboot,"
            echo "     lalu flash ulang modul ini."
        else
            echo "DIAGNOSA: file APK ada tapi package tidak terdaftar."
            echo "  -> Package di-reject saat boot scan. Cek baris berikut di logcat:"
            echo "     logcat -b system -d | grep -i -E 'privapp|com.android.camera'"
        fi
    elif [ "$PKGPATH" != "$APK_ABS" ]; then
        echo "DIAGNOSA: package com.android.camera dipakai ROM di:"
        echo "  $PKGPATH"
        echo "  -> Modul sudah membuat marker .replace untuk memblokir duplikat."
        echo "     REBOOT sekali lagi, setelah itu modul yang menang."
    else
        echo "DIAGNOSA: OK - MiuiCamera dari modul aktif."
    fi
    if [ ! -f /system/etc/public.libraries-xiaomi.txt ]; then
        echo
        echo "PERINGATAN: /system/etc/public.libraries-xiaomi.txt TIDAK ADA."
        echo "  libcamera_algoup_jni.xiaomi / libcamera_mianode_jni.xiaomi tidak"
        echo "  bisa di-load, dan app akan force close saat native method dipanggil."
        echo "  Berarti overlay /system tidak jalan - cek metamodule."
    fi
    echo
    echo "--- boot props ---"
    echo "privapp=$(getprop ro.control_privapp_permissions) emptysdk=$(getprop debug.anc.yuvsiq.emptysdk)"
    echo
    echo "--- grants log ---"
    cat "$LOG" 2>/dev/null | tail -n 20
    if [ -n "$CRASH" ]; then
        echo
        echo "--- last crash (com.android.camera) ---"
        printf '%s\n' "$CRASH" | tail -n 60
    fi
} > "$STATUS" 2>&1

# copy the report somewhere the user can grab it without root
SU=$(command -v su 2>/dev/null || echo /system/bin/su)
"$SU" -G 1015 -G 1028 -c "cp $STATUS /sdcard/micam_status.txt" 2>/dev/null
if [ -f /data/local/tmp/micam_crash.txt ]; then
    "$SU" -G 1015 -G 1028 -c "cp /data/local/tmp/micam_crash.txt /sdcard/micam_crash.txt" 2>/dev/null
fi

echo "done (needs_reboot=$NEEDS_REBOOT)" >> "$LOG"
