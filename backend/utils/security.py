"""
backend/utils/security.py

Helper keamanan untuk modul autentikasi (Tahap 4):
- Hashing & verifikasi password memakai Bcrypt (NFR Security, Tahap 1 bagian 4).
- Validasi URL redirect ("next") agar terhindar dari celah open-redirect
  saat pengguna diarahkan kembali setelah login.
"""

from urllib.parse import urljoin, urlparse

from flask import request

from backend.extensions import bcrypt


def hash_password(raw_password: str) -> str:
    """Meng-hash password mentah menjadi string hash Bcrypt yang aman disimpan di kolom password_hash."""
    return bcrypt.generate_password_hash(raw_password).decode("utf-8")


def verify_password(raw_password: str, password_hash: str) -> bool:
    """Memverifikasi password mentah terhadap hash Bcrypt yang tersimpan di database."""
    if not raw_password or not password_hash:
        return False
    return bcrypt.check_password_hash(password_hash, raw_password)


def is_safe_redirect_url(target: str) -> bool:
    """
    Memastikan URL redirect (parameter query `next`) tetap berada pada host
    yang sama dengan aplikasi, untuk mencegah open-redirect setelah login.
    """
    if not target:
        return False
    host_url = urlparse(request.host_url)
    redirect_url = urlparse(urljoin(request.host_url, target))
    return (
        redirect_url.scheme in ("http", "https")
        and host_url.netloc == redirect_url.netloc
    )
