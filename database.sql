-- =====================================================
-- DATABASE OBSERVA.FTI
-- =====================================================

CREATE DATABASE IF NOT EXISTS observa_fti
CHARACTER SET utf8mb4
COLLATE utf8mb4_unicode_ci;

USE observa_fti;

-- =====================================================
-- TABEL PENGGUNA
-- =====================================================

CREATE TABLE pengguna (

    id_pengguna INT AUTO_INCREMENT PRIMARY KEY,

    nama VARCHAR(100) NOT NULL,

    email VARCHAR(100) NOT NULL UNIQUE,

    password VARCHAR(255) NOT NULL,

    role VARCHAR(20) NOT NULL
        CHECK (role IN ('admin','dosen','kaprodi', 'kiosk')),

    status_aktif BOOLEAN DEFAULT TRUE,

    dibuat_pada TIMESTAMP DEFAULT CURRENT_TIMESTAMP,

    diperbarui_pada TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        ON UPDATE CURRENT_TIMESTAMP

);

-- =====================================================
-- TABEL PROGRAM STUDI
-- =====================================================

CREATE TABLE program_studi (

    id_program_studi INT AUTO_INCREMENT PRIMARY KEY,

    nama_program_studi VARCHAR(100) NOT NULL UNIQUE,

    status_aktif BOOLEAN DEFAULT TRUE,

    dibuat_pada TIMESTAMP DEFAULT CURRENT_TIMESTAMP,

    diperbarui_pada TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        ON UPDATE CURRENT_TIMESTAMP

);

-- =====================================================
-- TABEL FILE CLOUDINARY
-- =====================================================

CREATE TABLE file_cloudinary (

    id_file INT AUTO_INCREMENT PRIMARY KEY,

    nama_file VARCHAR(150) NOT NULL,

    public_id VARCHAR(255) NOT NULL UNIQUE,

    secure_url TEXT NOT NULL,

    resource_type VARCHAR(30) NOT NULL,

    dibuat_pada TIMESTAMP DEFAULT CURRENT_TIMESTAMP

);

-- =====================================================
-- TABEL DOSEN
-- =====================================================

CREATE TABLE dosen (

    id_dosen INT AUTO_INCREMENT PRIMARY KEY,

    id_pengguna INT NOT NULL,

    id_program_studi INT DEFAULT NULL,

    nidn VARCHAR(30) NOT NULL UNIQUE,

    id_file_tanda_tangan INT DEFAULT NULL,

    dibuat_pada TIMESTAMP DEFAULT CURRENT_TIMESTAMP,

    diperbarui_pada TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        ON UPDATE CURRENT_TIMESTAMP,

    CONSTRAINT fk_dosen_pengguna
        FOREIGN KEY (id_pengguna)
        REFERENCES pengguna(id_pengguna)
        ON UPDATE CASCADE
        ON DELETE RESTRICT,

    CONSTRAINT fk_dosen_program
        FOREIGN KEY (id_program_studi)
        REFERENCES program_studi(id_program_studi)
        ON UPDATE CASCADE
        ON DELETE RESTRICT,

    CONSTRAINT fk_dosen_ttd
        FOREIGN KEY (id_file_tanda_tangan)
        REFERENCES file_cloudinary(id_file)
        ON UPDATE CASCADE
        ON DELETE SET NULL

);

-- =====================================================
-- TABEL KAPRODI
-- =====================================================

CREATE TABLE kaprodi (

    id_kaprodi INT AUTO_INCREMENT PRIMARY KEY,

    id_pengguna INT NOT NULL,

    id_program_studi INT DEFAULT NULL,

    nidn VARCHAR(30) NOT NULL UNIQUE,

    id_file_tanda_tangan INT DEFAULT NULL,

    dibuat_pada TIMESTAMP DEFAULT CURRENT_TIMESTAMP,

    diperbarui_pada TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        ON UPDATE CURRENT_TIMESTAMP,

    CONSTRAINT fk_kaprodi_pengguna
        FOREIGN KEY (id_pengguna)
        REFERENCES pengguna(id_pengguna)
        ON UPDATE CASCADE
        ON DELETE RESTRICT,

    CONSTRAINT fk_kaprodi_program
        FOREIGN KEY (id_program_studi)
        REFERENCES program_studi(id_program_studi)
        ON UPDATE CASCADE
        ON DELETE RESTRICT,

    CONSTRAINT fk_kaprodi_ttd
        FOREIGN KEY (id_file_tanda_tangan)
        REFERENCES file_cloudinary(id_file)
        ON UPDATE CASCADE
        ON DELETE SET NULL

);

-- =====================================================
-- TABEL PENGAJUAN OBSERVASI
-- =====================================================

CREATE TABLE pengajuan_observasi (

    id_pengajuan INT AUTO_INCREMENT PRIMARY KEY,

    nama_mahasiswa VARCHAR(100) NOT NULL,

    nim VARCHAR(20) NOT NULL,

    email VARCHAR(100) NOT NULL,

    id_program_studi INT NOT NULL,

    id_dosen INT NOT NULL,

    nama_penerima VARCHAR(100) NOT NULL,

    nama_instansi VARCHAR(150) NOT NULL,

    alamat_instansi TEXT NOT NULL,

    mata_kuliah VARCHAR(100) NOT NULL,

    tanggal_observasi DATE NOT NULL,

    anggota_kelompok TEXT,

    status_dosen VARCHAR(30)
        DEFAULT 'Menunggu',

    catatan_dosen TEXT,

    status_kaprodi VARCHAR(30)
        DEFAULT 'Menunggu',

    catatan_kaprodi TEXT,

    status_pengajuan VARCHAR(30)
        DEFAULT 'Menunggu',

    tanggal_pengajuan TIMESTAMP
        DEFAULT CURRENT_TIMESTAMP,

    CONSTRAINT fk_pengajuan_program
        FOREIGN KEY (id_program_studi)
        REFERENCES program_studi(id_program_studi)
        ON UPDATE CASCADE
        ON DELETE RESTRICT,

    CONSTRAINT fk_pengajuan_dosen
        FOREIGN KEY (id_dosen)
        REFERENCES dosen(id_dosen)
        ON UPDATE CASCADE
        ON DELETE RESTRICT

);

-- =====================================================
-- TABEL PENGATURAN KOP
-- =====================================================

CREATE TABLE pengaturan_kop (

    id_pengaturan INT AUTO_INCREMENT PRIMARY KEY,

    id_background INT DEFAULT NULL,

    margin_atas DECIMAL(5,2) DEFAULT 20,

    margin_kiri DECIMAL(5,2) DEFAULT 20,

    margin_bawah DECIMAL(5,2) DEFAULT 20,

    margin_kanan DECIMAL(5,2) DEFAULT 20,

    ruang_aman_kop DECIMAL(5,2) DEFAULT NULL,

    diperbarui_pada TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        ON UPDATE CURRENT_TIMESTAMP,

    CONSTRAINT fk_background
        FOREIGN KEY (id_background)
        REFERENCES file_cloudinary(id_file)
        ON UPDATE CASCADE
        ON DELETE SET NULL

);
-- =====================================================
-- TABEL PENOMORAN DOKUMEN
-- =====================================================

CREATE TABLE dokumen_surat (

    id_dokumen INT AUTO_INCREMENT PRIMARY KEY,

    id_pengajuan INT NOT NULL UNIQUE,

    nomor_urut INT NOT NULL,

    nomor_dokumen VARCHAR(100) NOT NULL UNIQUE,

    tanggal_generate TIMESTAMP DEFAULT CURRENT_TIMESTAMP,

    jenis_dokumen ENUM('Hard File','TTD Digital') NOT NULL,

    CONSTRAINT fk_dokumen_pengajuan
        FOREIGN KEY (id_pengajuan)
        REFERENCES pengajuan_observasi(id_pengajuan)
        ON UPDATE CASCADE
        ON DELETE CASCADE

);


SELECT
    id_pengajuan,
    nama_mahasiswa,
    email
FROM pengajuan_observasi
ORDER BY id_pengajuan DESC;
