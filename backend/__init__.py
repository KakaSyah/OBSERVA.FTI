"""
backend/__init__.py

Application Factory Flask.
Seluruh inisialisasi (config, extensions, blueprint, logging, error
handler) dikumpulkan di sini agar mudah ditelusuri dan dites.

Struktur proyek (Tahap 15 - rapikan struktur): kode backend (Python)
tinggal di paket `backend/`, sementara seluruh aset frontend (template
Jinja & file static CSS/JS/gambar) dipindah ke folder `frontend/` di
root proyek agar pemisahan tanggung jawab lebih jelas. Karena itu,
`template_folder` & `static_folder` bawaan Flask (yang defaultnya
relatif ke paket ini) di-override secara eksplisit di bawah.
"""

import os
import secrets

from flask import Flask, redirect, url_for
from flask_login import current_user
from werkzeug.middleware.proxy_fix import ProxyFix

from backend.config import get_config
from backend.extensions import db, login_manager, session_ext, csrf, limiter, bcrypt
from backend.routes import ALL_BLUEPRINTS
from backend.middlewares.error_handler import register_error_handlers
from backend.middlewares.security_headers import register_security_headers
from backend.middlewares.auth_middleware import dashboard_endpoint_for
from backend.utils.logger import init_logging
from backend.utils.formatters import format_tanggal_indonesia, status_badge_class
from backend.services.cloudinary_service import init_cloudinary
from backend.services.email_service import init_resend
from backend.cli import register_cli_commands


def _reset_auth_state_on_start(app):
    """Paksa browser memulai sesi baru setiap proses aplikasi dinyalakan."""
    if not app.config.get("RESET_AUTH_ON_START", True):
        return

    boot_id = secrets.token_hex(4)
    app.config["SESSION_COOKIE_NAME"] = f"{app.config['SESSION_COOKIE_NAME']}_{boot_id}"
    app.config["REMEMBER_COOKIE_NAME"] = f"{app.config.get('REMEMBER_COOKIE_NAME', 'remember_token')}_{boot_id}"

    session_cache = app.config.get("SESSION_CACHELIB")
    if session_cache is not None and hasattr(session_cache, "clear"):
        session_cache.clear()


def create_app(config_object=None):
    """
    Factory utama pembuat instance Flask.

    Args:
        config_object: kelas konfigurasi opsional (untuk kebutuhan testing).
                        Jika None, akan dipilih otomatis via get_config().
    """
    # Root proyek = satu level di atas paket backend/ (.. dari file ini).
    project_root = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
    app = Flask(
        __name__,
        template_folder=os.path.join(project_root, "frontend", "templates"),
        static_folder=os.path.join(project_root, "frontend", "static"),
    )

    # 1. Konfigurasi
    app.config.from_object(config_object or get_config())
    _reset_auth_state_on_start(app)

    print("=" * 80)
    print("PROJECT ROOT :", project_root)
    print("MAX CONTENT :", app.config["MAX_CONTENT_LENGTH"])
    print("=" * 80)
    # 2. Logging (harus paling awal agar error inisialisasi berikutnya tercatat)
    init_logging(app)

    # 2b. ProxyFix (Tahap 13): saat deploy production di belakang reverse
    #     proxy (Nginx/Load Balancer), Werkzeug secara default membaca
    #     `request.remote_addr` dari koneksi TCP proxy itu sendiri (bukan
    #     IP klien asli) -- membuat rate limiting login (FR-03) dan
    #     activity_log (FR-53/55) mencatat IP yang salah. `TRUSTED_PROXY_COUNT`
    #     (default 0 = nonaktif) diset ke jumlah reverse proxy tepercaya di
    #     depan aplikasi agar hanya header X-Forwarded-* dari proxy yang
    #     dipercaya yang dipakai (mencegah spoofing IP oleh klien).
    trusted_proxy_count = app.config.get("TRUSTED_PROXY_COUNT", 0)
    if trusted_proxy_count > 0:
        app.wsgi_app = ProxyFix(
            app.wsgi_app,
            x_for=trusted_proxy_count,
            x_proto=trusted_proxy_count,
            x_host=trusted_proxy_count,
        )

    # 3. Extensions
    db.init_app(app)

    # Models are imported lazily by controllers/routes as needed.
    login_manager.init_app(app)

    # Flask-Session: keep using default session backend (filesystem or redis).
    # Di environment serverless (Vercel dkk), filesystem tidak bisa dipakai
    # (lihat backend/config/base.py -- SESSION_TYPE sengaja None di sana),
    # jadi session_ext TIDAK di-init_app() sama sekali di situ, dan Flask
    # otomatis jatuh kembali ke session cookie bawaannya sendiri.
    if not app.config.get("IS_SERVERLESS"):
        session_ext.init_app(app)
    csrf.init_app(app)
    limiter.init_app(app)
    bcrypt.init_app(app)

    # 4. Integrasi pihak ketiga (Cloudinary & Resend)
    init_cloudinary(app)
    init_resend(app)

    # 5. Blueprint (routing)
    for blueprint in ALL_BLUEPRINTS:
        app.register_blueprint(blueprint)

    # 5b. Jinja filter kustom untuk tampilan (tanggal Indonesia, badge status)
    #     dipakai lintas modul mahasiswa/dosen/kaprodi mulai Tahap 5.
    app.jinja_env.filters["tanggal_id"] = format_tanggal_indonesia
    app.jinja_env.filters["status_badge"] = status_badge_class

    # 6. Error handler global
    register_error_handlers(app)

    # 6b. Header keamanan HTTP (Tahap 13) pada seluruh response
    register_security_headers(app)

    # 7. Perintah Flask CLI kustom (seed role, buat akun admin pertama)
    register_cli_commands(app)

    # 8. Health-check endpoint sederhana untuk verifikasi deployment
    @app.get("/health")
    def health_check():
        return {"status": "ok", "app": app.config.get("APP_NAME")}, 200

    # 9. Halaman root: selalu arahkan ke halaman login.
    @app.route("/")
    def index():
        return redirect(url_for("auth.login"))

    app.logger.info("Aplikasi '%s' berhasil diinisialisasi.", app.config.get("APP_NAME"))
    return app
