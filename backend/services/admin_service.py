"""
backend/services/admin_service.py

Tahap 10 — Business logic Modul Admin: FR-40..FR-46 / UC-20..UC-31.
Mengikuti pola layer yang sama dengan `observation_service` (Tahap 5-7):
fokus pada logic domain (query & mutasi data + transaksi), pemetaan ke
flash message/redirect/abort HTTP adalah tugas `app/controllers/admin_controller.py`.

Isi:
- CRUD akun Mahasiswa/Dosen/Kaprodi (User + profil terkait, satu transaksi)  -> FR-40
- CRUD Program Studi                                                        -> FR-40
- Upload/kelola Kop Surat & Logo (Cloudinary)                                -> FR-41
- CRUD Template Surat (Cloudinary)                                           -> FR-42
- Setting margin surat default sistem (system_settings)                     -> FR-43
- Kelola Template Email (subjek & HTML, system_settings)                    -> FR-44
- Log aktivitas (read-only, filter & pagination)                            -> FR-45
- Ringkasan statistik dashboard                                             -> FR-46
"""

import json
import time
from datetime import datetime
from decimal import Decimal, InvalidOperation


def build_insert_sql_and_params(instance) -> tuple[str, list[object]]:
    """Bangun SQL INSERT eksplisit untuk objek domain tanpa mengandalkan session ORM."""
    model = instance.__class__
    pk_name = getattr(model, "_primary_key", None)
    columns = []
    values = []
    for name, column in getattr(model, "_columns", {}).items():
        if name == pk_name:
            continue
        value = getattr(instance, name, None)
        if value is None and getattr(column.kwargs, "get", lambda *_: None)("server_default") is not None:
            continue
        if name in {"created_at", "updated_at", "deleted_at"} and value is None:
            continue
        columns.append(f"`{column.column_name}`")
        values.append(value)
    placeholders = ", ".join(["%s"] * len(columns))
    sql = f"INSERT INTO `{model.__tablename__}` ({', '.join(columns)}) VALUES ({placeholders})"
    return sql, values


def build_update_sql_and_params(instance) -> tuple[str, list[object]]:
    """Bangun SQL UPDATE eksplisit untuk objek domain tanpa mengandalkan session ORM."""
    model = instance.__class__
    pk_name = getattr(model, "_primary_key", None)
    pk_value = getattr(instance, pk_name, None)
    if pk_value is None:
        raise ValueError("Cannot update model without primary key value.")
    fields = []
    values = []
    for name, column in getattr(model, "_columns", {}).items():
        if name == pk_name:
            continue
        fields.append(f"`{column.column_name}` = %s")
        values.append(getattr(instance, name, None))
    if not fields:
        return "", []
    values.append(pk_value)
    sql = f"UPDATE `{model.__tablename__}` SET {', '.join(fields)} WHERE `{getattr(model, '_columns', {}).get(pk_name).column_name}` = %s"
    return sql, values


def build_soft_delete_sql_and_params(instance) -> tuple[str, list[object]]:
    """Bangun SQL soft-delete eksplisit untuk objek domain."""
    model = instance.__class__
    pk_name = getattr(model, "_primary_key", None)
    pk_value = getattr(instance, pk_name, None)
    if pk_value is None:
        raise ValueError("Cannot soft delete model without primary key value.")
    sql = f"UPDATE `{model.__tablename__}` SET `deleted_at` = %s WHERE `{getattr(model, '_columns', {}).get(pk_name).column_name}` = %s"
    return sql, [datetime.utcnow(), pk_value]

from flask import current_app
from backend.extensions import db, Pagination
from backend.models.activity_log import ActivityLog
from backend.models.cloudinary_file import CloudinaryFile
from backend.models.email_log import EmailLog
from backend.models.head_of_program import HeadOfProgram
from backend.models.lecturer import Lecturer
from backend.models.letter_template import LetterTemplate
from backend.models.observation_request import ObservationRequest
from backend.models.role import Role
from backend.models.student import Student
from backend.models.study_program import StudyProgram
from backend.models.system_setting import SystemSetting
from backend.models.user import User
from backend.services import activity_log_service, cloudinary_service
from backend.services.kop_setting_service import DEFAULT_LETTER_MARGIN_CM as DEFAULT_MARGIN
from backend.utils.stats import avg_response_hours, monthly_trend
from backend.utils.security import hash_password
from backend.utils.uploads import (
    CATEGORY_DOCX,
    CATEGORY_IMAGE,
    CATEGORY_PDF,
    UploadValidationError,
    validate_upload_content,
)

PER_PAGE = 10
NEW_ACADEMIC_ROLES = {"dosen", "kaprodi"}
LECTURER_TYPES = {"Internal", "Eksternal"}


def _insert_instance(instance) -> int:
    sql, values = build_insert_sql_and_params(instance)
    lastrowid = db.insert(sql, values)
    pk_name = getattr(instance.__class__, "_primary_key", None)
    if pk_name and getattr(instance, pk_name, None) is None:
        setattr(instance, pk_name, lastrowid)
    return lastrowid


def _update_instance(instance) -> int:
    sql, values = build_update_sql_and_params(instance)
    if not sql:
        return 0
    cursor = db.execute(sql, values)
    return cursor.rowcount


def _soft_delete_instance(instance) -> int:
    sql, values = build_soft_delete_sql_and_params(instance)
    cursor = db.execute(sql, values)
    return cursor.rowcount


class AdminServiceError(Exception):
    """Error domain modul Admin (dipetakan controller ke flash message)."""


def _strip(value: object) -> str:
    return str(value or "").strip()


def _bool_from_value(value: object) -> bool:
    if isinstance(value, bool):
        return value
    if value is None:
        return False
    return str(value).strip().lower() in {"1", "true", "yes", "on", "y"}


# ======================================================================
# Helper internal
# ======================================================================

def _fetch_one_model(model, sql, params=None):
    row = db.fetchone(sql, params)
    return model.from_row(row) if row else None


def _fetch_all_models(model, sql, params=None):
    rows = db.fetchall(sql, params)
    return [model.from_row(row) for row in rows]


def _paginate_models(model, base_sql, count_sql, params, page: int):
    page = max(1, page)
    total = db.scalar(count_sql, params) or 0
    offset = (page - 1) * PER_PAGE
    items = _fetch_all_models(
        model,
        f"{base_sql} LIMIT %s OFFSET %s",
        list(params or []) + [PER_PAGE, offset],
    )
    return Pagination(items, page, PER_PAGE, total)


def _get_model_by_id(model, model_id: int):
    return _fetch_one_model(
        model,
        f"SELECT * FROM `{model.__tablename__}` WHERE `{model._columns[model._primary_key].column_name}` = %s LIMIT 1",
        (model_id,),
    )


def _role_or_error(role_name: str) -> Role:
    role = _fetch_one_model(
        Role,
        "SELECT * FROM `roles` WHERE `name` = %s LIMIT 1",
        (role_name,),
    )
    if role is None:
        raise AdminServiceError(
            f"Role '{role_name}' belum ada di database. Jalankan `flask seed-roles` terlebih dahulu."
        )
    return role


def _email_taken(email: str, exclude_user_id: int | None = None) -> bool:
    params = [email.strip().lower()]
    sql = "SELECT 1 FROM `users` WHERE LOWER(`email`) = %s AND `deleted_at` IS NULL"
    if exclude_user_id is not None:
        sql += " AND `id` != %s"
        params.append(exclude_user_id)
    return db.scalar(sql, params) is not None


def _nid_taken(nid: str, exclude_user_id: int | None = None) -> bool:
    params = [nid.strip().lower()]
    sql = "SELECT 1 FROM `users` WHERE LOWER(`nid`) = %s AND `deleted_at` IS NULL"
    if exclude_user_id is not None:
        sql += " AND `id` != %s"
        params.append(exclude_user_id)
    return db.scalar(sql, params) is not None


def _paginate_models_by_sql(model, base_sql, count_sql, params, page: int):
    return _paginate_models(model, base_sql, count_sql, params, page)


def _exists(sql, params=None) -> bool:
    return db.scalar(sql, params) is not None


def _count(sql, params=None) -> int:
    return int(db.scalar(sql, params) or 0)


def _ensure_unique_value(table: str, column: str, value: object, exclude_id: int | None = None) -> bool:
    sql = f"SELECT 1 FROM `{table}` WHERE LOWER(`{column}`) = %s AND `deleted_at` IS NULL"
    params = [str(value).strip().lower()]
    if exclude_id is not None:
        sql += " AND `id` != %s"
        params.append(exclude_id)
    return _exists(sql, params)


def _create_account(role_name: str, data: dict, profile_factory):
    """Buat User + profil terkait tanpa query builder.

    Commit dilakukan di sini untuk menjaga konsistensi transaksi.
    """
    email = data["email"].strip().lower()
    nid = data["nid"].strip()
    if _email_taken(email):
        raise AdminServiceError(f"Email '{email}' sudah terdaftar.")
    if _nid_taken(nid):
        raise AdminServiceError(f"NID '{nid}' sudah dipakai akun lain.")
    if not data.get("password"):
        raise AdminServiceError("Password wajib diisi saat membuat akun baru.")

    role = _role_or_error(role_name)
    try:
        user = User(
            role_id=role.id,
            name=data["name"].strip(),
            nid=nid,
            email=email,
            password_hash=hash_password(data["password"]),
            phone=data.get("phone", "").strip() or None,
            is_active_flag=bool(data.get("is_active_flag", True)),
        )
        _insert_instance(user)

        profile = profile_factory(user)
        _insert_instance(profile)

        db.commit()
        return user, profile
    except Exception:
        db.rollback()
        raise


def _update_account(user: User, data: dict) -> None:
    email = data["email"].strip().lower()
    nid = data["nid"].strip()
    if _email_taken(email, exclude_user_id=user.id):
        raise AdminServiceError(f"Email '{email}' sudah dipakai user lain.")
    if _nid_taken(nid, exclude_user_id=user.id):
        raise AdminServiceError(f"NID '{nid}' sudah dipakai akun lain.")
    user.name = data["name"].strip()
    user.nid = nid
    user.email = email
    user.phone = data.get("phone", "").strip() or None
    user.is_active_flag = bool(data.get("is_active_flag", True))
    if data.get("password"):
        user.password_hash = hash_password(data["password"])


def _soft_delete_account(user: User, profile) -> None:
    _soft_delete_instance(profile)
    _soft_delete_instance(user)
    user.is_active_flag = False
    _update_instance(user)
    db.commit()


# ======================================================================
# Master Data: Program Studi (FR-40 / UC-24)
# ======================================================================

def list_study_programs(page: int = 1, search: str | None = None):
    base_sql = "SELECT * FROM `study_programs` WHERE `deleted_at` IS NULL"
    count_sql = "SELECT COUNT(*) FROM `study_programs` WHERE `deleted_at` IS NULL"
    params: list[object] = []
    if search:
        like = f"%{search.strip()}%"
        base_sql += " AND (`name` LIKE %s OR `code` LIKE %s)"
        count_sql += " AND (`name` LIKE %s OR `code` LIKE %s)"
        params.extend([like, like])
    base_sql += " ORDER BY `name` ASC"
    return _paginate_models_by_sql(StudyProgram, base_sql, count_sql, params, page)


def get_study_program_or_none(program_id: int) -> StudyProgram | None:
    return _get_model_by_id(StudyProgram, program_id)


def all_study_program_choices() -> list[tuple[int, str]]:
    programs = _fetch_all_models(
        StudyProgram,
        "SELECT * FROM `study_programs` WHERE `deleted_at` IS NULL ORDER BY `name` ASC",
    )
    return [(p.id, f"{p.name} ({p.code})") for p in programs]


def academic_user_overview_new_schema() -> dict:
    lecturers = db.fetchall(
        "SELECT d.`id_dosen` AS `id`, d.`id_dosen`, d.`id_pengguna`, d.`id_program_studi`, "
        "d.`nidn`, COALESCE(NULLIF(d.`jenis_dosen`, ''), 'Internal') AS `jenis_dosen`, "
        "d.`id_file_tanda_tangan`, p.`nama`, p.`username`, p.`role`, "
        "p.`status_aktif`, ps.`nama_program_studi`, fc.`nama_file`, fc.`secure_url`, "
        "fc.`public_id` FROM `dosen` AS d "
        "JOIN `pengguna` AS p ON p.`id_pengguna` = d.`id_pengguna` "
        "JOIN `program_studi` AS ps ON ps.`id_program_studi` = d.`id_program_studi` "
        "LEFT JOIN `file_cloudinary` AS fc ON fc.`id_file` = d.`id_file_tanda_tangan` "
        "ORDER BY p.`nama` ASC"
    )
    heads_of_program = db.fetchall(
        "SELECT k.`id_kaprodi` AS `id`, k.`id_kaprodi`, k.`id_pengguna`, k.`id_program_studi`, "
        "k.`nidn`, k.`id_file_tanda_tangan`, p.`nama`, p.`username`, p.`role`, "
        "p.`status_aktif`, ps.`nama_program_studi`, fc.`nama_file`, fc.`secure_url`, "
        "fc.`public_id` FROM `kaprodi` AS k "
        "JOIN `pengguna` AS p ON p.`id_pengguna` = k.`id_pengguna` "
        "JOIN `program_studi` AS ps ON ps.`id_program_studi` = k.`id_program_studi` "
        "LEFT JOIN `file_cloudinary` AS fc ON fc.`id_file` = k.`id_file_tanda_tangan` "
        "ORDER BY p.`nama` ASC"
    )
    study_programs = db.fetchall(
        "SELECT ps.`id_program_studi` AS `id`, ps.`id_program_studi`, ps.`nama_program_studi`, "
        "ps.`status_aktif`, k.`id_kaprodi`, p.`nama` AS `nama_kaprodi` "
        "FROM `program_studi` AS ps "
        "LEFT JOIN `kaprodi` AS k ON k.`id_program_studi` = ps.`id_program_studi` "
        "LEFT JOIN `pengguna` AS p ON p.`id_pengguna` = k.`id_pengguna` "
        "ORDER BY ps.`nama_program_studi` ASC"
    )
    lecturer_candidates = db.fetchall(
        "SELECT d.`id_dosen`, d.`id_pengguna`, d.`nidn`, p.`nama`, ps.`nama_program_studi` "
        "FROM `dosen` AS d "
        "JOIN `pengguna` AS p ON p.`id_pengguna` = d.`id_pengguna` "
        "JOIN `program_studi` AS ps ON ps.`id_program_studi` = d.`id_program_studi` "
        "WHERE p.`role` = 'dosen' AND p.`status_aktif` = 1 "
        "AND COALESCE(NULLIF(d.`jenis_dosen`, ''), 'Internal') = 'Internal' "
        "ORDER BY p.`nama` ASC"
    )
    signature_files = db.fetchall(
        "SELECT `id_file`, `nama_file`, `public_id`, `secure_url`, `resource_type` "
        "FROM `file_cloudinary` ORDER BY `dibuat_pada` DESC"
    )
    return {
        "lecturers": lecturers,
        "heads_of_program": heads_of_program,
        "study_programs": study_programs,
        "lecturer_candidates": lecturer_candidates,
        "signature_files": signature_files,
        "kiosk_account": first_kiosk_account_new_schema(),
    }


def _normalize_lecturer_type(value) -> str:
    lecturer_type = _strip(value).capitalize() if value is not None else "Internal"
    if not lecturer_type:
        return "Internal"
    if lecturer_type not in LECTURER_TYPES:
        raise AdminServiceError("Jenis dosen harus Internal atau Eksternal.")
    return lecturer_type


def _ensure_internal_lecturer(lecturer_id: int) -> None:
    lecturer_type = db.scalar(
        "SELECT COALESCE(NULLIF(`jenis_dosen`, ''), 'Internal') FROM `dosen` "
        "WHERE `id_dosen` = %s LIMIT 1",
        (lecturer_id,),
    )
    if lecturer_type is None:
        raise AdminServiceError("Dosen calon kaprodi tidak ditemukan.")
    if str(lecturer_type).strip().lower() != "internal":
        raise AdminServiceError("Dosen eksternal tidak dapat didaftarkan sebagai Kaprodi.")


def first_kiosk_account_new_schema() -> dict | None:
    return db.fetchone(
        "SELECT `id_pengguna`, `nama`, `username`, `role`, `status_aktif` "
        "FROM `pengguna` WHERE `role` = 'kiosk' ORDER BY `id_pengguna` ASC LIMIT 1"
    )


def _ensure_required(data: dict, fields: list[str]) -> None:
    missing = [field for field in fields if not _strip(data.get(field))]
    if missing:
        raise AdminServiceError("Field wajib belum lengkap.")


def _ensure_username_available(username: str, exclude_user_id: int | None = None) -> None:
    sql = "SELECT 1 FROM `pengguna` WHERE LOWER(`username`) = %s"
    params: list[object] = [_strip(username).lower()]
    if exclude_user_id is not None:
        sql += " AND `id_pengguna` != %s"
        params.append(exclude_user_id)
    if db.scalar(sql, params) is not None:
        raise AdminServiceError(f"Username '{username}' sudah digunakan.")


def _ensure_program_available(name: str, exclude_program_id: int | None = None) -> None:
    sql = "SELECT 1 FROM `program_studi` WHERE LOWER(`nama_program_studi`) = %s"
    params: list[object] = [_strip(name).lower()]
    if exclude_program_id is not None:
        sql += " AND `id_program_studi` != %s"
        params.append(exclude_program_id)
    if db.scalar(sql, params) is not None:
        raise AdminServiceError(f"Program studi '{name}' sudah terdaftar.")


def _ensure_nidn_available(role: str, nidn: str, exclude_id: int | None = None) -> None:
    role = _strip(role)
    if role not in NEW_ACADEMIC_ROLES:
        raise AdminServiceError("Role akun akademik tidak valid.")
    params: list[object] = [_strip(nidn).lower()]
    lecturer_sql = "SELECT 1 FROM `dosen` WHERE LOWER(`nidn`) = %s"
    head_sql = "SELECT 1 FROM `kaprodi` WHERE LOWER(`nidn`) = %s"
    if role == "dosen" and exclude_id is not None:
        lecturer_sql += " AND `id_dosen` != %s"
        params_for_lecturer = [*params, exclude_id]
    else:
        params_for_lecturer = params
    if role == "kaprodi" and exclude_id is not None:
        head_sql += " AND `id_kaprodi` != %s"
        params_for_head = [*params, exclude_id]
    else:
        params_for_head = params
    if db.scalar(lecturer_sql, params_for_lecturer) is not None or db.scalar(head_sql, params_for_head) is not None:
        raise AdminServiceError(f"NIDN '{nidn}' sudah digunakan.")


def _get_program_or_error(program_id: int) -> dict:
    program = db.fetchone(
        "SELECT * FROM `program_studi` WHERE `id_program_studi` = %s LIMIT 1",
        (program_id,),
    )
    if program is None:
        raise AdminServiceError("Program studi tidak ditemukan.")
    return program


def _store_signature_file(file_storage) -> int | None:
    if file_storage is None or not getattr(file_storage, "filename", ""):
        return None
    filename = file_storage.filename or ""
    if not filename.lower().endswith(".png"):
        raise AdminServiceError("Tanda tangan harus berupa file PNG.")
    try:
        file_bytes = validate_upload_content(
            file_storage,
            category=CATEGORY_IMAGE,
            max_size_mb=current_app.config.get("UPLOAD_MAX_IMAGE_SIZE_MB", 5),
        )
        result = cloudinary_service.upload_bytes(
            file_bytes,
            public_id=f"tanda-tangan-{int(time.time())}",
            folder="tanda-tangan",
            resource_type="image",
        )
    except (UploadValidationError, cloudinary_service.CloudinaryServiceError) as exc:
        raise AdminServiceError(str(exc)) from exc
    return db.insert(
        "INSERT INTO `file_cloudinary` (`nama_file`, `public_id`, `secure_url`, `resource_type`) "
        "VALUES (%s, %s, %s, %s)",
        (
            filename,
            result.get("public_id"),
            result.get("secure_url"),
            "image",
        ),
    )


def save_kiosk_account_new_schema(data: dict) -> dict:
    _ensure_required(data, ["nama", "username"])
    account = first_kiosk_account_new_schema()
    username = _strip(data["username"])
    try:
        if account is None:
            if not _strip(data.get("password")):
                raise AdminServiceError("Password wajib diisi saat membuat akun kiosk.")
            _ensure_username_available(username)
            user_id = db.insert(
                "INSERT INTO `pengguna` (`nama`, `username`, `password`, `role`, `status_aktif`) "
                "VALUES (%s, %s, %s, 'kiosk', %s)",
                (
                    _strip(data["nama"]),
                    username,
                    hash_password(_strip(data["password"])),
                    _bool_from_value(data.get("status_aktif")),
                ),
            )
        else:
            user_id = account["id_pengguna"]
            _ensure_username_available(username, exclude_user_id=user_id)
            params: list[object] = [
                _strip(data["nama"]),
                username,
                _bool_from_value(data.get("status_aktif")),
            ]
            password_sql = ""
            if _strip(data.get("password")):
                password_sql = ", `password` = %s"
                params.append(hash_password(_strip(data["password"])))
            params.append(user_id)
            db.execute(
                "UPDATE `pengguna` SET `nama` = %s, `username` = %s, `status_aktif` = %s"
                f"{password_sql} WHERE `id_pengguna` = %s AND `role` = 'kiosk'",
                params,
            )
        db.commit()
        return db.fetchone("SELECT * FROM `pengguna` WHERE `id_pengguna` = %s", (user_id,))
    except Exception:
        db.rollback()
        raise


def create_academic_account_new_schema(data: dict, file_storage=None) -> dict:
    role = _strip(data.get("role"))
    if role not in NEW_ACADEMIC_ROLES:
        raise AdminServiceError("Pilih role dosen atau kaprodi.")
    _ensure_required(data, ["nama", "username", "password", "nidn", "id_program_studi"])
    username = _strip(data["username"])
    nidn = _strip(data["nidn"])
    program_id = int(data["id_program_studi"])
    _get_program_or_error(program_id)
    _ensure_username_available(username)
    _ensure_nidn_available(role, nidn)
    lecturer_type = _normalize_lecturer_type(data.get("jenis_dosen")) if role == "dosen" else None
    try:
        file_id = _store_signature_file(file_storage)
        user_id = db.insert(
            "INSERT INTO `pengguna` (`nama`, `username`, `password`, `role`, `status_aktif`) "
            "VALUES (%s, %s, %s, %s, %s)",
            (
                _strip(data["nama"]),
                username,
                hash_password(_strip(data["password"])),
                role,
                _bool_from_value(data.get("status_aktif")),
            ),
        )
        pk = "id_dosen" if role == "dosen" else "id_kaprodi"
        if role == "dosen":
            account_id = db.insert(
                "INSERT INTO `dosen` (`id_pengguna`, `id_program_studi`, `nidn`, `jenis_dosen`, `id_file_tanda_tangan`) "
                "VALUES (%s, %s, %s, %s, %s)",
                (user_id, program_id, nidn, lecturer_type, file_id),
            )
        else:
            account_id = db.insert(
                "INSERT INTO `kaprodi` (`id_pengguna`, `id_program_studi`, `nidn`, `id_file_tanda_tangan`) "
                "VALUES (%s, %s, %s, %s)",
                (user_id, program_id, nidn, file_id),
            )
        db.commit()
        return get_academic_account_new_schema(role, account_id)
    except Exception:
        db.rollback()
        raise


def get_academic_account_new_schema(role: str, account_id: int) -> dict | None:
    if role not in NEW_ACADEMIC_ROLES:
        return None
    table = "dosen" if role == "dosen" else "kaprodi"
    pk = "id_dosen" if role == "dosen" else "id_kaprodi"
    account = db.fetchone(
        f"SELECT a.`{pk}` AS `id`, a.*, p.`nama`, p.`username`, p.`role`, p.`status_aktif`, "
        "ps.`nama_program_studi`, fc.`nama_file`, fc.`secure_url`, fc.`public_id` "
        f"FROM `{table}` AS a "
        "JOIN `pengguna` AS p ON p.`id_pengguna` = a.`id_pengguna` "
        "JOIN `program_studi` AS ps ON ps.`id_program_studi` = a.`id_program_studi` "
        "LEFT JOIN `file_cloudinary` AS fc ON fc.`id_file` = a.`id_file_tanda_tangan` "
        f"WHERE a.`{pk}` = %s LIMIT 1",
        (account_id,),
    )
    if account is not None and role == "dosen" and not account.get("jenis_dosen"):
        account["jenis_dosen"] = "Internal"
    return account


def update_academic_account_new_schema(role: str, account_id: int, data: dict, file_storage=None) -> dict:
    account = get_academic_account_new_schema(role, account_id)
    if account is None:
        raise AdminServiceError("Akun akademik tidak ditemukan.")
    _ensure_required(data, ["nama", "username", "nidn", "id_program_studi"])
    username = _strip(data["username"])
    nidn = _strip(data["nidn"])
    program_id = int(data["id_program_studi"])
    _get_program_or_error(program_id)
    _ensure_username_available(username, exclude_user_id=account["id_pengguna"])
    _ensure_nidn_available(role, nidn, exclude_id=account_id)
    pk = "id_dosen" if role == "dosen" else "id_kaprodi"
    lecturer_type = _normalize_lecturer_type(data.get("jenis_dosen")) if role == "dosen" else None
    try:
        file_id = _store_signature_file(file_storage)
        params: list[object] = [
            _strip(data["nama"]),
            username,
            _bool_from_value(data.get("status_aktif")),
        ]
        password_sql = ""
        if _strip(data.get("password")):
            password_sql = ", `password` = %s"
            params.append(hash_password(_strip(data["password"])))
        params.append(account["id_pengguna"])
        db.execute(
            "UPDATE `pengguna` SET `nama` = %s, `username` = %s, `status_aktif` = %s"
            f"{password_sql} WHERE `id_pengguna` = %s",
            params,
        )
        if role == "dosen" and file_id is None:
            db.execute(
                "UPDATE `dosen` SET `id_program_studi` = %s, `nidn` = %s, `jenis_dosen` = %s WHERE `id_dosen` = %s",
                (program_id, nidn, lecturer_type, account_id),
            )
        elif role == "dosen":
            db.execute(
                "UPDATE `dosen` SET `id_program_studi` = %s, `nidn` = %s, `jenis_dosen` = %s, "
                "`id_file_tanda_tangan` = %s WHERE `id_dosen` = %s",
                (program_id, nidn, lecturer_type, file_id, account_id),
            )
        elif file_id is None:
            db.execute(
                "UPDATE `kaprodi` SET `id_program_studi` = %s, `nidn` = %s WHERE `id_kaprodi` = %s",
                (program_id, nidn, account_id),
            )
        else:
            db.execute(
                "UPDATE `kaprodi` SET `id_program_studi` = %s, `nidn` = %s, "
                "`id_file_tanda_tangan` = %s WHERE `id_kaprodi` = %s",
                (program_id, nidn, file_id, account_id),
            )
        db.commit()
        return get_academic_account_new_schema(role, account_id)
    except Exception:
        db.rollback()
        raise


def delete_academic_account_new_schema(role: str, account_id: int) -> None:
    account = get_academic_account_new_schema(role, account_id)
    if account is None:
        raise AdminServiceError("Akun akademik tidak ditemukan.")
    table = "dosen" if role == "dosen" else "kaprodi"
    pk = "id_dosen" if role == "dosen" else "id_kaprodi"
    try:
        db.execute(f"DELETE FROM `{table}` WHERE `{pk}` = %s", (account_id,))
        db.execute("DELETE FROM `pengguna` WHERE `id_pengguna` = %s", (account["id_pengguna"],))
        db.commit()
    except Exception:
        db.rollback()
        raise


def clear_signature_reference_new_schema(role: str, account_id: int) -> None:
    account = get_academic_account_new_schema(role, account_id)
    if account is None:
        raise AdminServiceError("Akun akademik tidak ditemukan.")
    table = "dosen" if role == "dosen" else "kaprodi"
    pk = "id_dosen" if role == "dosen" else "id_kaprodi"
    db.execute(f"UPDATE `{table}` SET `id_file_tanda_tangan` = NULL WHERE `{pk}` = %s", (account_id,))
    db.commit()


def create_program_with_head_new_schema(data: dict) -> dict:
    _ensure_required(data, ["nama_program_studi", "id_dosen"])
    program_name = _strip(data["nama_program_studi"])
    lecturer_id = int(data["id_dosen"])
    _ensure_program_available(program_name)
    lecturer = get_academic_account_new_schema("dosen", lecturer_id)
    if lecturer is None:
        raise AdminServiceError("Dosen calon kaprodi tidak ditemukan.")
    _ensure_internal_lecturer(lecturer_id)
    try:
        program_id = db.insert(
            "INSERT INTO `program_studi` (`nama_program_studi`, `status_aktif`) VALUES (%s, 1)",
            (program_name,),
        )
        db.execute(
            "UPDATE `pengguna` SET `role` = 'kaprodi' WHERE `id_pengguna` = %s",
            (lecturer["id_pengguna"],),
        )
        db.insert(
            "INSERT INTO `kaprodi` (`id_pengguna`, `id_program_studi`, `nidn`, `id_file_tanda_tangan`) "
            "VALUES (%s, %s, %s, %s)",
            (
                lecturer["id_pengguna"],
                program_id,
                lecturer["nidn"],
                lecturer["id_file_tanda_tangan"],
            ),
        )
        db.execute("DELETE FROM `dosen` WHERE `id_dosen` = %s", (lecturer_id,))
        db.commit()
        return db.fetchone("SELECT * FROM `program_studi` WHERE `id_program_studi` = %s", (program_id,))
    except Exception:
        db.rollback()
        raise


def create_program_new_schema(data: dict) -> dict:
    _ensure_required(data, ["nama_program_studi"])
    program_name = _strip(data["nama_program_studi"])
    _ensure_program_available(program_name)
    try:
        program_id = db.insert(
            "INSERT INTO `program_studi` (`nama_program_studi`, `status_aktif`) VALUES (%s, 1)",
            (program_name,),
        )
        db.commit()
        return db.fetchone("SELECT * FROM `program_studi` WHERE `id_program_studi` = %s", (program_id,))
    except Exception:
        db.rollback()
        raise


def assign_program_head_new_schema(data: dict) -> dict:
    _ensure_required(data, ["id_program_studi", "id_dosen"])
    program_id = int(data["id_program_studi"])
    lecturer_id = int(data["id_dosen"])
    program = db.fetchone("SELECT * FROM `program_studi` WHERE `id_program_studi` = %s LIMIT 1", (program_id,))
    if program is None:
        raise AdminServiceError("Program studi tidak ditemukan.")
    lecturer = get_academic_account_new_schema("dosen", lecturer_id)
    if lecturer is None:
        raise AdminServiceError("Dosen calon kaprodi tidak ditemukan.")
    _ensure_internal_lecturer(lecturer_id)
    try:
        db.execute("UPDATE `kaprodi` SET `id_program_studi` = NULL WHERE `id_program_studi` = %s", (program_id,))
        db.execute(
            "UPDATE `pengguna` SET `role` = 'kaprodi' WHERE `id_pengguna` = %s",
            (lecturer["id_pengguna"],),
        )
        db.insert(
            "INSERT INTO `kaprodi` (`id_pengguna`, `id_program_studi`, `nidn`, `id_file_tanda_tangan`) "
            "VALUES (%s, %s, %s, %s)",
            (
                lecturer["id_pengguna"],
                program_id,
                lecturer["nidn"],
                lecturer["id_file_tanda_tangan"],
            ),
        )
        db.execute("DELETE FROM `dosen` WHERE `id_dosen` = %s", (lecturer_id,))
        db.commit()
        return program
    except Exception:
        db.rollback()
        raise


def delete_program_new_schema(program_id: int) -> None:
    try:
        db.execute("UPDATE `dosen` SET `id_program_studi` = NULL WHERE `id_program_studi` = %s", (program_id,))
        db.execute("UPDATE `kaprodi` SET `id_program_studi` = NULL WHERE `id_program_studi` = %s", (program_id,))
        cursor = db.execute("DELETE FROM `program_studi` WHERE `id_program_studi` = %s", (program_id,))
        if cursor.rowcount == 0:
            db.rollback()
            raise AdminServiceError("Program studi tidak ditemukan.")
        db.commit()
    except AdminServiceError:
        raise
    except Exception:
        db.rollback()
        raise


def academic_user_overview() -> dict:
    lecturers = _fetch_all_models(
        Lecturer,
        "SELECT `lecturers`.* FROM `lecturers` "
        "JOIN `users` ON `lecturers`.`user_id` = `users`.`id` "
        "WHERE `lecturers`.`deleted_at` IS NULL AND `users`.`deleted_at` IS NULL "
        "ORDER BY `users`.`name` ASC",
    )
    heads_of_program = _fetch_all_models(
        HeadOfProgram,
        "SELECT `head_of_programs`.* FROM `head_of_programs` "
        "JOIN `users` ON `head_of_programs`.`user_id` = `users`.`id` "
        "WHERE `head_of_programs`.`deleted_at` IS NULL AND `users`.`deleted_at` IS NULL "
        "ORDER BY `users`.`name` ASC",
    )
    study_programs = _fetch_all_models(
        StudyProgram,
        "SELECT * FROM `study_programs` WHERE `deleted_at` IS NULL ORDER BY `name` ASC",
    )
    return {
        "lecturers": lecturers,
        "heads_of_program": heads_of_program,
        "study_programs": study_programs,
    }


def create_study_program(data: dict) -> StudyProgram:
    if db.scalar(
        "SELECT 1 FROM `study_programs` WHERE LOWER(`code`) = %s AND `deleted_at` IS NULL LIMIT 1",
        (data["code"].strip().lower(),),
    ) is not None:
        raise AdminServiceError(f"Kode prodi '{data['code']}' sudah dipakai.")
    program = StudyProgram(
        name=data["name"].strip(),
        code=data["code"].strip().upper(),
        faculty_name=data["faculty_name"].strip(),
    )
    _insert_instance(program)
    db.commit()
    return program


def update_study_program(program: StudyProgram, data: dict) -> StudyProgram:
    if db.scalar(
        "SELECT 1 FROM `study_programs` WHERE LOWER(`code`) = %s AND `id` != %s AND `deleted_at` IS NULL LIMIT 1",
        (data["code"].strip().lower(), program.id),
    ) is not None:
        raise AdminServiceError(f"Kode prodi '{data['code']}' sudah dipakai program studi lain.")
    program.name = data["name"].strip()
    program.code = data["code"].strip().upper()
    program.faculty_name = data["faculty_name"].strip()
    _update_instance(program)
    db.commit()
    return program


def delete_study_program(program: StudyProgram) -> None:
    if db.scalar(
        "SELECT 1 FROM `students` WHERE `study_program_id` = %s AND `deleted_at` IS NULL LIMIT 1",
        (program.id,),
    ) or db.scalar(
        "SELECT 1 FROM `lecturers` WHERE `study_program_id` = %s AND `deleted_at` IS NULL LIMIT 1",
        (program.id,),
    ) or db.scalar(
        "SELECT 1 FROM `head_of_programs` WHERE `study_program_id` = %s AND `deleted_at` IS NULL LIMIT 1",
        (program.id,),
    ):
        raise AdminServiceError(
            "Program studi tidak dapat dihapus karena masih memiliki mahasiswa/dosen/kaprodi aktif."
        )
    _soft_delete_instance(program)
    db.commit()


# ======================================================================
# Helper generik akun (User + profil 1:1): dipakai Mahasiswa/Dosen/Kaprodi
# ======================================================================

def _create_account(role_name: str, data: dict, profile_factory):
    """Buat User + baris profil terkait dalam satu transaksi raw SQL.

    Tahap 15 (Revisi Login): `data["nid"]` WAJIB diisi oleh caller.
    """
    email = data["email"].strip().lower()
    nid = data["nid"].strip()
    if _email_taken(email):
        raise AdminServiceError(f"Email '{email}' sudah terdaftar.")
    if _nid_taken(nid):
        raise AdminServiceError(f"NID '{nid}' sudah dipakai akun lain.")
    if not data.get("password"):
        raise AdminServiceError("Password wajib diisi saat membuat akun baru.")

    role = _role_or_error(role_name)
    try:
        user = User(
            role_id=role.id,
            name=data["name"].strip(),
            nid=nid,
            email=email,
            password_hash=hash_password(data["password"]),
            phone=data.get("phone", "").strip() or None,
            is_active_flag=bool(data.get("is_active_flag", True)),
        )
        _insert_instance(user)

        profile = profile_factory(user)
        _insert_instance(profile)

        db.commit()
        return user, profile
    except Exception:
        db.rollback()
        raise


def _update_account(user: User, data: dict) -> None:
    email = data["email"].strip().lower()
    nid = data["nid"].strip()
    if _email_taken(email, exclude_user_id=user.id):
        raise AdminServiceError(f"Email '{email}' sudah dipakai user lain.")
    if _nid_taken(nid, exclude_user_id=user.id):
        raise AdminServiceError(f"NID '{nid}' sudah dipakai akun lain.")
    user.name = data["name"].strip()
    user.nid = nid
    user.email = email
    user.phone = data.get("phone", "").strip() or None
    user.is_active_flag = bool(data.get("is_active_flag", True))
    if data.get("password"):
        user.password_hash = hash_password(data["password"])


def _soft_delete_account(user: User, profile) -> None:
    _soft_delete_instance(profile)
    _soft_delete_instance(user)
    user.is_active_flag = False
    _update_instance(user)
    db.commit()


# ======================================================================
# Master Data: Mahasiswa (FR-40 / UC-21)
# ======================================================================

def list_students(page: int = 1, search: str | None = None):
    base_sql = (
        "SELECT `students`.* FROM `students` "
        "JOIN `users` ON `students`.`user_id` = `users`.`id` "
        "WHERE `students`.`deleted_at` IS NULL AND `users`.`deleted_at` IS NULL"
    )
    count_sql = (
        "SELECT COUNT(*) FROM `students` "
        "JOIN `users` ON `students`.`user_id` = `users`.`id` "
        "WHERE `students`.`deleted_at` IS NULL AND `users`.`deleted_at` IS NULL"
    )
    params: list[object] = []
    if search:
        like = f"%{search.strip().lower()}%"
        base_sql += (
            " AND (LOWER(`users`.`name`) LIKE %s OR LOWER(`students`.`nim`) LIKE %s "
            "OR LOWER(`users`.`email`) LIKE %s)"
        )
        count_sql += (
            " AND (LOWER(`users`.`name`) LIKE %s OR LOWER(`students`.`nim`) LIKE %s "
            "OR LOWER(`users`.`email`) LIKE %s)"
        )
        params.extend([like, like, like])
    base_sql += " ORDER BY `users`.`name` ASC"
    return _paginate_models_by_sql(Student, base_sql, count_sql, params, page)


def get_student_or_none(student_id: int) -> Student | None:
    return _fetch_one_model(
        Student,
        "SELECT * FROM `students` WHERE `id` = %s AND `deleted_at` IS NULL LIMIT 1",
        (student_id,),
    )


def create_student(data: dict) -> Student:
    if _exists(
        "SELECT 1 FROM `students` WHERE LOWER(`nim`) = %s AND `deleted_at` IS NULL LIMIT 1",
        (data["nim"].strip().lower(),),
    ):
        raise AdminServiceError(f"NIM '{data['nim']}' sudah terdaftar.")
    data["nid"] = data["nim"].strip()

    def factory(user: User) -> Student:
        return Student(
            user_id=user.id,
            nim=data["nim"].strip(),
            semester=data["semester"],
            study_program_id=data["study_program_id"],
        )

    _, student = _create_account(Role.MAHASISWA, data, factory)
    return student


def update_student(student: Student, data: dict) -> Student:
    if _exists(
        "SELECT 1 FROM `students` WHERE LOWER(`nim`) = %s AND `deleted_at` IS NULL AND `id` != %s LIMIT 1",
        (data["nim"].strip().lower(), student.id),
    ):
        raise AdminServiceError(f"NIM '{data['nim']}' sudah dipakai mahasiswa lain.")
    data["nid"] = data["nim"].strip()
    _update_account(student.user, data)
    student.nim = data["nim"].strip()
    student.semester = data["semester"]
    student.study_program_id = data["study_program_id"]
    _update_instance(student)
    db.commit()
    return student


def delete_student(student: Student) -> None:
    if _exists(
        "SELECT 1 FROM `observation_requests` WHERE `student_id` = %s AND `deleted_at` IS NULL LIMIT 1",
        (student.id,),
    ):
        raise AdminServiceError(
            "Mahasiswa tidak dapat dihapus karena memiliki riwayat pengajuan surat. "
            "Nonaktifkan akunnya saja melalui form edit."
        )
    _soft_delete_account(student.user, student)


# ======================================================================
# Master Data: Dosen (FR-40 / UC-22)
# ======================================================================

def list_lecturers(page: int = 1, search: str | None = None):
    base_sql = (
        "SELECT `lecturers`.* FROM `lecturers` "
        "JOIN `users` ON `lecturers`.`user_id` = `users`.`id` "
        "WHERE `lecturers`.`deleted_at` IS NULL AND `users`.`deleted_at` IS NULL"
    )
    count_sql = (
        "SELECT COUNT(*) FROM `lecturers` "
        "JOIN `users` ON `lecturers`.`user_id` = `users`.`id` "
        "WHERE `lecturers`.`deleted_at` IS NULL AND `users`.`deleted_at` IS NULL"
    )
    params: list[object] = []
    if search:
        like = f"%{search.strip().lower()}%"
        base_sql += (
            " AND (LOWER(`users`.`name`) LIKE %s OR LOWER(`lecturers`.`nidn`) LIKE %s "
            "OR LOWER(`users`.`email`) LIKE %s)"
        )
        count_sql += (
            " AND (LOWER(`users`.`name`) LIKE %s OR LOWER(`lecturers`.`nidn`) LIKE %s "
            "OR LOWER(`users`.`email`) LIKE %s)"
        )
        params.extend([like, like, like])
    base_sql += " ORDER BY `users`.`name` ASC"
    return _paginate_models_by_sql(Lecturer, base_sql, count_sql, params, page)


def get_lecturer_or_none(lecturer_id: int) -> Lecturer | None:
    return _fetch_one_model(
        Lecturer,
        "SELECT * FROM `lecturers` WHERE `id` = %s AND `deleted_at` IS NULL LIMIT 1",
        (lecturer_id,),
    )


def create_lecturer(data: dict) -> Lecturer:
    if _exists(
        "SELECT 1 FROM `lecturers` WHERE LOWER(`nidn`) = %s AND `deleted_at` IS NULL LIMIT 1",
        (data["nidn"].strip().lower(),),
    ):
        raise AdminServiceError(f"NIDN '{data['nidn']}' sudah terdaftar.")
    data["nid"] = data["nidn"].strip()

    def factory(user: User) -> Lecturer:
        return Lecturer(user_id=user.id, nidn=data["nidn"].strip(), study_program_id=data["study_program_id"])

    _, lecturer = _create_account(Role.DOSEN, data, factory)
    return lecturer


def update_lecturer(lecturer: Lecturer, data: dict) -> Lecturer:
    if _exists(
        "SELECT 1 FROM `lecturers` WHERE LOWER(`nidn`) = %s AND `deleted_at` IS NULL AND `id` != %s LIMIT 1",
        (data["nidn"].strip().lower(), lecturer.id),
    ):
        raise AdminServiceError(f"NIDN '{data['nidn']}' sudah dipakai dosen lain.")
    data["nid"] = data["nidn"].strip()
    _update_account(lecturer.user, data)
    lecturer.nidn = data["nidn"].strip()
    lecturer.study_program_id = data["study_program_id"]
    _update_instance(lecturer)
    db.commit()
    return lecturer


def delete_lecturer(lecturer: Lecturer) -> None:
    if _exists(
        "SELECT 1 FROM `observation_requests` WHERE `lecturer_id` = %s AND `deleted_at` IS NULL LIMIT 1",
        (lecturer.id,),
    ):
        raise AdminServiceError(
            "Dosen tidak dapat dihapus karena memiliki riwayat pengajuan surat sebagai pembimbing. "
            "Nonaktifkan akunnya saja melalui form edit."
        )
    _soft_delete_account(lecturer.user, lecturer)


# ======================================================================
# Master Data: Kaprodi (FR-40 / UC-23)
# ======================================================================

def list_head_of_programs(page: int = 1, search: str | None = None):
    base_sql = (
        "SELECT `head_of_programs`.* FROM `head_of_programs` "
        "JOIN `users` ON `head_of_programs`.`user_id` = `users`.`id` "
        "WHERE `head_of_programs`.`deleted_at` IS NULL AND `users`.`deleted_at` IS NULL"
    )
    count_sql = (
        "SELECT COUNT(*) FROM `head_of_programs` "
        "JOIN `users` ON `head_of_programs`.`user_id` = `users`.`id` "
        "WHERE `head_of_programs`.`deleted_at` IS NULL AND `users`.`deleted_at` IS NULL"
    )
    params: list[object] = []
    if search:
        like = f"%{search.strip().lower()}%"
        base_sql += (
            " AND (LOWER(`users`.`name`) LIKE %s OR LOWER(`users`.`email`) LIKE %s "
            "OR LOWER(`head_of_programs`.`nidn`) LIKE %s)"
        )
        count_sql += (
            " AND (LOWER(`users`.`name`) LIKE %s OR LOWER(`users`.`email`) LIKE %s "
            "OR LOWER(`head_of_programs`.`nidn`) LIKE %s)"
        )
        params.extend([like, like, like])
    base_sql += " ORDER BY `users`.`name` ASC"
    return _paginate_models_by_sql(HeadOfProgram, base_sql, count_sql, params, page)


def get_head_of_program_or_none(hop_id: int) -> HeadOfProgram | None:
    return _fetch_one_model(
        HeadOfProgram,
        "SELECT * FROM `head_of_programs` WHERE `id` = %s AND `deleted_at` IS NULL LIMIT 1",
        (hop_id,),
    )


def _ensure_prodi_available_for_hop(study_program_id: int, exclude_hop_id: int | None = None) -> None:
    sql = "SELECT 1 FROM `head_of_programs` WHERE `study_program_id` = %s AND `deleted_at` IS NULL"
    params: list[object] = [study_program_id]
    if exclude_hop_id is not None:
        sql += " AND `id` != %s"
        params.append(exclude_hop_id)
    if _exists(sql, params):
        raise AdminServiceError("Program studi tersebut sudah memiliki kaprodi aktif lainnya.")


def _nidn_kaprodi_taken(nidn: str, exclude_hop_id: int | None = None) -> bool:
    sql = "SELECT 1 FROM `head_of_programs` WHERE LOWER(`nidn`) = %s AND `deleted_at` IS NULL"
    params = [nidn.lower()]
    if exclude_hop_id is not None:
        sql += " AND `id` != %s"
        params.append(exclude_hop_id)
    return _exists(sql, params)


def create_head_of_program(data: dict) -> HeadOfProgram:
    _ensure_prodi_available_for_hop(data["study_program_id"])
    nidn = data["nidn"].strip()
    if _nidn_kaprodi_taken(nidn):
        raise AdminServiceError(f"NIDN '{nidn}' sudah terdaftar.")
    data["nid"] = nidn

    def factory(user: User) -> HeadOfProgram:
        return HeadOfProgram(user_id=user.id, study_program_id=data["study_program_id"], nidn=nidn)

    _, hop = _create_account(Role.KAPRODI, data, factory)
    program = _get_model_by_id(StudyProgram, data["study_program_id"])
    if program is not None:
        program.head_of_program_id = hop.id
        _update_instance(program)
        db.commit()
    return hop


def update_head_of_program(hop: HeadOfProgram, data: dict) -> HeadOfProgram:
    _ensure_prodi_available_for_hop(data["study_program_id"], exclude_hop_id=hop.id)
    nidn = data["nidn"].strip()
    if _nidn_kaprodi_taken(nidn, exclude_hop_id=hop.id):
        raise AdminServiceError(f"NIDN '{nidn}' sudah dipakai kaprodi lain.")
    data["nid"] = nidn
    _update_account(hop.user, data)
    hop.nidn = nidn

    old_program_id = hop.study_program_id
    hop.study_program_id = data["study_program_id"]

    if old_program_id != hop.study_program_id:
        old_program = _get_model_by_id(StudyProgram, old_program_id)
        if old_program is not None and old_program.head_of_program_id == hop.id:
            old_program.head_of_program_id = None
            _update_instance(old_program)
        new_program = _get_model_by_id(StudyProgram, hop.study_program_id)
        if new_program is not None:
            new_program.head_of_program_id = hop.id
            _update_instance(new_program)

    _update_instance(hop)
    db.commit()
    return hop


def delete_head_of_program(hop: HeadOfProgram) -> None:
    program = _get_model_by_id(StudyProgram, hop.study_program_id)
    if program is not None and program.head_of_program_id == hop.id:
        program.head_of_program_id = None
        _update_instance(program)
    _soft_delete_account(hop.user, hop)


# ======================================================================
# Akun Login Mahasiswa / Kiosk (Tahap 15 — Revisi Login)
# ======================================================================
#
# Berbeda dari `students` (data akademik NIM/nama/semester/prodi dipakai
# untuk mencocokkan pemohon di form "Ajukan Surat", lihat UC-21 di atas),
# akun di sini adalah kredensial LOGIN kiosk yang dipakai bersama-sama di
# komputer TU: NID bebas ditentukan admin + password, TANPA
# baris `students` terkait (`user.student_profile` == None). Sebelum Tahap
# 15 akun ini hanya bisa dibuat lewat `flask create-kiosk-mahasiswa` (CLI);
# sekarang admin bisa membuatnya langsung dari halaman Admin.

def list_kiosk_accounts(page: int = 1, search: str | None = None):
    role = _role_or_error(Role.MAHASISWA)
    base_sql = (
        "SELECT `users`.* FROM `users` "
        "LEFT JOIN `students` ON `students`.`user_id` = `users`.`id` "
        "WHERE `users`.`deleted_at` IS NULL AND `users`.`role_id` = %s "
        "AND `students`.`id` IS NULL"
    )
    count_sql = (
        "SELECT COUNT(*) FROM `users` "
        "LEFT JOIN `students` ON `students`.`user_id` = `users`.`id` "
        "WHERE `users`.`deleted_at` IS NULL AND `users`.`role_id` = %s "
        "AND `students`.`id` IS NULL"
    )
    params: list[object] = [role.id]
    if search:
        like = f"%{search.strip().lower()}%"
        base_sql += " AND (LOWER(`users`.`name`) LIKE %s OR LOWER(`users`.`nid`) LIKE %s)"
        count_sql += " AND (LOWER(`users`.`name`) LIKE %s OR LOWER(`users`.`nid`) LIKE %s)"
        params.extend([like, like])
    base_sql += " ORDER BY `users`.`name` ASC"
    return _paginate_models_by_sql(User, base_sql, count_sql, params, page)


def first_kiosk_account() -> User | None:
    role = _role_or_error(Role.MAHASISWA)
    return _fetch_one_model(
        User,
        "SELECT `users`.* FROM `users` "
        "LEFT JOIN `students` ON `students`.`user_id` = `users`.`id` "
        "WHERE `users`.`deleted_at` IS NULL AND `users`.`role_id` = %s "
        "AND `students`.`id` IS NULL ORDER BY `users`.`created_at` ASC LIMIT 1",
        (role.id,),
    )


def get_kiosk_account_or_none(user_id: int) -> User | None:
    role = _role_or_error(Role.MAHASISWA)
    return _fetch_one_model(
        User,
        "SELECT `users`.* FROM `users` "
        "LEFT JOIN `students` ON `students`.`user_id` = `users`.`id` "
        "WHERE `users`.`deleted_at` IS NULL AND `users`.`role_id` = %s "
        "AND `students`.`id` IS NULL AND `users`.`id` = %s LIMIT 1",
        (role.id, user_id),
    )


def create_kiosk_account(data: dict) -> User:
    nid = data["nid"].strip()
    if _nid_taken(nid):
        raise AdminServiceError(f"NID '{nid}' sudah dipakai akun lain.")
    if not data.get("password"):
        raise AdminServiceError("Password wajib diisi saat membuat akun baru.")

    role = _role_or_error(Role.MAHASISWA)
    placeholder_email = f"{nid.lower()}@kiosk.local"
    if _email_taken(placeholder_email):
        raise AdminServiceError(f"NID '{nid}' menghasilkan email kiosk yang bentrok, gunakan NID lain.")

    user = User(
        role_id=role.id,
        name=data["name"].strip(),
        nid=nid,
        email=placeholder_email,
        password_hash=hash_password(data["password"]),
        is_active_flag=bool(data.get("is_active_flag", True)),
    )
    _insert_instance(user)
    db.commit()
    return user


def update_kiosk_account(user: User, data: dict) -> User:
    nid = data["nid"].strip()
    if _nid_taken(nid, exclude_user_id=user.id):
        raise AdminServiceError(f"NID '{nid}' sudah dipakai akun lain.")
    user.name = data["name"].strip()
    if nid.lower() != user.nid.lower():
        user.nid = nid
        user.email = f"{nid.lower()}@kiosk.local"
    user.is_active_flag = bool(data.get("is_active_flag", True))
    if data.get("password"):
        user.password_hash = hash_password(data["password"])
    _update_instance(user)
    db.commit()
    return user


def delete_kiosk_account(user: User) -> None:
    _soft_delete_instance(user)
    user.is_active_flag = False
    _update_instance(user)
    db.commit()


# ======================================================================
# Konfigurasi Surat: Kop Surat & Logo (FR-41 / UC-25)
# ======================================================================

def latest_letterhead_files() -> dict:
    """File terbaru per kategori kop surat/logo (untuk ditampilkan di halaman admin)."""
    result = {}
    for file_type in (
        CloudinaryFile.TYPE_KOP_SURAT,
        CloudinaryFile.TYPE_LOGO_FAKULTAS,
        CloudinaryFile.TYPE_LOGO_UNIVERSITAS,
    ):
        result[file_type] = _fetch_one_model(
            CloudinaryFile,
            "SELECT * FROM `cloudinary_files` WHERE `file_type` = %s AND `deleted_at` IS NULL "
            "ORDER BY `created_at` DESC LIMIT 1",
            (file_type,),
        )
    return result


def get_letterhead_file_or_none(file_id: int) -> CloudinaryFile | None:
    return _fetch_one_model(
        CloudinaryFile,
        "SELECT * FROM `cloudinary_files` WHERE `id` = %s AND `deleted_at` IS NULL LIMIT 1",
        (file_id,),
    )


def upload_letterhead_file(file_storage, file_type: str, uploader: User) -> CloudinaryFile:
    """FR-41: unggah kop surat/logo baru. File lama TIDAK dihapus otomatis (dipertahankan
    sebagai riwayat) — cukup soft-delete manual lewat `delete_letterhead_file` bila perlu,
    karena `pdf_service` selalu memakai baris ter-baru yang belum dihapus."""
    # Tahap 13: FileAllowed (form) hanya memeriksa EKSTENSI nama file, yang
    # mudah dipalsukan -- di sini isi biner file turut diverifikasi benar-benar
    # gambar (PNG/JPEG) sebelum diunggah ke Cloudinary.
    try:
        data = validate_upload_content(
            file_storage,
            category=CATEGORY_IMAGE,
            max_size_mb=current_app.config.get("UPLOAD_MAX_IMAGE_SIZE_MB", 5),
        )
    except UploadValidationError as exc:
        raise AdminServiceError(str(exc)) from exc

    public_id = f"{file_type}-{int(time.time())}"
    try:
        result = cloudinary_service.upload_bytes(
            data, public_id=public_id, folder=f"letterhead/{file_type}", resource_type="image"
        )
    except cloudinary_service.CloudinaryServiceError as exc:
        raise AdminServiceError(str(exc)) from exc

    record = CloudinaryFile(
        uploader_id=uploader.id,
        file_type=file_type,
        public_id=result.get("public_id", public_id),
        secure_url=result.get("secure_url"),
        original_filename=file_storage.filename,
        file_size=result.get("bytes"),
    )
    _insert_instance(record)
    _insert_instance(
        activity_log_service.build(
            ActivityLog.ACTION_UPLOAD,
            user=uploader,
            description=(
                f"Admin '{uploader.email}' mengunggah {file_type} "
                f"('{file_storage.filename}')."
            ),
        )
    )
    db.commit()
    return record


def delete_letterhead_file(file_record: CloudinaryFile) -> None:
    try:
        cloudinary_service.delete_resource(file_record.public_id, resource_type="image")
    except cloudinary_service.CloudinaryServiceError as exc:
        current_app.logger.warning(
            "Gagal menghapus resource Cloudinary '%s': %s (baris tetap ditandai terhapus).",
            file_record.public_id, exc,
        )
    _soft_delete_instance(file_record)
    db.commit()


def latest_letterhead_files() -> dict:
    result = {
        CloudinaryFile.TYPE_KOP_SURAT: None,
        CloudinaryFile.TYPE_LOGO_FAKULTAS: None,
        CloudinaryFile.TYPE_LOGO_UNIVERSITAS: None,
    }
    row = db.fetchone(
        "SELECT fc.`id_file` AS `id`, fc.`nama_file` AS `original_filename`, fc.`public_id`, "
        "fc.`secure_url`, fc.`resource_type`, fc.`dibuat_pada` AS `created_at` "
        "FROM `pengaturan_kop` AS pk "
        "LEFT JOIN `file_cloudinary` AS fc ON fc.`id_file` = pk.`id_background` "
        "ORDER BY pk.`id_pengaturan` DESC LIMIT 1"
    )
    if row and row.get("id") is not None:
        result[CloudinaryFile.TYPE_KOP_SURAT] = row
    return result


def list_letterhead_background_options() -> list[dict]:
    return db.fetchall(
        "SELECT `id_file` AS `id`, `nama_file` AS `original_filename`, `public_id`, "
        "`secure_url`, `resource_type`, `dibuat_pada` AS `created_at` "
        "FROM `file_cloudinary` "
        "WHERE LOWER(COALESCE(`resource_type`, '')) IN ('image', 'png', 'jpg', 'jpeg') "
        "ORDER BY `dibuat_pada` DESC"
    )


def get_letterhead_file_or_none(file_id: int):
    return db.fetchone(
        "SELECT `id_file` AS `id`, `nama_file` AS `original_filename`, `public_id`, "
        "`secure_url`, `resource_type`, `dibuat_pada` AS `created_at` "
        "FROM `file_cloudinary` WHERE `id_file` = %s LIMIT 1",
        (file_id,),
    )


def upload_letterhead_file(file_storage, file_type: str, uploader: User):
    try:
        data = validate_upload_content(
            file_storage,
            category=CATEGORY_IMAGE,
            max_size_mb=current_app.config.get("UPLOAD_MAX_IMAGE_SIZE_MB", 5),
        )
    except UploadValidationError as exc:
        raise AdminServiceError(str(exc)) from exc

    public_id = f"{file_type}-{int(time.time())}"
    try:
        result = cloudinary_service.upload_bytes(
            data,
            public_id=public_id,
            folder=f"letterhead/{file_type}",
            resource_type="image",
        )
    except cloudinary_service.CloudinaryServiceError as exc:
        raise AdminServiceError(str(exc)) from exc

    file_id = db.insert(
        "INSERT INTO `file_cloudinary` (`nama_file`, `public_id`, `secure_url`, `resource_type`) "
        "VALUES (%s, %s, %s, %s)",
        (
            file_storage.filename,
            result.get("public_id", public_id),
            result.get("secure_url"),
            "image",
        ),
    )
    if file_type == CloudinaryFile.TYPE_KOP_SURAT:
        setting = db.fetchone(
            "SELECT `id_pengaturan` FROM `pengaturan_kop` ORDER BY `id_pengaturan` DESC LIMIT 1"
        )
        if setting:
            db.execute(
                "UPDATE `pengaturan_kop` SET `id_background` = %s WHERE `id_pengaturan` = %s",
                (file_id, setting["id_pengaturan"]),
            )
        else:
            db.execute("INSERT INTO `pengaturan_kop` (`id_background`) VALUES (%s)", (file_id,))
    db.commit()
    return get_letterhead_file_or_none(file_id)


def delete_letterhead_file(file_record) -> None:
    try:
        cloudinary_service.delete_resource(file_record["public_id"], resource_type="image")
    except cloudinary_service.CloudinaryServiceError as exc:
        current_app.logger.warning(
            "Gagal menghapus resource Cloudinary '%s': %s.",
            file_record["public_id"],
            exc,
        )
    db.execute(
        "UPDATE `pengaturan_kop` SET `id_background` = NULL WHERE `id_background` = %s",
        (file_record["id"],),
    )
    db.execute("DELETE FROM `file_cloudinary` WHERE `id_file` = %s", (file_record["id"],))
    db.commit()


# ======================================================================
# Konfigurasi Surat: Template Surat (FR-42 / UC-26)
# ======================================================================

def list_letter_templates():
    return _fetch_all_models(
        LetterTemplate,
        "SELECT * FROM `letter_templates` WHERE `deleted_at` IS NULL ORDER BY `updated_at` DESC",
    )


def get_letter_template_or_none(template_id: int) -> LetterTemplate | None:
    return _fetch_one_model(
        LetterTemplate,
        "SELECT * FROM `letter_templates` WHERE `id` = %s AND `deleted_at` IS NULL LIMIT 1",
        (template_id,),
    )


def _deactivate_other_templates(exclude_id: int | None = None) -> None:
    sql = "UPDATE `letter_templates` SET `is_active` = FALSE WHERE `deleted_at` IS NULL AND `is_active` = TRUE"
    params: list[object] = []
    if exclude_id is not None:
        sql += " AND `id` != %s"
        params.append(exclude_id)
    db.execute(sql, params)


def _validate_letter_template_file(file_storage) -> bytes:
    """Tahap 13: verifikasi isi biner Template Surat sesuai ekstensinya
    (PDF/DOCX) sebelum diunggah ke Cloudinary -- lihat `app/utils/uploads.py`."""
    extension = (file_storage.filename or "").rsplit(".", 1)[-1].lower()
    category = CATEGORY_DOCX if extension == "docx" else CATEGORY_PDF
    try:
        return validate_upload_content(
            file_storage,
            category=category,
            max_size_mb=current_app.config.get("UPLOAD_MAX_TEMPLATE_SIZE_MB", 10),
        )
    except UploadValidationError as exc:
        raise AdminServiceError(str(exc)) from exc


def create_letter_template(data: dict, file_storage, uploader: User) -> LetterTemplate:
    cloudinary_file = None
    if file_storage and file_storage.filename:
        file_bytes = _validate_letter_template_file(file_storage)
        try:
            result = cloudinary_service.upload_bytes(
                file_bytes,
                public_id=f"template-surat-{int(time.time())}",
                folder="letter-templates",
                resource_type="raw",
            )
        except cloudinary_service.CloudinaryServiceError as exc:
            raise AdminServiceError(str(exc)) from exc
        cloudinary_file = CloudinaryFile(
            uploader_id=uploader.id,
            file_type=CloudinaryFile.TYPE_TEMPLATE_SURAT,
            public_id=result.get("public_id"),
            secure_url=result.get("secure_url"),
            original_filename=file_storage.filename,
            file_size=result.get("bytes"),
        )
        _insert_instance(cloudinary_file)

    template = LetterTemplate(
        name=data["name"].strip(),
        cloudinary_file_id=cloudinary_file.id if cloudinary_file else None,
        margin_top=data["margin_top"],
        margin_bottom=data["margin_bottom"],
        margin_left=data["margin_left"],
        margin_right=data["margin_right"],
        is_active=bool(data.get("is_active")),
    )
    _insert_instance(template)

    if template.is_active:
        _deactivate_other_templates(exclude_id=template.id)

    if cloudinary_file is not None:
        _insert_instance(
            activity_log_service.build(
                ActivityLog.ACTION_UPLOAD,
                user=uploader,
                description=(
                    f"Admin '{uploader.email}' mengunggah template surat "
                    f"'{template.name}' ('{file_storage.filename}')."
                ),
            )
        )

    db.commit()
    return template


def update_letter_template(template: LetterTemplate, data: dict, file_storage, uploader: User) -> LetterTemplate:
    if file_storage and file_storage.filename:
        file_bytes = _validate_letter_template_file(file_storage)
        try:
            result = cloudinary_service.upload_bytes(
                file_bytes,
                public_id=f"template-surat-{template.id}-{int(time.time())}",
                folder="letter-templates",
                resource_type="raw",
            )
        except cloudinary_service.CloudinaryServiceError as exc:
            raise AdminServiceError(str(exc)) from exc
        cloudinary_file = CloudinaryFile(
            uploader_id=uploader.id,
            file_type=CloudinaryFile.TYPE_TEMPLATE_SURAT,
            public_id=result.get("public_id"),
            secure_url=result.get("secure_url"),
            original_filename=file_storage.filename,
            file_size=result.get("bytes"),
        )
        _insert_instance(cloudinary_file)
        template.cloudinary_file_id = cloudinary_file.id

    template.name = data["name"].strip()
    template.margin_top = data["margin_top"]
    template.margin_bottom = data["margin_bottom"]
    template.margin_left = data["margin_left"]
    template.margin_right = data["margin_right"]
    template.is_active = bool(data.get("is_active"))

    if template.is_active:
        _deactivate_other_templates(exclude_id=template.id)

    if file_storage and file_storage.filename:
        _insert_instance(
            activity_log_service.build(
                ActivityLog.ACTION_UPLOAD,
                user=uploader,
                description=(
                    f"Admin '{uploader.email}' mengunggah ulang berkas template surat "
                    f"'{template.name}' ('{file_storage.filename}')."
                ),
            )
        )

    _update_instance(template)
    db.commit()
    return template


def delete_letter_template(template: LetterTemplate) -> None:
    if _exists(
        "SELECT 1 FROM `observation_requests` WHERE `letter_template_id` = %s AND `deleted_at` IS NULL LIMIT 1",
        (template.id,),
    ):
        raise AdminServiceError(
            "Template surat tidak dapat dihapus karena sudah pernah dipakai pada pengajuan. "
            "Nonaktifkan saja melalui form edit."
        )
    _soft_delete_instance(template)
    _update_instance(template)
    db.commit()


# ======================================================================
# Konfigurasi Surat: Setting Margin Default (FR-43 / UC-27)
# ======================================================================

def get_margin_setting() -> dict:
    setting_row = db.fetchone(
        "SELECT * FROM `system_settings` WHERE `setting_key` = %s LIMIT 1",
        (SystemSetting.KEY_LETTER_MARGIN,),
    )
    if setting_row is None:
        return dict(DEFAULT_MARGIN)
    try:
        raw = json.loads(setting_row["setting_value"])
        return {
            "top": Decimal(str(raw.get("margin_top", DEFAULT_MARGIN["top"]))),
            "bottom": Decimal(str(raw.get("margin_bottom", DEFAULT_MARGIN["bottom"]))),
            "left": Decimal(str(raw.get("margin_left", DEFAULT_MARGIN["left"]))),
            "right": Decimal(str(raw.get("margin_right", DEFAULT_MARGIN["right"]))),
        }
    except (ValueError, TypeError, InvalidOperation, json.JSONDecodeError):
        current_app.logger.error("Nilai system_settings['%s'] rusak, memakai default.", SystemSetting.KEY_LETTER_MARGIN)
        return dict(DEFAULT_MARGIN)


def update_margin_setting(data: dict, actor: User) -> SystemSetting:
    value = json.dumps(
        {
            "margin_top": str(data["margin_top"]),
            "margin_bottom": str(data["margin_bottom"]),
            "margin_left": str(data["margin_left"]),
            "margin_right": str(data["margin_right"]),
        }
    )
    row = db.fetchone(
        "SELECT * FROM `system_settings` WHERE `setting_key` = %s LIMIT 1",
        (SystemSetting.KEY_LETTER_MARGIN,),
    )
    if row is None:
        setting = SystemSetting(
            setting_key=SystemSetting.KEY_LETTER_MARGIN,
            setting_value=value,
            description="Margin surat default (dipakai jika belum ada Template Surat aktif).",
            updated_by=actor.id,
        )
        _insert_instance(setting)
    else:
        setting = SystemSetting.from_row(row)
        setting.setting_value = value
        setting.updated_by = actor.id
        _update_instance(setting)
    db.commit()
    return setting


def get_margin_setting() -> dict:
    row = db.fetchone(
        "SELECT `margin_atas`, `margin_kiri`, `margin_bawah`, `margin_kanan`, `ruang_aman_kop`, `id_background` "
        "FROM `pengaturan_kop` ORDER BY `id_pengaturan` DESC LIMIT 1"
    )
    if row is None:
        return {"top": 20, "left": 20, "bottom": 20, "right": 20, "header_clearance": 20, "id_background": None}
    return {
        "top": row["margin_atas"],
        "left": row["margin_kiri"],
        "bottom": row["margin_bawah"],
        "right": row["margin_kanan"],
        "header_clearance": row["ruang_aman_kop"] if row["ruang_aman_kop"] is not None else 20,
        "id_background": row["id_background"],
    }


def _validate_kop_margin(value, field_label: str):
    if value is None or str(value).strip() == "":
        raise AdminServiceError(f"{field_label} wajib diisi.")
    try:
        margin = Decimal(str(value))
    except (InvalidOperation, ValueError):
        raise AdminServiceError(f"{field_label} harus berupa angka.")
    if margin < 0:
        raise AdminServiceError(f"{field_label} tidak boleh negatif.")
    return margin


def _normalize_background_id(value):
    if value is None or str(value).strip() == "":
        return None
    try:
        background_id = int(value)
    except (TypeError, ValueError):
        raise AdminServiceError("Background KOP tidak valid.")
    if db.scalar("SELECT 1 FROM `file_cloudinary` WHERE `id_file` = %s LIMIT 1", (background_id,)) is None:
        raise AdminServiceError("Background KOP tidak ditemukan.")
    return background_id


def update_margin_setting(data: dict, actor: User):
    row = db.fetchone("SELECT `id_pengaturan` FROM `pengaturan_kop` ORDER BY `id_pengaturan` DESC LIMIT 1")
    params = (
        _validate_kop_margin(data.get("margin_top"), "Margin Atas"),
        _validate_kop_margin(data.get("margin_left"), "Margin Kiri"),
        _validate_kop_margin(data.get("margin_bottom"), "Margin Bawah"),
        _validate_kop_margin(data.get("margin_right"), "Margin Kanan"),
        _validate_kop_margin(data.get("header_clearance"), "Ruang Aman Kop"),
        _normalize_background_id(data.get("id_background")),
    )
    if row:
        db.execute(
            "UPDATE `pengaturan_kop` SET `margin_atas` = %s, `margin_kiri` = %s, "
            "`margin_bawah` = %s, `margin_kanan` = %s, `ruang_aman_kop` = %s, `id_background` = %s WHERE `id_pengaturan` = %s",
            (*params, row["id_pengaturan"]),
        )
    else:
        db.execute(
            "INSERT INTO `pengaturan_kop` (`margin_atas`, `margin_kiri`, `margin_bawah`, `margin_kanan`, `ruang_aman_kop`, `id_background`) "
            "VALUES (%s, %s, %s, %s, %s, %s)",
            params,
        )
    db.commit()
    return get_margin_setting()


# ======================================================================
# Konfigurasi Surat: Template Email (FR-44 / UC-28)
# ======================================================================

# Daftar baku jenis notifikasi email yang bisa dikustomisasi Admin, selaras
# dengan fungsi `notify_*` pada `app/services/email_service.py` (Tahap 9).
EMAIL_TEMPLATE_TYPES = {
    "lecturer_approved": "Dosen Menyetujui Pengajuan",
    "lecturer_rejected": "Dosen Menolak Pengajuan",
    "head_of_program_rejected": "Kaprodi Menolak Pengajuan",
    "official_letter_issued": "Surat Resmi Terbit",
}


def _email_template_key(type_key: str) -> str:
    return f"email_template:{type_key}"


def list_email_template_overrides() -> dict:
    """Map type_key -> {"subject": str, "html_body": str} | None (None jika masih memakai bawaan)."""
    result = {}
    for type_key in EMAIL_TEMPLATE_TYPES:
        row = db.fetchone(
            "SELECT * FROM `system_settings` WHERE `setting_key` = %s LIMIT 1",
            (_email_template_key(type_key),),
        )
        if row is None:
            result[type_key] = None
            continue
        try:
            result[type_key] = json.loads(row["setting_value"])
        except json.JSONDecodeError:
            result[type_key] = None
    return result


def get_email_template_override(type_key: str) -> dict | None:
    if type_key not in EMAIL_TEMPLATE_TYPES:
        raise AdminServiceError(f"Jenis template email '{type_key}' tidak dikenal.")
    row = db.fetchone(
        "SELECT * FROM `system_settings` WHERE `setting_key` = %s LIMIT 1",
        (_email_template_key(type_key),),
    )
    if row is None:
        return None
    try:
        return json.loads(row["setting_value"])
    except json.JSONDecodeError:
        return None


def save_email_template_override(type_key: str, data: dict, actor: User) -> SystemSetting:
    if type_key not in EMAIL_TEMPLATE_TYPES:
        raise AdminServiceError(f"Jenis template email '{type_key}' tidak dikenal.")
    value = json.dumps({"subject": data["subject"].strip(), "html_body": data["html_body"]})
    key = _email_template_key(type_key)
    row = db.fetchone(
        "SELECT * FROM `system_settings` WHERE `setting_key` = %s LIMIT 1",
        (key,),
    )
    if row is None:
        setting = SystemSetting(
            setting_key=key,
            setting_value=value,
            description=f"Override template email: {EMAIL_TEMPLATE_TYPES[type_key]}",
            updated_by=actor.id,
        )
        _insert_instance(setting)
    else:
        setting = SystemSetting.from_row(row)
        setting.setting_value = value
        setting.updated_by = actor.id
        _update_instance(setting)
    db.commit()
    return setting


def reset_email_template_override(type_key: str) -> None:
    """Kembalikan ke template bawaan (hapus override) — FR-44."""
    db.execute(
        "DELETE FROM `system_settings` WHERE `setting_key` = %s",
        (_email_template_key(type_key),),
    )
    db.commit()


# ======================================================================
# Log Aktivitas (FR-45 / UC-29)
# ======================================================================

def list_activity_logs(page: int = 1, action: str | None = None):
    base_sql = "SELECT * FROM `activity_logs`"
    count_sql = "SELECT COUNT(*) FROM `activity_logs`"
    params: list[object] = []
    if action:
        base_sql += " WHERE `action` = %s"
        count_sql += " WHERE `action` = %s"
        params.append(action)
    base_sql += " ORDER BY `created_at` DESC"
    return _paginate_models_by_sql(ActivityLog, base_sql, count_sql, params, page)


def list_observation_requests(page: int = 1, status: str | None = None, search: str | None = None):
    base_sql = (
        "SELECT orq.* FROM `observation_requests` AS orq "
        "JOIN `students` AS s ON s.`id` = orq.`student_id` "
        "JOIN `users` AS u ON u.`id` = s.`user_id` "
        "WHERE orq.`deleted_at` IS NULL"
    )
    count_sql = (
        "SELECT COUNT(*) FROM `observation_requests` AS orq "
        "JOIN `students` AS s ON s.`id` = orq.`student_id` "
        "JOIN `users` AS u ON u.`id` = s.`user_id` "
        "WHERE orq.`deleted_at` IS NULL"
    )
    params: list[object] = []
    if status:
        status_groups = {
            "approved": [ObservationRequest.STATUS_SELESAI],
            "rejected": [ObservationRequest.STATUS_DITOLAK_DOSEN, ObservationRequest.STATUS_DITOLAK_KAPRODI],
            "pending": [ObservationRequest.STATUS_MENUNGGU_DOSEN, ObservationRequest.STATUS_MENUNGGU_KAPRODI],
        }
        statuses = status_groups.get(status, [status])
        placeholders = ", ".join(["%s"] * len(statuses))
        base_sql += f" AND orq.`status` IN ({placeholders})"
        count_sql += f" AND orq.`status` IN ({placeholders})"
        params.extend(statuses)
    if search:
        search_term = f"%{search}%"
        search_sql = (
            " AND (u.`name` LIKE %s OR s.`nim` LIKE %s OR orq.`course_name` LIKE %s "
            "OR orq.`topic` LIKE %s OR orq.`destination_institution` LIKE %s "
            "OR CAST(orq.`id` AS CHAR) LIKE %s)"
        )
        base_sql += search_sql
        count_sql += search_sql
        params.extend([search_term] * 6)
    base_sql += " ORDER BY orq.`created_at` DESC"
    return _paginate_models_by_sql(ObservationRequest, base_sql, count_sql, params, page)


def submission_history_summary() -> dict:
    approved = _count(
        "SELECT COUNT(*) FROM `observation_requests` WHERE `deleted_at` IS NULL AND `status` = %s",
        (ObservationRequest.STATUS_SELESAI,),
    )
    rejected = _count(
        "SELECT COUNT(*) FROM `observation_requests` WHERE `deleted_at` IS NULL AND `status` IN (%s, %s)",
        (ObservationRequest.STATUS_DITOLAK_DOSEN, ObservationRequest.STATUS_DITOLAK_KAPRODI),
    )
    pending = _count(
        "SELECT COUNT(*) FROM `observation_requests` WHERE `deleted_at` IS NULL AND `status` IN (%s, %s)",
        (ObservationRequest.STATUS_MENUNGGU_DOSEN, ObservationRequest.STATUS_MENUNGGU_KAPRODI),
    )
    return {"approved": approved, "rejected": rejected, "pending": pending}


def delete_submission_history_bulk(request_ids) -> int:
    """Hard-delete pengajuan yang dipilih beserta relasi FK langsungnya."""
    try:
        ids = sorted({int(request_id) for request_id in request_ids if int(request_id) > 0})
    except (TypeError, ValueError):
        raise AdminServiceError("Data riwayat pengajuan tidak valid.")
    if not ids:
        raise AdminServiceError("Pilih minimal satu riwayat pengajuan.")

    placeholders = ", ".join(["%s"] * len(ids))
    rows = db.fetchall(
        f"SELECT `id_pengajuan` FROM `pengajuan_observasi` WHERE `id_pengajuan` IN ({placeholders})",
        ids,
    )
    existing_ids = [row["id_pengajuan"] for row in rows]
    if not existing_ids:
        raise AdminServiceError("Riwayat pengajuan yang dipilih tidak ditemukan.")

    existing_placeholders = ", ".join(["%s"] * len(existing_ids))
    dependencies = db.fetchall(
        "SELECT `TABLE_NAME`, `COLUMN_NAME` FROM `information_schema`.`KEY_COLUMN_USAGE` "
        "WHERE `REFERENCED_TABLE_SCHEMA` = DATABASE() "
        "AND `REFERENCED_TABLE_NAME` = %s",
        ("pengajuan_observasi",),
    )
    try:
        for dependency in dependencies:
            table_name = dependency["TABLE_NAME"]
            column_name = dependency["COLUMN_NAME"]
            if not (table_name.replace("_", "").isalnum() and column_name.replace("_", "").isalnum()):
                raise AdminServiceError("Relasi riwayat pengajuan tidak valid.")
            db.execute(
                f"DELETE FROM `{table_name}` WHERE `{column_name}` IN ({existing_placeholders})",
                existing_ids,
            )
        db.execute(
            f"DELETE FROM `pengajuan_observasi` WHERE `id_pengajuan` IN ({existing_placeholders})",
            existing_ids,
        )
        db.commit()
    except Exception as exc:
        db.rollback()
        if isinstance(exc, AdminServiceError):
            raise
        raise AdminServiceError("Gagal menghapus riwayat pengajuan.") from exc
    return len(existing_ids)


def distinct_activity_actions() -> list[str]:
    rows = db.fetchall(
        "SELECT DISTINCT `action` FROM `activity_logs` ORDER BY `action` ASC"
    )
    return [row["action"] for row in rows]


# ======================================================================
# Dashboard Statistik (FR-46 / UC-30)
# ======================================================================

def dashboard_summary() -> dict:
    total_students = _count("SELECT COUNT(DISTINCT `nim`) FROM `pengajuan_observasi`")
    total_lecturers = _count(
        "SELECT COUNT(*) FROM `dosen` AS d "
        "JOIN `pengguna` AS u ON u.`id_pengguna` = d.`id_pengguna` "
        "WHERE u.`status_aktif` = 1"
    )
    total_head_of_programs = _count(
        "SELECT COUNT(*) FROM `kaprodi` AS k "
        "JOIN `pengguna` AS u ON u.`id_pengguna` = k.`id_pengguna` "
        "WHERE u.`status_aktif` = 1"
    )
    total_study_programs = _count("SELECT COUNT(*) FROM `program_studi`")
    total_requests = _count("SELECT COUNT(*) FROM `pengajuan_observasi`")
    total_finished = _count(
        "SELECT COUNT(*) FROM `pengajuan_observasi` WHERE LOWER(`status_pengajuan`) = %s",
        ("disetujui",),
    )
    total_pending = _count(
        "SELECT COUNT(*) FROM `pengajuan_observasi` WHERE LOWER(`status_pengajuan`) = %s",
        ("menunggu",),
    )
    total_rejected = _count(
        "SELECT COUNT(*) FROM `pengajuan_observasi` WHERE LOWER(`status_pengajuan`) = %s",
        ("ditolak",),
    )
    total_email_sent = 0
    total_email_failed = 0
    total_storage_bytes = 0

    status_rows = db.fetchall(
        "SELECT `status_pengajuan` AS `status`, COUNT(*) AS `count` "
        "FROM `pengajuan_observasi` GROUP BY `status_pengajuan` ORDER BY `status_pengajuan` ASC"
    )
    requests_per_status = {row["status"]: row["count"] for row in status_rows}

    created_rows = db.fetchall("SELECT `tanggal_pengajuan` FROM `pengajuan_observasi`")
    all_created_at = [row["tanggal_pengajuan"] for row in created_rows]
    trend = monthly_trend(all_created_at, lambda dt: dt)
    avg_completion = 0

    requests_per_prodi_rows = db.fetchall(
        "SELECT ps.`nama_program_studi` AS `name`, COUNT(po.`id_pengajuan`) AS `count` "
        "FROM `program_studi` AS ps "
        "LEFT JOIN `pengajuan_observasi` AS po ON po.`id_program_studi` = ps.`id_program_studi` "
        "GROUP BY ps.`id_program_studi`, ps.`nama_program_studi` "
        "ORDER BY `count` DESC"
    )

    margin_row = db.fetchone(
        "SELECT `margin_atas`, `margin_kiri`, `margin_bawah`, `margin_kanan` "
        "FROM `pengaturan_kop` ORDER BY `id_pengaturan` DESC LIMIT 1"
    )
    margin_setting = {
        "top": margin_row["margin_atas"] if margin_row else 20,
        "left": margin_row["margin_kiri"] if margin_row else 20,
        "bottom": margin_row["margin_bawah"] if margin_row else 20,
        "right": margin_row["margin_kanan"] if margin_row else 20,
    }

    return {
        "total_students": total_students,
        "total_lecturers": total_lecturers,
        "total_head_of_programs": total_head_of_programs,
        "total_study_programs": total_study_programs,
        "total_requests": total_requests,
        "total_finished": total_finished,
        "total_pending": total_pending,
        "total_rejected": total_rejected,
        "total_email_sent": total_email_sent,
        "total_email_failed": total_email_failed,
        "total_storage_mb": round((total_storage_bytes or 0) / (1024 * 1024), 2),
        "requests_per_status": requests_per_status,
        "all_statuses": ObservationRequest.ALL_STATUSES,
        "monthly_trend": trend,
        "avg_completion_hours": avg_completion,
        "margin_setting": margin_setting,
        "requests_per_prodi": [
            {"name": row["name"], "code": "", "count": row["count"]}
            for row in requests_per_prodi_rows
        ],
    }


def _history_status_groups(status: str | None):
    if not status:
        return None
    groups = {
        "approved": ["disetujui", "selesai"],
        "rejected": ["ditolak"],
        "pending": ["menunggu"],
    }
    return groups.get(status, [status.lower()])


def list_observation_requests(page: int = 1, status: str | None = None, search: str | None = None):
    from backend.services import observation_service as obs_service

    where = []
    params: list[object] = []
    statuses = _history_status_groups(status)
    if statuses:
        placeholders = ", ".join(["%s"] * len(statuses))
        where.append(f"LOWER(po.`status_pengajuan`) IN ({placeholders})")
        params.extend(statuses)
    if search:
        search_term = f"%{search}%"
        where.append(
            "(po.`nama_mahasiswa` LIKE %s OR po.`nim` LIKE %s OR po.`mata_kuliah` LIKE %s "
            "OR po.`nama_penerima` LIKE %s OR po.`nama_instansi` LIKE %s "
            "OR ds.`nomor_dokumen` LIKE %s OR du.`nama` LIKE %s)"
        )
        params.extend([search_term] * 7)
    where_sql = f"WHERE {' AND '.join(where)}" if where else ""
    return obs_service._paginate_pengajuan(where_sql, params, page)


def submission_history_summary() -> dict:
    approved = _count(
        "SELECT COUNT(*) FROM `pengajuan_observasi` WHERE LOWER(`status_pengajuan`) IN (%s, %s)",
        ("disetujui", "selesai"),
    )
    rejected = _count(
        "SELECT COUNT(*) FROM `pengajuan_observasi` WHERE LOWER(`status_pengajuan`) = %s",
        ("ditolak",),
    )
    pending = _count(
        "SELECT COUNT(*) FROM `pengajuan_observasi` WHERE LOWER(`status_pengajuan`) = %s",
        ("menunggu",),
    )
    return {"approved": approved, "rejected": rejected, "pending": pending}
