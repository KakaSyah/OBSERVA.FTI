"""
backend/middlewares/security_headers.py

Tahap 13 (Hardening Keamanan) — menambahkan header HTTP keamanan standar
pada SETIAP response, melengkapi proteksi yang sudah ada sejak tahap-tahap
sebelumnya (CSRF sejak Tahap 2, secure cookie sejak Tahap 2/4, rate limit
login sejak Tahap 4). Header ini murni pertahanan sisi browser/klien:

- X-Content-Type-Options: nosniff
    Mencegah browser menebak (sniff) tipe konten di luar Content-Type yang
    dikirim server -- mengurangi risiko file upload disalahgunakan sebagai
    HTML/JS oleh browser korban.
- X-Frame-Options: DENY
    Mencegah halaman aplikasi ditanam di <iframe> situs lain (clickjacking).
- Referrer-Policy: strict-origin-when-cross-origin
    Membatasi informasi URL yang dikirim ke situs lain lewat header Referer.
- Permissions-Policy
    Menonaktifkan akses ke API browser sensitif (kamera, mikrofon, lokasi)
    yang memang tidak dipakai aplikasi ini.
- Content-Security-Policy
    Membatasi sumber skrip/gaya/gambar hanya ke domain sendiri dan CDN
    Bootstrap yang sudah dipakai sejak awal template dasar (lihat
    `app/templates/layouts/base.html`). `'unsafe-inline'` pada script-src
    & style-src TERPAKSA masih diizinkan karena beberapa halaman (mis.
    dashboard, detail surat) memakai <script> inline & atribut
    onclick/onchange untuk interaktivitas ringan (chart, konfirmasi modal)
    -- migrasi penuh ke skrip eksternal + nonce adalah pekerjaan
    styling/refactor templat yang di luar cakupan Tahap 13, dicatat sebagai
    catatan keamanan di README.
- Strict-Transport-Security (HSTS)
    HANYA dikirim saat request datang lewat HTTPS (produksi di balik
    reverse proxy/HTTPS) -- mengirim HSTS di HTTP polos (mis. saat
    development lokal) tidak berguna dan berpotensi salah konfigurasi.
"""

from flask import request


_CSP = (
    "default-src 'self'; "
    "script-src 'self' 'unsafe-inline' https://cdn.jsdelivr.net; "
    "style-src 'self' 'unsafe-inline' https://cdn.jsdelivr.net; "
    "img-src 'self' data: https://res.cloudinary.com; "
    "font-src 'self' https://cdn.jsdelivr.net; "
    "object-src 'none'; "
    "frame-ancestors 'none'; "
    "base-uri 'self'; "
    "form-action 'self'"
)


def register_security_headers(app):
    """Mendaftarkan hook `after_request` yang menambahkan header keamanan
    standar ke seluruh response (halaman HTML maupun JSON API)."""

    @app.after_request
    def _apply_security_headers(response):
        response.headers.setdefault("X-Content-Type-Options", "nosniff")
        response.headers.setdefault("X-Frame-Options", "DENY")
        response.headers.setdefault("Referrer-Policy", "strict-origin-when-cross-origin")
        response.headers.setdefault(
            "Permissions-Policy", "geolocation=(), camera=(), microphone=()"
        )
        response.headers.setdefault("Content-Security-Policy", _CSP)

        if request.is_secure:
            response.headers.setdefault(
                "Strict-Transport-Security", "max-age=31536000; includeSubDomains"
            )

        return response
