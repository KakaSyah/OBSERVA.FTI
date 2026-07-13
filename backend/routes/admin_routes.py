from flask import Blueprint

from backend.controllers import admin_controller as controller
from backend.middlewares.auth_middleware import role_required
from backend.models.role import Role

admin_bp = Blueprint("admin", __name__, url_prefix="/admin")


@admin_bp.route("/dashboard")
@role_required(Role.ADMIN)
def dashboard():
    return controller.show_dashboard()


@admin_bp.route("/akademik-pengguna", methods=["GET", "POST"])
@role_required(Role.ADMIN)
def akademik_pengguna():
    return controller.show_academic_users()


@admin_bp.route("/akademik-pengguna/akun/<string:role>/<int:account_id>/hapus", methods=["POST"])
@role_required(Role.ADMIN)
def akademik_pengguna_account_delete(role, account_id):
    return controller.delete_academic_account(role, account_id)


@admin_bp.route("/akademik-pengguna/ttd/<string:role>/<int:account_id>/hapus", methods=["POST"])
@role_required(Role.ADMIN)
def akademik_pengguna_signature_delete(role, account_id):
    return controller.delete_academic_signature(role, account_id)


@admin_bp.route("/akademik-pengguna/prodi/<int:program_id>/hapus", methods=["POST"])
@role_required(Role.ADMIN)
def akademik_pengguna_program_delete(program_id):
    return controller.delete_academic_program(program_id)


@admin_bp.route("/kop-surat", methods=["GET"])
@role_required(Role.ADMIN)
def kop_surat():
    return controller.show_letterhead_page()


@admin_bp.route("/kop-surat/<string:file_type>/unggah", methods=["POST"])
@role_required(Role.ADMIN)
def kop_surat_upload(file_type):
    return controller.upload_letterhead(file_type)


@admin_bp.route("/kop-surat/<int:file_id>/hapus", methods=["POST"])
@role_required(Role.ADMIN)
def kop_surat_delete(file_id):
    return controller.delete_letterhead(file_id)


@admin_bp.route("/template-surat", methods=["GET"])
@role_required(Role.ADMIN)
def template_surat_list():
    return controller.list_letter_templates()


@admin_bp.route("/template-surat/tambah", methods=["GET", "POST"])
@role_required(Role.ADMIN)
def template_surat_create():
    return controller.create_letter_template()


@admin_bp.route("/template-surat/<int:template_id>/edit", methods=["GET", "POST"])
@role_required(Role.ADMIN)
def template_surat_edit(template_id):
    return controller.edit_letter_template(template_id)


@admin_bp.route("/template-surat/<int:template_id>/hapus", methods=["POST"])
@role_required(Role.ADMIN)
def template_surat_delete(template_id):
    return controller.delete_letter_template(template_id)


@admin_bp.route("/setting-margin", methods=["GET", "POST"])
@role_required(Role.ADMIN)
def setting_margin():
    return controller.show_margin_setting()


@admin_bp.route("/template-email", methods=["GET"])
@role_required(Role.ADMIN)
def template_email_list():
    return controller.list_email_templates()


@admin_bp.route("/template-email/<string:type_key>/edit", methods=["GET", "POST"])
@role_required(Role.ADMIN)
def template_email_edit(type_key):
    return controller.edit_email_template(type_key)


@admin_bp.route("/template-email/<string:type_key>/reset", methods=["POST"])
@role_required(Role.ADMIN)
def template_email_reset(type_key):
    return controller.reset_email_template(type_key)


@admin_bp.route("/riwayat-pengajuan", methods=["GET"])
@role_required(Role.ADMIN)
def riwayat_pengajuan():
    return controller.list_submission_history()


@admin_bp.route("/riwayat-pengajuan/bulk-delete", methods=["POST"])
@role_required(Role.ADMIN)
def riwayat_pengajuan_bulk_delete():
    return controller.bulk_delete_submission_history()


@admin_bp.route("/profil", methods=["GET", "POST"])
@role_required(Role.ADMIN)
def profil():
    return controller.profile()
