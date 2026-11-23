# tanzanite-miuicamera

Port **MiuiCamera (HyperOS Camera)** ke **Redmi Note 14 4G** (`tanzanite`, MT6789 / Helio G99) yang menjalankan ROM AOSP/Halcyon.

Repo ini berdiri sendiri dan **tidak** berisi tooling overclock. Untuk overclock, lihat repo terpisah `tanzanite-overclock`.

## Status

Working sejak v1.6:

- Preview kamera **live** (tidak hitam)
- Foto tersimpan normal, termasuk di **mode malam / Night**
- Video slow-motion 120fps diputar **4× lebih lambat** (retime otomatis)
- Tidak ada force close setelah jepret
- Modul bisa dipasang lewat **Magisk** atau **KernelSU**

## Kenapa perlu di-port

Donor yang dipakai adalah MiuiCamera dari LineageOS 24.0 `flourite` (Qualcomm, 2026-11-14). Vendor tanzanite (MediaTek) punya generasi MIA yang berbeda dan tidak menyediakan HIDL `vendor.xiaomi.hardware.campostproc@1.0`, jadi tiga lapis crash harus ditangani:

| Lapisan | Gejala | Perbaikan |
|---|---|---|
| `libmicampostproc_client.so` (donor) | Null deref di `MiPostProcSessionIntf::initialize` / `preProcessFrame` | 14 fungsi session di-stub jadi `return 0` |
| `libcamera_algoup_jni.xiaomi.so` | `MIAProcessFrame` langsung ke engine vendor → crash di `MiaFrameWrapper` | `processFrame`, `Jni_ProcessFrameWithSync_V10/V11` di-stub |
| `camerahalserver` | SIGABRT di `libanc_mfnr.so` saat `build_kernel` OpenCL | `resetprop debug.anc.yuvsiq.emptysdk 1` dari `service.sh` |
| `libcamera_ispinterface_jni.xiaomi.so` (night mode) | `UnsatisfiedLinkError: nativeClassInit` saat initFeatureSetting | Library stub ARM64 2.224 byte, 11 method JNI no-op (`queryFeatureSetting` return `null`, dipakai caller tapi hasilnya diabaikan) |

Foto tetap dihasilkan oleh HAL kamera; yang dilewati hanya jalur post-processing yang tidak kompatibel.

### Slow motion

Vendor tanzanite tidak punya tag `com.xiaomi.camera.supportedfeatures.CamSupportedSlowMotion`. MiuiCamera tetap merekam HSR 120fps (HAL mendukung 1280x720@120), tetapi tidak menulis metadata `SlowMotion_Data`, sehingga galeri memutar file 120fps itu kecepatan normal. `slowmo_watch.sh` memantau `DCIM/Camera/*_HSR_120.mp4` dan menulis ulang timing `stts` (750 → 3000 tick @90000 timescale) sehingga video menjadi 30fps / 4× lambat. Proses ini butuh beberapa detik hingga ~30 detik tergantung jumlah entri.

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
python build_module.py --files files --output ../miuicamera_tanzanite_v1.6_ksu_magisk.zip
```

Atau patch manual:

```sh
python patch_postproc_client.py files/libmicampostproc_client.so patched_client.so
python patch_algoup_jni.py files/libcamera_algoup_jni.xiaomi.so patched_jni.so
python build_isp_stub.py   # menghasilkan libcamera_ispinterface_jni.xiaomi.so
```

Offset patch spesifik untuk donor `flourite` 2026-11-14. Jangan pakai donor versi lain tanpa verifikasi alamat fungsi.

## Pasang

Flash zip lewat aplikasi Magisk atau KernelSU, lalu reboot. Modul otomatis:

- memberi runtime permission MiuiCamera
- menetapkan `debug.anc.yuvsiq.emptysdk=1`
- menjalankan watcher slow-motion yang me-retime file `*_HSR_120.mp4` baru

Jangan pasang dua kali di device yang sudah memakai modul ini lewat `meta-overlayfs` — bisa dobel overlay.

Prebuilt: [`miuicamera_tanzanite_v1.6_ksu_magisk.zip`](https://github.com/gbrsaski20/tanzanite-miuicamera/releases/download/v1.2.0/miuicamera_tanzanite_v1.6_ksu_magisk.zip)

## Keterbatasan

- Efek MIA (beauty, HDR fusion) dimatikan.
- Mode malam bisa jepret tanpa FC, tetapi tanpa fusion SuperNight Xiaomi — hasilnya foto low-light langsung dari HAL.
- Slow motion adalah retime 120fps → 30fps, bukan interpolasi/MEIN Xiaomi; track audio dinonaktifkan agar tidak terputus di tengah.
- MFNR MediaTek dimatikan.
- Foto adalah keluaran langsung HAL.
- Belum diuji di ROM selain Halcyon/AOSP tanzanite.

## Disclaimer

Binary donor, APK, dan library vendor tidak disertakan. Ambil dari perangkat/ROM milikmu sendiri sesuai hukum yang berlaku. Modul ini bisa berubah perilaku setelah update ROM. Pakai risiko sendiri.

## License

MIT — lihat [LICENSE](LICENSE). Tidak mencakup firmware atau binary Xiaomi/MediaTek.
