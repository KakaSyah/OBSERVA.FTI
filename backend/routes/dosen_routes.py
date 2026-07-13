"""
backend/routes/dosen_routes.py

Blueprint modul Dosen (Tahap 6): FR-20..FR-24 / UC-08..UC-13.
Route di sini sengaja tetap tipis (hanya routing + pemetaan HTTP method);
seluruh logic didelegasikan ke app.controllers.dosen_controller, yang lalu
memanggil app.services.observation_service untuk akses data — sesuai pola
routes -> controllers -> services pada Tahap 1 bagian 9 (sama seperti
`mahasiswa_routes.py` pada Tahap 5).
"""

from flask import Blueprint

from backend.controllers import dosen_controller as controller
from backend.middlewares.auth_middleware import role_required
from backend.models.role import Role

dosen_bp = Blueprint("dosen", __name__, url_prefix="/dosen")


@dosen_bp.route("/dashboard")
@role_required(Role.DOSEN)
def dashboard():
    return controller.show_dashboard()


@dosen_bp.route("/surat-masuk", methods=["GET"])
@role_required(Role.DOSEN)
def surat_masuk():
    """FR-20 / UC-09: daftar surat masuk yang menunggu persetujuan dosen ini."""
    return controller.list_incoming()


@dosen_bp.route("/surat-masuk/<int:request_id>", methods=["GET"])
@role_required(Role.DOSEN)
def detail_surat_masuk(request_id):
    return controller.show_detail(request_id)


@dosen_bp.route("/surat-masuk/<int:request_id>/setujui", methods=["POST"])
@role_required(Role.DOSEN)
def setujui_surat(request_id):
    """FR-21/FR-22 (UC-10): setujui pengajuan, diteruskan ke Kaprodi."""
    return controller.approve_request(request_id)


@dosen_bp.route("/surat-masuk/<int:request_id>/tolak", methods=["POST"])
@role_required(Role.DOSEN)
def tolak_surat(request_id):
    """FR-21/FR-23 (UC-11): tolak pengajuan (+catatan opsional)."""
    return controller.reject_request(request_id)


@dosen_bp.route("/riwayat-persetujuan", methods=["GET"])
@role_required(Role.DOSEN)
def riwayat_persetujuan():
    """FR-24 / UC-12: riwayat persetujuan yang pernah dilakukan dosen ini."""
    return controller.list_approval_history()


@dosen_bp.route("/profil", methods=["GET", "POST"])
@role_required(Role.DOSEN)
def profil():
    """FR-05 / UC-13: lihat & perbarui profil dosen."""
    return controller.profile()
