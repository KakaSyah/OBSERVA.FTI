"""
backend/controllers/admin_controller.py

Controller modul Admin (Tahap 10) — jembatan antara route (HTTP: request
parsing, flash message, redirect) dan `app.services.admin_service`
(business logic murni), sesuai pola routes -> controllers -> services
yang sama persis dengan modul Mahasiswa/Dosen/Kaprodi (Tahap 5-7).
"""

from flask import abort, current_app, flash, jsonify, redirect, render_template, request, url_for
from flask_login import current_user

from backend.extensions import db
from backend.forms.admin_forms import (
    ActivityLogFilterForm,
    EmailTemplateForm,
    HeadOfProgramForm,
    KioskAccountForm,
    LecturerForm,
    LetterheadUploadForm,
    LetterTemplateForm,
    MarginSettingForm,
    ObservationRequestFilterForm,
    ProfileForm,
    StudentForm,
    StudyProgramForm,
)
from backend.models.cloudinary_file import CloudinaryFile
from backend.models.observation_request import ObservationRequest
from backend.services import admin_service, kop_setting_service


# ======================================================================
# Dashboard (UC-20 lanjutan, FR-46)
# ======================================================================

def show_dashboard():
    summary = admin_service.dashboard_summary()
    summary["margin_setting"] = kop_setting_service.get_active_kop_setting()
    return render_template("admin/dashboard.html", **summary)


def show_academic_users():
    if request.method == "POST":
        form_name = request.form.get("form_name", "")
        try:
            if form_name == "kiosk_account":
                admin_service.save_kiosk_account_new_schema(
                    {
                        "nama": request.form.get("nama"),
                        "username": request.form.get("username"),
                        "password": request.form.get("password"),
                        "status_aktif": request.form.get("status_aktif"),
                    }
                )
                flash("Akun kiosk mahasiswa berhasil disimpan.", "success")
            elif form_name == "academic_create":
                admin_service.create_academic_account_new_schema(
                    {
                        "role": request.form.get("role"),
                        "nama": request.form.get("nama"),
                        "username": request.form.get("username"),
                        "password": request.form.get("password"),
                        "nidn": request.form.get("nidn"),
                        "jenis_dosen": request.form.get("jenis_dosen"),
                        "id_program_studi": request.form.get("id_program_studi"),
                        "status_aktif": request.form.get("status_aktif"),
                    },
                    request.files.get("signature_file"),
                )
                flash("Akun akademik berhasil dibuat.", "success")
            elif form_name == "academic_update":
                admin_service.update_academic_account_new_schema(
                    request.form.get("role"),
                    request.form.get("account_id", type=int),
                    {
                        "nama": request.form.get("nama"),
                        "username": request.form.get("username"),
                        "password": request.form.get("password"),
                        "nidn": request.form.get("nidn"),
                        "jenis_dosen": request.form.get("jenis_dosen"),
                        "id_program_studi": request.form.get("id_program_studi"),
                        "status_aktif": request.form.get("status_aktif"),
                    },
                    request.files.get("signature_file"),
                )
                flash("Akun akademik berhasil diperbarui.", "success")
            elif form_name == "program_create":
                if request.form.get("id_program_studi"):
                    admin_service.assign_program_head_new_schema(
                        {
                            "id_program_studi": request.form.get("id_program_studi"),
                            "id_dosen": request.form.get("id_dosen"),
                        }
                    )
                    flash("Kaprodi berhasil disimpan.", "success")
                else:
                    admin_service.create_program_new_schema(
                        {"nama_program_studi": request.form.get("nama_program_studi")}
                    )
                    flash("Program studi berhasil ditambahkan.", "success")
            else:
                flash("Aksi form tidak dikenal.", "warning")
        except admin_service.AdminServiceError as exc:
            flash(str(exc), "warning")
        except Exception as exc:
            current_app.logger.exception("Gagal memproses Kelola Akademik & Pengguna: %s", exc)
            flash("Data gagal diproses. Periksa relasi database dan coba lagi.", "danger")
        return redirect(url_for("admin.akademik_pengguna"))

    overview = admin_service.academic_user_overview_new_schema()
    return render_template("admin/akademik_pengguna.html", **overview)


def delete_academic_account(role, account_id):
    try:
        admin_service.delete_academic_account_new_schema(role, account_id)
        flash("Akun akademik berhasil dihapus.", "success")
    except admin_service.AdminServiceError as exc:
        flash(str(exc), "warning")
    except Exception as exc:
        current_app.logger.exception("Gagal menghapus akun akademik: %s", exc)
        flash("Akun akademik gagal dihapus karena masih memiliki relasi data.", "danger")
    return redirect(url_for("admin.akademik_pengguna"))


def delete_academic_signature(role, account_id):
    try:
        admin_service.clear_signature_reference_new_schema(role, account_id)
        flash("Referensi tanda tangan berhasil dihapus.", "success")
    except admin_service.AdminServiceError as exc:
        flash(str(exc), "warning")
    return redirect(url_for("admin.akademik_pengguna"))


def delete_academic_program(program_id):
    try:
        admin_service.delete_program_new_schema(program_id)
        flash("Program studi berhasil dihapus.", "success")
    except admin_service.AdminServiceError as exc:
        flash(str(exc), "warning")
    except Exception as exc:
        current_app.logger.exception("Gagal menghapus program studi: %s", exc)
        flash("Program studi gagal dihapus karena masih memiliki relasi data.", "danger")
    return redirect(url_for("admin.akademik_pengguna"))


# ======================================================================
# Helper internal form <-> data dict
# ======================================================================

def _account_data_from_form(form) -> dict:
    return {
        "name": form.name.data,
        "email": form.email.data,
        "phone": form.phone.data,
        "password": form.password.data,
        "is_active_flag": form.is_active_flag.data,
    }


def _populate_study_program_choices(form) -> None:
    form.study_program_id.choices = admin_service.all_study_program_choices()


# ======================================================================
# Master Data: Program Studi (FR-40 / UC-24)
# ======================================================================

def list_study_programs():
    page = request.args.get("page", 1, type=int)
    search = request.args.get("q", "").strip() or None
    pagination = admin_service.list_study_programs(page=page, search=search)
    return render_template(
        "admin/prodi_list.html", pagination=pagination, items=pagination.items, search=search or ""
    )


def create_study_program():
    form = StudyProgramForm()
    if form.validate_on_submit():
        try:
            program = admin_service.create_study_program(
                {"name": form.name.data, "code": form.code.data, "faculty_name": form.faculty_name.data}
            )
        except admin_service.AdminServiceError as exc:
            flash(str(exc), "warning")
            return render_template("admin/prodi_form.html", form=form, mode="create")
        current_app.logger.info("Admin '%s' membuat program studi '%s'.", current_user.email, program.code)
        flash(f"Program studi '{program.name}' berhasil dibuat.", "success")
        return redirect(url_for("admin.prodi_list"))
    return render_template("admin/prodi_form.html", form=form, mode="create")


def edit_study_program(program_id):
    program = admin_service.get_study_program_or_none(program_id)
    if program is None:
        abort(404)
    form = StudyProgramForm(obj=program)
    if form.validate_on_submit():
        try:
            admin_service.update_study_program(
                program, {"name": form.name.data, "code": form.code.data, "faculty_name": form.faculty_name.data}
            )
        except admin_service.AdminServiceError as exc:
            flash(str(exc), "warning")
            return render_template("admin/prodi_form.html", form=form, mode="edit", program=program)
        flash(f"Program studi '{program.name}' berhasil diperbarui.", "success")
        return redirect(url_for("admin.prodi_list"))
    return render_template("admin/prodi_form.html", form=form, mode="edit", program=program)


def delete_study_program(program_id):
    program = admin_service.get_study_program_or_none(program_id)
    if program is None:
        abort(404)
    try:
        admin_service.delete_study_program(program)
        flash(f"Program studi '{program.name}' berhasil dihapus.", "success")
    except admin_service.AdminServiceError as exc:
        flash(str(exc), "warning")
    return redirect(url_for("admin.prodi_list"))


# ======================================================================
# Master Data: Mahasiswa (FR-40 / UC-21)
# ======================================================================

def list_students():
    page = request.args.get("page", 1, type=int)
    search = request.args.get("q", "").strip() or None
    pagination = admin_service.list_students(page=page, search=search)
    return render_template(
        "admin/mahasiswa_list.html", pagination=pagination, items=pagination.items, search=search or ""
    )


def create_student():
    form = StudentForm()
    _populate_study_program_choices(form)
    if form.validate_on_submit():
        data = _account_data_from_form(form)
        data.update({"nim": form.nim.data, "semester": form.semester.data, "study_program_id": form.study_program_id.data})
        try:
            student = admin_service.create_student(data)
        except admin_service.AdminServiceError as exc:
            flash(str(exc), "warning")
            return render_template("admin/mahasiswa_form.html", form=form, mode="create")
        current_app.logger.info("Admin '%s' membuat akun mahasiswa NIM %s.", current_user.email, student.nim)
        flash(f"Akun mahasiswa '{student.user.name}' berhasil dibuat.", "success")
        return redirect(url_for("admin.mahasiswa_list"))
    return render_template("admin/mahasiswa_form.html", form=form, mode="create")


def edit_student(student_id):
    student = admin_service.get_student_or_none(student_id)
    if student is None:
        abort(404)
    form = StudentForm(obj=student)
    _populate_study_program_choices(form)
    if request.method == "GET":
        form.name.data = student.user.name
        form.email.data = student.user.email
        form.phone.data = student.user.phone
        form.is_active_flag.data = student.user.is_active_flag
    if form.validate_on_submit():
        data = _account_data_from_form(form)
        data.update({"nim": form.nim.data, "semester": form.semester.data, "study_program_id": form.study_program_id.data})
        try:
            admin_service.update_student(student, data)
        except admin_service.AdminServiceError as exc:
            flash(str(exc), "warning")
            return render_template("admin/mahasiswa_form.html", form=form, mode="edit", student=student)
        flash(f"Akun mahasiswa '{student.user.name}' berhasil diperbarui.", "success")
        return redirect(url_for("admin.mahasiswa_list"))
    return render_template("admin/mahasiswa_form.html", form=form, mode="edit", student=student)


def delete_student(student_id):
    student = admin_service.get_student_or_none(student_id)
    if student is None:
        abort(404)
    try:
        name = student.user.name
        admin_service.delete_student(student)
        flash(f"Akun mahasiswa '{name}' berhasil dihapus.", "success")
    except admin_service.AdminServiceError as exc:
        flash(str(exc), "warning")
    return redirect(url_for("admin.mahasiswa_list"))


# ======================================================================
# Master Data: Dosen (FR-40 / UC-22)
# ======================================================================

def list_lecturers():
    page = request.args.get("page", 1, type=int)
    search = request.args.get("q", "").strip() or None
    pagination = admin_service.list_lecturers(page=page, search=search)
    return render_template(
        "admin/dosen_list.html", pagination=pagination, items=pagination.items, search=search or ""
    )


def create_lecturer():
    form = LecturerForm()
    _populate_study_program_choices(form)
    if form.validate_on_submit():
        data = _account_data_from_form(form)
        data.update({"nidn": form.nidn.data, "study_program_id": form.study_program_id.data})
        try:
            lecturer = admin_service.create_lecturer(data)
        except admin_service.AdminServiceError as exc:
            flash(str(exc), "warning")
            return render_template("admin/dosen_form.html", form=form, mode="create")
        current_app.logger.info("Admin '%s' membuat akun dosen NIDN %s.", current_user.email, lecturer.nidn)
        flash(f"Akun dosen '{lecturer.user.name}' berhasil dibuat.", "success")
        return redirect(url_for("admin.dosen_list"))
    return render_template("admin/dosen_form.html", form=form, mode="create")


def edit_lecturer(lecturer_id):
    lecturer = admin_service.get_lecturer_or_none(lecturer_id)
    if lecturer is None:
        abort(404)
    form = LecturerForm(obj=lecturer)
    _populate_study_program_choices(form)
    if request.method == "GET":
        form.name.data = lecturer.user.name
        form.email.data = lecturer.user.email
        form.phone.data = lecturer.user.phone
        form.is_active_flag.data = lecturer.user.is_active_flag
    if form.validate_on_submit():
        data = _account_data_from_form(form)
        data.update({"nidn": form.nidn.data, "study_program_id": form.study_program_id.data})
        try:
            admin_service.update_lecturer(lecturer, data)
        except admin_service.AdminServiceError as exc:
            flash(str(exc), "warning")
            return render_template("admin/dosen_form.html", form=form, mode="edit", lecturer=lecturer)
        flash(f"Akun dosen '{lecturer.user.name}' berhasil diperbarui.", "success")
        return redirect(url_for("admin.dosen_list"))
    return render_template("admin/dosen_form.html", form=form, mode="edit", lecturer=lecturer)


def delete_lecturer(lecturer_id):
    lecturer = admin_service.get_lecturer_or_none(lecturer_id)
    if lecturer is None:
        abort(404)
    try:
        name = lecturer.user.name
        admin_service.delete_lecturer(lecturer)
        flash(f"Akun dosen '{name}' berhasil dihapus.", "success")
    except admin_service.AdminServiceError as exc:
        flash(str(exc), "warning")
    return redirect(url_for("admin.dosen_list"))


# ======================================================================
# Master Data: Kaprodi (FR-40 / UC-23)
# ======================================================================

def list_head_of_programs():
    page = request.args.get("page", 1, type=int)
    search = request.args.get("q", "").strip() or None
    pagination = admin_service.list_head_of_programs(page=page, search=search)
    return render_template(
        "admin/kaprodi_list.html", pagination=pagination, items=pagination.items, search=search or ""
    )


def create_head_of_program():
    form = HeadOfProgramForm()
    _populate_study_program_choices(form)
    if form.validate_on_submit():
        data = _account_data_from_form(form)
        data.update({"study_program_id": form.study_program_id.data, "nidn": form.nidn.data})
        try:
            hop = admin_service.create_head_of_program(data)
        except admin_service.AdminServiceError as exc:
            flash(str(exc), "warning")
            return render_template("admin/kaprodi_form.html", form=form, mode="create")
        current_app.logger.info("Admin '%s' membuat akun kaprodi '%s'.", current_user.email, hop.user.email)
        flash(f"Akun kaprodi '{hop.user.name}' berhasil dibuat.", "success")
        return redirect(url_for("admin.kaprodi_list"))
    return render_template("admin/kaprodi_form.html", form=form, mode="create")


def edit_head_of_program(hop_id):
    hop = admin_service.get_head_of_program_or_none(hop_id)
    if hop is None:
        abort(404)
    form = HeadOfProgramForm(obj=hop)
    _populate_study_program_choices(form)
    if request.method == "GET":
        form.name.data = hop.user.name
        form.email.data = hop.user.email
        form.phone.data = hop.user.phone
        form.is_active_flag.data = hop.user.is_active_flag
    if form.validate_on_submit():
        data = _account_data_from_form(form)
        data.update({"study_program_id": form.study_program_id.data, "nidn": form.nidn.data})
        try:
            admin_service.update_head_of_program(hop, data)
        except admin_service.AdminServiceError as exc:
            flash(str(exc), "warning")
            return render_template("admin/kaprodi_form.html", form=form, mode="edit", hop=hop)
        flash(f"Akun kaprodi '{hop.user.name}' berhasil diperbarui.", "success")
        return redirect(url_for("admin.kaprodi_list"))
    return render_template("admin/kaprodi_form.html", form=form, mode="edit", hop=hop)


def delete_head_of_program(hop_id):
    hop = admin_service.get_head_of_program_or_none(hop_id)
    if hop is None:
        abort(404)
    try:
        name = hop.user.name
        admin_service.delete_head_of_program(hop)
        flash(f"Akun kaprodi '{name}' berhasil dihapus.", "success")
    except admin_service.AdminServiceError as exc:
        flash(str(exc), "warning")
    return redirect(url_for("admin.kaprodi_list"))


# ======================================================================
# Akun Login Mahasiswa / Kiosk (Tahap 15 — Revisi Login)
# ======================================================================

def list_kiosk_accounts():
    page = request.args.get("page", 1, type=int)
    search = request.args.get("q", "").strip() or None
    pagination = admin_service.list_kiosk_accounts(page=page, search=search)
    return render_template(
        "admin/akun_mahasiswa_list.html", pagination=pagination, items=pagination.items, search=search or ""
    )


def create_kiosk_account():
    form = KioskAccountForm()
    if form.validate_on_submit():
        data = {
            "name": form.name.data,
            "nid": form.nid.data,
            "password": form.password.data,
            "is_active_flag": form.is_active_flag.data,
        }
        try:
            account = admin_service.create_kiosk_account(data)
        except admin_service.AdminServiceError as exc:
            flash(str(exc), "warning")
            return render_template("admin/akun_mahasiswa_form.html", form=form, mode="create")
        current_app.logger.info("Admin '%s' membuat akun login mahasiswa NID '%s'.", current_user.nid, account.nid)
        flash(f"Akun login mahasiswa '{account.nid}' berhasil dibuat.", "success")
        return redirect(url_for("admin.akun_mahasiswa_list"))
    return render_template("admin/akun_mahasiswa_form.html", form=form, mode="create")


def edit_kiosk_account(user_id):
    account = admin_service.get_kiosk_account_or_none(user_id)
    if account is None:
        abort(404)
    form = KioskAccountForm(obj=account)
    if request.method == "GET":
        form.is_active_flag.data = account.is_active_flag
    if form.validate_on_submit():
        data = {
            "name": form.name.data,
            "nid": form.nid.data,
            "password": form.password.data,
            "is_active_flag": form.is_active_flag.data,
        }
        try:
            admin_service.update_kiosk_account(account, data)
        except admin_service.AdminServiceError as exc:
            flash(str(exc), "warning")
            return render_template("admin/akun_mahasiswa_form.html", form=form, mode="edit", account=account)
        flash(f"Akun login mahasiswa '{account.nid}' berhasil diperbarui.", "success")
        return redirect(url_for("admin.akun_mahasiswa_list"))
    return render_template("admin/akun_mahasiswa_form.html", form=form, mode="edit", account=account)


def delete_kiosk_account(user_id):
    account = admin_service.get_kiosk_account_or_none(user_id)
    if account is None:
        abort(404)
    nid = account.nid
    admin_service.delete_kiosk_account(account)
    flash(f"Akun login mahasiswa '{nid}' berhasil dihapus.", "success")
    return redirect(url_for("admin.akun_mahasiswa_list"))


# ======================================================================
# Konfigurasi Surat: Kop Surat & Logo (FR-41 / UC-25)
# ======================================================================

_LETTERHEAD_LABELS = {
    CloudinaryFile.TYPE_KOP_SURAT: "Kop Surat",
    CloudinaryFile.TYPE_LOGO_FAKULTAS: "Logo Fakultas",
    CloudinaryFile.TYPE_LOGO_UNIVERSITAS: "Logo Universitas",
}


def show_letterhead_page():
    current_files = admin_service.latest_letterhead_files()
    margin_setting = admin_service.get_margin_setting()
    forms = {file_type: LetterheadUploadForm(prefix=file_type) for file_type in _LETTERHEAD_LABELS}
    return render_template(
        "admin/kop_surat.html",
        current_files=current_files,
        forms=forms,
        labels=_LETTERHEAD_LABELS,
        margin_setting=margin_setting,
    )


def upload_letterhead(file_type):
    if file_type not in _LETTERHEAD_LABELS:
        abort(404)
    form = LetterheadUploadForm(prefix=file_type)
    wants_json = request.headers.get("X-Requested-With") == "XMLHttpRequest" or request.accept_mimetypes.best == "application/json"
    upload_file = form.file.data or request.files.get("file") or next(iter(request.files.values()), None)
    if upload_file and upload_file.filename:
        try:
            file_record = admin_service.upload_letterhead_file(upload_file, file_type, current_user)
            if wants_json:
                return jsonify(
                    {
                        "ok": True,
                        "file": {
                            "id": file_record["id"],
                            "original_filename": file_record["original_filename"],
                            "public_id": file_record["public_id"],
                            "secure_url": file_record["secure_url"],
                            "resource_type": file_record["resource_type"],
                        },
                    }
                )
            flash(f"{_LETTERHEAD_LABELS[file_type]} berhasil diunggah.", "success")
        except admin_service.AdminServiceError as exc:
            if wants_json:
                return jsonify({"ok": False, "message": str(exc)}), 400
            flash(str(exc), "warning")
    else:
        message = "File wajib dipilih."
        if wants_json:
            return jsonify({"ok": False, "message": message}), 400
        flash(message, "warning")
    return redirect(url_for("admin.kop_surat"))


def delete_letterhead(file_id):
    file_record = admin_service.get_letterhead_file_or_none(file_id)
    if file_record is None:
        abort(404)
    label = _LETTERHEAD_LABELS.get(CloudinaryFile.TYPE_KOP_SURAT, "Kop Surat")
    admin_service.delete_letterhead_file(file_record)
    flash(f"{label} berhasil dihapus. Sistem akan memakai berkas terbaru berikutnya (jika ada).", "success")
    return redirect(url_for("admin.kop_surat"))


# ======================================================================
# Konfigurasi Surat: Template Surat (FR-42 / UC-26)
# ======================================================================

def list_letter_templates():
    templates = admin_service.list_letter_templates()
    return render_template("admin/template_surat_list.html", templates=templates)


def create_letter_template():
    form = LetterTemplateForm()
    if form.validate_on_submit():
        try:
            template = admin_service.create_letter_template(
                {
                    "name": form.name.data,
                    "margin_top": form.margin_top.data,
                    "margin_bottom": form.margin_bottom.data,
                    "margin_left": form.margin_left.data,
                    "margin_right": form.margin_right.data,
                    "is_active": form.is_active.data,
                },
                form.file.data,
                current_user,
            )
        except admin_service.AdminServiceError as exc:
            flash(str(exc), "warning")
            return render_template("admin/template_surat_form.html", form=form, mode="create")
        current_app.logger.info("Admin '%s' membuat template surat '%s'.", current_user.email, template.name)
        flash(f"Template surat '{template.name}' berhasil dibuat.", "success")
        return redirect(url_for("admin.template_surat_list"))
    return render_template("admin/template_surat_form.html", form=form, mode="create")


def edit_letter_template(template_id):
    template = admin_service.get_letter_template_or_none(template_id)
    if template is None:
        abort(404)
    form = LetterTemplateForm(obj=template)
    if form.validate_on_submit():
        try:
            admin_service.update_letter_template(
                template,
                {
                    "name": form.name.data,
                    "margin_top": form.margin_top.data,
                    "margin_bottom": form.margin_bottom.data,
                    "margin_left": form.margin_left.data,
                    "margin_right": form.margin_right.data,
                    "is_active": form.is_active.data,
                },
                form.file.data,
                current_user,
            )
        except admin_service.AdminServiceError as exc:
            flash(str(exc), "warning")
            return render_template("admin/template_surat_form.html", form=form, mode="edit", template=template)
        flash(f"Template surat '{template.name}' berhasil diperbarui.", "success")
        return redirect(url_for("admin.template_surat_list"))
    return render_template("admin/template_surat_form.html", form=form, mode="edit", template=template)


def delete_letter_template(template_id):
    template = admin_service.get_letter_template_or_none(template_id)
    if template is None:
        abort(404)
    try:
        name = template.name
        admin_service.delete_letter_template(template)
        flash(f"Template surat '{name}' berhasil dihapus.", "success")
    except admin_service.AdminServiceError as exc:
        flash(str(exc), "warning")
    return redirect(url_for("admin.template_surat_list"))


# ======================================================================
# Konfigurasi Surat: Setting Margin Default (FR-43 / UC-27)
# ======================================================================

def show_margin_setting():
    if request.method == "POST":
        try:
            admin_service.update_margin_setting(
                {
                    "margin_top": request.form.get("margin_top"),
                    "margin_bottom": request.form.get("margin_bottom"),
                    "margin_left": request.form.get("margin_left"),
                    "margin_right": request.form.get("margin_right"),
                    "header_clearance": request.form.get("header_clearance"),
                    "id_background": request.form.get("id_background"),
                },
                current_user,
            )
            current_app.logger.info("Admin '%s' memperbarui pengaturan KOP.", current_user.email)
            flash("Pengaturan KOP berhasil disimpan.", "success")
        except admin_service.AdminServiceError as exc:
            flash(str(exc), "warning")
        return redirect(url_for("admin.kop_surat"))

    current = admin_service.get_margin_setting()
    form = MarginSettingForm(
        margin_top=current["top"], margin_bottom=current["bottom"], margin_left=current["left"], margin_right=current["right"]
    )
    return render_template("admin/setting_margin.html", form=form)


# ======================================================================
# Konfigurasi Surat: Template Email (FR-44 / UC-28)
# ======================================================================

def list_email_templates():
    overrides = admin_service.list_email_template_overrides()
    return render_template(
        "admin/template_email_list.html", types=admin_service.EMAIL_TEMPLATE_TYPES, overrides=overrides
    )


def edit_email_template(type_key):
    if type_key not in admin_service.EMAIL_TEMPLATE_TYPES:
        abort(404)
    override = admin_service.get_email_template_override(type_key)
    form = EmailTemplateForm(data=override) if (override and request.method == "GET") else EmailTemplateForm()
    if form.validate_on_submit():
        admin_service.save_email_template_override(
            type_key, {"subject": form.subject.data, "html_body": form.html_body.data}, current_user
        )
        current_app.logger.info(
            "Admin '%s' memperbarui template email '%s'.", current_user.email, type_key
        )
        flash("Template email berhasil disimpan.", "success")
        return redirect(url_for("admin.template_email_list"))
    return render_template(
        "admin/template_email_form.html",
        form=form,
        type_key=type_key,
        type_label=admin_service.EMAIL_TEMPLATE_TYPES[type_key],
        has_override=override is not None,
    )


def reset_email_template(type_key):
    if type_key not in admin_service.EMAIL_TEMPLATE_TYPES:
        abort(404)
    admin_service.reset_email_template_override(type_key)
    flash("Template email dikembalikan ke bawaan sistem.", "success")
    return redirect(url_for("admin.template_email_list"))


# ======================================================================
# Riwayat Pengajuan (FR-45 / UC-29)
# ======================================================================

def list_submission_history():
    page = request.args.get("page", 1, type=int)
    status = request.args.get("status", "").strip() or None
    search = request.args.get("q", "").strip() or None
    filter_form = ObservationRequestFilterForm(status=status)
    filter_form.status.choices = [
        ("", "Semua Status"),
        *[(s, s) for s in ObservationRequest.ALL_STATUSES],
    ]
    pagination = admin_service.list_observation_requests(page=page, status=status, search=search)
    return render_template(
        "admin/riwayat_pengajuan.html",
        pagination=pagination,
        items=pagination.items,
        filter_form=filter_form,
        status=status or "",
        search=search or "",
        pagination_args={k: v for k, v in {"status": status or "", "q": search or ""}.items() if v},
        summary=admin_service.submission_history_summary(),
    )


def bulk_delete_submission_history():
    payload = request.get_json(silent=True) or {}
    try:
        deleted_count = admin_service.delete_submission_history_bulk(payload.get("ids", []))
    except admin_service.AdminServiceError as exc:
        return jsonify({"ok": False, "message": str(exc)}), 400
    except Exception:
        current_app.logger.exception("Gagal menghapus bulk riwayat pengajuan.")
        return jsonify({"ok": False, "message": "Gagal menghapus riwayat pengajuan."}), 500
    return jsonify(
        {
            "ok": True,
            "message": "Riwayat pengajuan berhasil dihapus.",
            "deleted_count": deleted_count,
            "summary": admin_service.submission_history_summary(),
        }
    )


# ======================================================================
# Kelola Profil (FR-05 / UC-31)
# ======================================================================

def profile():
    form = ProfileForm(obj=current_user)
    if form.validate_on_submit():
        current_user.name = form.name.data.strip()
        current_user.phone = form.phone.data.strip() if form.phone.data else None
        db.execute(
            "UPDATE `users` SET `name` = %s, `phone` = %s WHERE `id` = %s",
            (current_user.name, current_user.phone, current_user.id),
        )
        db.commit()
        current_app.logger.info("Admin '%s' memperbarui profil.", current_user.email)
        flash("Profil berhasil diperbarui.", "success")
        return redirect(url_for("admin.profil"))
    return render_template("admin/profil.html", form=form)
