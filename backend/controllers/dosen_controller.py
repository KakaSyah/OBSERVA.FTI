"""
backend/controllers/dosen_controller.py

Controller modul Dosen (Tahap 6) — jembatan antara route (HTTP: request
parsing, flash message, redirect) dan service (business logic murni), sesuai
pola pada Tahap 1 bagian 9: routes/ (thin) -> controllers/ -> services/.
Mengikuti pola yang sama persis dengan `mahasiswa_controller.py` (Tahap 5).
"""

from types import SimpleNamespace

from flask import abort, current_app, flash, redirect, render_template, request, url_for
from flask_login import current_user, logout_user

from backend.forms.dosen_forms import ApprovalNoteForm, ProfileForm
from backend.services import observation_service as obs_service
from backend.extensions import db


# ---------- Helper internal ----------

def _current_lecturer():
    row = db.fetchone(
        "SELECT d.`id_dosen`, d.`id_pengguna`, d.`id_program_studi`, d.`nidn`, "
        "p.`nama_program_studi`, u.`nama`, u.`username`, u.`status_aktif` "
        "FROM `dosen` AS d "
        "JOIN `pengguna` AS u ON u.`id_pengguna` = d.`id_pengguna` "
        "LEFT JOIN `program_studi` AS p ON p.`id_program_studi` = d.`id_program_studi` "
        "WHERE d.`id_pengguna` = %s LIMIT 1",
        (current_user.id,),
    )
    if row is None:
        current_app.logger.warning(
            "User id=%s ber-role dosen tapi tidak punya baris dosen.", current_user.id
        )
        logout_user()
        flash(
            "Akun dosen ini belum memiliki profil dosen. Silakan login dengan akun dosen yang dibuat dari menu Admin > Kelola Akademik & Pengguna.",
            "warning",
        )
        return None
    return SimpleNamespace(
        id=row["id_dosen"],
        user_id=row["id_pengguna"],
        study_program_id=row["id_program_studi"],
        nidn=row["nidn"],
        user=SimpleNamespace(
            id=row["id_pengguna"],
            name=row["nama"],
            username=row["username"],
            email=row["username"],
            is_active=bool(row["status_aktif"]),
        ),
        study_program=SimpleNamespace(
            id=row["id_program_studi"],
            name=row["nama_program_studi"] or "",
            code="",
        ),
    )


def _get_lecturer_request_or_404(request_id, lecturer):
    obs = obs_service.get_lecturer_request(request_id, lecturer)
    if obs is None:
        abort(404)
    return obs


# ---------- Dashboard (UC-08 lanjutan) ----------

def show_dashboard():
    lecturer = _current_lecturer()
    if lecturer is None:
        return redirect(url_for("auth.login"))
    summary = obs_service.get_dashboard_summary_for_lecturer(lecturer, current_user)
    return render_template(
        "dosen/dashboard.html",
        lecturer=lecturer,
        approval_history=obs_service.approval_history_for_lecturer(lecturer),
        **summary,
    )


# ---------- Daftar surat masuk (UC-09, FR-20) ----------

def list_incoming():
    lecturer = _current_lecturer()
    if lecturer is None:
        return redirect(url_for("auth.login"))
    page = request.args.get("page", 1, type=int)
    pagination = obs_service.list_incoming_for_lecturer(lecturer, page=page)
    return render_template(
        "dosen/surat_masuk.html", pagination=pagination, items=pagination.items
    )


# ---------- Detail surat + aksi setujui/tolak (UC-10, UC-11, FR-21) ----------

def show_detail(request_id):
    lecturer = _current_lecturer()
    if lecturer is None:
        return redirect(url_for("auth.login"))
    obs = _get_lecturer_request_or_404(request_id, lecturer)
    approval_logs = obs_service.approval_logs_for_request(obs.id)
    approve_form = ApprovalNoteForm(prefix="approve")
    reject_form = ApprovalNoteForm(prefix="reject")
    return render_template(
        "dosen/detail_surat.html",
        observation_request=obs,
        approval_logs=approval_logs,
        approve_form=approve_form,
        reject_form=reject_form,
    )


def approve_request(request_id):
    lecturer = _current_lecturer()
    if lecturer is None:
        return redirect(url_for("auth.login"))
    obs = _get_lecturer_request_or_404(request_id, lecturer)
    form = ApprovalNoteForm(prefix="approve")

    if not form.validate_on_submit():
        flash("Catatan tidak valid. Maksimal 500 karakter.", "warning")
        return redirect(url_for("dosen.detail_surat_masuk", request_id=obs.id))

    try:
        obs_service.approve_by_lecturer(obs, current_user, form.note.data)
    except obs_service.ObservationRequestError as exc:
        flash(str(exc), "warning")
        return redirect(url_for("dosen.detail_surat_masuk", request_id=obs.id))

    current_app.logger.info(
        "Dosen '%s' menyetujui pengajuan id=%s.", current_user.email, obs.id
    )
    flash("Pengajuan disetujui dan diteruskan ke Kaprodi.", "success")
    return redirect(url_for("dosen.detail_surat_masuk", request_id=obs.id))


def reject_request(request_id):
    lecturer = _current_lecturer()
    if lecturer is None:
        return redirect(url_for("auth.login"))
    obs = _get_lecturer_request_or_404(request_id, lecturer)
    form = ApprovalNoteForm(prefix="reject")

    if not form.validate_on_submit():
        flash("Catatan tidak valid. Maksimal 500 karakter.", "warning")
        return redirect(url_for("dosen.detail_surat_masuk", request_id=obs.id))

    try:
        obs_service.reject_by_lecturer(obs, current_user, form.note.data)
    except obs_service.ObservationRequestError as exc:
        flash(str(exc), "warning")
        return redirect(url_for("dosen.detail_surat_masuk", request_id=obs.id))

    current_app.logger.info(
        "Dosen '%s' menolak pengajuan id=%s.", current_user.email, obs.id
    )
    flash("Pengajuan ditolak. Mahasiswa akan melihat catatan penolakan Anda.", "success")
    return redirect(url_for("dosen.detail_surat_masuk", request_id=obs.id))


# ---------- Riwayat persetujuan (UC-12, FR-24) ----------

def list_approval_history():
    page = request.args.get("page", 1, type=int)
    pagination = obs_service.list_approval_history_for_lecturer(current_user.id, page=page)
    return render_template(
        "dosen/riwayat_persetujuan.html", pagination=pagination, items=pagination.items
    )


# ---------- Kelola profil (UC-13, FR-05) ----------

def profile():
    lecturer = _current_lecturer()
    if lecturer is None:
        return redirect(url_for("auth.login"))
    form = ProfileForm(obj=current_user)

    if form.validate_on_submit():
        current_user.name = form.name.data.strip()
        current_user.phone = form.phone.data.strip() if form.phone.data else None
        db.execute(
            "UPDATE `pengguna` SET `nama` = %s WHERE `id_pengguna` = %s",
            (current_user.name, current_user.id),
        )
        db.commit()
        current_app.logger.info("Dosen '%s' memperbarui profil.", current_user.email)
        flash("Profil berhasil diperbarui.", "success")
        return redirect(url_for("dosen.profil"))

    return render_template("dosen/profil.html", form=form, lecturer=lecturer)
