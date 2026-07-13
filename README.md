# Sistem Pengajuan Surat Izin Observasi

Aplikasi web untuk mendigitalkan alur pengajuan surat izin observasi:
Mahasiswa → Dosen Pembimbing → Kaprodi → Penerbitan Surat (PDF + Email).

Status pembangunan saat ini: **Tahap 12 — Activity Log & Audit Trail Lintas Modul**
(lihat bagian "Tahap Selanjutnya" untuk Tahap 13-14).

## Teknologi

- Backend: Python, Flask (Blueprint, Jinja2, Flask-Login, Flask-Session, raw PyMySQL/DB helper)
- Database: TiDB Cloud (MySQL-compatible) via PyMySQL
- File storage: Cloudinary
- Email: Resend API
- Frontend: HTML5, CSS3, Vanilla JavaScript

## Persiapan Environment

1. **Buat virtual environment**
   ```bash
   python -m venv venv
   source venv/bin/activate        # Linux/Mac
   venv\Scripts\activate           # Windows
   ```

2. **Install dependency**
   ```bash
   pip install -r requirements.txt
   ```

   > **Catatan (Tahap 8):** `WeasyPrint` (dipakai `pdf_service` untuk generate
   > PDF surat) butuh library sistem Pango, Cairo, & GDK-Pixbuf di luar `pip`.
   > - Ubuntu/Debian: `sudo apt-get install libpango-1.0-0 libpangocairo-1.0-0 libgdk-pixbuf2.0-0 libcairo2`
   > - macOS (Homebrew): `brew install pango`
   >
   > Tanpa ini, fitur cetak draft & generate surat resmi akan gagal dengan
   > pesan error yang jelas (`PdfGenerationError`), namun sisa aplikasi tetap
   > berjalan normal.

3. **Salin file environment**
   ```bash
   cp .env.example .env
   ```
   Lalu isi seluruh nilai pada `.env`:
   - `DATABASE_URL` — connection string TiDB Cloud (didapat dari dashboard TiDB Cloud, menu "Connect").
   - `CLOUDINARY_CLOUD_NAME`, `CLOUDINARY_API_KEY`, `CLOUDINARY_API_SECRET` — dari dashboard Cloudinary.
   - `RESEND_API_KEY`, `RESEND_SENDER_EMAIL` — dari dashboard Resend.
   - `FACULTY_CODE` — kode fakultas untuk format nomor surat FR-50
     (mis. `FIK`); `UNIVERSITY_NAME`/`UNIVERSITY_ADDRESS` — teks kop surat
     fallback yang dipakai `pdf_service` selama Admin belum mengunggah
     kop surat resmi lewat menu Admin > Kop Surat & Logo (Tahap 10).
   - `SECRET_KEY`, `SESSION_SECRET` — string acak yang panjang & rahasia (misal `python -c "import secrets; print(secrets.token_hex(32))"`).

4. **Jalankan aplikasi (mode development)**
   ```bash
   flask run
   ```
   atau
   ```bash
   python wsgi.py
   ```

5. **Migrasi database sudah dihapus**
   Folder `migrations/` sudah dihapus karena runtime sekarang menggunakan
   raw PyMySQL dan tidak lagi tergantung pada Alembic/Flask-Migrate.

   Semua skrip migrasi legacy telah dihapus agar kode lebih ringkas dan
   agar tidak ada artefak ORM yang tersisa.

6. **Verifikasi**
   Buka `http://localhost:5000/health` — seharusnya mengembalikan JSON `{"status": "ok", ...}`.

## Struktur Project

> **Catatan restrukturisasi:** kode Python (logic aplikasi) dikelompokkan
> di `backend/`, sedangkan seluruh aset tampilan (template Jinja2, CSS, JS,
> gambar) dikelompokkan di `frontend/`. Ini tetap satu aplikasi Flask yang
> sama (server-rendered), bukan dua project/server terpisah — pemisahan
> ini hanya untuk kerapian & kemudahan navigasi folder.

Lihat dokumen Tahap 1 (`01-analisis-sistem.md`) bagian "Struktur Folder Project" untuk penjelasan lengkap tiap folder.

Ringkasan folder utama:

| Folder | Isi |
|---|---|
| `backend/config/` | Kelas konfigurasi (base/development/production), membaca dari `.env` |
| `backend/models/` | Model layer berbasis helper raw PyMySQL — 14 model sesuai ERD |
| `backend/forms/` | Form Flask-WTF (proteksi CSRF otomatis) — `LoginForm` (Tahap 4) |
| `backend/routes/` | Blueprint per role (auth, mahasiswa, dosen, kaprodi, admin) |
| `backend/controllers/` | Penghubung route ↔ service (akan diisi bertahap) |
| `backend/services/` | Business logic murni (Cloudinary, Resend, PDF, dsb.) |
| `backend/middlewares/` | Auth guard (`role_required`), rate limit, error handler |
| `backend/utils/` | Helper: validator, formatter, logger |
| `backend/emails/` | Template & renderer email HTML |
| `frontend/templates/` | Halaman web (Jinja2) |
| `frontend/static/` | CSS, JS, gambar |
| `migrations/` | Legacy Alembic migration scripts (Flask-Migrate) untuk referensi skema |
| `uploads/` | Folder temp sebelum file diunggah ke Cloudinary |
| `logs/` | File log aplikasi |

## Catatan Keamanan

- **Jangan pernah** commit file `.env` yang berisi nilai asli (sudah masuk `.gitignore`).
- Seluruh secret (database, Cloudinary, Resend, session) wajib melalui environment variable.
- `SECRET_KEY` dan `DATABASE_URL` wajib diisi — aplikasi akan menolak start jika kosong (lihat `backend/config/base.py`).
- Daftar lengkap hardening tambahan (header HTTP keamanan, validasi isi
  file upload, perbaikan celah SSTI pada Template Email, dsb.) ada di
  bagian **"Hardening Keamanan, Validasi Menyeluruh, Error Handling &
  Logging (Tahap 13)"** di bawah.

## Model & Migrasi (Tahap 3)

Seluruh 14 model pada `backend/models/` mengikuti ERD & skema SQL di
`01-analisis-sistem.md` bagian 7 & 8, dengan konvensi:
- `TimestampMixin` (`created_at`, `updated_at`) dan `SoftDeleteMixin` (`deleted_at`)
  pada `backend/models/base.py`, dipakai oleh entitas master/transaksi utama.
- Tabel log (`approval_logs`, `email_logs`, `activity_logs`, `letter_numbers`)
  sengaja tidak pakai mixin karena hanya butuh `created_at` (sesuai desain audit trail — append-only).
- Relasi melingkar `study_programs` ↔ `head_of_programs` ditangani dengan
  `use_alter=True` pada FK `fk_prodi_kaprodi`, sama seperti pendekatan
  `ALTER TABLE` pada skrip SQL Tahap 1.
- `User` mengimplementasikan `flask_login.UserMixin` beserta `user_loader`.

## Integrasi Email Resend (Tahap 9)

Mengimplementasikan FR-15, FR-23, FR-33, FR-52, FR-54 — email notifikasi
ke MAHASISWA pada setiap perubahan status penting, dikirim lewat Resend,
dicatat sebagai `email_logs`.

- **`backend/services/email_service.py`**:
  - `send_email(...)` — wrapper generik kirim satu email via
    `resend.Emails.send`, dengan retry sederhana (`EMAIL_MAX_ATTEMPTS`,
    default 2 percobaan, jeda 0.5 detik) sesuai NFR Reliability bagian 4.
    Lampiran (PDF surat resmi) dikirim sebagai base64 sesuai format REST
    API Resend.
  - `notify_lecturer_approved` / `notify_lecturer_rejected` /
    `notify_head_of_program_rejected` / `notify_official_letter_issued`
    — satu fungsi per jenis notifikasi. Masing-masing me-render template
    di `frontend/templates/emails/`, mengirim, lalu **selalu** mengembalikan
    objek `EmailLog` (status `sent` atau `failed`, FR-54) — TIDAK pernah
    melempar exception ke pemanggil, sehingga kegagalan Resend tidak
    membatalkan approval/penolakan yang sudah tercatat.
- **Template email** (`frontend/templates/emails/`): `_base_email.html`
  (layout bersama, CSS inline per elemen — banyak klien email mengabaikan
  `<style>` blok/CDN eksternal) + `_detail_table.html` (ringkasan surat)
  dipakai oleh `lecturer_approved.html`, `lecturer_rejected.html`,
  `head_of_program_rejected.html`, `official_letter_issued.html`
  (satu-satunya yang membawa lampiran PDF).
- **`observation_service`** — dipanggil di titik yang sama persis dengan
  `approval_log`, dalam SATU transaksi commit:
  - `approve_by_lecturer` → `notify_lecturer_approved`
  - `reject_by_lecturer` → `notify_lecturer_rejected`
  - `reject_by_head_of_program` → `notify_head_of_program_rejected`
  - `approve_by_head_of_program` → setelah nomor surat/PDF/upload
    Cloudinary (Tahap 8) sukses, dipanggil `notify_official_letter_issued`
    (lampiran PDF). Sesuai Activity Diagram Tahap 1 bagian 6, status
    akhir baru menjadi **`Selesai`** jika email sukses terkirim; jika
    gagal (setelah retry), status tetap **`Surat Dikirim`** — mahasiswa
    tetap bisa mengunduh PDF langsung, hanya emailnya yang perlu
    ditindaklanjuti manual/di kemudian hari (Tahap 12 dapat menambah job
    retry terjadwal berbasis `email_logs.status='failed'`).
- Halaman detail mahasiswa & Kaprodi diperbarui menampilkan perbedaan
  status `Selesai` (email terkirim) vs `Surat Dikirim` (email gagal,
  PDF tetap bisa diunduh).
- **Belum tercakup** (sesuai Activity Diagram Tahap 1 bagian 6):
  notifikasi ke Dosen (surat baru masuk) & Kaprodi (surat diteruskan)
  ditandai **"(in-app)"**, bukan email — butuh tabel `notifications` baru
  di luar ERD Tahap 1, sengaja belum diimplementasikan di tahap ini.
- Config baru (`.env`): `EMAIL_MAX_ATTEMPTS` (lihat `.env.example`).

## Service Inti: Penomoran Surat, Generate PDF, Cloudinary (Tahap 8)

Mengimplementasikan FR-50/FR-51/FR-52 (bagian storage) — tiga service baru
yang dipanggil **satu transaksi atomik** oleh
`observation_service.approve_by_head_of_program` (FR-32), persis mengikuti
Activity Diagram Tahap 1 bagian 6: Disetujui Kaprodi -> generate nomor ->
generate PDF -> upload -> status `Surat Dikirim`.

- **`backend/services/letter_number_service.py`** (FR-50) — menghasilkan nomor
  surat berformat `{urutan}/{kode_fakultas}/OBS/{bulan_romawi}/{tahun}`
  (`kode_fakultas` dari env `FACULTY_CODE`). Auto-increment per periode
  (bulan, tahun) dititipkan pada baris `system_settings` bertipe
  `letter_counter_{tahun}_{bulan}` (JSON `{"counter": n}`) yang dikunci
  dengan `SELECT ... FOR UPDATE` (`with_for_update()`) sebelum
  dibaca/ditambah, mencegah dua approval bersamaan pada periode yang sama
  menghasilkan nomor surat duplikat. Melempar `LetterNumberError` jika
  pengajuan sudah bernomor atau terjadi bentrok unique constraint.
- **`backend/services/pdf_service.py`** (FR-51) — render `pdf/surat_resmi.html`
  (surat resmi, bernomor, ada blok tanda tangan Kaprodi — tanda tangan
  digital tersertifikasi masih placeholder sesuai ruang lingkup Tahap 1
  bagian 1.3) atau `pdf/draft_surat.html` (draft, watermark, belum
  bernomor) lewat Jinja, lalu dikonversi ke PDF dengan **WeasyPrint**.
  Margin diambil dari `LetterTemplate` aktif (FR-43) atau default kolom
  bila belum ada; kop surat memakai `CloudinaryFile` terbaru
  (`kop_surat`/`logo_fakultas`/`logo_universitas`) bila Admin sudah pernah
  mengunggah (Tahap 10), atau fallback teks berbasis `UNIVERSITY_NAME`/
  `UNIVERSITY_ADDRESS` (env) + `faculty_name` prodi mahasiswa. CSS ditulis
  inline (bukan CDN) agar generate PDF tidak bergantung jaringan eksternal
  (NFR Reliability). Melempar `PdfGenerationError` jika WeasyPrint/
  dependency sistemnya (Pango/Cairo/GDK-Pixbuf) belum terpasang, atau bila
  render gagal.
- **`backend/services/cloudinary_service.py`** (FR-51/FR-52 storage) —
  ditambah `upload_bytes`/`delete_resource` generik (`resource_type="raw"`
  untuk PDF) dan `upload_official_letter_pdf` yang dipakai
  `observation_service`. `init_cloudinary` (Tahap 2) tidak berubah.
  Melempar `CloudinaryServiceError` bila kredensial kosong atau upload
  API gagal.
- **`observation_service.approve_by_head_of_program`** — ketiga langkah di
  atas dibungkus `try/except` di dalam transaksi yang sama dengan
  `approval_log` & mutasi status: bila salah satu gagal, **seluruh**
  perubahan (termasuk approval & counter nomor surat) di-rollback lewat
  `db.session.rollback()`, pengajuan kembali ke `Menunggu Persetujuan
  Kaprodi`, dan Kaprodi melihat flash error berisi alasan gagal serta
  dapat mencoba menyetujui ulang tanpa risiko nomor surat "bocor"
  (ter-increment padahal PDF gagal terbit).
- **Print Draft mahasiswa** (`GET /mahasiswa/riwayat-surat/<id>/cetak-draft`,
  FR-11) diperbarui memakai `pdf_service.generate_draft_pdf` — sekarang
  mengembalikan PDF sungguhan (`Content-Type: application/pdf`, tampil
  inline di tab baru) menggantikan halaman HTML cetak-browser Tahap 5.
  Draft tidak diunggah ke Cloudinary (dibuat on-the-fly setiap diminta)
  karena sifatnya sementara/berulang sebelum dikirim ke dosen.
- **Download surat resmi mahasiswa** (FR-14) kini benar-benar berfungsi:
  begitu Kaprodi menyetujui, `pdf_final_url` terisi URL Cloudinary dan
  halaman detail/riwayat mahasiswa menampilkan tombol unduh — mahasiswa
  tidak perlu menunggu email Tahap 9 untuk mengambil PDF-nya.
- Config baru (`.env`): `FACULTY_CODE`, `UNIVERSITY_NAME`,
  `UNIVERSITY_ADDRESS` (lihat `.env.example`).
- Belum tercakup di tahap ini (menyusul tahap terkait): pengiriman email
  (Tahap 9), upload kop surat/template/logo oleh Admin (Tahap 10, saat ini
  `cloudinary_files` masih selalu kosong sehingga PDF selalu memakai
  fallback teks), dan pencatatan terstruktur ke `activity_logs` (Tahap 12).

## Modul Admin (Tahap 10)

Implementasi FR-40–FR-46 / UC-20–UC-31, mengikuti pola `routes/` (thin) ->
`controllers/admin_controller.py` -> `services/admin_service.py`, sesuai
arsitektur yang sama dengan modul Mahasiswa/Dosen/Kaprodi (Tahap 5-7).

- **Kelola Mahasiswa/Dosen/Kaprodi** (`/admin/mahasiswa`, `/admin/dosen`,
  `/admin/kaprodi`, FR-40/UC-21-23) — CRUD akun lengkap: setiap create
  membuat baris `users` + profil terkait (`students`/`lecturers`/
  `head_of_programs`) dalam **satu transaksi** (`db.session.flush()` untuk
  mendapatkan `user.id` sebelum insert profil, rollback otomatis bila
  salah satu gagal). Password memakai Bcrypt yang sama dengan
  `auth_forms` (Tahap 4); saat edit, field password boleh dikosongkan
  (password lama dipertahankan). Delete bersifat **soft-delete** ganda
  (User + profil) dan ditolak (flash warning) bila akun tsb masih punya
  riwayat pengajuan surat (`observation_requests`), demi menjaga audit
  trail tetap utuh. Khusus Kaprodi: satu program studi hanya boleh
  memiliki satu kaprodi aktif (`_ensure_prodi_available_for_hop`), dan
  pointer `study_programs.head_of_program_id` disinkronkan otomatis.
- **Kelola Program Studi** (`/admin/prodi`, FR-40/UC-24) — CRUD kode/nama/
  fakultas; delete ditolak bila masih ada mahasiswa/dosen/kaprodi aktif
  di prodi tsb.
- **Kop Surat & Logo** (`/admin/kop-surat`, FR-41/UC-25) — upload PNG/JPG
  ke Cloudinary per kategori (Kop Surat, Logo Fakultas, Logo Universitas)
  memakai tiga instance form dengan **prefix WTForms berbeda** (pola yang
  sama dengan `ApprovalNoteForm` Tahap 6-7). File TERBARU yang belum
  dihapus otomatis dipakai `pdf_service` (Tahap 8) — sejak tahap ini,
  fallback teks kop surat hanya aktif bila Admin belum pernah mengunggah
  apa pun.
- **Template Surat** (`/admin/template-surat`, FR-42/UC-26) — CRUD
  `letter_templates` beserta upload berkas (PDF/DOCX) opsional ke
  Cloudinary; hanya satu template boleh berstatus **Aktif** dalam satu
  waktu (mengaktifkan satu otomatis menonaktifkan lainnya). Template aktif
  inilah yang membawa margin surat yang dipakai `pdf_service` (FR-43).
- **Setting Margin Surat** (`/admin/setting-margin`, FR-43/UC-27) — margin
  default sistem tersimpan di `system_settings` (key `letter_margin`,
  pola JSON yang sama dengan counter nomor surat Tahap 8). `pdf_service`
  kini memprioritaskan margin `LetterTemplate` aktif; bila belum ada
  template aktif, dipakai setting ini; bila setting ini juga belum pernah
  diisi, dipakai margin bawaan kolom (2.5/2.5/3.0/2.5 cm) — lihat
  `_system_default_margin()` di `pdf_service.py`.
- **Template Email** (`/admin/template-email`, FR-44/UC-28) — subjek & isi
  HTML tiap jenis notifikasi (`lecturer_approved`, `lecturer_rejected`,
  `head_of_program_rejected`, `official_letter_issued`) juga disimpan di
  `system_settings` (key `email_template:{jenis}`, tabel dedicated tidak
  ada di ERD Tahap 1). `email_service._notify` (Tahap 9) diperbarui:
  bila override tersedia, di-render sebagai template Jinja string dengan
  variabel yang sama (`observation_request`, dst); bila override gagal
  di-parse/di-render (mis. Admin salah ketik syntax), **otomatis jatuh
  kembali** ke file template bawaan di `frontend/templates/emails/` agar
  pengiriman notifikasi tidak pernah gagal hanya karena kustomisasi yang
  keliru. Tombol "Kembalikan ke Bawaan" menghapus override.
- **Riwayat Pengajuan** (`/admin/riwayat-pengajuan`, FR-45/UC-29) — tampilan
  daftar pengajuan surat observasi dengan filter status & paginasi.
  Halaman ini menampilkan `observation_requests` dan memberikan ringkasan
  status pengajuan bagi Admin.
- **Dashboard Statistik** (`/admin/dashboard`, FR-46/UC-30) — ringkasan
  jumlah mahasiswa/dosen/kaprodi/prodi, jumlah pengajuan per kelompok
  status, jumlah email terkirim/gagal (`email_logs`), dan total storage
  Cloudinary terpakai (`SUM(cloudinary_files.file_size)`, dalam MB).
  Dashboard lintas-role yang lebih kaya (grafik, tren waktu) menyusul
  **Tahap 11**.
- **Kelola Profil** (`/admin/profil`, FR-05/UC-31) — Admin dapat mengubah
  nama & no. HP miliknya sendiri, sama seperti pola profil Mahasiswa/
  Dosen/Kaprodi.
- Seluruh halaman memakai macro Jinja bersama di
  `frontend/templates/admin/_macros.html` (`render_field`, `pagination_nav`,
  `delete_button`) untuk konsistensi tampilan Bootstrap 5 dan mengurangi
  duplikasi lintas 18 halaman modul ini.
- Belum tercakup di tahap ini (menyusul tahap terkait): pencatatan
  otomatis `activity_logs` di titik-titik aksi modul lain (Tahap 12),
  dan hardening validasi/error handling menyeluruh (Tahap 13).

## Dashboard & Statistik Seluruh Role (Tahap 11)

Memperkaya keempat dashboard (Mahasiswa Tahap 5, Dosen Tahap 6, Kaprodi
Tahap 7, Admin Tahap 10) yang sebelumnya hanya menampilkan angka ringkas,
dengan grafik tren & metrik waktu proses. Tidak ada FR/UC baru (roadmap
Tahap 1 bagian 13 menyebut tahap ini sebagai "Dashboard & statistik
seluruh role" tanpa nomor FR khusus di luar FR-46 yang sudah dikerjakan
Tahap 10) — murni penyempurnaan tampilan & analitik di atas data yang
sudah ada.

- **`backend/utils/stats.py`** (baru) — dua helper statistik generik dipakai
  bersama oleh `observation_service` & `admin_service` agar tidak
  duplikasi logic:
  - `monthly_trend(items, date_getter, months=6)` — jumlah `items` per
    bulan untuk 6 bulan terakhir (dihitung di Python, bukan `GROUP BY`
    SQL per-bulan, agar portable lintas backend DB).
  - `avg_response_hours(pairs)` — rata-rata selisih jam antar pasangan
    `(mulai, selesai)`; mengembalikan `None` (bukan 0) bila tidak ada
    data, supaya dashboard bisa menampilkan "-" alih-alih angka yang
    menyesatkan.
- **Dashboard Mahasiswa** (`observation_service.get_dashboard_summary`) —
  ditambah kartu **Ditolak** (sebelumnya sudah dihitung tapi belum
  ditampilkan) dan grafik batang tren jumlah pengajuan per bulan.
- **Dashboard Dosen** (`get_dashboard_summary_for_lecturer`) — ditambah
  **rata-rata waktu respon** (jam dari pengajuan dibuat hingga dosen
  mengambil keputusan approve/reject, dihitung dari selisih
  `observation_requests.created_at` & `approval_logs.created_at`) dan
  grafik tren jumlah keputusan per bulan.
- **Dashboard Kaprodi** (`get_dashboard_summary_for_head_of_program`) —
  metrik yang sama persis (rata-rata waktu respon & tren keputusan per
  bulan), diskop ke pengajuan prodi yang dipimpin kaprodi tsb.
- **Dashboard Admin** (`admin_service.dashboard_summary`) — ditambah
  grafik tren pengajuan sistem per bulan, **rata-rata waktu total proses**
  hingga status `Selesai` (`created_at` -> `updated_at`), dan tabel
  rincian jumlah pengajuan per program studi.
- **Visualisasi**: grafik batang memakai **Chart.js** (CDN, sama seperti
  Bootstrap yang sudah dipakai lewat CDN sejak Tahap 2) lewat elemen
  `<canvas>` + `{% block extra_scripts %}` pada tiap halaman dashboard —
  data tren dikirim ke JS lewat filter Jinja bawaan Flask `| tojson`.
- Tidak ada perubahan skema database maupun endpoint baru pada tahap ini
  — seluruhnya penyempurnaan `services/` & `templates/` di atas data yang
  sudah tersedia sejak Tahap 5-10.

## Activity Log & Audit Trail Lintas Modul (Tahap 12)

Melengkapi sisi TULIS `activity_logs` yang sejak Tahap 10 baru punya sisi
  BACA. Tidak ada FR baru di luar FR-53..FR-55 & NFR Auditability
  (Tahap 1 bagian 4) yang sudah didefinisikan sejak Tahap 1 — tahap ini
  murni mengisi implementasi pencatatannya.
- **`backend/services/activity_log_service.py`** (baru) — satu-satunya pintu
  masuk penulisan `activity_logs`, dengan dua gaya pemakaian:
  - `build(...)` — buat instance `ActivityLog` TANPA commit, untuk aksi
    yang harus ikut dalam transaksi atomik yang sama dengan mutasi lain
    (mis. approve/reject di `observation_service`), mengikuti pola
    `email_service.notify_*` & `letter_number_service.generate_for_request`
    sejak Tahap 8-9.
  - `record(...)` — buat + commit langsung dalam transaksi sendiri, untuk
    aksi berdiri sendiri (login, logout, error handler global). Kegagalan
    menulis log di-*rollback* & dicatat ke `app.logger` teknis, TIDAK
    pernah dilempar sebagai exception — audit trail tidak boleh
    menggagalkan aksi utama pengguna.
  - Helper siap pakai per-aksi: `log_login`, `log_logout`, `log_error`,
    `log_upload`, `log_generate_pdf`, `build_approve`, `build_reject`,
    `build_generate_pdf`, `build_send_email`.
- **Cakupan aksi**: persis 8 konstanta `ActivityLog.ACTION_*` (login,
  logout, approve, reject, upload, generate_pdf, send_email, error) —
  sama persis dengan daftar NFR Auditability Tahap 1 bagian 4. CRUD master
  data murni (kelola mahasiswa/dosen/kaprodi/prodi, Tahap 10) dan
  penghapusan berkas (kop surat/template) SENGAJA tidak dicatat ke sini
  karena di luar 8 kategori tsb — tetap tercatat lewat `app.logger` teknis
  seperti sebelumnya.
- **Titik integrasi**:
  - `auth_routes.login` / `logout` — login sukses, login gagal (kredensial
    salah/akun nonaktif dicatat sebagai `error`), dan logout.
  - `observation_service.approve_by_lecturer` / `reject_by_lecturer` —
    `approve`/`reject` + `send_email` ikut dalam commit tunggal yang sama.
  - `observation_service.approve_by_head_of_program` — `approve` +
    `generate_pdf` (surat resmi) + `send_email` ikut transaksi atomik
    penerbitan surat; jika penerbitan gagal & di-*rollback*, kegagalan
    dicatat sebagai `error` lewat transaksi terpisah (sesi utama sudah
    di-*rollback* sehingga tidak bisa dipakai lagi).
  - `observation_service.reject_by_head_of_program` — `reject` + `send_email`.
  - `mahasiswa_controller.print_draft` — `generate_pdf` (berdiri sendiri,
    bukan bagian transaksi domain lain) & `error` bila gagal.
  - `admin_service.upload_letterhead_file` / `create_letter_template` /
    `update_letter_template` (saat berkas diganti) — `upload`.
  - `middlewares/error_handler.py` — error 403, 429, dan 500 dicatat
    sebagai `error`, dilampiri user yang sedang login jika ada.
- Tidak ada perubahan skema database (tabel `activity_logs` & halaman
  bacanya sudah ada sejak Tahap 3 & 10) maupun endpoint baru pada tahap
  ini — seluruhnya penambahan pencatatan di `services/`, `routes/`,
  `controllers/`, dan `middlewares/` yang sudah ada.

## Hardening Keamanan, Validasi Menyeluruh, Error Handling & Logging (Tahap 13)

Tahap ini tidak menambah FR baru — murni memperkuat implementasi NFR
Security, Reliability, dan Auditability (Tahap 1 bagian 4) yang selama
Tahap 2-12 sudah berjalan, plus menutup beberapa celah yang baru terlihat
setelah seluruh modul lengkap.

### 1. Perbaikan celah Server-Side Template Injection (SSTI)
- **Temuan**: `email_service._render_with_override` (Tahap 9/FR-44) me-
  render override Subjek/Isi HTML Template Email milik Admin memakai
  `current_app.jinja_env` — Jinja environment PENUH aplikasi. Ini berarti
  isi template yang tersimpan di database dieksekusi sebagai kode Jinja
  tanpa batasan, berisiko *Server-Side Template Injection* (mis. akses ke
  `__class__`/`__globals__` Python) jika akun Admin diambil alih.
- **Perbaikan**: override kini dirender lewat `jinja2.sandbox.SandboxedEnvironment`
  khusus (`backend/services/email_service.py::_sandboxed_env`) yang memblokir
  akses ke atribut/metode tidak aman, sementara variabel konteks biasa
  (`{{ observation_request.topic }}`, dst.) tetap berfungsi seperti
  sebelumnya. Tidak ada perubahan pada `/admin/template-email` (FR-44) dari
  sisi pengguna.

### 2. Validasi isi file upload (bukan hanya ekstensi)
- **Temuan**: `LetterheadUploadForm`/`LetterTemplateForm` (Tahap 10, FR-41/
  FR-42) hanya memvalidasi EKSTENSI nama file lewat `FileAllowed` —
  gampang dipalsukan (mis. mengganti nama file berbahaya jadi `*.png`).
- **Perbaikan**: `backend/utils/uploads.py` (baru) memverifikasi tanda tangan
  biner (*magic bytes*) file sesuai kategori yang diharapkan (image/pdf/
  docx), dan khusus gambar turut diverifikasi lewat Pillow
  (`Image.verify()`) agar file yang isinya rusak/bukan gambar sungguhan
  tetap ditolak. Dipanggil dari `admin_service.upload_letterhead_file`,
  `create_letter_template`, dan `update_letter_template` SEBELUM file
  diunggah ke Cloudinary — kegagalan validasi dipetakan ke
  `AdminServiceError` (flash message), pola yang sama seperti error
  Cloudinary yang sudah ada.
- Batas ukuran PER FILE (`UPLOAD_MAX_IMAGE_SIZE_MB`, `UPLOAD_MAX_TEMPLATE_SIZE_MB`,
  default 5MB/10MB) ditambahkan terpisah dari `MAX_CONTENT_LENGTH_MB` yang
  sudah ada sejak Tahap 2 (yang membatasi ukuran TOTAL satu request, bukan
  satu file individual).

### 3. Header HTTP keamanan (`backend/middlewares/security_headers.py`, baru)
Hook `after_request` menambahkan pada seluruh response: `X-Content-Type-Options: nosniff`,
`X-Frame-Options: DENY` (anti clickjacking), `Referrer-Policy`,
`Permissions-Policy` (menonaktifkan kamera/mikrofon/lokasi yang memang
tidak dipakai), `Content-Security-Policy` (membatasi sumber skrip/gaya/
gambar ke domain sendiri + CDN Bootstrap yang sudah dipakai sejak awal),
dan `Strict-Transport-Security` (hanya dikirim saat request HTTPS).
**Catatan jujur**: CSP masih mengizinkan `'unsafe-inline'` pada
script-src/style-src karena beberapa halaman memakai `<script>` inline &
atribut `onclick`/`onchange` untuk interaktivitas ringan — migrasi penuh
ke skrip eksternal + nonce adalah pekerjaan refactor templat yang
disengaja ditunda ke **Tahap 14** (styling/polishing) agar tidak
mencampur perubahan keamanan dengan perubahan tampilan dalam satu tahap.

### 4. Error handling tambahan (`backend/middlewares/error_handler.py`)
Melengkapi handler 403/404/405/429/500 (Tahap 12) dengan:
- **CSRFError (400)** — token CSRF hilang/kedaluwarsa/tidak cocok
  ditangani terpisah dari 400 generik dengan pesan yang jelas ke pengguna
  ("sesi kedaluwarsa, muat ulang halaman"), tetap tercatat sebagai
  `activity_log` `error` untuk audit (mis. mendeteksi percobaan CSRF).
- **400 generik** — jaring pengaman untuk request malformed lain.
- **413 Payload Too Large** — saat upload melebihi `MAX_CONTENT_LENGTH`.
- Template `errors/400.html` dan `errors/413.html` (baru) mengikuti pola
  `errors/403.html` dkk. yang sudah ada.

### 5. Validasi form lebih ketat (`backend/forms/__init__.py`, baru: validator bersama)
- `phone_validator()` — No. HP harus berformat angka/spasi/`+`/`-` (dipakai
  di seluruh `ProfileForm` Mahasiswa/Dosen/Kaprodi dan `StudentForm`/
  `LecturerForm`/`HeadOfProgramForm` Admin), mencegah input bukan nomor
  telepon lolos hanya karena panjangnya valid.
- `identifier_validator()` — NIM/NIDN dibatasi pola huruf/angka/`-`/`.`
  (3-30 karakter), dipakai di `StudentForm.nim` dan `LecturerForm.nidn`.
- `password_complexity_validator()` — password BARU yang di-set/diubah
  Admin (bukan form login) kini wajib minimal 8 karakter DAN mengandung
  kombinasi huruf+angka (naik dari sekadar minimal 6 karakter sejak
  Tahap 4/10). **Sengaja tidak diterapkan ke `LoginForm`** (Tahap 4) —
  memperketat validasi PANJANG pada form login akan membuat akun lama
  dengan password < 8 karakter tidak bisa login sama sekali meski
  passwordnya benar; kompleksitas hanya relevan saat password baru dibuat.

### 6. Logging aplikasi (`backend/utils/logger.py`)
- Setiap baris log teknis kini otomatis menyertakan IP, endpoint, dan
  user yang sedang login (`_RequestContextFilter`) — sebelumnya harus
  disebutkan manual per pemanggilan `app.logger.xxx(...)`, sekarang
  konsisten di semua log termasuk yang berasal dari `logging.getLogger(__name__)`
  pada service (`email_service`, `cloudinary_service`, dst., yang secara
  otomatis menjadi child logger dari `app.logger`).
- File log KEDUA (`logs/error.log`) berisi HANYA level WARNING ke atas,
  terpisah dari `logs/app.log` (semua level >= `LOG_LEVEL`) agar operator
  bisa memantau kondisi bermasalah tanpa tercampur log rutin.

### 7. IP klien asli di balik reverse proxy (`backend/__init__.py`)
`ProxyFix` (Werkzeug) diaktifkan hanya jika `TRUSTED_PROXY_COUNT` (.env,
default 0) > 0, agar `request.remote_addr` yang dipakai rate limiter
(FR-03) dan `activity_log`/log teknis (FR-53/55) tetap akurat saat
aplikasi di-deploy di belakang reverse proxy (Nginx, dsb.), tanpa
membuka celah spoofing IP lewat header `X-Forwarded-For` saat TIDAK ada
proxy tepercaya (default: header tsb diabaikan sepenuhnya).

### Tidak berubah
Tidak ada perubahan skema database maupun endpoint/halaman baru pada
tahap ini — seluruhnya penguatan pada layer `services/`, `middlewares/`,
`forms/`, dan `utils/` yang sudah ada.

## Tahap Selanjutnya

- **Tahap 14**: Styling UI/UX responsif sesuai referensi desain, polishing,
  testing akhir.

## Modul Kaprodi (Tahap 7)

Implementasi FR-30-FR-34 / UC-14-UC-19, mengikuti pola routes/ (thin) ->
controllers/kaprodi_controller.py -> services/observation_service.py
persis seperti Modul Dosen (Tahap 6) - ketiga controller (mahasiswa, dosen,
kaprodi) berbagi service yang sama karena sama-sama beroperasi pada
ObservationRequest.

- Daftar persetujuan (GET /kaprodi/daftar-persetujuan, FR-30/UC-15) -
  daftar pengajuan berstatus Menunggu Persetujuan Kaprodi pada program
  studi yang dipimpin kaprodi yang sedang login
  (observation_service.list_incoming_for_head_of_program), dipaginasi
  (10/halaman) dan diurutkan FIFO agar antrean adil.
- Detail & aksi (GET /kaprodi/daftar-persetujuan/<id>, FR-30) -
  menampilkan detail pengajuan, timeline approval_logs, serta dua form
  aksi (Setujui/Tolak) yang hanya tampil selama status masih
  Menunggu Persetujuan Kaprodi (ObservationRequest.is_waiting_head_of_program).
  Kaprodi tetap bisa membuka detail pengajuan yang sudah ia proses
  sebelumnya (mis. dari Riwayat), hanya saja form aksi disembunyikan.
- Setujui (POST /kaprodi/daftar-persetujuan/<id>/setujui,
  FR-31/FR-32/UC-16) - status berpindah ke Disetujui Kaprodi dan dicatat
  pada approval_logs (role_at_approval="kaprodi", action="approve").
  FR-32 mengamanatkan bahwa persetujuan ini men-trigger generate nomor
  surat, generate PDF final, dan pengiriman email secara otomatis;
  penomoran + generate PDF + upload Cloudinary sekarang sudah terpasang
  (Tahap 8, lihat bagian "Service Inti" di atas) dan dibungkus dalam
  transaksi atomik yang sama dengan approval_log di atas - bila salah
  satu gagal, seluruhnya rollback. Status akhir setelah sukses:
  Surat Dikirim. Pengiriman email masih # TODO (Tahap 9).
- Tolak (POST /kaprodi/daftar-persetujuan/<id>/tolak,
  FR-31/FR-33/UC-17) - status berpindah ke Ditolak Kaprodi,
  rejection_note diisi dari catatan (jika ada), dan tercatat pada
  approval_logs (action="reject"). Mahasiswa akan melihat status &
  catatan ini di halaman detail pengajuannya (Tahap 5); notifikasi email
  menyusul Tahap 9.
- Riwayat (GET /kaprodi/riwayat, FR-34/UC-18) - seluruh keputusan
  (setujui/tolak) yang pernah diambil kaprodi ini, diambil langsung dari
  approval_logs, dipaginasi, terbaru lebih dulu.
- Kelola profil (GET/POST /kaprodi/profil, FR-05/UC-19) - kaprodi
  dapat mengubah nama & no. HP; email dan program studi bersifat baku
  (dikelola Admin, Tahap 10).
- Dashboard (GET /kaprodi/dashboard) - ringkasan jumlah pengajuan
  prodi yang menunggu, sudah disetujui, dan sudah ditolak (dihitung dari
  approval_logs milik kaprodi ini), plus 5 pengajuan menunggu terlama
  yang butuh tindakan segera.
- Proteksi kepemilikan: _get_head_of_program_request_or_404 memastikan
  kaprodi hanya bisa melihat/memproses pengajuan yang study_program_id-nya
  memang prodi yang ia pimpin (404 jika bukan) - pola yang sama dengan
  proteksi kepemilikan dosen pada Tahap 6.
- Notifikasi email (FR-15/Tahap 9) dan pencatatan terstruktur ke
  activity_logs (FR-55/Tahap 12) belum aktif di tahap ini; sementara
  aktivitas dicatat lewat app.logger, sama seperti pola Tahap 4-6.
  Penomoran & generate PDF surat resmi (FR-50/FR-51) sudah aktif sejak
  Tahap 8.

## Modul Dosen (Tahap 6)

Implementasi FR-20–FR-24 / UC-08–UC-13, mengikuti pola `routes/` (thin) ->
`controllers/dosen_controller.py` -> `services/observation_service.py`
persis seperti Modul Mahasiswa (Tahap 5) — kedua controller berbagi
service yang sama karena sama-sama beroperasi pada `ObservationRequest`.

- **Surat masuk** (`GET /dosen/surat-masuk`, FR-20/UC-09) — daftar
  pengajuan berstatus `Menunggu Persetujuan Dosen` yang dibimbing dosen
  yang sedang login (`observation_service.list_incoming_for_lecturer`),
  dipaginasi (10/halaman) dan diurutkan FIFO (dari yang paling lama
  menunggu) agar antrean adil.
- **Detail & aksi** (`GET /dosen/surat-masuk/<id>`, FR-20) — menampilkan
  detail pengajuan, timeline `approval_logs`, serta dua form aksi
  (Setujui/Tolak) yang hanya tampil selama status masih
  `Menunggu Persetujuan Dosen` (`ObservationRequest.is_waiting_lecturer`).
  Dosen tetap bisa membuka detail pengajuan yang sudah ia proses
  sebelumnya (mis. dari Riwayat Persetujuan), hanya saja form aksi
  disembunyikan.
- **Setujui** (`POST /dosen/surat-masuk/<id>/setujui`, FR-21/FR-22/UC-10) —
  status berpindah langsung ke `Menunggu Persetujuan Kaprodi` (prodi
  mahasiswa terkait sudah otomatis benar karena `study_program_id`
  disalin dari profil mahasiswa saat pengajuan dibuat, Tahap 5) dan
  dicatat pada `approval_logs` (`role_at_approval="dosen"`,
  `action="approve"`) dalam satu transaksi (`db.session.commit()`
  tunggal) agar atomik sesuai NFR Reliability. Catatan bersifat opsional
  sesuai FR-21.
- **Tolak** (`POST /dosen/surat-masuk/<id>/tolak`, FR-21/FR-23/UC-11) —
  status berpindah ke `Ditolak Dosen`, `rejection_note` diisi dari
  catatan (jika ada), dan tercatat pada `approval_logs`
  (`action="reject"`). Mahasiswa akan melihat status & catatan ini di
  halaman detail pengajuannya (Tahap 5); notifikasi email menyusul
  **Tahap 9**.
- **Riwayat persetujuan** (`GET /dosen/riwayat-persetujuan`, FR-24/UC-12) —
  seluruh keputusan (setujui/tolak) yang pernah diambil dosen ini,
  diambil langsung dari `approval_logs` (bukan dari `ObservationRequest`,
  karena satu pengajuan hanya menyimpan status terkininya), dipaginasi,
  terbaru lebih dulu.
- **Kelola profil** (`GET/POST /dosen/profil`, FR-05/UC-13) — dosen dapat
  mengubah nama & no. HP; NIDN, email, dan program studi bersifat baku
  (dikelola Admin, Tahap 10).
- **Dashboard** (`GET /dosen/dashboard`) — ringkasan jumlah surat
  menunggu, sudah disetujui, dan sudah ditolak (dihitung dari
  `approval_logs` milik dosen ini), plus 5 surat masuk terlama yang
  butuh tindakan segera.
- Dua form aksi (Setujui/Tolak) pada satu halaman detail memakai
  `ApprovalNoteForm` dengan **prefix WTForms berbeda** (`approve-` dan
  `reject-`) agar nama field (termasuk `csrf_token`) tidak bentrok dan
  masing-masing form tervalidasi independen.
- Proteksi kepemilikan: `_get_lecturer_request_or_404` memastikan dosen
  hanya bisa melihat/memproses pengajuan yang lecturer_id-nya memang
  dirinya sendiri (404 jika bukan); aksi approve/reject juga menolak
  (flash warning) bila status pengajuan sudah berubah sejak halaman
  dibuka (race condition sederhana antar-tab/dosen ganda).
- Notifikasi email (FR-15/Tahap 9) dan pencatatan terstruktur ke
  `activity_logs` (FR-55/Tahap 12) belum aktif di tahap ini; sementara
  aktivitas dicatat lewat `app.logger`, sama seperti pola Tahap 4 & 5.

## Modul Mahasiswa (Tahap 5)

Implementasi FR-10–FR-15 / UC-01–UC-07, mengikuti pola `routes/` (thin) ->
`controllers/mahasiswa_controller.py` -> `services/observation_service.py`
sesuai arsitektur Tahap 1 bagian 9:

- **Ajukan surat** (`GET/POST /mahasiswa/ajukan-surat`) — form Flask-WTF
  (`backend/forms/mahasiswa_forms.py::ObservationRequestForm`) menyimpan
  `ObservationRequest` berstatus `Draft`. Field NIM/Nama/Prodi/Semester/Email
  tidak ditanyakan ulang karena diambil dari profil `Student`/`User` yang
  sedang login; pilihan Dosen Pembimbing dibatasi ke dosen aktif pada prodi
  mahasiswa yang sama.
- **Ubah draft** (`GET/POST /mahasiswa/riwayat-surat/<id>/edit`) — hanya
  diizinkan selama status masih `Draft` (`ObservationRequest.is_editable`).
- **Print Draft** (`GET /mahasiswa/riwayat-surat/<id>/cetak-draft`, FR-11) —
  menghasilkan PDF sungguhan (`pdf_service.generate_draft_pdf`, WeasyPrint,
  watermark "DRAFT — BELUM RESMI", belum bernomor), ditampilkan inline di
  tab baru. Dibuat on-the-fly setiap diminta (tidak diunggah ke
  Cloudinary) karena sifatnya sementara sebelum dikirim ke dosen.
- **Kirim ke Dosen** (`POST /mahasiswa/riwayat-surat/<id>/kirim`, FR-12) —
  transisi status `Draft -> Menunggu Persetujuan Dosen`; setelah ini draft
  tidak dapat diubah lagi. Notifikasi email ke dosen menyusul **Tahap 9**.
- **Riwayat & detail** (`GET /mahasiswa/riwayat-surat`, FR-13) — daftar
  dipaginasi (`observation_service.list_for_student`, 10/halaman) dengan
  filter status; halaman detail menampilkan timeline `approval_logs`,
  nomor surat (bila sudah terbit), serta tombol unduh PDF resmi begitu
  `pdf_final_url` tersedia (Tahap 8).
- **Download surat resmi** (`GET /mahasiswa/riwayat-surat/<id>/download`,
  FR-14) — redirect ke `pdf_final_url` (Cloudinary), otomatis terisi
  begitu Kaprodi menyetujui pengajuan (Tahap 8: `letter_number_service` +
  `pdf_service` + `cloudinary_service`, dipanggil dari
  `observation_service.approve_by_head_of_program`) — mahasiswa tidak
  perlu menunggu email Tahap 9 untuk mengunduhnya.
- **Kelola profil** (`GET/POST /mahasiswa/profil`, FR-05/UC-07) — mahasiswa
  dapat mengubah nama, no. HP, dan semester; NIM/email/prodi bersifat baku
  (dikelola Admin, Tahap 10).
- Notifikasi email (FR-15) dan pencatatan terstruktur ke `activity_logs`
  (FR-55) belum aktif di tahap ini — menyusul Tahap 9 & 12; sementara
  aktivitas penting dicatat lewat `app.logger`, sama seperti pola Tahap 4.

Jinja filter baru di `backend/utils/formatters.py` (didaftarkan di
`create_app()`): `{{ value | tanggal_id }}` (format tanggal Indonesia) dan
`{{ status | status_badge }}` (kelas warna badge Bootstrap sesuai status alur).

## Modul Autentikasi (Tahap 4)

Implementasi login, logout, RBAC, rate limit, dan CSRF sesuai FR-01–FR-04:

- **Login** (`GET/POST /auth/login`) — form Flask-WTF (`backend/forms/auth_forms.py`)
  dengan validasi server-side, password diverifikasi via Bcrypt
  (`backend/utils/security.py`), pencarian email case-insensitive.
- **Logout** (`POST /auth/logout`) — invalidasi session via `flask_login.logout_user()`,
  hanya menerima POST + CSRF token agar tidak bisa dipicu via link/GET.
- **RBAC** — decorator `role_required(*roles)` pada `backend/middlewares/auth_middleware.py`
  membungkus `login_required`; dipakai pada endpoint `/mahasiswa/dashboard`,
  `/dosen/dashboard`, `/kaprodi/dashboard`, `/admin/dashboard` (masih berupa
  placeholder, konten lengkap menyusul di Tahap 5-7 & 10) untuk membuktikan
  seorang mahasiswa tidak bisa mengakses dashboard dosen/kaprodi/admin (403),
  begitu pula sebaliknya.
- **Rate limiting** (FR-03) — via Flask-Limiter, hanya membatasi method POST pada
  `/auth/login`, nilai `RATE_LIMIT_LOGIN_ATTEMPTS` / `RATE_LIMIT_LOGIN_WINDOW_MINUTES`
  dari `.env`. Percobaan yang melebihi batas mendapat respons 429.
- **CSRF** — aktif global lewat `CSRFProtect` (Tahap 2); form login otomatis
  menyertakan token via `form.hidden_tag()`, form logout menyertakan token
  manual di `layouts/base.html`.
- **Redirect setelah login** — diarahkan ke dashboard sesuai role
  (`dashboard_endpoint_for()`), atau ke parameter `?next=` bila valid & aman
  (dicegah open-redirect via `is_safe_redirect_url()`).

### Setup akun pertama (development)

Akun **admin pertama** tetap dibuat lewat Flask CLI kustom (`backend/cli.py`)
karena belum ada Admin lain yang bisa membuatkannya lewat UI:

```bash
flask seed-roles          # membuat 4 role: mahasiswa, dosen, kaprodi, admin
flask create-admin        # membuat akun admin pertama (interaktif)
```

Setelah itu, akun admin dapat login di `/auth/login` dan diarahkan ke
`/admin/dashboard`. Sejak **Tahap 10**, seluruh akun mahasiswa/dosen/
kaprodi berikutnya sudah bisa dibuat langsung lewat UI Admin
(`/admin/mahasiswa`, `/admin/dosen`, `/admin/kaprodi` — lihat bagian
"Modul Admin (Tahap 10)" di atas), tanpa perlu lagi `flask shell` manual.


---

## Tahap 14 — Styling UI/UX & Mode Kiosk Mahasiswa

Tahap ini menerapkan desain visual (Figma: brand "OBSERVA.FTI", palet navy
`#0B192E` / oranye `#E77817` / biru `#00589B`, font Poppins + Inter) dan
sekaligus **mengubah arsitektur login mahasiswa** menjadi mode kiosk atas
permintaan produk. Bagian dokumentasi mahasiswa di atas (yang menyebut
`/mahasiswa/dashboard`, `/mahasiswa/riwayat-surat/*`, `/mahasiswa/profil`)
menjelaskan desain Tahap 5 yang **sudah digantikan** oleh alur berikut:

### Alur baru
1. **Satu akun login bersama** untuk seluruh mahasiswa (bukan per-individu):
   dibuat lewat `flask create-kiosk-mahasiswa` (mirip `create-admin`).
   Akun ini sengaja tidak memiliki baris `students` terkait.
2. `GET /mahasiswa/welcome` — halaman sambutan ("Selamat Datang di Layanan
   Form Digital") dengan satu tombol "Mulai Isi Form". Logout **tidak**
   ditampilkan sebagai tombol; keluar dari sesi kiosk dilakukan dengan
   mengklik logo bulat di halaman ini 5x dalam 2 detik.
3. `GET/POST /mahasiswa/ajukan-surat` — satu-satunya form. Mahasiswa
   mengetik **NIM** miliknya secara manual; sistem mencocokkannya ke data
   `students` yang sudah didaftarkan Admin (`observation_service.
   find_student_by_nim`). Prodi & dosen pembimbing juga dipilih di form ini
   (dosen difilter otomatis sesuai prodi via JS, divalidasi ulang di server).
   Dua tombol aksi:
   - **Cetak Hardfile** — generate & buka PDF draft di tab baru (`formtarget=
     "_blank"`), mahasiswa tetap berada di form.
   - **Kirim TTD Digital** — submit final ke dosen pembimbing, lalu
     redirect ke `/mahasiswa/welcome` (bukan ke halaman riwayat/detail).

### Konsekuensi & catatan
- Endpoint lama `/mahasiswa/dashboard`, `/mahasiswa/riwayat-surat*`,
  `/mahasiswa/profil` **dihapus** dari blueprint karena bergantung pada
  profil Student per-individu yang login (`current_user.student_profile`),
  yang sudah tidak berlaku untuk akun kiosk bersama.
- Fungsi service pendukungnya (`list_for_student`, `get_owned_request`, dst.)
  tetap dipertahankan di `observation_service.py` bila fitur "cek status
  surat by NIM" ingin ditambahkan kembali di iterasi berikutnya.
- Klik "Cetak Hardfile" lalu "Kirim TTD Digital" pada isian yang sama akan
  membuat dua baris `observation_requests` terpisah (draft yang dicetak
  tidak otomatis dipakai ulang oleh aksi kirim) — draft yang tidak
  dilanjutkan akan tertinggal berstatus `Draft` dan aman diabaikan/
  dibersihkan secara berkala; ini trade-off yang disengaja untuk menjaga
  form tetap satu halaman sederhana tanpa endpoint AJAX tambahan.
- Halaman Login (`/auth/login`) dirombak menjadi split-screen (panel navy
  form + panel putih ilustrasi) dan **dipakai bersama oleh semua role**
  (mahasiswa/dosen/kaprodi/admin) — desain diambil dari referensi Figma
  yang sama di keempat file `PAGE_*.zip`.
- Dashboard Dosen/Kaprodi/Admin (login per-individu, tanpa perubahan alur)
  **belum** di-restyle pada iterasi ini karena file desain Figma yang
  diunggah untuk ketiga role tsb ternyata hanya berisi halaman Login (lihat
  pembahasan di awal sesi Tahap 14); menyusul begitu file desain dashboard
  yang benar tersedia.
