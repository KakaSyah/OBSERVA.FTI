"""
backend/middlewares/error_handler.py

Registrasi error handler global agar seluruh error dikembalikan dalam
bentuk halaman/response yang konsisten dan tidak membocorkan detail
internal aplikasi (stack trace, query SQL, dsb.) ke pengguna.

Tahap 12: error 403 (akses ditolak), 429 (rate limit) dan 500 (kesalahan
server) juga dicatat ke tabel `activity_logs` (`ActivityLog.ACTION_ERROR`)
lewat `activity_log_service.log_error`, selain tetap dicatat ke
`app.logger` seperti sebelumnya -- keduanya berguna untuk keperluan audit
berbeda (`app.logger` untuk debugging teknis dgn stack trace, activity_log
    untuk ringkasan audit yang bisa difilter Admin). Pencatatan memakai user
    yang sedang login jika ada (anonim -> None).
  lama dibuka lagi setelah lama tidak aktif, atau percobaan pemalsuan
  request lintas situs). Ditangani TERPISAH dari 400 generik agar pesan ke
  pengguna lebih jelas ("sesi kedaluwarsa, coba lagi") dan tetap tercatat
  sebagai `error` untuk audit.
- 413 Payload Too Large -- request melebihi `MAX_CONTENT_LENGTH`
  (app/config/base.py), umumnya saat upload file kop surat/template
  (FR-41/FR-42) melebihi batas.
- 400 generik -- jaring pengaman untuk request malformed lain (body JSON
  rusak, dsb.) yang bukan CSRFError.
"""

from flask import render_template, request, jsonify
from flask_login import current_user
from flask_wtf.csrf import CSRFError

from backend.services import activity_log_service


def _actor():
    """User yang sedang login untuk dilampirkan ke activity_log, atau None
    jika request datang dari pengguna anonim (mis. akses tanpa login)."""
    return current_user if getattr(current_user, "is_authenticated", False) else None


def register_error_handlers(app):
    """Mendaftarkan handler untuk error 400 (termasuk CSRFError), 403, 404, 405, 413, 429, dan 500."""

    def _wants_json() -> bool:
        return request.path.startswith("/api/") or request.is_json

    @app.errorhandler(403)
    def forbidden(error):
        app.logger.warning("403 Forbidden: %s", request.path)
        activity_log_service.log_error(
            f"403 Forbidden: akses ditolak ke '{request.path}'.", user=_actor()
        )
        if _wants_json():
            return jsonify(message="Akses ditolak."), 403
        return render_template("errors/403.html"), 403

    @app.errorhandler(404)
    def not_found(error):
        if _wants_json():
            return jsonify(message="Halaman/endpoint tidak ditemukan."), 404
        return render_template("errors/404.html"), 404

    @app.errorhandler(405)
    def method_not_allowed(error):
        if _wants_json():
            return jsonify(message="Method tidak diizinkan."), 405
        return render_template("errors/404.html"), 405

    @app.errorhandler(CSRFError)
    def csrf_error(error):
        app.logger.warning("CSRF Error: %s pada %s", error.description, request.path)
        activity_log_service.log_error(
            f"CSRF Error pada '{request.path}': {error.description}.", user=_actor()
        )
        message = "Sesi/token keamanan telah kedaluwarsa. Silakan muat ulang halaman dan coba lagi."
        if _wants_json():
            return jsonify(message=message), 400
        return render_template("errors/400.html", message=message), 400

    @app.errorhandler(400)
    def bad_request(error):
        app.logger.warning("400 Bad Request: %s pada %s", error, request.path)
        message = "Permintaan tidak valid."
        if _wants_json():
            return jsonify(message=message), 400
        return render_template("errors/400.html", message=message), 400

    @app.errorhandler(413)
    def payload_too_large(error):
        if request.path.startswith("/kaprodi/upload-final-pdf/"):
            app.logger.warning(
                "413 PDF final: path=%s content_length=%s bytes MAX_CONTENT_LENGTH=%s bytes IP=%s (endpoint ini seharusnya tidak menerima file mentah lagi, kemungkinan regresi frontend).",
                request.path,
                request.content_length,
                app.config.get("MAX_CONTENT_LENGTH"),
                request.remote_addr,
            )
        else:
            app.logger.warning("413 Payload Too Large: %s dari IP=%s", request.path, request.remote_addr)
        message = "Ukuran file/permintaan melebihi batas maksimum yang diizinkan."
        if _wants_json():
            return jsonify(message=message), 413
        return render_template("errors/413.html", message=message), 413

    @app.errorhandler(429)
    def too_many_requests(error):
        app.logger.warning(
            "429 Too Many Requests: %s dari IP=%s", request.path, request.remote_addr
        )
        activity_log_service.log_error(
            f"429 Too Many Requests pada '{request.path}' dari IP={request.remote_addr}.",
            user=_actor(),
        )
        if _wants_json():
            return jsonify(message="Terlalu banyak percobaan. Silakan coba lagi beberapa saat lagi."), 429
        return render_template("errors/429.html"), 429

    @app.errorhandler(500)
    def internal_server_error(error):
        app.logger.error("500 Internal Server Error: %s", error, exc_info=True)
        activity_log_service.log_error(
            f"500 Internal Server Error pada '{request.path}': {error}", user=_actor()
        )
        if _wants_json():
            return jsonify(message="Terjadi kesalahan pada server."), 500
        return render_template("errors/500.html"), 500
