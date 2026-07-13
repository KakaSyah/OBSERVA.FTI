"""
backend/utils/logger.py

Konfigurasi logging aplikasi ke file (dan console saat development).
Log aktivitas domain (login, approval, dsb.) dicatat terpisah ke tabel
activity_logs melalui app/services/activity_log_service.py (Tahap 12);
logger ini khusus untuk log teknis aplikasi/error.

Tahap 13 (Hardening & Logging Aplikasi) menambahkan dua hal di atas
fondasi Tahap 2:
- `_RequestContextFilter` menyisipkan alamat IP, endpoint, dan user yang
  sedang login (jika ada) ke SETIAP baris log teknis, tanpa perlu
  menuliskannya manual di setiap pemanggilan `app.logger.xxx(...)` --
  penting untuk investigasi insiden keamanan (mis. menelusuri IP di balik
  serangkaian percobaan login gagal).
- File log KEDUA (`error.log`) berisi HANYA level WARNING ke atas,
  terpisah dari `app.log` (yang mencatat semua level >= LOG_LEVEL) --
  memudahkan operator memantau kondisi darurat tanpa harus menyaring log
  informasi rutin.
"""

import logging
import os
from logging.handlers import RotatingFileHandler

from flask import has_request_context, request


class _RequestContextFilter(logging.Filter):
    """Menyisipkan atribut `ip`, `endpoint`, dan `user` ke setiap LogRecord
    bila dipanggil dalam konteks request HTTP aktif; nilai default aman
    (mis. saat logging terjadi di luar request, seperti CLI/startup).

    `current_user` (flask_login) diimpor DI DALAM method, bukan di level
    modul, untuk menghindari import silang saat `login_manager` belum
    ter-init sepenuhnya pada tahap awal `create_app()`.
    """

    def filter(self, record: logging.LogRecord) -> bool:
        if has_request_context():
            record.ip = request.remote_addr or "-"
            record.endpoint = request.endpoint or request.path
            try:
                from flask_login import current_user

                record.user = (
                    current_user.email
                    if getattr(current_user, "is_authenticated", False)
                    else "anonim"
                )
            except Exception:  # noqa: BLE001 - logging TIDAK BOLEH ikut gagal karena ini
                record.user = "-"
        else:
            record.ip = "-"
            record.endpoint = "-"
            record.user = "-"
        return True


def init_logging(app):
    """Inisialisasi logging aplikasi berdasarkan konfigurasi di .env."""
    log_level = getattr(logging, app.config.get("LOG_LEVEL", "INFO").upper(), logging.INFO)
    formatter = logging.Formatter(
        "[%(asctime)s] %(levelname)s in %(module)s "
        "(ip=%(ip)s user=%(user)s endpoint=%(endpoint)s): %(message)s"
    )
    context_filter = _RequestContextFilter()

    # Platform serverless (Vercel, AWS Lambda, dll) punya filesystem READ-ONLY
    # di luar /tmp, dan tiap invocation bisa berjalan di container baru --
    # RotatingFileHandler akan selalu gagal (OSError: Read-only file system)
    # dan MEMATIKAN seluruh aplikasi karena dipanggil sebelum app siap
    # menerima request. Di environment ini, log cukup ditulis ke stdout/stderr
    # -- otomatis tertangkap oleh dashboard log platform tsb (mis. Vercel
    # "Logs"/"Functions" tab), tanpa perlu menulis file sama sekali.
    is_serverless = bool(os.environ.get("VERCEL") or os.environ.get("AWS_LAMBDA_FUNCTION_NAME"))

    if is_serverless:
        stream_handler = logging.StreamHandler()
        stream_handler.setFormatter(formatter)
        stream_handler.setLevel(log_level)
        stream_handler.addFilter(context_filter)
        app.logger.setLevel(log_level)
        app.logger.addHandler(stream_handler)
        app.logger.info(
            "Logging berhasil diinisialisasi ke stdout (mode serverless terdeteksi)."
        )
        return

    log_dir = app.config.get("LOG_DIR", "logs")
    log_file_name = app.config.get("LOG_FILE_NAME", "app.log")

    os.makedirs(log_dir, exist_ok=True)
    log_path = os.path.join(log_dir, log_file_name)
    error_log_path = os.path.join(log_dir, "error.log")

    # Log utama: seluruh level >= LOG_LEVEL (default INFO), rotasi 5MB x 5 file.
    file_handler = RotatingFileHandler(
        log_path, maxBytes=5 * 1024 * 1024, backupCount=5, encoding="utf-8"
    )
    file_handler.setFormatter(formatter)
    file_handler.setLevel(log_level)
    file_handler.addFilter(context_filter)

    # Log error terpisah: hanya WARNING ke atas, agar mudah dipantau operator
    # tanpa terpecah oleh log INFO rutin (mis. dipakai `tail -f logs/error.log`).
    error_handler = RotatingFileHandler(
        error_log_path, maxBytes=5 * 1024 * 1024, backupCount=5, encoding="utf-8"
    )
    error_handler.setFormatter(formatter)
    error_handler.setLevel(logging.WARNING)
    error_handler.addFilter(context_filter)

    app.logger.setLevel(log_level)
    app.logger.addHandler(file_handler)
    app.logger.addHandler(error_handler)

    if app.config.get("DEBUG"):
        console_handler = logging.StreamHandler()
        console_handler.setFormatter(formatter)
        console_handler.addFilter(context_filter)
        app.logger.addHandler(console_handler)

    app.logger.info("Logging berhasil diinisialisasi (level=%s).", app.config.get("LOG_LEVEL"))
