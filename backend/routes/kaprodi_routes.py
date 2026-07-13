"""
backend/routes/kaprodi_routes.py

Blueprint modul Kaprodi (Tahap 7): FR-30..FR-34 / UC-14..UC-19.
Route di sini sengaja tetap tipis (hanya routing + pemetaan HTTP method);
seluruh logic didelegasikan ke app.controllers.kaprodi_controller, yang lalu
memanggil app.services.observation_service untuk akses data — sesuai pola
routes -> controllers -> services pada Tahap 1 bagian 9 (sama seperti
`dosen_routes.py` pada Tahap 6).
"""

from flask import Blueprint

from backend.controllers import kaprodi_controller as controller
from backend.middlewares.auth_middleware import role_required
from backend.models.role import Role

kaprodi_bp = Blueprint("kaprodi", __name__, url_prefix="/kaprodi")


@kaprodi_bp.route("/dashboard")
@role_required(Role.KAPRODI)
def dashboard():
    return controller.show_dashboard()


@kaprodi_bp.route("/daftar-persetujuan", methods=["GET"])
@role_required(Role.KAPRODI)
def daftar_persetujuan():
    """FR-30 / UC-15: daftar surat yang menunggu persetujuan akhir kaprodi ini."""
    return controller.list_incoming()


@kaprodi_bp.route("/daftar-persetujuan/<int:request_id>", methods=["GET"])
@role_required(Role.KAPRODI)
def detail_persetujuan(request_id):
    return controller.show_detail(request_id)


@kaprodi_bp.route("/daftar-persetujuan/<int:request_id>/setujui", methods=["POST"])
@role_required(Role.KAPRODI)
def setujui_surat(request_id):
    """FR-31/FR-32 (UC-16): setujui pengajuan sebagai persetujuan akhir."""
    return controller.approve_request(request_id)


@kaprodi_bp.route("/upload-final-pdf/<int:request_id>/sign", methods=["POST"])
@role_required(Role.KAPRODI)
def sign_final_pdf_upload(request_id):
    """Buat signed upload params agar browser bisa mengunggah PDF final langsung ke Cloudinary."""
    return controller.sign_final_pdf_upload(request_id)


@kaprodi_bp.route("/upload-final-pdf/<int:request_id>", methods=["POST"])
@role_required(Role.KAPRODI)
def upload_final_pdf(request_id):
    """Terima referensi hasil upload Cloudinary (JSON), bukan file PDF mentah lagi."""
    return controller.upload_final_pdf(request_id)


@kaprodi_bp.route("/daftar-persetujuan/<int:request_id>/tolak", methods=["POST"])
@role_required(Role.KAPRODI)
def tolak_surat(request_id):
    """FR-31/FR-33 (UC-17): tolak pengajuan (+catatan opsional)."""
    return controller.reject_request(request_id)


@kaprodi_bp.route("/riwayat", methods=["GET"])
@role_required(Role.KAPRODI)
def riwayat():
    """FR-34 / UC-18: riwayat persetujuan yang pernah dilakukan kaprodi ini."""
    return controller.list_approval_history()


@kaprodi_bp.route("/profil", methods=["GET", "POST"])
@role_required(Role.KAPRODI)
def profil():
    """FR-05 / UC-19: lihat & perbarui profil kaprodi."""
    return controller.profile()
