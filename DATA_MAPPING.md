# Data Mapping OBSERVA.FTI

Dokumen ini mencatat data frontend yang sebelumnya masih memakai nilai contoh atau dummy. Nilai tersebut sudah dikosongkan di UI dan nantinya perlu diisi dari backend.

## ADMIN

### Dashboard

| Data | Source Backend |
| --- | --- |
| Total Surat | tabel `observation_requests` |
| Surat Disetujui | tabel `observation_requests.status` |
| Surat Ditolak | tabel `observation_requests.status` |
| Surat Menunggu | tabel `observation_requests.status` |
| Total Dosen | tabel `lecturers` dan `users` |
| Margin Atas | tabel `system_settings` / pengaturan KOP |
| Margin Kiri | tabel `system_settings` / pengaturan KOP |
| Margin Bawah | tabel `system_settings` / pengaturan KOP |
| Margin Kanan | tabel `system_settings` / pengaturan KOP |
| Preview Nomor Surat | tabel `letter_numbers` |
| Preview Perihal Surat | tabel `observation_requests.topic` |
| Preview Penerima Surat | tabel `observation_requests.topic` / field penerima |
| Preview Instansi | tabel `observation_requests.destination_institution` |
| Preview Alamat Instansi | tabel `observation_requests.institution_address` |
| Preview Tanggal Surat | tabel `observation_requests.submission_date` / tanggal terbit surat |
| Preview Prodi | tabel `study_programs` |
| Preview Dosen | tabel `lecturers` dan `users` |
| Preview Kaprodi | tabel `head_of_programs`, `study_programs`, dan `users` |

### Kelola Dosen

| Data | Source Backend |
| --- | --- |
| Nama | tabel `users.name` |
| Email | tabel `users.email` |
| NIDN | tabel `lecturers.nidn` |
| No HP | tabel `users.phone` |
| Prodi | tabel `study_programs` |
| Status | tabel `users.is_active_flag` |
| Tanda Tangan PNG | tabel `cloudinary_files` / storage tanda tangan |
| Role | tabel `roles` |

### Kelola Kaprodi

| Data | Source Backend |
| --- | --- |
| Nama | tabel `users.name` |
| Email | tabel `users.email` |
| NIDN | tabel `head_of_programs.nidn` |
| No HP | tabel `users.phone` |
| Prodi | tabel `study_programs` |
| Status | tabel `users.is_active_flag` |
| Tanda Tangan PNG | tabel `cloudinary_files` / storage tanda tangan |
| Role | tabel `roles` |

### Program Studi

| Data | Source Backend |
| --- | --- |
| Nama Prodi | tabel `study_programs.name` |
| Kode Prodi | tabel `study_programs.code` |
| Fakultas | tabel `study_programs.faculty_name` |
| Kaprodi | tabel `study_programs.head_of_program_id` dan `head_of_programs` |
| Daftar Prodi | tabel `study_programs` |

### Akun Kiosk Mahasiswa

| Data | Source Backend |
| --- | --- |
| Nama Akun | tabel `users.name` |
| User / Kode Login | tabel `users.nid` |
| Password | tabel `users.password_hash` |
| Status Aktif | tabel `users.is_active_flag` |

### Pengaturan KOP

| Data | Source Backend |
| --- | --- |
| Margin Atas | tabel `system_settings` / pengaturan KOP |
| Margin Kiri | tabel `system_settings` / pengaturan KOP |
| Margin Bawah | tabel `system_settings` / pengaturan KOP |
| Margin Kanan | tabel `system_settings` / pengaturan KOP |
| Background KOP | tabel `cloudinary_files` dengan tipe KOP surat |
| Logo UKSW | tabel `cloudinary_files` dengan tipe logo universitas |
| Logo Fakultas | tabel `cloudinary_files` dengan tipe logo fakultas |
| Nama File KOP Aktif | tabel `cloudinary_files.original_filename` |
| Preview Surat KOP | tabel `observation_requests`, `letter_numbers`, `study_programs`, `lecturers`, dan `head_of_programs` |

### Riwayat Pengajuan

| Data | Source Backend |
| --- | --- |
| ID Dokumen | tabel `observation_requests.id` dan `created_at` |
| Nama Mahasiswa | tabel `students` dan `users` |
| NIM | tabel `students.nim` |
| Mata Kuliah | tabel `observation_requests.course_name` |
| Status Surat | tabel `observation_requests.status` |
| Tanggal Pengajuan | tabel `observation_requests.created_at` |
| Ringkasan Disetujui | tabel `observation_requests.status` |
| Ringkasan Ditolak | tabel `observation_requests.status` |
| Ringkasan Menunggu | tabel `observation_requests.status` |

## MAHASISWA

### Data Pemohon

| Data | Source Backend |
| --- | --- |
| Nama | tabel `students` dan `users.name` |
| NIM | tabel `students.nim` |
| Email | tabel `users.email` |
| Tanggal Rencana Observasi | tabel `observation_requests.submission_date` |

### Tujuan Observasi

| Data | Source Backend |
| --- | --- |
| Instansi | tabel `observation_requests.destination_institution` |
| Penerima | tabel `observation_requests.topic` / field penerima |
| Alamat | tabel `observation_requests.institution_address` |

### Data Akademik

| Data | Source Backend |
| --- | --- |
| Mata Kuliah | tabel `observation_requests.course_name` |
| Dosen | tabel `lecturers` dan `users` |
| Prodi | tabel `study_programs` |
| Jenis Dosen | tabel `lecturers` / konfigurasi pengampu |
| Dosen Eksternal | tabel `observation_requests` / tabel pengampu eksternal jika dibuat |

### Anggota Kelompok

| Data | Source Backend |
| --- | --- |
| Nama | tabel anggota pengajuan / `observation_request_members` |
| NIM | tabel anggota pengajuan / `observation_request_members` |

### Preview Surat

| Data | Source Backend |
| --- | --- |
| Background Surat | tabel `cloudinary_files` dengan tipe KOP surat |
| Nomor Surat | tabel `letter_numbers` |
| Tanggal Surat | tabel `observation_requests.submission_date` / tanggal terbit surat |
| Perihal | tabel `observation_requests.topic` |
| Penerima | tabel `observation_requests.topic` / field penerima |
| Instansi | tabel `observation_requests.destination_institution` |
| Alamat Instansi | tabel `observation_requests.institution_address` |
| Nama Prodi | tabel `study_programs.name` |
| Nama Mata Kuliah | tabel `observation_requests.course_name` |
| Dosen Pengampu | tabel `lecturers` dan `users` |
| Kaprodi | tabel `head_of_programs`, `study_programs`, dan `users` |
| Anggota Kelompok | tabel anggota pengajuan / `observation_request_members` |

## DOSEN

### Daftar Surat

| Data | Source Backend |
| --- | --- |
| ID Dokumen | tabel `observation_requests.id` dan `letter_numbers` |
| Nama Mahasiswa | tabel `students` dan `users` |
| NIM | tabel `students.nim` |
| Email | tabel `users.email` |
| Tanggal Observasi | tabel `observation_requests.submission_date` |
| Penerima Surat | tabel `observation_requests.topic` / field penerima |
| Instansi | tabel `observation_requests.destination_institution` |
| Alamat Instansi | tabel `observation_requests.institution_address` |
| Mata Kuliah | tabel `observation_requests.course_name` |
| Jenis Dosen | tabel `lecturers` / konfigurasi pengampu |
| Dosen Internal | tabel `lecturers` dan `users` |
| Dosen Eksternal | tabel `observation_requests` / tabel pengampu eksternal jika dibuat |
| Anggota Kelompok | tabel anggota pengajuan / `observation_request_members` |
| Status Approval | tabel `observation_requests.status` dan `approval_logs` |

### Riwayat

| Data | Source Backend |
| --- | --- |
| ID Dokumen | tabel `observation_requests.id` dan `letter_numbers` |
| Nama Mahasiswa | tabel `students` dan `users` |
| NIM | tabel `students.nim` |
| Mata Kuliah | tabel `observation_requests.course_name` |
| Instansi | tabel `observation_requests.destination_institution` |
| Tanggal | tabel `approval_logs.created_at` |
| Status Approval | tabel `approval_logs.action` / `observation_requests.status` |

### Catatan Evaluasi

| Data | Source Backend |
| --- | --- |
| Catatan Evaluasi | tabel `approval_logs.note` |
| Keputusan Dosen | tabel `approval_logs.action` |
| Validator Dosen | tabel `lecturers` dan `users` |

## KAPRODI

### Daftar Surat

| Data | Source Backend |
| --- | --- |
| ID Dokumen | tabel `observation_requests.id` dan `letter_numbers` |
| Nama Mahasiswa | tabel `students` dan `users` |
| NIM | tabel `students.nim` |
| Email | tabel `users.email` |
| Tanggal Observasi | tabel `observation_requests.submission_date` |
| Penerima Surat | tabel `observation_requests.topic` / field penerima |
| Instansi | tabel `observation_requests.destination_institution` |
| Alamat Instansi | tabel `observation_requests.institution_address` |
| Mata Kuliah | tabel `observation_requests.course_name` |
| Dosen Internal | tabel `lecturers` dan `users` |
| Anggota Kelompok | tabel anggota pengajuan / `observation_request_members` |
| Status Approval | tabel `observation_requests.status` dan `approval_logs` |

### Riwayat

| Data | Source Backend |
| --- | --- |
| ID Dokumen | tabel `observation_requests.id` dan `letter_numbers` |
| Nama Mahasiswa | tabel `students` dan `users` |
| NIM | tabel `students.nim` |
| Mata Kuliah | tabel `observation_requests.course_name` |
| Instansi | tabel `observation_requests.destination_institution` |
| Tanggal | tabel `approval_logs.created_at` |
| Status Approval | tabel `approval_logs.action` / `observation_requests.status` |

### Catatan Validasi

| Data | Source Backend |
| --- | --- |
| Catatan Validasi | tabel `approval_logs.note` |
| Keputusan Kaprodi | tabel `approval_logs.action` |
| Validator Kaprodi | tabel `head_of_programs` dan `users` |

