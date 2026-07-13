"""
backend/routes/mahasiswa_routes.py

Blueprint modul Mahasiswa. Sejak Tahap 14, alur ini berjalan dalam mode
KIOSK: satu akun login dipakai bersama (lihat `flask create-kiosk-mahasiswa`
di app/cli.py), dan navigasinya sengaja disederhanakan menjadi dua halaman:

    /mahasiswa/welcome        -> layar sambutan, tombol "Mulai Isi Form"
    /mahasiswa/ajukan-surat   -> satu-satunya form (FR-10..FR-12): isi data,
                                  lalu "Cetak Hardfile" (draft PDF, tetap di
                                  halaman ini) atau "Kirim TTD Digital"
                                  (submit ke dosen, lalu kembali ke Welcome).

Route lama berbasis request_id (riwayat/detail/edit/cetak-draft/kirim/
download/profil, Tahap 5) dihapus dari alur utama kiosk ini -- lihat
catatan di app/controllers/mahasiswa_controller.py.
"""

from flask import Blueprint

from backend.controllers import mahasiswa_controller as controller
from backend.middlewares.auth_middleware import role_required
from backend.models.role import Role

mahasiswa_bp = Blueprint("mahasiswa", __name__, url_prefix="/mahasiswa")


@mahasiswa_bp.route("/welcome")
@role_required(Role.MAHASISWA)
def welcome():
    """Layar sambutan kiosk: satu-satunya pintu masuk setelah login."""
    return controller.show_welcome()


@mahasiswa_bp.route("/ajukan-surat", methods=["GET", "POST"])
@role_required(Role.MAHASISWA)
def ajukan_surat():
    """FR-10..FR-12: isi form, cetak draft, dan/atau kirim ke dosen (satu halaman)."""
    return controller.new_observation_request()
