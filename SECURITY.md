# Keamanan

Jangan laporkan celah keamanan lewat issue publik. Gunakan **Security > Report a vulnerability** di halaman GitHub repositori ini, sertakan langkah dan dampaknya.

Sebelum dipakai di produksi:

- Pasang di belakang HTTPS.
- Isi `JWT_SECRET_KEY` dan `WEBHOOK_TOKEN` dengan nilai acak.
- Ganti password admin pertama.
- Jangan buka port PostgreSQL ke internet.
- Batasi akses ke folder `backups/`, isinya termasuk template sidik jari.
