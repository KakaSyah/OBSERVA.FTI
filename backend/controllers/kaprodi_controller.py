"""
backend/controllers/kaprodi_controller.py

Controller modul Kaprodi (Tahap 7) — jembatan antara route (HTTP: request
parsing, flash message, redirect) dan service (business logic murni), sesuai
pola pada Tahap 1 bagian 9: routes/ (thin) -> controllers/ -> services/.
Mengikuti pola yang sama persis dengan `dosen_controller.py` (Tahap 6).
"""

from types import SimpleNamespace

from flask import abort, current_app, flash, jsonify, redirect, render_template, request, url_for
from flask_login import current_user, logout_user

from backend.forms.kaprodi_forms import ApprovalNoteForm, ProfileForm
from backend.services import cloudinary_service, kop_setting_service, observation_service as obs_service
from backend.extensions import db


# ---------- Helper internal ----------

def _current_head_of_program():
    row = db.fetchone(
        "SELECT k.`id_kaprodi`, k.`id_pengguna`, k.`id_program_studi`, k.`nidn`, "
        "p.`nama_program_studi`, u.`nama`, u.`username`, u.`status_aktif` "
        "FROM `kaprodi` AS k "
        "JOIN `pengguna` AS u ON u.`id_pengguna` = k.`id_pengguna` "
        "LEFT JOIN `program_studi` AS p ON p.`id_program_studi` = k.`id_program_studi` "
        "WHERE k.`id_pengguna` = %s LIMIT 1",
        (current_user.id,),
    )
    if row is None:
        current_app.logger.warning(
            "User id=%s ber-role kaprodi tapi tidak punya baris kaprodi.", current_user.id
        )
        logout_user()
        flash(
            "Akun kaprodi ini belum memiliki profil kaprodi. Silakan login dengan akun kaprodi yang dibuat dari menu Admin > Kelola Akademik & Pengguna.",
            "warning",
        )
        return None
    return SimpleNamespace(
        id=row["id_kaprodi"],
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


def _get_head_of_program_request_or_404(request_id, head_of_program):
    obs = obs_service.get_head_of_program_request(request_id, head_of_program)
    if obs is None:
        abort(404)
    return obs


# ---------- Dashboard (UC-14 lanjutan) ----------

def show_dashboard():
    head_of_program = _current_head_of_program()
    if head_of_program is None:
        return redirect(url_for("auth.login"))
    summary = obs_service.get_dashboard_summary_for_head_of_program(head_of_program, current_user)
    return render_template(
        "kaprodi/dashboard.html",
        head_of_program=head_of_program,
        approval_history=obs_service.approval_history_for_head_of_program(head_of_program),
        kop_setting=kop_setting_service.get_active_kop_setting(),
        **summary,
    )


# ---------- Daftar persetujuan akhir (UC-15, FR-30) ----------

def list_incoming():
    head_of_program = _current_head_of_program()
    if head_of_program is None:
        return redirect(url_for("auth.login"))
    page = request.args.get("page", 1, type=int)
    pagination = obs_service.list_incoming_for_head_of_program(head_of_program, page=page)
    return render_template(
        "kaprodi/daftar_persetujuan.html", pagination=pagination, items=pagination.items
    )


# ---------- Detail surat + aksi setujui/tolak (UC-16, UC-17, FR-31) ----------

def show_detail(request_id):
    head_of_program = _current_head_of_program()
    if head_of_program is None:
        return redirect(url_for("auth.login"))
    obs = _get_head_of_program_request_or_404(request_id, head_of_program)
    approval_logs = obs_service.approval_logs_for_request(obs.id)
    approve_form = ApprovalNoteForm(prefix="approve")
    reject_form = ApprovalNoteForm(prefix="reject")
    return render_template(
        "kaprodi/detail_surat.html",
        observation_request=obs,
        approval_logs=approval_logs,
        approve_form=approve_form,
        reject_form=reject_form,
    )


def approve_request(request_id):
    head_of_program = _current_head_of_program()
    if head_of_program is None:
        return redirect(url_for("auth.login"))
    obs = _get_head_of_program_request_or_404(request_id, head_of_program)
    form = ApprovalNoteForm(prefix="approve")

    if not form.validate_on_submit():
        flash("Catatan tidak valid. Maksimal 500 karakter.", "warning")
        return redirect(url_for("kaprodi.detail_persetujuan", request_id=obs.id))

    try:
        obs_service.approve_by_head_of_program(obs, current_user, form.note.data)
    except obs_service.ObservationRequestError as exc:
        flash(str(exc), "warning")
        return redirect(url_for("kaprodi.detail_persetujuan", request_id=obs.id))

    current_app.logger.info(
        "Kaprodi '%s' menyetujui pengajuan id=%s. Nomor surat: %s. Status akhir: %s.",
        current_user.email,
        obs.id,
        obs.letter_number.formatted_number if obs.letter_number else "-",
        obs.status,
    )
    letter_number = getattr(getattr(obs, "letter_number", None), "formatted_number", None)
    if letter_number:
        flash(f"Pengajuan disetujui. Surat resmi nomor {letter_number} berhasil diterbitkan.", "success")
    else:
        flash("Pengajuan disetujui.", "success")
    return redirect(url_for("kaprodi.detail_persetujuan", request_id=obs.id))


def final_pdf_upload_signature(request_id):
    """Hasilkan signed upload params agar browser Kaprodi bisa unggah PDF
    final LANGSUNG ke Cloudinary (bypass limit ~4.5MB body request Vercel
    Serverless Function -- lihat cloudinary_service.generate_signed_upload_params)."""
    head_of_program = _current_head_of_program()
    if head_of_program is None:
        return jsonify(ok=False, message="Sesi Kaprodi tidak valid."), 401
    obs = _get_head_of_program_request_or_404(request_id, head_of_program)
    try:
        params = cloudinary_service.generate_signed_upload_params(obs.id)
    except cloudinary_service.CloudinaryServiceError as exc:
        return jsonify(ok=False, message=str(exc)), 500
    return jsonify(ok=True, **params)


def upload_final_pdf(request_id):
    """Catat PDF final yang SUDAH diunggah browser LANGSUNG ke Cloudinary
    (lewat signed params dari final_pdf_upload_signature) -- backend di sini
    hanya menerima metadata kecil (secure_url/public_id), bukan file PDF-nya
    sendiri, supaya tidak lagi kena limit ~4.5MB body request Vercel."""
    head_of_program = _current_head_of_program()
    if head_of_program is None:
        return jsonify(ok=False, message="Sesi Kaprodi tidak valid."), 401
    obs = _get_head_of_program_request_or_404(request_id, head_of_program)

    payload = request.get_json(silent=True) or {}
    secure_url = (payload.get("secure_url") or "").strip()
    public_id = (payload.get("public_id") or "").strip()
    resource_type = (payload.get("resource_type") or "raw").strip() or "raw"

    if not secure_url or not public_id:
        return jsonify(ok=False, message="Data hasil unggah Cloudinary (secure_url/public_id) wajib dikirim."), 400
    # Pastikan public_id memang milik pengajuan ini (bukan hasil tempelan
    # sembarang) -- samakan formatnya dengan yang dibuat generate_signed_upload_params.
    if public_id != f"surat-resmi/observation-request-{obs.id}":
        return jsonify(ok=False, message="public_id tidak sesuai dengan pengajuan ini."), 400

    try:
        upload_result = obs_service.upload_final_pdf(
            obs, secure_url=secure_url, public_id=public_id, resource_type=resource_type
        )
    except (obs_service.ObservationRequestError, cloudinary_service.CloudinaryServiceError) as exc:
        return jsonify(ok=False, message=str(exc)), 400

    current_app.logger.info(
        "PDF final pengajuan id=%s diunggah browser langsung ke Cloudinary dan tercatat di backend.",
        obs.id,
    )
    return jsonify(
        ok=True,
        file_id=upload_result["file_id"],
        secure_url=upload_result["secure_url"],
    )


def reject_request(request_id):
    head_of_program = _current_head_of_program()
    if head_of_program is None:
        return redirect(url_for("auth.login"))
    obs = _get_head_of_program_request_or_404(request_id, head_of_program)
    form = ApprovalNoteForm(prefix="reject")

    if not form.validate_on_submit():
        flash("Catatan tidak valid. Maksimal 500 karakter.", "warning")
        return redirect(url_for("kaprodi.detail_persetujuan", request_id=obs.id))

    try:
        obs_service.reject_by_head_of_program(obs, current_user, form.note.data)
    except obs_service.ObservationRequestError as exc:
        flash(str(exc), "warning")
        return redirect(url_for("kaprodi.detail_persetujuan", request_id=obs.id))

    current_app.logger.info(
        "Kaprodi '%s' menolak pengajuan id=%s.", current_user.email, obs.id
    )
    flash("Pengajuan ditolak. Mahasiswa akan melihat catatan penolakan Anda.", "success")
    return redirect(url_for("kaprodi.detail_persetujuan", request_id=obs.id))


# ---------- Riwayat persetujuan (UC-18, FR-34) ----------

def list_approval_history():
    page = request.args.get("page", 1, type=int)
    pagination = obs_service.list_approval_history_for_head_of_program(current_user.id, page=page)
    return render_template(
        "kaprodi/riwayat.html", pagination=pagination, items=pagination.items
    )


# ---------- Kelola profil (UC-19, FR-05) ----------

def profile():
    head_of_program = _current_head_of_program()
    if head_of_program is None:
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
        current_app.logger.info("Kaprodi '%s' memperbarui profil.", current_user.email)
        flash("Profil berhasil diperbarui.", "success")
        return redirect(url_for("kaprodi.profil"))

    return render_template("kaprodi/profil.html", form=form, head_of_program=head_of_program)
