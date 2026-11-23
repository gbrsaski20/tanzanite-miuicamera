#!/system/bin/sh
# Installer for the universal MiuiCamera module.
#
# Everything that used to differ per ROM (framework compat, privapp whitelist,
# overlay support) is handled here or in post-fs-data.sh / service.sh, so there
# is exactly one zip for every ROM.

ui_print " "
ui_print "***********************************************"
ui_print "  MiuiCamera Universal (com.android.camera)"
ui_print "  AOSP / LineageOS / EvoX / HyperOS - tanzanite"
ui_print "***********************************************"
ui_print " "

# ---------------------------------------------------------------- root flavour
ROOT="unknown"
if [ -n "$KSU" ] || [ -d /data/adb/ksu ]; then
    ROOT="KernelSU"
fi
if [ -d /data/adb/magisk ] && [ ! -d /data/adb/ksu ]; then
    ROOT="Magisk"
fi
if [ -d /data/adb/ap ]; then
    ROOT="APatch"
fi
ui_print "- Root terdeteksi: $ROOT"

# ------------------------------------------------------- /system overlay check
# KernelSU alone cannot overlay /system: it only mounts /data.  A metamodule
# (meta-overlayfs or magic_mount) is mandatory.  Without it the module flashes
# fine but the app never appears - which is exactly the "aplikasi gak nongol"
# symptom.
if [ "$ROOT" = "KernelSU" ]; then
    if [ -d /data/adb/modules/meta-overlayfs ] || [ -d /data/adb/modules/magic_mount ] \
       || [ -d /data/adb/modules/hybrid_mount ]; then
        ui_print "- Metamodule overlay: OK"
    else
        ui_print " "
        ui_print "! PERINGATAN: KernelSU TIDAK bisa overlay /system tanpa metamodule."
        ui_print "! Tanpa metamodule, modul terpasang tapi app TIDAK akan muncul."
        ui_print "! Pasang dulu meta-overlayfs, reboot, lalu flash ulang modul ini."
        ui_print "! Detail: https://github.com/gbrsaski20/tanzanite-miuicamera"
        ui_print " "
    fi
fi

# ------------------------------------------------------- duplicate module ids
if [ -d /data/adb/modules/miuicamera_universal ]; then
    ui_print "- Modul lama 'miuicamera_universal' terdeteksi, akan digantikan."
fi

# ------------------------------------------------------------------- file perm
set_perm_recursive "$MODPATH/system/priv-app/MiuiCamera" 0 0 0755 0644
set_perm_recursive "$MODPATH/system/lib64" 0 0 0755 0644
set_perm_recursive "$MODPATH/system/etc" 0 0 0755 0644
set_perm "$MODPATH/slowmo_watch.sh" 0 0 0755
set_perm "$MODPATH/post-fs-data.sh" 0 0 0755
set_perm "$MODPATH/service.sh" 0 0 0755
set_perm "$MODPATH/diag.sh" 0 0 0755
set_perm "$MODPATH/uninstall.sh" 0 0 0755

# ------------------------------------------------ public.libraries-xiaomi.txt
# MiuiCamera loads its two JNI libraries by bare name and they are not inside
# the APK, so /system/lib64 must advertise them as public.  If the ROM already
# ships the file, keep its content and only append what is missing - replacing
# it blindly would drop other libraries the ROM registered.
PL="$MODPATH/system/etc/public.libraries-xiaomi.txt"
ROM_PL=/system/etc/public.libraries-xiaomi.txt
if [ -f "$ROM_PL" ]; then
    cp -f "$ROM_PL" "$PL" 2>/dev/null
fi
for lib in libcamera_algoup_jni.xiaomi.so libcamera_mianode_jni.xiaomi.so; do
    grep -qx "$lib" "$PL" 2>/dev/null || echo "$lib" >> "$PL"
done
ui_print "- public.libraries-xiaomi.txt: $(wc -l < "$PL" 2>/dev/null | tr -d ' ') entri"

# ------------------------------------------------------------- icon overlay
if [ -f "$MODPATH/product/overlay/MiuiCameraOverlayFlourite.apk" ]; then
    set_perm_recursive "$MODPATH/product/overlay" 0 0 0755 0644
    ui_print "- Static RRO icon overlay disertakan (dari ROM donor)."
fi

ui_print " "
ui_print "- APK sudah di-patch agar tidak butuh CameraCharacteristics.getNativeCopy()"
ui_print "  (penyebab force close di ROM yang framework.jar-nya di-strip)."
ui_print "- Privapp whitelist lengkap + enforcement dilonggarkan saat boot."
ui_print "- Kalau app tetap tidak muncul, buka /sdcard/micam_status.txt"
ui_print "  (dibuat otomatis setelah reboot) dan kirim isinya."
ui_print "- Reboot untuk mengaktifkan module."
ui_print " "
