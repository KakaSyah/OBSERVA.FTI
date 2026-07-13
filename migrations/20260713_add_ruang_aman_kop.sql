-- Jalankan sekali pada database yang sudah ada sebelum deploy aplikasi.
ALTER TABLE `pengaturan_kop`
    ADD COLUMN `ruang_aman_kop` DECIMAL(5,2) NULL DEFAULT NULL AFTER `margin_kanan`;
