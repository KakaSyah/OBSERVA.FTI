"""
backend/services/observation_service.py

Business logic modul Mahasiswa, Dosen, dan Kaprodi untuk pengajuan surat izin observasi.
"""

import json
import secrets

from flask import current_app

from backend.extensions import Pagination, db
from backend.models.approval_log import ApprovalLog
from backend.models.lecturer import Lecturer
from backend.models.observation_request import ObservationRequest
from backend.models.role import Role
from backend.models.student import Student
from backend.models.user import User
from backend.services import activity_log_service, cloudinary_service, email_service, letter_number_service
from backend.utils.security import hash_password
from backend.utils.stats import avg_response_hours as _avg_response_hours
from backend.utils.stats import monthly_trend as _monthly_trend

PER_PAGE = 10


def _insert_instance(instance) -> int:
    model = instance.__class__
    pk_name = model._primary_key
    columns = []
    values = []
    for name, column in model._columns.items():
        if name == pk_name:
            continue
        value = getattr(instance, name, None)
        if value is None and column.kwargs.get("server_default") is not None:
            continue
        if name in {"created_at", "updated_at", "deleted_at"} and value is None:
            continue
        columns.append(f"`{column.column_name}`")
        values.append(value)
    placeholders = ", ".join(["%s"] * len(columns))
    sql = f"INSERT INTO `{model.__tablename__}` ({', '.join(columns)}) VALUES ({placeholders})"
    lastrowid = db.insert(sql, values)
    if pk_name and getattr(instance, pk_name, None) is None:
        setattr(instance, pk_name, lastrowid)
    return lastrowid


def _update_instance(instance) -> int:
    model = instance.__class__
    pk_name = model._primary_key
    pk_value = getattr(instance, pk_name, None)
    if pk_value is None:
        raise ValueError("Cannot update model without primary key value.")
    fields = []
    values = []
    for name, column in model._columns.items():
        if name == pk_name:
            continue
        value = getattr(instance, name, None)
        if name in {"created_at", "updated_at", "deleted_at"} and value is None:
            continue
        fields.append(f"`{column.column_name}` = %s")
        values.append(value)
    if not fields:
        return 0
    values.append(pk_value)
    sql = f"UPDATE `{model.__tablename__}` SET {', '.join(fields)} WHERE `{model._columns[pk_name].column_name}` = %s"
    cursor = db.execute(sql, values)
    return cursor.rowcount


class ObservationRequestError(Exception):
    """Error domain pengajuan surat (dipetakan controller ke flash message)."""


def _fetch_one_model(model, sql, params=None):
    row = db.fetchone(sql, params)
    return model.from_row(row) if row else None


def _fetch_all_models(model, sql, params=None):
    rows = db.fetchall(sql, params)
    return [model.from_row(row) for row in rows]


def _paginate_models(model, base_sql, count_sql, params, page: int, per_page: int = PER_PAGE):
    page = max(1, page)
    total = int(db.scalar(count_sql, params) or 0)
    offset = (page - 1) * per_page
    items = _fetch_all_models(
        model,
        f"{base_sql} LIMIT %s OFFSET %s",
        list(params or []) + [per_page, offset],
    )
    return Pagination(items, page, per_page, total)


def _count(sql, params=None) -> int:
    return int(db.scalar(sql, params) or 0)


def get_lecturer_choices(study_program_id):
    sql = (
        "SELECT `lecturers`.* FROM `lecturers` "
        "JOIN `users` ON `lecturers`.`user_id` = `users`.`id` "
        "WHERE `lecturers`.`study_program_id` = %s "
        "AND `lecturers`.`deleted_at` IS NULL "
        "AND `users`.`deleted_at` IS NULL "
        "AND `users`.`is_active` = TRUE "
        "ORDER BY `users`.`name` ASC"
    )
    return _fetch_all_models(Lecturer, sql, (study_program_id,))


def find_student_by_nim(nim: str):
    nim = (nim or "").strip()
    if not nim:
        return None
    return _fetch_one_model(
        Student,
        "SELECT * FROM `students` WHERE LOWER(`nim`) = %s AND `deleted_at` IS NULL LIMIT 1",
        (nim.lower(),),
    )


def get_or_create_student_by_nim(nim: str, study_program_id: int):
    nim = (nim or "").strip()
    if not nim:
        return None

    student = find_student_by_nim(nim)
    if student is not None:
        return student

    role_id = db.scalar("SELECT `id` FROM `roles` WHERE `name` = %s LIMIT 1", (Role.MAHASISWA,))
    if role_id is None:
        raise ObservationRequestError("Role mahasiswa belum tersedia di database.")

    login_nid = nim[:30]
    if db.scalar("SELECT 1 FROM `users` WHERE LOWER(`nid`) = LOWER(%s) LIMIT 1", (login_nid,)):
        login_nid = f"AUTO{secrets.token_hex(4)}"[:30]

    email = f"{nim.lower()}@student.local"
    if db.scalar("SELECT 1 FROM `users` WHERE LOWER(`email`) = LOWER(%s) LIMIT 1", (email,)):
        email = f"student-{secrets.token_hex(8)}@student.local"

    user = User(
        role_id=role_id,
        name=f"Mahasiswa {nim}",
        nid=login_nid,
        email=email,
        password_hash=hash_password(secrets.token_urlsafe(18)),
        is_active_flag=True,
    )
    try:
        _insert_instance(user)
        student = Student(
            user_id=user.id,
            nim=nim,
            semester=1,
            study_program_id=study_program_id,
        )
        _insert_instance(student)
        db.commit()
        return student
    except Exception as exc:
        db.rollback()
        raise ObservationRequestError(f"Persetujuan final gagal diterbitkan: {exc}") from exc


def get_owned_request(request_id, student):
    return _fetch_one_model(
        ObservationRequest,
        "SELECT * FROM `observation_requests` WHERE `id` = %s AND `student_id` = %s AND `deleted_at` IS NULL LIMIT 1",
        (request_id, student.id),
    )


def create_draft(student, form) -> ObservationRequest:
    obs = ObservationRequest(
        student_id=student.id,
        lecturer_id=form.lecturer_id.data,
        study_program_id=student.study_program_id,
        destination_institution=form.destination_institution.data.strip(),
        institution_address=form.institution_address.data.strip(),
        topic=form.topic.data.strip(),
        course_name=form.course_name.data.strip(),
        submission_date=form.submission_date.data,
        status=ObservationRequest.STATUS_DRAFT,
    )
    _insert_instance(obs)
    db.commit()
    return obs


def update_draft(obs: ObservationRequest, form) -> ObservationRequest:
    if not obs.is_editable:
        raise ObservationRequestError("Pengajuan yang sudah dikirim tidak dapat diubah lagi.")

    obs.lecturer_id = form.lecturer_id.data
    obs.destination_institution = form.destination_institution.data.strip()
    obs.institution_address = form.institution_address.data.strip()
    obs.topic = form.topic.data.strip()
    obs.course_name = form.course_name.data.strip()
    obs.submission_date = form.submission_date.data
    _update_instance(obs)
    db.commit()
    return obs


def send_to_lecturer(obs: ObservationRequest) -> ObservationRequest:
    if not obs.is_draft:
        raise ObservationRequestError("Pengajuan sudah pernah dikirim sebelumnya dan tidak dapat dikirim ulang.")

    obs.status = ObservationRequest.STATUS_MENUNGGU_DOSEN
    _update_instance(obs)
    db.commit()
    return obs


def list_for_student(student, status=None, page: int = 1, per_page: int = PER_PAGE):
    base_sql = "SELECT * FROM `observation_requests` WHERE `student_id` = %s AND `deleted_at` IS NULL"
    count_sql = "SELECT COUNT(*) FROM `observation_requests` WHERE `student_id` = %s AND `deleted_at` IS NULL"
    params: list[object] = [student.id]
    if status:
        base_sql += " AND `status` = %s"
        count_sql += " AND `status` = %s"
        params.append(status)
    base_sql += " ORDER BY `created_at` DESC"
    return _paginate_models(ObservationRequest, base_sql, count_sql, params, page, per_page)


def get_dashboard_summary(student) -> dict:
    base_params = [student.id]
    counts = {
        "draft": _count(
            "SELECT COUNT(*) FROM `observation_requests` WHERE `student_id` = %s AND `deleted_at` IS NULL AND `status` = %s",
            [*base_params, ObservationRequest.STATUS_DRAFT],
        ),
        "menunggu": _count(
            "SELECT COUNT(*) FROM `observation_requests` WHERE `student_id` = %s AND `deleted_at` IS NULL AND `status` IN (%s, %s)",
            [*base_params, ObservationRequest.STATUS_MENUNGGU_DOSEN, ObservationRequest.STATUS_MENUNGGU_KAPRODI],
        ),
        "selesai": _count(
            "SELECT COUNT(*) FROM `observation_requests` WHERE `student_id` = %s AND `deleted_at` IS NULL AND `status` = %s",
            [*base_params, ObservationRequest.STATUS_SELESAI],
        ),
        "ditolak": _count(
            "SELECT COUNT(*) FROM `observation_requests` WHERE `student_id` = %s AND `deleted_at` IS NULL AND `status` IN (%s, %s)",
            [*base_params, ObservationRequest.STATUS_DITOLAK_DOSEN, ObservationRequest.STATUS_DITOLAK_KAPRODI],
        ),
    }
    recent = _fetch_all_models(
        ObservationRequest,
        "SELECT * FROM `observation_requests` WHERE `student_id` = %s AND `deleted_at` IS NULL ORDER BY `created_at` DESC LIMIT 5",
        base_params,
    )
    created_rows = db.fetchall(
        "SELECT `created_at` FROM `observation_requests` WHERE `student_id` = %s AND `deleted_at` IS NULL",
        base_params,
    )
    return {
        "total": _count(
            "SELECT COUNT(*) FROM `observation_requests` WHERE `student_id` = %s AND `deleted_at` IS NULL",
            base_params,
        ),
        "counts": counts,
        "recent": recent,
        "monthly_trend": _monthly_trend([row["created_at"] for row in created_rows], lambda dt: dt),
    }


def get_lecturer_request(request_id, lecturer):
    return _fetch_one_model(
        ObservationRequest,
        "SELECT * FROM `observation_requests` WHERE `id` = %s AND `lecturer_id` = %s AND `deleted_at` IS NULL LIMIT 1",
        (request_id, lecturer.id),
    )


def list_incoming_for_lecturer(lecturer, page: int = 1, per_page: int = PER_PAGE):
    return _paginate_models(
        ObservationRequest,
        "SELECT * FROM `observation_requests` WHERE `lecturer_id` = %s AND `status` = %s AND `deleted_at` IS NULL",
        "SELECT COUNT(*) FROM `observation_requests` WHERE `lecturer_id` = %s AND `status` = %s AND `deleted_at` IS NULL",
        [lecturer.id, ObservationRequest.STATUS_MENUNGGU_DOSEN],
        page,
        per_page,
    )


def approve_by_lecturer(obs: ObservationRequest, actor_user, note: str | None) -> ObservationRequest:
    if not obs.is_waiting_lecturer:
        raise ObservationRequestError("Pengajuan ini sudah diproses sebelumnya dan tidak dapat disetujui ulang.")

    clean_note = (note or "").strip() or None
    obs.status = ObservationRequest.STATUS_MENUNGGU_KAPRODI
    _update_instance(obs)
    _insert_instance(
        ApprovalLog(
            observation_request_id=obs.id,
            actor_user_id=actor_user.id,
            role_at_approval=ApprovalLog.ROLE_DOSEN,
            action=ApprovalLog.ACTION_APPROVE,
            note=clean_note,
        )
    )
    _insert_instance(
        activity_log_service.build_approve(
            actor_user,
            f"Dosen '{actor_user.email}' menyetujui pengajuan id={obs.id} (diteruskan ke Kaprodi).",
        )
    )
    email_log = email_service.notify_lecturer_approved(obs, clean_note)
    _insert_instance(email_log)
    _insert_instance(
        activity_log_service.build_send_email(
            actor_user,
            f"Notifikasi persetujuan dosen untuk pengajuan id={obs.id} ke '{email_log.recipient_email}': {email_log.status}.",
        )
    )
    db.commit()
    return obs


def reject_by_lecturer(obs: ObservationRequest, actor_user, note: str | None) -> ObservationRequest:
    if not obs.is_waiting_lecturer:
        raise ObservationRequestError("Pengajuan ini sudah diproses sebelumnya dan tidak dapat ditolak ulang.")

    clean_note = (note or "").strip() or None
    obs.status = ObservationRequest.STATUS_DITOLAK_DOSEN
    obs.rejection_note = clean_note
    _update_instance(obs)
    _insert_instance(
        ApprovalLog(
            observation_request_id=obs.id,
            actor_user_id=actor_user.id,
            role_at_approval=ApprovalLog.ROLE_DOSEN,
            action=ApprovalLog.ACTION_REJECT,
            note=clean_note,
        )
    )
    _insert_instance(
        activity_log_service.build_reject(actor_user, f"Dosen '{actor_user.email}' menolak pengajuan id={obs.id}.")
    )
    email_log = email_service.notify_lecturer_rejected(obs)
    _insert_instance(email_log)
    _insert_instance(
        activity_log_service.build_send_email(
            actor_user,
            f"Notifikasi penolakan dosen untuk pengajuan id={obs.id} ke '{email_log.recipient_email}': {email_log.status}.",
        )
    )
    db.commit()
    return obs


def list_approval_history_for_lecturer(user_id, page: int = 1, per_page: int = PER_PAGE):
    return _paginate_models(
        ApprovalLog,
        "SELECT * FROM `approval_logs` WHERE `actor_user_id` = %s AND `role_at_approval` = %s",
        "SELECT COUNT(*) FROM `approval_logs` WHERE `actor_user_id` = %s AND `role_at_approval` = %s",
        [user_id, ApprovalLog.ROLE_DOSEN],
        page,
        per_page,
    )


def get_dashboard_summary_for_lecturer(lecturer, user) -> dict:
    base_params = [lecturer.id]
    waiting = _count(
        "SELECT COUNT(*) FROM `observation_requests` WHERE `lecturer_id` = %s AND `deleted_at` IS NULL AND `status` = %s",
        [*base_params, ObservationRequest.STATUS_MENUNGGU_DOSEN],
    )
    counts = {
        "menunggu": waiting,
        "disetujui": _count(
            "SELECT COUNT(*) FROM `approval_logs` WHERE `actor_user_id` = %s AND `role_at_approval` = %s AND `action` = %s",
            [user.id, ApprovalLog.ROLE_DOSEN, ApprovalLog.ACTION_APPROVE],
        ),
        "ditolak": _count(
            "SELECT COUNT(*) FROM `approval_logs` WHERE `actor_user_id` = %s AND `role_at_approval` = %s AND `action` = %s",
            [user.id, ApprovalLog.ROLE_DOSEN, ApprovalLog.ACTION_REJECT],
        ),
    }
    decision_rows = db.fetchall(
        "SELECT `observation_requests`.`created_at`, `approval_logs`.`created_at` AS `decision_at` "
        "FROM `observation_requests` "
        "JOIN `approval_logs` ON `approval_logs`.`observation_request_id` = `observation_requests`.`id` "
        "WHERE `approval_logs`.`actor_user_id` = %s AND `approval_logs`.`role_at_approval` = %s",
        (user.id, ApprovalLog.ROLE_DOSEN),
    )
    recent = _fetch_all_models(
        ObservationRequest,
        "SELECT * FROM `observation_requests` WHERE `lecturer_id` = %s AND `deleted_at` IS NULL AND `status` = %s ORDER BY `created_at` ASC LIMIT 5",
        [lecturer.id, ObservationRequest.STATUS_MENUNGGU_DOSEN],
    )
    return {
        "total": _count(
            "SELECT COUNT(*) FROM `observation_requests` WHERE `lecturer_id` = %s AND `deleted_at` IS NULL",
            base_params,
        ),
        "counts": counts,
        "recent": recent,
        "avg_response_hours": _avg_response_hours([(row["created_at"], row["decision_at"]) for row in decision_rows]),
        "monthly_trend": _monthly_trend([row["decision_at"] for row in decision_rows], lambda pair: pair),
    }


def get_head_of_program_request(request_id, head_of_program):
    return _fetch_one_model(
        ObservationRequest,
        "SELECT * FROM `observation_requests` WHERE `id` = %s AND `study_program_id` = %s AND `deleted_at` IS NULL LIMIT 1",
        (request_id, head_of_program.study_program_id),
    )


def list_incoming_for_head_of_program(head_of_program, page: int = 1, per_page: int = PER_PAGE):
    return _paginate_models(
        ObservationRequest,
        "SELECT * FROM `observation_requests` WHERE `study_program_id` = %s AND `status` = %s AND `deleted_at` IS NULL",
        "SELECT COUNT(*) FROM `observation_requests` WHERE `study_program_id` = %s AND `status` = %s AND `deleted_at` IS NULL",
        [head_of_program.study_program_id, ObservationRequest.STATUS_MENUNGGU_KAPRODI],
        page,
        per_page,
    )




def list_approval_history_for_head_of_program(user_id, page: int = 1, per_page: int = PER_PAGE):
    return _paginate_models(
        ApprovalLog,
        "SELECT * FROM `approval_logs` WHERE `actor_user_id` = %s AND `role_at_approval` = %s",
        "SELECT COUNT(*) FROM `approval_logs` WHERE `actor_user_id` = %s AND `role_at_approval` = %s",
        [user_id, ApprovalLog.ROLE_KAPRODI],
        page,
        per_page,
    )


def get_dashboard_summary_for_head_of_program(head_of_program, user) -> dict:
    counts = {
        "menunggu": _count(
            "SELECT COUNT(*) FROM `observation_requests` WHERE `study_program_id` = %s AND `deleted_at` IS NULL AND `status` = %s",
            [head_of_program.study_program_id, ObservationRequest.STATUS_MENUNGGU_KAPRODI],
        ),
        "disetujui": _count(
            "SELECT COUNT(*) FROM `approval_logs` WHERE `actor_user_id` = %s AND `role_at_approval` = %s AND `action` = %s",
            [user.id, ApprovalLog.ROLE_KAPRODI, ApprovalLog.ACTION_APPROVE],
        ),
        "ditolak": _count(
            "SELECT COUNT(*) FROM `approval_logs` WHERE `actor_user_id` = %s AND `role_at_approval` = %s AND `action` = %s",
            [user.id, ApprovalLog.ROLE_KAPRODI, ApprovalLog.ACTION_REJECT],
        ),
    }
    decision_rows = db.fetchall(
        "SELECT `observation_requests`.`created_at`, `approval_logs`.`created_at` AS `decision_at` "
        "FROM `observation_requests` "
        "JOIN `approval_logs` ON `approval_logs`.`observation_request_id` = `observation_requests`.`id` "
        "WHERE `approval_logs`.`actor_user_id` = %s AND `approval_logs`.`role_at_approval` = %s",
        (user.id, ApprovalLog.ROLE_KAPRODI),
    )
    recent = _fetch_all_models(
        ObservationRequest,
        "SELECT * FROM `observation_requests` WHERE `study_program_id` = %s AND `deleted_at` IS NULL AND `status` = %s ORDER BY `created_at` ASC LIMIT 5",
        [head_of_program.study_program_id, ObservationRequest.STATUS_MENUNGGU_KAPRODI],
    )
    return {
        "total": _count(
            "SELECT COUNT(*) FROM `observation_requests` WHERE `study_program_id` = %s AND `deleted_at` IS NULL",
            (head_of_program.study_program_id,),
        ),
        "counts": counts,
        "recent": recent,
        "avg_response_hours": _avg_response_hours([(row["created_at"], row["decision_at"]) for row in decision_rows]),
        "monthly_trend": _monthly_trend([row["decision_at"] for row in decision_rows], lambda pair: pair),
    }


from datetime import date, datetime
from types import SimpleNamespace


def _blank_user(name="", email="", user_id=None):
    return SimpleNamespace(id=user_id, name=name or "", username=email or "", email=email or "")


def _request_status(row):
    lecturer_status = (row.get("status_dosen") or "").strip().lower()
    head_status = (row.get("status_kaprodi") or "").strip().lower()
    request_status = (row.get("status_pengajuan") or "").strip()
    if lecturer_status == "ditolak":
        return "Ditolak Dosen"
    if head_status == "ditolak":
        return "Ditolak Kaprodi"
    if head_status == "menunggu":
        return "Menunggu Kaprodi"
    if lecturer_status == "menunggu":
        return "Menunggu Dosen"
    if request_status.lower() == "disetujui":
        return "Selesai"
    if request_status.lower() == "ditolak":
        return "Ditolak"
    return request_status or "Menunggu Dosen"


def _request_from_pengajuan(row):
    created_at = row.get("tanggal_pengajuan") or datetime.now()
    student = SimpleNamespace(
        id=row.get("nim"),
        nim=row.get("nim") or "",
        semester=1,
        study_program_id=row.get("id_program_studi"),
        user=_blank_user(row.get("nama_mahasiswa"), row.get("email")),
    )
    lecturer = SimpleNamespace(
        id=row.get("id_dosen"),
        nidn=row.get("dosen_nidn") or "",
        user=_blank_user(row.get("dosen_nama"), row.get("dosen_username"), row.get("dosen_user_id")),
        signature_url=row.get("dosen_signature_url") or "",
    )
    study_program = SimpleNamespace(
        id=row.get("id_program_studi"),
        name=row.get("nama_program_studi") or "",
        code="",
    )
    status = _request_status(row)
    rejection_note = row.get("catatan_dosen") or row.get("catatan_kaprodi")
    try:
        group_members = json.loads(row.get("anggota_kelompok") or "[]")
    except (TypeError, ValueError):
        group_members = []
    return SimpleNamespace(
        id=row["id_pengajuan"],
        student=student,
        lecturer=lecturer,
        study_program=study_program,
        student_id=row.get("nim"),
        lecturer_id=row.get("id_dosen"),
        lecturer_type=row.get("jenis_dosen") or "Internal",
        document_number=row.get("nomor_dokumen"),
        document_type=row.get("jenis_dokumen"),
        head_of_program_name=row.get("nama_kaprodi") or "-",
        head_of_program_signature_url=row.get("kaprodi_signature_url") or "",
        study_program_id=row.get("id_program_studi"),
        destination_institution=row.get("nama_instansi") or "",
        institution_address=row.get("alamat_instansi") or "",
        topic=row.get("nama_penerima") or "",
        course_name=row.get("mata_kuliah") or "",
        submission_date=row.get("tanggal_observasi") or created_at,
        created_at=created_at,
        status=status,
        status_dosen=row.get("status_dosen"),
        status_kaprodi=row.get("status_kaprodi"),
        status_pengajuan=row.get("status_pengajuan"),
        rejection_note=rejection_note,
        group_members=group_members,
        letter_number=SimpleNamespace(formatted_number=row.get("nomor_dokumen")) if row.get("nomor_dokumen") else None,
        pdf_final_url=None,
        is_waiting_lecturer=(row.get("status_dosen") or "").strip().lower() == "menunggu",
        is_waiting_head_of_program=(
            (row.get("status_dosen") or "").strip().lower() == "disetujui"
            and (row.get("status_kaprodi") or "").strip().lower() == "menunggu"
        ),
        is_rejected="ditolak" in status.lower(),
        is_draft=False,
        is_editable=False,
    )


def _pengajuan_select():
    return (
        "SELECT po.*, ps.`nama_program_studi`, "
        "d.`nidn` AS `dosen_nidn`, COALESCE(NULLIF(d.`jenis_dosen`, ''), 'Internal') AS `jenis_dosen`, "
        "du.`id_pengguna` AS `dosen_user_id`, "
        "du.`nama` AS `dosen_nama`, du.`username` AS `dosen_username`, "
        "ds.`nomor_dokumen` AS `nomor_dokumen`, ds.`jenis_dokumen` AS `jenis_dokumen`, "
        "ku.`nama` AS `nama_kaprodi`, "
        "fc_dosen.`secure_url` AS `dosen_signature_url`, "
        "fc_kaprodi.`secure_url` AS `kaprodi_signature_url` "
        "FROM `pengajuan_observasi` AS po "
        "LEFT JOIN `program_studi` AS ps ON ps.`id_program_studi` = po.`id_program_studi` "
        "LEFT JOIN `dosen` AS d ON d.`id_dosen` = po.`id_dosen` "
        "LEFT JOIN `pengguna` AS du ON du.`id_pengguna` = d.`id_pengguna` "
        "LEFT JOIN `dokumen_surat` AS ds ON ds.`id_pengajuan` = po.`id_pengajuan` "
        "LEFT JOIN `kaprodi` AS k ON k.`id_program_studi` = po.`id_program_studi` "
        "LEFT JOIN `pengguna` AS ku ON ku.`id_pengguna` = k.`id_pengguna` "
        "LEFT JOIN `file_cloudinary` AS fc_dosen ON fc_dosen.`id_file` = d.`id_file_tanda_tangan` "
        "LEFT JOIN `file_cloudinary` AS fc_kaprodi ON fc_kaprodi.`id_file` = k.`id_file_tanda_tangan` "
    )


def _paginate_pengajuan(where_sql, params, page: int, per_page: int = PER_PAGE, order_sql=None):
    page = max(1, page)
    count_sql = (
        "SELECT COUNT(*) FROM `pengajuan_observasi` AS po "
        "LEFT JOIN `dosen` AS d ON d.`id_dosen` = po.`id_dosen` "
        "LEFT JOIN `pengguna` AS du ON du.`id_pengguna` = d.`id_pengguna` "
        "LEFT JOIN `dokumen_surat` AS ds ON ds.`id_pengajuan` = po.`id_pengajuan` "
        f"{where_sql}"
    )
    total = int(db.scalar(count_sql, params) or 0)
    offset = (page - 1) * per_page
    rows = db.fetchall(
        f"{_pengajuan_select()} {where_sql} {order_sql or 'ORDER BY po.`tanggal_pengajuan` DESC'} LIMIT %s OFFSET %s",
        list(params or []) + [per_page, offset],
    )
    return Pagination([_request_from_pengajuan(row) for row in rows], page, per_page, total)


def approval_logs_for_request(request_id):
    row = db.fetchone(
        "SELECT po.*, dpu.`nama` AS `dosen_nama`, kpu.`nama` AS `kaprodi_nama` "
        "FROM `pengajuan_observasi` AS po "
        "LEFT JOIN `dosen` AS d ON d.`id_dosen` = po.`id_dosen` "
        "LEFT JOIN `pengguna` AS dpu ON dpu.`id_pengguna` = d.`id_pengguna` "
        "LEFT JOIN `program_studi` AS ps ON ps.`id_program_studi` = po.`id_program_studi` "
        "LEFT JOIN `kaprodi` AS k ON k.`id_program_studi` = ps.`id_program_studi` "
        "LEFT JOIN `pengguna` AS kpu ON kpu.`id_pengguna` = k.`id_pengguna` "
        "WHERE po.`id_pengajuan` = %s LIMIT 1",
        (request_id,),
    )
    if row is None:
        return []
    logs = []
    if (row.get("status_dosen") or "").strip().lower() in {"disetujui", "ditolak"}:
        logs.append(
            SimpleNamespace(
                actor=_blank_user(row.get("dosen_nama")),
                role_at_approval="dosen",
                action="approve" if row["status_dosen"].lower() == "disetujui" else "reject",
                note=row.get("catatan_dosen"),
                created_at=row.get("tanggal_pengajuan") or datetime.now(),
            )
        )
    if (row.get("status_kaprodi") or "").strip().lower() in {"disetujui", "ditolak"}:
        logs.append(
            SimpleNamespace(
                actor=_blank_user(row.get("kaprodi_nama")),
                role_at_approval="kaprodi",
                action="approve" if row["status_kaprodi"].lower() == "disetujui" else "reject",
                note=row.get("catatan_kaprodi"),
                created_at=row.get("tanggal_pengajuan") or datetime.now(),
            )
        )
    return logs


def get_lecturer_choices(study_program_id):
    rows = db.fetchall(
        "SELECT d.`id_dosen`, d.`id_program_studi`, d.`nidn`, "
        "COALESCE(NULLIF(d.`jenis_dosen`, ''), 'Internal') AS `jenis_dosen`, "
        "u.`id_pengguna`, u.`nama`, u.`username`, u.`status_aktif` "
        "FROM `dosen` AS d "
        "JOIN `pengguna` AS u ON u.`id_pengguna` = d.`id_pengguna` "
        "WHERE d.`id_program_studi` = %s AND u.`status_aktif` = 1 "
        "ORDER BY u.`nama` ASC",
        (study_program_id,),
    )
    return [
        SimpleNamespace(
            id=row["id_dosen"],
            study_program_id=row["id_program_studi"],
            nidn=row["nidn"],
            lecturer_type=row["jenis_dosen"],
            user=_blank_user(row["nama"], row["username"], row["id_pengguna"]),
        )
        for row in rows
    ]


def get_or_create_student_by_nim(nim: str, study_program_id: int):
    clean_nim = (nim or "").strip()
    if not clean_nim:
        return None
    return SimpleNamespace(
        id=clean_nim,
        nim=clean_nim,
        study_program_id=study_program_id,
        user=_blank_user(clean_nim),
    )


def _format_document_number(sequence: int, document_date: date | None = None) -> str:
    document_date = document_date or date.today()
    return f"{sequence:04d}/OBS-FTI/{document_date:%d/%m/%Y}"


def preview_document_number() -> str:
    """Calon nomor untuk preview; hanya membaca data tanpa INSERT."""
    next_sequence = int(
        db.scalar("SELECT COALESCE(MAX(`nomor_urut`), 0) + 1 FROM `dokumen_surat`") or 1
    )
    return _format_document_number(next_sequence)


def ensure_document_number(request_id: int, document_type: str) -> str:
    """Ambil nomor resmi yang ada atau buat satu nomor baru secara transaksional."""
    if document_type not in {"Hard File", "TTD Digital"}:
        raise ObservationRequestError("Jenis dokumen tidak valid.")

    existing = db.fetchone(
        "SELECT `nomor_dokumen`, `jenis_dokumen` FROM `dokumen_surat` WHERE `id_pengajuan` = %s LIMIT 1",
        (request_id,),
    )
    if existing:
        if existing.get("jenis_dokumen") != document_type:
            db.execute(
                "UPDATE `dokumen_surat` SET `jenis_dokumen` = %s WHERE `id_pengajuan` = %s",
                (document_type, request_id),
            )
            db.commit()
        return existing["nomor_dokumen"]

    try:
        next_sequence = int(
            db.scalar("SELECT COALESCE(MAX(`nomor_urut`), 0) + 1 FROM `dokumen_surat` FOR UPDATE") or 1
        )
        document_number = _format_document_number(next_sequence)
        db.insert(
            "INSERT INTO `dokumen_surat` (`id_pengajuan`, `nomor_urut`, `nomor_dokumen`, `jenis_dokumen`) "
            "VALUES (%s, %s, %s, %s)",
            (request_id, next_sequence, document_number, document_type),
        )
        db.commit()
        return document_number
    except Exception as exc:
        db.rollback()
        existing = db.fetchone(
            "SELECT `nomor_dokumen` FROM `dokumen_surat` WHERE `id_pengajuan` = %s LIMIT 1",
            (request_id,),
        )
        if existing:
            return existing["nomor_dokumen"]
        raise ObservationRequestError("Gagal membuat nomor dokumen.") from exc


def complete_hard_file_print(request_id: int):
    """Finalisasi setelah dialog cetak browser ditutup; aman dipanggil berulang."""
    obs = get_request_by_id(request_id)
    if obs is None:
        raise ObservationRequestError("Pengajuan tidak ditemukan.")

    document_number = ensure_document_number(request_id, "Hard File")
    db.execute(
        "UPDATE `pengajuan_observasi` SET `status_pengajuan` = %s WHERE `id_pengajuan` = %s",
        ("Selesai", request_id),
    )
    db.commit()
    return document_number


def create_draft(student, form, group_members="[]"):
    request_id = db.insert(
        "INSERT INTO `pengajuan_observasi` "
        "(`nama_mahasiswa`, `nim`, `email`, `id_program_studi`, `id_dosen`, `nama_penerima`, "
        "`nama_instansi`, `alamat_instansi`, `mata_kuliah`, `tanggal_observasi`, `anggota_kelompok`, "
        "`status_dosen`, `status_kaprodi`, `status_pengajuan`) "
        "VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)",
        (
            student.user.name or student.nim,
            student.nim,
            getattr(student.user, "email", "") or "",
            form.study_program_id.data,
            form.lecturer_id.data,
            form.topic.data.strip(),
            form.destination_institution.data.strip(),
            form.institution_address.data.strip(),
            form.course_name.data.strip(),
            form.submission_date.data,
            group_members,
            "Menunggu",
            "Menunggu",
            "Menunggu",
        ),
    )
    db.commit()
    return get_request_by_id(request_id)


def send_to_lecturer(obs):
    return obs


def get_request_by_id(request_id):
    row = db.fetchone(f"{_pengajuan_select()} WHERE po.`id_pengajuan` = %s LIMIT 1", (request_id,))
    return _request_from_pengajuan(row) if row else None


def get_lecturer_request(request_id, lecturer):
    row = db.fetchone(
        f"{_pengajuan_select()} WHERE po.`id_pengajuan` = %s AND po.`id_dosen` = %s LIMIT 1",
        (request_id, lecturer.id),
    )
    return _request_from_pengajuan(row) if row else None


def list_incoming_for_lecturer(lecturer, page: int = 1, per_page: int = PER_PAGE):
    return _paginate_pengajuan(
        "WHERE po.`id_dosen` = %s AND LOWER(po.`status_dosen`) = %s",
        [lecturer.id, "menunggu"],
        page,
        per_page,
        "ORDER BY po.`tanggal_pengajuan` ASC",
    )


def approve_by_lecturer(obs, actor_user, note: str | None):
    if not obs.is_waiting_lecturer:
        raise ObservationRequestError("Pengajuan ini sudah diproses sebelumnya dan tidak dapat disetujui ulang.")
    db.execute(
        "UPDATE `pengajuan_observasi` SET `status_dosen` = %s, `catatan_dosen` = %s, "
        "`status_kaprodi` = %s, `status_pengajuan` = %s WHERE `id_pengajuan` = %s",
        ("Disetujui", (note or "").strip() or None, "Menunggu", "Menunggu", obs.id),
    )
    db.commit()
    return get_request_by_id(obs.id)


def reject_by_lecturer(obs, actor_user, note: str | None):
    if not obs.is_waiting_lecturer:
        raise ObservationRequestError("Pengajuan ini sudah diproses sebelumnya dan tidak dapat ditolak ulang.")
    db.execute(
        "UPDATE `pengajuan_observasi` SET `status_dosen` = %s, `catatan_dosen` = %s, "
        "`status_pengajuan` = %s WHERE `id_pengajuan` = %s",
        ("Ditolak", (note or "").strip() or None, "Ditolak", obs.id),
    )
    db.commit()
    return get_request_by_id(obs.id)


def list_approval_history_for_lecturer(user_id, page: int = 1, per_page: int = PER_PAGE):
    row = db.fetchone("SELECT `id_dosen` FROM `dosen` WHERE `id_pengguna` = %s LIMIT 1", (user_id,))
    if row is None:
        return Pagination([], max(1, page), per_page, 0)
    return _paginate_pengajuan(
        "WHERE po.`id_dosen` = %s AND LOWER(po.`status_dosen`) IN (%s, %s)",
        [row["id_dosen"], "disetujui", "ditolak"],
        page,
        per_page,
    )


def approval_history_for_lecturer(lecturer, limit: int = 100):
    return _paginate_pengajuan(
        "WHERE po.`id_dosen` = %s AND LOWER(po.`status_dosen`) IN (%s, %s)",
        [lecturer.id, "disetujui", "ditolak"],
        1,
        limit,
        "ORDER BY po.`tanggal_pengajuan` ASC",
    ).items


def get_dashboard_summary_for_lecturer(lecturer, user) -> dict:
    total = _count("SELECT COUNT(*) FROM `pengajuan_observasi` WHERE `id_dosen` = %s", (lecturer.id,))
    counts = {
        "menunggu": _count(
            "SELECT COUNT(*) FROM `pengajuan_observasi` WHERE `id_dosen` = %s AND LOWER(`status_dosen`) = %s",
            (lecturer.id, "menunggu"),
        ),
        "disetujui": _count(
            "SELECT COUNT(*) FROM `pengajuan_observasi` WHERE `id_dosen` = %s AND LOWER(`status_dosen`) = %s",
            (lecturer.id, "disetujui"),
        ),
        "ditolak": _count(
            "SELECT COUNT(*) FROM `pengajuan_observasi` WHERE `id_dosen` = %s AND LOWER(`status_dosen`) = %s",
            (lecturer.id, "ditolak"),
        ),
    }
    recent = _paginate_pengajuan(
        "WHERE po.`id_dosen` = %s AND LOWER(po.`status_dosen`) = %s",
        [lecturer.id, "menunggu"],
        1,
        5,
        "ORDER BY po.`tanggal_pengajuan` ASC",
    ).items
    return {"total": total, "counts": counts, "recent": recent, "avg_response_hours": 0, "monthly_trend": []}


def get_head_of_program_request(request_id, head_of_program):
    row = db.fetchone(
        f"{_pengajuan_select()} WHERE po.`id_pengajuan` = %s AND po.`id_program_studi` = %s LIMIT 1",
        (request_id, head_of_program.study_program_id),
    )
    return _request_from_pengajuan(row) if row else None


def list_incoming_for_head_of_program(head_of_program, page: int = 1, per_page: int = PER_PAGE):
    return _paginate_pengajuan(
        "WHERE po.`id_program_studi` = %s AND LOWER(po.`status_dosen`) = %s AND LOWER(po.`status_kaprodi`) = %s",
        [head_of_program.study_program_id, "disetujui", "menunggu"],
        page,
        per_page,
        "ORDER BY po.`tanggal_pengajuan` ASC",
    )


def approve_by_head_of_program(obs, actor_user, note: str | None):
    if not obs.is_waiting_head_of_program:
        raise ObservationRequestError("Pengajuan ini sudah diproses sebelumnya dan tidak dapat disetujui ulang.")
    try:
        db.execute(
            "UPDATE `pengajuan_observasi` SET `status_kaprodi` = %s, `catatan_kaprodi` = %s, "
            "`status_pengajuan` = %s WHERE `id_pengajuan` = %s",
            ("Disetujui", (note or "").strip() or None, "Disetujui", obs.id),
        )

        # Ensure there is a document number record for this request (dokumen_surat).
        try:
            document_number = ensure_document_number(obs.id, "TTD Digital")
        except ObservationRequestError:
            # ensure_document_number already logged/rolled back; re-raise to caller
            db.rollback()
            raise

        # ensure the returned observation object has a letter_number usable by email templates
        try:
            obs.letter_number = SimpleNamespace(formatted_number=document_number)
        except Exception:
            obs.letter_number = SimpleNamespace(formatted_number=document_number)

        # Activity log (use model-based insertion helper)
        try:
            _insert_instance(
                activity_log_service.build_approve(
                    actor_user,
                    f"Kaprodi '{actor_user.email}' menyetujui pengajuan id={obs.id} (persetujuan akhir).",
                )
            )
        except Exception:
            # best-effort; continue
            try:
                current_app.logger.exception("Gagal mencatat activity_log untuk persetujuan kaprodi id=%s", obs.id)
            except RuntimeError:
                import logging as _log

                _log.getLogger(__name__).exception("Gagal mencatat activity_log untuk persetujuan kaprodi id=%s", obs.id)
        db.commit()
        return get_request_by_id(obs.id)
    except Exception:
        db.rollback()
        raise


def _fetch_bytes_from_url(url: str, timeout: int = 20) -> bytes:
    """Ambil kembali isi file dari URL publik (dipakai untuk lampiran email
    setelah PDF final diunggah browser LANGSUNG ke Cloudinary)."""
    import urllib.request

    with urllib.request.urlopen(url, timeout=timeout) as response:  # noqa: S310 - URL dari Cloudinary sendiri
        return response.read()


def upload_final_pdf(obs, *, secure_url: str, public_id: str, resource_type: str = "raw") -> dict:
    """Catat PDF final yang sudah diunggah BROWSER LANGSUNG ke Cloudinary
    (bukan lewat backend lagi -- lihat cloudinary_service.generate_signed_upload_params)
    setelah persetujuan Kaprodi, lalu kirim email notifikasi dengan lampiran PDF."""
    if (getattr(obs, "status_kaprodi", "") or "").strip().lower() != "disetujui":
        raise ObservationRequestError("PDF final hanya dapat diunggah setelah persetujuan Kaprodi.")

    try:
        upload_result = cloudinary_service.register_official_letter_pdf(
            obs.id, secure_url=secure_url, public_id=public_id, resource_type=resource_type
        )
        cursor = db.execute(
            "UPDATE `dokumen_surat` SET `id_file_pdf` = %s, `tanggal_upload_pdf` = NOW() "
            "WHERE `id_pengajuan` = %s",
            (upload_result["file_id"], obs.id),
        )
        if cursor.rowcount != 1:
            raise ObservationRequestError("Dokumen surat untuk pengajuan ini tidak ditemukan.")

        # Ensure obs has letter_number for email subject/template; prefer existing value.
        if getattr(obs, "letter_number", None) is None:
            # try to populate from dokumen_surat.nomor_dokumen
            row = db.fetchone("SELECT `nomor_dokumen` FROM `dokumen_surat` WHERE `id_pengajuan` = %s LIMIT 1", (obs.id,))
            docnum = row.get("nomor_dokumen") if row else None
            obs.letter_number = SimpleNamespace(formatted_number=docnum) if docnum else None

        db.commit()

        # PDF sudah ada di Cloudinary (diunggah langsung oleh browser demi
        # menghindari limit 413 Vercel), tapi email (Resend) tetap perlu
        # melampirkan file-nya sebagai bytes -- ambil kembali dari secure_url
        # yang sama. Kalau proses ambil-ulang ini gagal, JANGAN gagalkan
        # seluruh proses (PDF & data sudah tersimpan dengan benar) --
        # cukup catat sebagai EmailLog gagal, sama seperti pola gagal-email
        # yang sudah ada di bawah.
        try:
            pdf_bytes = _fetch_bytes_from_url(secure_url)
        except Exception as exc:
            try:
                current_app.logger.error(
                    "Gagal mengambil kembali PDF final dari Cloudinary untuk lampiran email id=%s: %s", obs.id, exc
                )
            except RuntimeError:
                import logging as _log

                _log.getLogger(__name__).error(
                    "Gagal mengambil kembali PDF final dari Cloudinary untuk lampiran email id=%s: %s", obs.id, exc
                )
            pdf_bytes = None

        # Send notification email with PDF attachment; do NOT fail overall if email fails.
        try:
            if pdf_bytes is None:
                raise ObservationRequestError("PDF bytes tidak tersedia (gagal diambil ulang dari Cloudinary).")
            email_log = email_service.notify_official_letter_issued(obs, pdf_bytes)
        except Exception as exc:
            # If email_service raises (shouldn't in normal flow), convert to failed EmailLog
            try:
                current_app.logger.error("Gagal mengirim email surat resmi untuk pengajuan id=%s: %s", obs.id, exc)
            except RuntimeError:
                import logging as _log

                _log.getLogger(__name__).error("Gagal mengirim email surat resmi untuk pengajuan id=%s: %s", obs.id, exc)
            from backend.models.email_log import EmailLog
            email_log = EmailLog(
                observation_request_id=obs.id,
                recipient_email=getattr(getattr(obs, 'student', None), 'user', SimpleNamespace(email='')).email,
                subject=f"Surat Izin Observasi Resmi Terbit — {getattr(getattr(obs, 'letter_number', None), 'formatted_number', '')}",
                status=EmailLog.STATUS_FAILED,
                error_message=str(exc)[:500],
            )

        # Persist email log and activity log in same transactional flow
        try:
            _insert_instance(email_log)
            _insert_instance(
                activity_log_service.build_send_email(
                    None,
                    f"Notifikasi pengiriman surat resmi untuk pengajuan id={obs.id} ke '{getattr(email_log, 'recipient_email', '')}': {getattr(email_log, 'status', '')}.",
                )
            )
        except Exception:
            try:
                current_app.logger.exception("Gagal mencatat EmailLog/activity_log untuk pengajuan id=%s", obs.id)
            except RuntimeError:
                import logging as _log

                _log.getLogger(__name__).exception("Gagal mencatat EmailLog/activity_log untuk pengajuan id=%s", obs.id)

        db.commit()
        return upload_result
    except (ObservationRequestError, cloudinary_service.CloudinaryServiceError):
        db.rollback()
        raise
    except Exception as exc:
        db.rollback()
        raise ObservationRequestError(f"Gagal menyimpan PDF final: {exc}") from exc


def reject_by_head_of_program(obs, actor_user, note: str | None):
    if not obs.is_waiting_head_of_program:
        raise ObservationRequestError("Pengajuan ini sudah diproses sebelumnya dan tidak dapat ditolak ulang.")
    db.execute(
        "UPDATE `pengajuan_observasi` SET `status_kaprodi` = %s, `catatan_kaprodi` = %s, "
        "`status_pengajuan` = %s WHERE `id_pengajuan` = %s",
        ("Ditolak", (note or "").strip() or None, "Ditolak", obs.id),
    )

    # notify applicant that Kaprodi rejected the request (email)
    try:
        email_log = email_service.notify_head_of_program_rejected(obs)
        try:
            _insert_instance(email_log)
            _insert_instance(
                activity_log_service.build_send_email(
                    actor_user,
                    f"Notifikasi penolakan kaprodi untuk pengajuan id={obs.id} ke '{email_log.recipient_email}': {email_log.status}.",
                )
            )
        except Exception:
            try:
                current_app.logger.exception("Gagal mencatat EmailLog/activity_log untuk penolakan kaprodi id=%s", obs.id)
            except RuntimeError:
                import logging as _log

                _log.getLogger(__name__).exception("Gagal mencatat EmailLog/activity_log untuk penolakan kaprodi id=%s", obs.id)
    except Exception:
        try:
            current_app.logger.exception("Gagal mengirim notifikasi penolakan kaprodi untuk pengajuan id=%s", obs.id)
        except RuntimeError:
            import logging as _log

            _log.getLogger(__name__).exception("Gagal mengirim notifikasi penolakan kaprodi untuk pengajuan id=%s", obs.id)

    db.commit()
    return get_request_by_id(obs.id)


def list_approval_history_for_head_of_program(user_id, page: int = 1, per_page: int = PER_PAGE):
    row = db.fetchone("SELECT `id_program_studi` FROM `kaprodi` WHERE `id_pengguna` = %s LIMIT 1", (user_id,))
    if row is None:
        return Pagination([], max(1, page), per_page, 0)
    return _paginate_pengajuan(
        "WHERE po.`id_program_studi` = %s AND LOWER(po.`status_kaprodi`) IN (%s, %s)",
        [row["id_program_studi"], "disetujui", "ditolak"],
        page,
        per_page,
    )


def approval_history_for_head_of_program(head_of_program, limit: int = 100):
    return _paginate_pengajuan(
        "WHERE po.`id_program_studi` = %s AND LOWER(po.`status_kaprodi`) IN (%s, %s)",
        [head_of_program.study_program_id, "disetujui", "ditolak"],
        1,
        limit,
        "ORDER BY po.`tanggal_pengajuan` ASC",
    ).items


def get_dashboard_summary_for_head_of_program(head_of_program, user) -> dict:
    total = _count(
        "SELECT COUNT(*) FROM `pengajuan_observasi` WHERE `id_program_studi` = %s",
        (head_of_program.study_program_id,),
    )
    counts = {
        "menunggu": _count(
            "SELECT COUNT(*) FROM `pengajuan_observasi` WHERE `id_program_studi` = %s "
            "AND LOWER(`status_dosen`) = %s AND LOWER(`status_kaprodi`) = %s",
            (head_of_program.study_program_id, "disetujui", "menunggu"),
        ),
        "disetujui": _count(
            "SELECT COUNT(*) FROM `pengajuan_observasi` WHERE `id_program_studi` = %s AND LOWER(`status_kaprodi`) = %s",
            (head_of_program.study_program_id, "disetujui"),
        ),
        "ditolak": _count(
            "SELECT COUNT(*) FROM `pengajuan_observasi` WHERE `id_program_studi` = %s AND LOWER(`status_kaprodi`) = %s",
            (head_of_program.study_program_id, "ditolak"),
        ),
    }
    recent = _paginate_pengajuan(
        "WHERE po.`id_program_studi` = %s AND LOWER(po.`status_dosen`) = %s AND LOWER(po.`status_kaprodi`) = %s",
        [head_of_program.study_program_id, "disetujui", "menunggu"],
        1,
        5,
        "ORDER BY po.`tanggal_pengajuan` ASC",
    ).items
    return {"total": total, "counts": counts, "recent": recent, "avg_response_hours": 0, "monthly_trend": []}
