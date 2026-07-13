"""
backend/config/base.py

Konfigurasi dasar aplikasi. Seluruh nilai WAJIB diambil dari environment
variable (.env), tidak boleh ada nilai sensitif yang di-hardcode di sini.
"""

import os
from datetime import timedelta
from urllib.parse import quote_plus

from cachelib import FileSystemCache
from dotenv import load_dotenv

# Muat file .env dari root project sebelum konfigurasi dibaca.
load_dotenv()


def _get_bool(key: str, default: bool = False) -> bool:
    """Konversi nilai environment variable string menjadi boolean."""
    value = os.getenv(key)
    if value is None:
        return default
    return value.strip().lower() in {"1", "true", "yes", "on"}


def _get_int(key: str, default: int) -> int:
    """Konversi nilai environment variable string menjadi integer dengan aman."""
    value = os.getenv(key)
    if value is None or value == "":
        return default
    try:
        return int(value)
    except ValueError:
        return default


def _get_list(key: str, default: list | None = None) -> list:
    """Konversi environment variable berformat 'a,b,c' menjadi list."""
    value = os.getenv(key)
    if not value:
        return default or []
    return [item.strip() for item in value.split(",") if item.strip()]


class BaseConfig:
    """Konfigurasi bersama untuk seluruh environment (dev/prod)."""

    # ---------- APPLICATION ----------
    APP_NAME = os.getenv("APP_NAME", "Sistem Pengajuan Surat Izin Observasi")
    APP_URL = os.getenv("APP_URL", "http://localhost:5000")
    SECRET_KEY = os.getenv("SECRET_KEY")
    DEBUG = _get_bool("DEBUG", False)

    if not SECRET_KEY:
        raise RuntimeError(
            "SECRET_KEY belum diset di environment variable (.env). "
            "Aplikasi tidak boleh berjalan tanpa SECRET_KEY."
        )

    # ---------- DATABASE (TiDB / MySQL via raw connector) ----------
    DATABASE_URL = os.getenv("DATABASE_URL")
    if not DATABASE_URL:
        db_host = os.getenv("DB_HOST")
        db_port = os.getenv("DB_PORT", "4000")
        db_username = os.getenv("DB_USERNAME")
        db_password = os.getenv("DB_PASSWORD")
        db_database = os.getenv("DB_DATABASE")

        if db_host and db_username and db_password and db_database:
            encoded_password = quote_plus(db_password)
            DATABASE_URL = (
                f"mysql://{db_username}:{encoded_password}@"
                f"{db_host}:{db_port}/{db_database}"
                f"?ssl_verify_cert=true&ssl_verify_identity=true"
            )

    if not DATABASE_URL:
        raise RuntimeError(
            "DATABASE_URL belum diset di environment variable (.env)."
        )

    # ---------- SESSION ----------
    # Gunakan backend filesystem agar Flask-Session tidak mencoba membuat
    # interface penyimpanan session khusus ORM.
    #
    # Di platform serverless (Vercel dkk), filesystem read-only di luar /tmp
    # dan tidak persisten antar-invocation, jadi Flask-Session berbasis file
    # TIDAK BISA dipakai (lihat backend/__init__.py::create_app, session_ext
    # hanya di-init_app() bila IS_SERVERLESS bernilai False). Di environment
    # itu, Flask otomatis jatuh kembali ke session cookie bawaan miliknya
    # sendiri (ditandatangani SECRET_KEY, disimpan di browser, tidak butuh
    # penyimpanan di server) -- cukup untuk data session yang kecil (id user
    # login, flag, dsb) yang dipakai aplikasi ini.
    IS_SERVERLESS = bool(os.getenv("VERCEL") or os.getenv("AWS_LAMBDA_FUNCTION_NAME"))

    if IS_SERVERLESS:
        SESSION_TYPE = None
        SESSION_CACHELIB = None
    else:
        SESSION_TYPE = "cachelib"
        SESSION_FILE_DIR = os.getenv("SESSION_FILE_DIR", os.path.join(os.getcwd(), ".flask_session"))
        SESSION_CACHELIB = FileSystemCache(cache_dir=SESSION_FILE_DIR, threshold=500)
    SESSION_PERMANENT = _get_bool("SESSION_PERMANENT", False)
    SESSION_COOKIE_NAME = os.getenv("SESSION_COOKIE_NAME", "izin_observasi_session")
    SESSION_COOKIE_SECURE = _get_bool("SESSION_COOKIE_SECURE", True)
    SESSION_COOKIE_HTTPONLY = _get_bool("SESSION_COOKIE_HTTPONLY", True)
    SESSION_COOKIE_SAMESITE = os.getenv("SESSION_COOKIE_SAMESITE", "Lax")
    PERMANENT_SESSION_LIFETIME = timedelta(
        minutes=_get_int("PERMANENT_SESSION_LIFETIME_MINUTES", 60)
    )
    SESSION_SECRET = os.getenv("SESSION_SECRET", SECRET_KEY)
    RESET_AUTH_ON_START = _get_bool("RESET_AUTH_ON_START", True)
    REMEMBER_COOKIE_NAME = os.getenv("REMEMBER_COOKIE_NAME", "izin_observasi_remember")

    # ---------- CLOUDINARY ----------
    CLOUDINARY_CLOUD_NAME = os.getenv("CLOUDINARY_CLOUD_NAME")
    CLOUDINARY_API_KEY = os.getenv("CLOUDINARY_API_KEY")
    CLOUDINARY_API_SECRET = os.getenv("CLOUDINARY_API_SECRET")
    CLOUDINARY_UPLOAD_FOLDER = os.getenv(
        "CLOUDINARY_UPLOAD_FOLDER", "sistem-izin-observasi"
    )
    CLOUDINARY_SECURE = _get_bool("CLOUDINARY_SECURE", True)

    # ---------- RESEND (EMAIL) ----------
    RESEND_API_KEY = os.getenv("RESEND_API_KEY")
    RESEND_SENDER_EMAIL = os.getenv("RESEND_SENDER_EMAIL")
    RESEND_SENDER_NAME = os.getenv("RESEND_SENDER_NAME", "Sistem Izin Observasi")
    # Retry sederhana (NFR Reliability, Tahap 1 bagian 4) — jumlah percobaan
    # total (termasuk percobaan pertama) sebelum email_log ditandai 'failed'.
    EMAIL_MAX_ATTEMPTS = _get_int("EMAIL_MAX_ATTEMPTS", 2)

    # ---------- SURAT RESMI (letter_number_service & pdf_service, Tahap 8) ----------
    # Kode fakultas dipakai pada format nomor surat FR-50:
    # "{urutan}/{kode_fakultas}/OBS/{bulan_romawi}/{tahun}".
    # Nama & alamat universitas dipakai sebagai teks kop surat fallback pada
    # pdf_service selama Admin belum mengunggah kop surat resmi (Tahap 10).
    FACULTY_CODE = os.getenv("FACULTY_CODE", "FAK")
    UNIVERSITY_NAME = os.getenv("UNIVERSITY_NAME", "Universitas Contoh")
    UNIVERSITY_ADDRESS = os.getenv(
        "UNIVERSITY_ADDRESS", "Jl. Contoh Pendidikan No. 1, Kota Contoh"
    )

    # ---------- RATE LIMIT ----------
    RATELIMIT_STORAGE_URI = os.getenv("RATELIMIT_STORAGE_URI", "memory://")

    # ---------- REVERSE PROXY (Tahap 13) ----------
    # Jumlah reverse proxy tepercaya di depan aplikasi (mis. 1 jika hanya
    # Nginx). 0 (default) berarti aplikasi diakses langsung tanpa proxy,
    # sehingga header X-Forwarded-* DIABAIKAN (tidak dipercaya begitu saja)
    # -- lihat app/__init__.py::create_app (ProxyFix).
    TRUSTED_PROXY_COUNT = _get_int("TRUSTED_PROXY_COUNT", 0)

    # ---------- UPLOAD ----------
    MAX_CONTENT_LENGTH = _get_int("MAX_CONTENT_LENGTH_MB", 50) * 1024 * 1024
    ALLOWED_UPLOAD_EXTENSIONS = set(
        _get_list("ALLOWED_UPLOAD_EXTENSIONS", ["pdf", "png", "jpg", "jpeg", "docx"])
    )
    UPLOAD_TEMP_DIR = os.path.join(os.getcwd(), "uploads")
    # Batas ukuran PER FILE (Tahap 13) -- berbeda dari MAX_CONTENT_LENGTH di
    # atas yang membatasi ukuran TOTAL satu request HTTP. Dipakai
    # app/services/admin_service.py saat validasi isi file (app/utils/uploads.py).
    UPLOAD_MAX_IMAGE_SIZE_MB = _get_int("UPLOAD_MAX_IMAGE_SIZE_MB", 5)
    UPLOAD_MAX_TEMPLATE_SIZE_MB = _get_int("UPLOAD_MAX_TEMPLATE_SIZE_MB", 10)

    # ---------- LOGGING ----------
    LOG_LEVEL = os.getenv("LOG_LEVEL", "INFO")
    LOG_DIR = os.getenv("LOG_DIR", "logs")
    LOG_FILE_NAME = os.getenv("LOG_FILE_NAME", "app.log")

    # ---------- WTF / CSRF ----------
    WTF_CSRF_ENABLED = True
    WTF_CSRF_TIME_LIMIT = None  # tidak expired selama session masih valid
