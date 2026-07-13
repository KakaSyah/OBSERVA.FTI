"""
backend/controllers/mahasiswa_controller.py

Controller modul Mahasiswa (Tahap 5, alur diperbarui Tahap 14 — kiosk).

Sejak Tahap 14, akun mahasiswa yang login TIDAK mewakili satu individu
(satu kredensial dipakai bersama di kiosk TU, lihat `flask
create-kiosk-mahasiswa`). Karena itu:
- Tidak ada lagi "profil Student milik user yang login" (`_current_student`
  dihapus) — identitas pemohon (NIM) diketik manual di form dan dicocokkan
  ke tabel `students` oleh `observation_service.find_student_by_nim`.
- Alur berpusat pada SATU halaman "Ajukan Surat" dengan dua aksi: cetak
  draft (buka PDF di tab baru, tetap di form) dan kirim ke dosen (submit
  final, lalu kembali ke halaman Welcome — bukan ke riwayat/detail).
- `show_dashboard`/riwayat/detail/download/profil per-individu (Tahap 5
  lama) dipertahankan di service layer untuk kemungkinan pemakaian lain,
  namun tidak lagi menjadi bagian dari alur utama kiosk ini.
"""

import json
from types import SimpleNamespace

from flask import current_app, flash, jsonify, redirect, render_template, request, url_for
from flask_login import current_user

from backend.extensions import db
from backend.forms.mahasiswa_forms import ObservationRequestForm
from backend.services import kop_setting_service
from backend.services import observation_service as obs_service


MAX_GROUP_MEMBERS = 10


# ---------- Welcome (kiosk landing page) ----------

def show_welcome():
    return render_template("mahasiswa/welcome.html")


# ---------- Helper internal ----------

def _populate_form_choices(form):
    """Isi choices `study_program_id` (seluruh prodi aktif) & `lecturer_id`
    (dosen aktif pada prodi yang sedang dipilih -- via data-prodi attribute,
    difilter di sisi klien oleh JS inline di ajukan_surat.html; validasi
    akhir tetap dilakukan di server saat submit). Mengembalikan
    `lecturer_prodi_map` (untuk validasi server) sekaligus `lecturers_json`
    (untuk filter dropdown sisi klien)."""
    prodi_list = []
    for row in db.fetchall(
        "SELECT `id_program_studi`, `nama_program_studi` FROM `program_studi` "
        "WHERE `status_aktif` = 1 ORDER BY `nama_program_studi` ASC"
    ):
        prodi_list.append(
            SimpleNamespace(id=row["id_program_studi"], name=row["nama_program_studi"], code="")
        )
    form.study_program_id.choices = [(p.id, p.name) for p in prodi_list]

    lecturers = []
    for prodi in prodi_list:
        lecturers.extend(obs_service.get_lecturer_choices(prodi.id))
    form.lecturer_id.choices = [(l.id, f"{l.user.name} (NIDN {l.nidn})") for l in lecturers]

    lecturer_prodi_map = {
        l.id: {"study_program_id": l.study_program_id, "lecturer_type": l.lecturer_type}
        for l in lecturers
    }
    lecturers_json = [
        {
            "id": l.id,
            "label": f"{l.user.name} (NIDN {l.nidn})",
            "study_program_id": l.study_program_id,
            "lecturer_type": l.lecturer_type,
        }
        for l in lecturers
    ]
    heads_by_program = {}
    for row in db.fetchall(
        "SELECT k.`id_program_studi`, u.`nama` FROM `kaprodi` AS k "
        "JOIN `pengguna` AS u ON u.`id_pengguna` = k.`id_pengguna` "
        "WHERE u.`status_aktif` = 1"
    ):
        heads_by_program.setdefault(row["id_program_studi"], []).append(row["nama"])
    heads_of_program_json = {
        str(program_id): names[0]
        for program_id, names in heads_by_program.items()
        if len(names) == 1
    }
    return lecturer_prodi_map, lecturers_json, heads_of_program_json


def _resolve_student_or_error(form):
    """Ambil data Student dari NIM, atau buat otomatis jika NIM belum terdaftar."""
    try:
        student = obs_service.get_or_create_student_by_nim(form.nim.data, form.study_program_id.data)
    except obs_service.ObservationRequestError as exc:
        form.nim.errors.append(str(exc))
        return None

    if student.study_program_id != form.study_program_id.data:
        form.study_program_id.errors.append(
            "Program studi yang dipilih tidak sesuai dengan data mahasiswa terdaftar untuk NIM ini."
        )
        return None

    return student


def _group_member_limit_exceeded(raw_members: str) -> bool:
    """Cegah payload manual yang mengirim lebih dari batas anggota kelompok."""
    try:
        members = json.loads(raw_members or "[]")
    except (TypeError, ValueError):
        return False
    return isinstance(members, list) and len(members) > MAX_GROUP_MEMBERS


# ---------- Ajukan surat: cetak draft & kirim ke dosen (UC-02..04, FR-10..12) ----------

def new_observation_request():
    if request.method == "POST" and request.form.get("action") == "complete_print":
        try:
            request_id = int(request.form.get("request_id", ""))
            current_app.logger.debug(
                "Cetak Hard File finalisasi: method=%s path=%s request_id=%s",
                request.method,
                request.path,
                request_id,
            )
            document_number = obs_service.complete_hard_file_print(request_id)
        except (TypeError, ValueError, obs_service.ObservationRequestError) as exc:
            return jsonify(ok=False, message=str(exc) or "Gagal menyelesaikan cetak hard file."), 400
        return jsonify(ok=True, document_number=document_number, document_type="Hard File")

    form = ObservationRequestForm()
    lecturer_prodi_map, lecturers_json, heads_of_program_json = _populate_form_choices(form)

    if form.validate_on_submit():
        group_members = request.form.get("anggota_kelompok", "[]")
        if _group_member_limit_exceeded(group_members):
            message = "Maksimal anggota kelompok adalah 10 orang."
            if request.form.get("action") == "print":
                return jsonify(ok=False, message=message), 400
            flash(message, "warning")
            return render_template(
                "mahasiswa/ajukan_surat.html",
                form=form,
                lecturers_json=lecturers_json,
                heads_of_program_json=heads_of_program_json,
                kop_setting=kop_setting_service.get_active_kop_setting(),
                candidate_document_number=obs_service.preview_document_number(),
            )

        student = _resolve_student_or_error(form)
        selected_lecturer_type = request.form.get("jenis_dosen", "").strip()
        selected_action = request.form.get("action", "kirim")
        lecturer_data = lecturer_prodi_map.get(form.lecturer_id.data)
        if selected_lecturer_type not in {"Internal", "Eksternal"}:
            form.lecturer_id.errors.append("Pilih jenis dosen terlebih dahulu.")
            student = None
        elif student is not None and (
            lecturer_data is None
            or lecturer_data["study_program_id"] != form.study_program_id.data
            or lecturer_data["lecturer_type"] != selected_lecturer_type
        ):
            form.lecturer_id.errors.append("Dosen pembimbing tidak valid untuk jenis dosen yang dipilih.")
            student = None
        elif (
            student is not None
            and selected_lecturer_type == "Eksternal"
            and selected_action != "print"
        ):
            # Dosen eksternal tidak punya akun di sistem sehingga tidak bisa approval
            # maupun menandatangani digital. Alur 2 wajib dihentikan di sini, sebelum
            # draft pengajuan dibuat sama sekali. Alur 1 (print/Cetak Hardfile) tidak
            # terpengaruh oleh cabang ini karena selected_action == "print" dikecualikan.
            message = "Dosen eksternal tidak bisa menggunakan fitur Tanda Tangan Digital. Silakan gunakan Cetak Hardfile."
            form.lecturer_id.errors.append(message)
            flash(message, "warning")
            student = None

        if student is not None:
            action = request.form.get("action", "kirim")
            student.user.name = request.form.get("student_name", "").strip() or student.user.name
            student.user.email = (
                request.form.get("student_email", "").strip()
                or getattr(current_user, "email", "")
                or getattr(current_user, "username", "")
            )
            obs = obs_service.create_draft(student, form, group_members)
            current_app.logger.info(
                "Kiosk mahasiswa membuat draft pengajuan id=%s untuk NIM=%s.", obs.id, student.nim
            )

            if action == "print":
                current_app.logger.debug(
                    "Cetak Hard File siap dicetak browser: method=%s path=%s request_id=%s nim=%s",
                    request.method,
                    request.path,
                    obs.id,
                    student.nim,
                )
                return jsonify(ok=True, request_id=obs.id)

            try:
                obs_service.ensure_document_number(obs.id, "TTD Digital")
            except obs_service.ObservationRequestError as exc:
                current_app.logger.error("Gagal membuat nomor dokumen untuk pengajuan id=%s: %s", obs.id, exc)
                flash(str(exc), "warning")
                return redirect(url_for("mahasiswa.welcome"))

            try:
                obs_service.send_to_lecturer(obs)
            except obs_service.ObservationRequestError as exc:
                flash(str(exc), "warning")
                return redirect(url_for("mahasiswa.welcome"))

            current_app.logger.info(
                "Kiosk mahasiswa mengirim pengajuan id=%s (NIM=%s) ke dosen pembimbing.",
                obs.id,
                student.nim,
            )
            flash(
                f"Pengajuan atas nama {student.user.name} ({student.nim}) berhasil dikirim ke "
                "dosen pembimbing. Status dapat dipantau melalui email yang terdaftar.",
                "success",
            )
            return redirect(url_for("mahasiswa.welcome"))

    return render_template(
        "mahasiswa/ajukan_surat.html",
        form=form,
        lecturers_json=lecturers_json,
        heads_of_program_json=heads_of_program_json,
        kop_setting=kop_setting_service.get_active_kop_setting(),
        candidate_document_number=obs_service.preview_document_number(),
    )

# ---------------------------------------------------------------------
# CATATAN Tahap 14 (kiosk): fungsi per-individu Tahap 5 lama --
# edit_observation_request, print_draft(request_id)/send_observation_request
# (versi lama berbasis request_id terpisah), list_history, show_detail,
# download_letter, profile -- SENGAJA DIHAPUS dari controller ini karena
# bergantung pada `current_user.student_profile` per-individu yang sudah
# tidak berlaku pada akun kiosk bersama. Fungsi service pendukungnya
# (observation_service.list_for_student, get_owned_request, dst.) tetap
# dipertahankan di service layer bila modul "cek status surat by NIM"
# ingin ditambahkan kembali di iterasi berikutnya.
# ---------------------------------------------------------------------
