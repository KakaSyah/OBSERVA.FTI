"""
backend/services/activity_log_service.py

Tahap 12 — Activity Log & Audit Trail lintas modul (FR-53..FR-55, NFR
Auditability Tahap 1 bagian 4). Menyediakan API tunggal untuk mencatat
baris `activity_logs`, dikonsumsi oleh:
- `app/routes/auth_routes.py`            (login, logout)
- `app/services/observation_service.py`  (approve, reject, generate_pdf,
  send_email pada alur Dosen & Kaprodi)
- `app/services/admin_service.py`        (upload kop surat & template surat)
- `app/controllers/mahasiswa_controller.py` (generate_pdf saat print draft)
- `app/middlewares/error_handler.py`     (error 403/429/500)

Cakupan aksi SENGAJA dibatasi persis pada 8 konstanta `ActivityLog.ACTION_*`
(login, logout, approve, reject, upload, generate_pdf, send_email, error)
— daftar yang sama persis dengan NFR Auditability Tahap 1 bagian 4. Aksi
CRUD master data murni (kelola mahasiswa/dosen/kaprodi/prodi di Tahap 10)
TIDAK termasuk cakupan tahap ini karena tidak masuk daftar tsb; aksi
tersebut tetap tercatat lewat `app.logger` teknis seperti sebelumnya.
Penghapusan berkas (kop surat/template) juga tidak dicatat di sini dengan
alasan yang sama (tidak ada konstanta aksi "delete" pada model) — hanya
UNGGAHnya yang dicatat sesuai FR-41/FR-42.

Dua gaya pemakaian, menyesuaikan dengan pola commit yang sudah dipakai
modul lain sejak Tahap 8-9 (`letter_number_service.generate_for_request`,
`email_service.notify_*`):

- `build(...)`  : membuat instance `ActivityLog` TANPA commit. Dipakai saat
  pencatatan harus ikut dalam transaksi atomik yang sama dengan mutasi
  lain (mis. approve/reject di `observation_service`, sesuai NFR
  Reliability Tahap 1 bagian 4). Pemanggil bertanggung jawab melakukan
  `db.session.add(...)` sebelum `db.session.commit()` miliknya sendiri.
- `record(...)` : membuat + `db.session.add()` + `db.session.commit()`
  dalam transaksi sendiri. Dipakai untuk aksi berdiri sendiri yang bukan
  bagian dari transaksi domain lain (login, logout, error handler global).

Prinsip penting: audit trail TIDAK BOLEH pernah menggagalkan aksi utama
pengguna. `record()` membungkus commit-nya sendiri dengan try/except —
jika penulisan log gagal, di-rollback & dicatat ke `app.logger` teknis,
bukan dilempar sebagai exception ke pemanggil.
"""

from __future__ import annotations

from flask import current_app
from flask import request as flask_request

from backend.extensions import db
from backend.models.activity_log import ActivityLog


def _client_ip() -> str | None:
    """IP klien dari konteks request HTTP aktif, atau None bila dipanggil
    di luar request (mis. dari Flask CLI/command Tahap 4)."""
    try:
        return flask_request.remote_addr
    except RuntimeError:
        return None


def _resolve_user_id(user) -> int | None:
    """Terima baik objek `User`/`current_user` maupun langsung user_id (int)."""
    if user is None:
        return None
    return getattr(user, "id", user)


def build(
    action: str,
    *,
    user=None,
    description: str | None = None,
    ip_address: str | None = None,
) -> ActivityLog:
    """Buat instance `ActivityLog` TANPA commit (lihat catatan modul di atas)."""
    return ActivityLog(
        user_id=_resolve_user_id(user),
        action=action,
        description=(description or "").strip()[:500] or None,
        ip_address=ip_address if ip_address is not None else _client_ip(),
    )


def _insert_activity_log(user_id: int | None, action: str, description: str | None, ip_address: str | None) -> int:
    """Insert one activity_log row using raw SQL and return the inserted id."""
    return db.insert(
        "INSERT INTO `activity_logs` (`user_id`, `action`, `description`, `ip_address`) "
        "VALUES (%s, %s, %s, %s)",
        (user_id, action, description, ip_address),
    )


def record(
    action: str,
    *,
    user=None,
    description: str | None = None,
    ip_address: str | None = None,
) -> ActivityLog | None:
    """Buat + simpan satu baris `ActivityLog` dalam transaksi sendiri.

    Mengembalikan `None` (bukan melempar exception) jika penulisan log
    gagal, agar aksi utama pengguna tidak pernah gagal hanya karena audit
    trail bermasalah.
    """
    log = build(action, user=user, description=description, ip_address=ip_address)
    try:
        _insert_activity_log(
            user_id=log.user_id,
            action=log.action,
            description=log.description,
            ip_address=log.ip_address,
        )
        db.commit()
        return log
    except Exception as exc:  # noqa: BLE001 - audit trail tidak boleh menggagalkan aksi utama
        db.rollback()
        current_app.logger.error(
            "Gagal mencatat activity_log (action=%s): %s", action, exc
        )
        return None


# =====================================================================
# ---------- Helper per-aksi (memetakan konstanta ActivityLog) --------
# =====================================================================

def log_login(user, description: str | None = None) -> ActivityLog | None:
    """FR-01/FR-55 (UC-01/08/14/20): login berhasil untuk seluruh role."""
    return record(
        ActivityLog.ACTION_LOGIN,
        user=user,
        description=description or f"Login berhasil untuk '{user.email}'.",
    )


def log_logout(user, description: str | None = None) -> ActivityLog | None:
    """FR-04/FR-55: logout & invalidasi session untuk seluruh role."""
    return record(
        ActivityLog.ACTION_LOGOUT,
        user=user,
        description=description or f"Logout untuk '{user.email}'.",
    )


def log_error(description: str, user=None) -> ActivityLog | None:
    """FR-55/NFR Auditability: kegagalan proses penting (login gagal,
    penerbitan surat gagal, error tak tertangani, dsb.)."""
    return record(ActivityLog.ACTION_ERROR, user=user, description=description)


def log_upload(user, description: str) -> ActivityLog | None:
    """FR-41/FR-42/FR-55: unggah kop surat, logo, atau template surat."""
    return record(ActivityLog.ACTION_UPLOAD, user=user, description=description)


def log_generate_pdf(user, description: str) -> ActivityLog | None:
    """FR-51/FR-55: generate PDF berdiri sendiri (mis. cetak draft di
    `mahasiswa_controller.print_draft`) yang bukan bagian dari transaksi
    domain lain — dipakai lewat `record()` (commit sendiri). Untuk generate
    PDF yang merupakan bagian dari transaksi approval (surat resmi), pakai
    `build_generate_pdf()` agar ikut commit tunggal yang sama."""
    return record(ActivityLog.ACTION_GENERATE_PDF, user=user, description=description)


def build_approve(user, description: str) -> ActivityLog:
    """FR-22/FR-32/FR-55: persetujuan dosen atau kaprodi — dipakai lewat
    `build()` agar ikut dalam transaksi atomik approval di `observation_service`."""
    return build(ActivityLog.ACTION_APPROVE, user=user, description=description)


def build_reject(user, description: str) -> ActivityLog:
    """FR-23/FR-33/FR-55: penolakan dosen atau kaprodi — dipakai lewat
    `build()` agar ikut dalam transaksi atomik penolakan di `observation_service`."""
    return build(ActivityLog.ACTION_REJECT, user=user, description=description)


def build_generate_pdf(user, description: str) -> ActivityLog:
    """FR-51/FR-55: generate PDF draft maupun surat resmi — dipakai lewat
    `build()` agar ikut dalam transaksi atomik yang relevan."""
    return build(ActivityLog.ACTION_GENERATE_PDF, user=user, description=description)


def build_send_email(user, description: str) -> ActivityLog:
    """FR-52/FR-55: pengiriman email notifikasi (Resend) — dipakai lewat
    `build()` agar ikut dalam transaksi atomik approval/reject terkait."""
    return build(ActivityLog.ACTION_SEND_EMAIL, user=user, description=description)
