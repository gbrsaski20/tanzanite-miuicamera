# tanzanite-miuicamera

Port **MiuiCamera (HyperOS Camera)** ke **Redmi Note 14 4G** (`tanzanite`, MT6789 / Helio G99) yang menjalankan ROM AOSP / LineageOS / Evolution X / Halcyon.

Repo ini berdiri sendiri dan **tidak** berisi tooling overclock. Untuk overclock, lihat repo terpisah `tanzanite-overclock`.

## Status v2.0 — satu modul untuk semua ROM

Sejak v2.0 hanya ada **satu zip**. Tidak ada lagi build "normal" vs "EvoX".

| Fitur | Status |
|---|---|
| Preview kamera live | OK |
| Foto tersimpan, termasuk mode malam | OK |
| Force close saat jepret | OK (sudah diperbaiki sejak v1.4) |
| Jalan di ROM yang `framework.jar`-nya di-strip | OK (APK sudah di-patch, lihat bawah) |
| Icon muncul di semua ROM | OK **kalau** syarat overlay terpenuhi (lihat Peringatan) |
| Slow motion 120fps | File di-retime, tapi galeri masih sering menampilkan durasi lama |

## Peringatan: KernelSU butuh metamodule

KernelSU **tidak bisa** overlay `/system` sendirian — ia hanya mount `/data`. Modul ini menaruh APK di `/system/priv-app/MiuiCamera`, jadi di KernelSU kamu **wajib** punya metamodule:

- `meta-overlayfs` (disarankan), atau
- `magic_mount` / `hybrid_mount`

Tanpa itu, zip tetap terpasang tanpa error tapi **aplikasi tidak akan pernah muncul**. Ini penyebab paling umum dari laporan "aplikasinya gak nongol".

Magisk dan APatch tidak butuh metamodule.

## Kalau aplikasi tidak muncul atau terhenti

Setelah reboot, modul menulis laporan ke **`/sdcard/micam_status.txt`**. Isinya sudah menyimpulkan sendiri penyebabnya:

| Isi laporan | Artinya | Tindakan |
|---|---|---|
| `system overlay: no` | Overlay `/system` tidak jalan | KernelSU → pasang metamodule, reboot, flash ulang |
| `package path: <not installed>` tapi overlay `yes` | Package di-reject saat boot scan | Kirim laporannya; cek `logcat -b system -d \| grep -i privapp` |
| `package path: /system/priv-app/Camera2/...` | ROM sudah punya paket `com.android.camera` dan menang | Modul sudah otomatis membuat marker `.replace`; **reboot sekali lagi** |
| `DIAGNOSA: OK` | Modul aktif | Kalau masih crash, kirim `/sdcard/micam_crash.txt` |

Untuk laporan yang lebih lengkap:

```sh
su -c "sh /data/adb/modules/miuicamera_tanzanite/diag.sh"
# hasil: /sdcard/micam_diag.txt
```

## Kenapa perlu di-port

Donor yang dipakai adalah MiuiCamera dari LineageOS 24.0 `flourite` (Qualcomm, 2026-11-14). Vendor tanzanite (MediaTek) punya generasi MIA yang berbeda dan tidak menyediakan HIDL `vendor.xiaomi.hardware.campostproc@1.0`, jadi beberapa lapis crash harus ditangani:

| Lapisan | Gejala | Perbaikan |
|---|---|---|
| `libmicampostproc_client.so` (donor) | Null deref di `MiPostProcSessionIntf::initialize` / `preProcessFrame` | 14 fungsi session di-stub jadi `return 0` |
| `libcamera_algoup_jni.xiaomi.so` | `MIAProcessFrame` langsung ke engine vendor → crash di `MiaFrameWrapper` | `processFrame`, `Jni_ProcessFrameWithSync_V10/V11` di-stub |
| `camerahalserver` | SIGABRT di `libanc_mfnr.so` saat `build_kernel` OpenCL | `resetprop debug.anc.yuvsiq.emptysdk 1` dari `post-fs-data.sh` |
| `libcamera_ispinterface_jni.xiaomi.so` (night mode) | `UnsatisfiedLinkError: nativeClassInit` | Library stub ARM64 2.224 byte, 11 method JNI no-op |
| `framework.jar` ROM custom | `NoSuchMethodError: getNativeCopy()` saat buka kamera | Call site di APK dialihkan ke API publik (lihat bawah) |

Foto tetap dihasilkan oleh HAL kamera; yang dilewati hanya jalur post-processing yang tidak kompatibel.

## Kompatibilitas framework (dulu "varian EvoX")

Banyak ROM custom membangun `framework.jar` tanpa method `@hide`
`CameraCharacteristics.getNativeCopy()`. MiuiCamera memanggilnya saat menyusun
daftar vendor key, jadi app langsung mati:

```
java.lang.NoSuchMethodError: No virtual method
getNativeCopy()Landroid/hardware/camera2/impl/CameraMetadataNative;
in class Landroid/hardware/camera2/CameraCharacteristics;
    at eq.b.c(SourceFile:0)
    at n9.f.<init>(SourceFile:878)
```

`camera/patch_aosp_apk.py` mengganti `invoke-static eq.b.c()` di `n9.f.<init>`
dengan `goto` langsung ke jalur fallback publik yang **sudah ada di kode
aslinya**: `CameraCharacteristics.getAvailableCaptureRequestKeys()`. Kedua jalur
mengisi `HashMap` yang sama (nama key → key), jadi tidak ada fitur yang hilang —
di ROM AOSP key vendor Xiaomi itu memang tidak ada.

Patch dilakukan byte-level pada `classes4.dex` yang tersimpan **STORED**, jadi
APK tidak pernah di-recompress dan alignment 4 KiB semua native library di
`lib/arm64-v8a` tetap utuh. Setelah itu signature/checksum dex dan CRC lokal +
central directory ZIP diperbaiki. Script memverifikasi:

- 8 byte di call site harus persis `invoke` + `move-result-object` (kalau beda → abort, bukan menghasilkan dex rusak);
- penggantian menutupi **kedua** instruksi. Kalau `move-result-object` dibiarkan, ART menolak method-nya (`move-result` harus mengikuti `invoke`) dan app crash di **semua** ROM.

Patch ini sekarang **selalu** dipakai, bukan varian terpisah.

Satu hal yang **belum** di-patch: `CaptureRequest.getNativeCopy()` di `eq.e.b`,
yang hanya dipakai saat menyusun request HSR (rekaman 120fps). Kalau ROM-mu juga
menghapus method itu, slow-motion bisa crash walau kamera normal jalan. Belum
disentuh karena fallback publik untuk membangun `CaptureRequest.Builder` tidak
ada, dan patch asal-asalan akan merusak rekaman di ROM yang method-nya lengkap.

## Build

Binary Xiaomi **tidak disertakan repo ini**. Ambil dari ROM yang kamu punya hak pakainya, lalu taruh di `camera/files/`:

```
MiuiCamera.apk
libcamera_algoup_jni.xiaomi.so
libcamera_mianode_jni.xiaomi.so
libmicampostproc_client.so
vendor.xiaomi.hardware.campostproc@1.0.so
```

Lalu:

```sh
cd camera
python build_module.py --files files --output ../miuicamera_universal_v2.0_ksu_magisk.zip
```

Atau patch manual:

```sh
python patch_postproc_client.py files/libmicampostproc_client.so patched_client.so
python patch_algoup_jni.py files/libcamera_algoup_jni.xiaomi.so patched_jni.so
python patch_aosp_apk.py files/MiuiCamera.apk MiuiCamera_patched.apk
python build_isp_stub.py   # menghasilkan libcamera_ispinterface_jni.xiaomi.so
```

Offset patch spesifik untuk donor `flourite` 2026-11-14. Jangan pakai donor versi lain tanpa verifikasi alamat fungsi.

## Isi modul

| File | Fungsi |
|---|---|
| `customize.sh` | deteksi root, cek metamodule KernelSU, set permission |
| `post-fs-data.sh` | `ro.control_privapp_permissions=log` + `debug.anc.yuvsiq.emptysdk=1` sebelum system_server |
| `service.sh` | laporan status, self-repair konflik paket, grant permission, simpan crash log, start watcher slow-mo |
| `slowmo_watch.sh` | retime `*_HSR_120.mp4` (120fps → 30fps, 4× lambat) |
| `diag.sh` | kolektor diagnosa manual → `/sdcard/micam_diag.txt` |
| `uninstall.sh` | matikan watcher dan bersihkan state |

`ro.control_privapp_permissions=log` dipasang karena pada build `enforce`, priv-app yang meminta permission `signature|privileged` di luar whitelist akan **ditolak utuh saat boot scan** — package-nya di-skip tanpa dialog, icon tidak pernah muncul. Whitelist modul ini sudah lengkap untuk platform AOSP (12 permission privileged), tapi ROM bisa menambah/mengganti nama permission, jadi enforcement-nya dilonggarkan sebagai jaring pengaman.

## Slow motion

Vendor tanzanite tidak punya tag `com.xiaomi.camera.supportedfeatures.CamSupportedSlowMotion`. MiuiCamera tetap merekam HSR 120fps, tetapi tidak menulis metadata `SlowMotion_Data`, sehingga galeri memutar file itu kecepatan normal.

`slowmo_watch.sh` memantau `DCIM/Camera/*_HSR_120.mp4`, lalu menulis ulang timing `stts` (750 → 3000 tick @90000 timescale), `mdhd`/`tkhd`/`mvhd`, dan menonaktifkan track audio. Di level file hasilnya benar (12,36 s → 49,46 s saat diperiksa dengan parser MP4), **tetapi galeri/pemutar masih menampilkan durasi lama** — kemungkinan MediaStore meng-cache durasi sebelum file di-patch.

**Status: dibiarkan apa adanya.** Tidak ada FC, jadi eksperimen ini sengaja tidak dilanjutkan. Jangan menganggap fitur slow-motion sudah benar-benar berfungsi.

## Keterbatasan

- Efek MIA (beauty, HDR fusion) dimatikan.
- Mode malam bisa jepret tanpa FC, tetapi tanpa fusion SuperNight Xiaomi.
- MFNR MediaTek dimatikan.
- Slow motion belum benar-benar beres (lihat di atas).
- Rekaman 120fps bisa crash di ROM yang juga menghapus `CaptureRequest.getNativeCopy()`.
- Diuji langsung hanya di tanzanite/Halcyon. ROM lain bergantung pada laporan `/sdcard/micam_status.txt`.

## Disclaimer

Binary donor, APK, dan library vendor tidak disertakan. Ambil dari perangkat/ROM milikmu sendiri sesuai hukum yang berlaku. Modul ini bisa berubah perilaku setelah update ROM. Pakai risiko sendiri.

## License

MIT — lihat [LICENSE](LICENSE). Tidak mencakup firmware atau binary Xiaomi/MediaTek.
