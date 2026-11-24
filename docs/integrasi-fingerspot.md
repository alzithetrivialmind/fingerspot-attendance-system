# Integrasi dengan fingerspot.io

Catatan teknis tentang cara aplikasi ini memakai Developer API dan webhook fingerspot.io. Sebagian perilaku di bawah ditemukan saat pengujian dengan mesin Revo WDV-204BNC dan berbeda dari dokumentasi resmi. Mesin lain bisa berbeda.

## Alur perintah

1. Aplikasi mengirim `POST {FINGERSPOT_API_URL}/{aksi}` dengan header `Authorization: Bearer <API key>`, berisi `trans_id` dan `cloud_id`.
2. API menjawab bahwa perintah diterima. **Ini belum berarti mesin menjalankannya.**
3. Mesin menjalankan perintah, lalu fingerspot.io mengirim hasilnya ke webhook dengan `trans_id` yang sama.
4. Aplikasi mencocokkan `trans_id` di tabel `fingerspot_trans_logs` dan memperbarui status.

Kode: [`app/services/fingerspot_api.py`](../app/services/fingerspot_api.py), [`app/routers/webhook.py`](../app/routers/webhook.py).

## Endpoint yang dipakai

| Aksi | Isi tambahan | Hasil |
|---|---|---|
| `get_attlog` | `start_date`, `end_date` (`YYYY-MM-DD`, maks. 2 hari menurut dokumentasi) | Langsung di jawaban API |
| `get_device` | | Langsung di jawaban API |
| `get_all_pin` | | Webhook `get_userid_list` |
| `get_userinfo` | `pin` | Webhook `get_userinfo` |
| `set_userinfo` | `data: {pin, name, privilege, password, rfid, template}` | Webhook `set_userinfo` |
| `delete_userinfo` | `pin` | Webhook `delete_userinfo` |
| `set_time` | `timezone` | Webhook `set_time` |
| `restart_device` | | Webhook `restart_device` |

## Hal yang perlu diketahui

**`trans_id` harus angka 32-bit.** fingerspot.io mengubahnya menjadi integer sebelum dikirim balik. UUID `386a...` kembali sebagai `386` dan `f97...` sebagai `0`, sehingga jawaban tidak bisa dicocokkan.

**`set_userinfo` perlu semua isian di dalam `data`.** Tanpa `privilege`, `password`, dan `rfid`, mesin menjawab `ERR_02`. Kirim string kosong untuk yang tidak dipakai.

**Sidik jari ikut di `template`.** Tidak ada endpoint sidik jari terpisah. `get_userinfo` mengembalikan `template` dan `set_userinfo` menerimanya. Template hanya berlaku antar mesin bertipe sama.

**Kirim `privilege` yang sama.** Nilai `1` berarti pengguna biasa. Mengirim `1` untuk admin mesin menurunkan haknya, jadi hak itu dibaca dulu lewat `get_userinfo`.

**Status sukses bisa `OK` atau `1`.** Keduanya diterima. Nilai yang tidak dikenal dicatat di log dan dibiarkan menunggu.

**PIN yang tidak ada di mesin tidak dijawab.** Mesin diam saja untuk `get_userinfo` dengan PIN yang tidak terdaftar.

**`data` bisa berupa objek, list, atau string JSON.** Ketiganya ditangani untuk `attlog`.

**Jam scan tanpa zona waktu.** Nilainya adalah jam mesin. Sesuaikan `TIMEZONE`.

## Bentuk webhook

Scan:

```json
{
  "type": "attlog",
  "cloud_id": "C26XXXXXXXXXXXXX",
  "trans_id": "0",
  "data": {"pin": "1001", "scan": "2026-01-05 07:58:03", "verify": "1", "status_scan": "0"}
}
```

`verify`: 1 sidik jari, 2 password, 3 kartu, 4 wajah, 5 GPS, 6 vena.

Jawaban perintah:

```json
{"type": "set_userinfo", "cloud_id": "C26XXXXXXXXXXXXX", "trans_id": 123456789, "data": {"status": "OK"}}
```

Webhook ditolak dengan 403 bila `cloud_id` tidak terdaftar atau `token` salah.

## Sumber data dan data dobel

Scan dianggap sama bila PIN dan waktunya sama, dari mesin atau sumber mana pun. Bila scan yang sama masuk lagi dari sumber dengan prioritas lebih tinggi, catatannya diperbarui:

`REALTIME` (webhook) > `PULLED` (`get_attlog`) > `IMPORTED` (file)

Import file membuat karyawan baru untuk PIN yang belum ada, sedangkan webhook dan tarik scan tidak.

## Antrean karyawan ke mesin

Tabel `employee_device_access`, diproses tiap 10 detik oleh [`sync_engine.py`](../app/services/sync_engine.py).

| Status | Arti |
|---|---|
| `PENDING_ADD` | Menunggu dikirim, atau menunggu jawaban mesin |
| `PENDING_REMOVE` | Menunggu dihapus, atau menunggu jawaban mesin |
| `SYNCED` | Mesin sudah mengonfirmasi |
| `FAILED` | Gagal, alasannya di `last_error` |

- Bila template atau hak mesin belum tersimpan, `get_userinfo` diminta dulu dan ditunggu 60 detik.
- Penghapusan tanpa salinan template berakhir `FAILED` dan tidak dikirim.
- Perintah dikirim ulang tiap 5 menit, maksimal 6 kali.
- Jawaban perintah lama tidak menimpa keputusan yang lebih baru.
- Mengganti PIN mengirim data dengan PIN baru, tetapi PIN lama tidak dihapus otomatis dari mesin.
- Menghapus permanen karyawan (hanya yang tanpa scan) langsung mengirim `delete_userinfo` tanpa salinan template.

## Memecahkan masalah

| Gejala | Periksa |
|---|---|
| Scan tidak masuk | Mesin online? URL webhook benar dan bisa dibuka dari internet? Lihat `docker compose logs app` |
| Log `Webhook ditolak (cloud_id ...)` | Cloud ID di *Pengaturan > Mesin absensi* |
| Log `Webhook ditolak (token ...)` | `?token=` di URL webhook sama dengan `WEBHOOK_TOKEN` |
| `FINGERSPOT_API_KEY is not configured` | Isi `.env`, lalu `docker compose up -d` |
| Perintah menunggu terus | Webhook tidak sampai, atau mesin tidak terhubung ke cloud |
| Jam scan bergeser | `TIMEZONE` dan jam mesin (*Samakan jam mesin*) |

Setiap webhook dicatat tanpa isi datanya:

```
Webhook diterima type=set_userinfo trans_id=123456789 cocok=True status=OK cloud_id=... isian=status
```
