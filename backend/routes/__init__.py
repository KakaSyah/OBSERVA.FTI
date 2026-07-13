"""
backend/routes/__init__.py

Mengumpulkan seluruh blueprint agar mudah didaftarkan di app factory.
"""

from backend.routes.auth_routes import auth_bp
from backend.routes.mahasiswa_routes import mahasiswa_bp
from backend.routes.dosen_routes import dosen_bp
from backend.routes.kaprodi_routes import kaprodi_bp
from backend.routes.admin_routes import admin_bp

# Daftar blueprint siap didaftarkan lewat app.register_blueprint()
ALL_BLUEPRINTS = (
    auth_bp,
    mahasiswa_bp,
    dosen_bp,
    kaprodi_bp,
    admin_bp,
)
