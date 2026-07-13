"""
backend/services/email_service.py

Tahap 9 — Integrasi email Resend (FR-15, FR-23, FR-33, FR-52, FR-54).

Berisi:
- `init_resend(app)`               : konfigurasi API key (Tahap 2, tidak berubah).
- `send_email(...)`                : wrapper generik kirim satu email via
  Resend, dengan retry sederhana (NFR Reliability bagian 4) sebanyak
  `EMAIL_MAX_ATTEMPTS` percobaan.
- `notify_*(...)`                  : satu fungsi per jenis notifikasi
  (dosen menyetujui/menolak, kaprodi menolak, surat resmi terbit dengan
  lampiran PDF), masing-masing me-render template HTML di
  `app/templates/emails/`, mengirim via `send_email`, lalu MENCATAT hasilnya
  (sukses/gagal) sebagai baris `EmailLog` (FR-54) yang dikembalikan ke
  pemanggil untuk ditambahkan ke sesi (`db.session.add`) — pola yang sama
  dengan `letter_number_service.generate_for_request` (Tahap 8): fungsi di
  modul ini TIDAK melakukan commit sendiri.

Catatan desain penting: kegagalan pengiriman email (mis. Resend API down)
SENGAJA tidak melempar exception ke pemanggil (observation_service) —
hanya dicatat sebagai `EmailLog` berstatus 'failed'. Surat resmi yang
sudah bernomor & tersimpan di Cloudinary (Tahap 8) tetap valid dan bisa
diunduh mahasiswa meskipun emailnya sempat gagal terkirim; observation_service
memakai status EmailLog ini untuk memutuskan status akhir pengajuan
('Selesai' jika terkirim, tetap 'Surat Dikirim' jika gagal — lihat
`approve_by_head_of_program`).

Sesuai Activity Diagram Tahap 1 bagian 6, hanya mahasiswa yang menerima
EMAIL (via Resend). Notifikasi ke Dosen/Kaprodi pada diagram tersebut
ditandai "(in-app)" — sistem notifikasi in-app membutuhkan tabel baru di
luar ERD Tahap 1 sehingga sengaja belum diimplementasikan di sini.
"""

import base64
import logging
import time

from flask import current_app, render_template
from jinja2.sandbox import SandboxedEnvironment
import resend

from backend.models.email_log import EmailLog

logger = logging.getLogger(__name__)

# Tahap 13 (Hardening Keamanan): subjek & isi HTML Template Email BOLEH
# diganti Admin lewat FR-44 (/admin/template-email) dan sebelumnya
# di-render langsung memakai `current_app.jinja_env` -- Jinja environment
# PENUH aplikasi, yang memberi akses ke objek/atribut internal Python
# (mis. `{{ ''.__class__.__mro__ }}`) sehingga berpotensi Server-Side
# Template Injection (SSTI) jika akun Admin diambil alih. Override kini
# di-render lewat `SandboxedEnvironment` (Jinja2 bawaan) yang memblokir
# akses ke atribut/metode "tidak aman" (dunder, `__globals__`, dsb.),
# sementara variabel konteks biasa (`observation_request.topic`, dst.)
# tetap bisa dipakai seperti sebelumnya.
_sandboxed_env = SandboxedEnvironment(autoescape=True)


class EmailServiceError(Exception):
    """Error domain pengiriman email (dipakai internal; TIDAK menembus ke observation_service)."""


def init_resend(app):
    """
    Konfigurasi Resend API key dari environment variable (.env).
    Dipanggil sekali saat app factory dijalankan.
    """
    api_key = app.config.get("RESEND_API_KEY")

    if not api_key:
        logger.warning(
            "RESEND_API_KEY belum diset. Fitur pengiriman email belum dapat digunakan."
        )
        return

    resend.api_key = api_key
    logger.info(
        "Resend berhasil dikonfigurasi (sender=%s).",
        app.config.get("RESEND_SENDER_EMAIL"),
    )


def _sender() -> str:
    name = current_app.config.get("RESEND_SENDER_NAME")
    email = current_app.config.get("RESEND_SENDER_EMAIL")
    return f"{name} <{email}>" if name else email


def send_email(*, to: str, subject: str, html: str, attachment: dict | None = None) -> dict:
    """
    Kirim satu email via Resend, dengan retry sederhana sebanyak
    `EMAIL_MAX_ATTEMPTS` (default 2) percobaan sebelum menyerah.

    `attachment` (opsional): dict `{"filename": str, "content": bytes}`.

    Mengembalikan dict hasil API Resend (memuat `id`) jika sukses.
    Melempar `EmailServiceError` jika seluruh percobaan gagal — fungsi ini
    dipanggil dari dalam `notify_*` di bawah, yang MENANGKAP error tersebut
    agar tidak menembus ke observation_service.
    """
    api_key = current_app.config.get("RESEND_API_KEY")
    if not api_key:
        raise EmailServiceError("RESEND_API_KEY belum dikonfigurasi di .env.")

    params = {
        "from": _sender(),
        "to": [to],
        "subject": subject,
        "html": html,
    }
    if attachment is not None:
        params["attachments"] = [
            {
                "filename": attachment["filename"],
                # Resend REST API menerima isi lampiran sebagai base64 string.
                "content": base64.b64encode(attachment["content"]).decode("ascii"),
            }
        ]

    max_attempts = max(1, current_app.config.get("EMAIL_MAX_ATTEMPTS", 2))
    last_error: Exception | None = None

    for attempt in range(1, max_attempts + 1):
        try:
            result = resend.Emails.send(params)
            return result
        except Exception as exc:  # noqa: BLE001 - Resend SDK bisa melempar berbagai jenis error
            last_error = exc
            logger.warning(
                "Percobaan kirim email ke '%s' gagal (attempt %s/%s): %s",
                to, attempt, max_attempts, exc,
            )
            if attempt < max_attempts:
                time.sleep(0.5)  # retry sederhana sesuai NFR Reliability, bukan job queue

    raise EmailServiceError(f"Gagal mengirim email setelah {max_attempts} percobaan: {last_error}")


def _render_with_override(template_name: str, default_subject: str, render_context: dict):
    """
    FR-44 (Tahap 10): jika Admin sudah mengganti subjek/isi HTML jenis
    notifikasi `template_name` lewat `/admin/template-email`, pakai versi
    itu (di-render sebagai string Jinja dengan variabel yang sama seperti
    template bawaan). Jika override tidak ada, error saat parsing, atau
    render-nya gagal (mis. Admin salah ketik syntax Jinja), JATUH KEMBALI
    ke file template bawaan di `app/templates/emails/` agar pengiriman
    notifikasi tidak pernah gagal hanya karena kesalahan isi kustomisasi.
    """
    from backend.services import admin_service  # import ditunda: hindari import silang di level modul

    try:
        override = admin_service.get_email_template_override(template_name)
    except Exception:  # noqa: BLE001 - jenis template tak dikenal / DB bermasalah -> pakai bawaan
        override = None

    if override:
        try:
            subject = _sandboxed_env.from_string(override["subject"]).render(**render_context)
            html = _sandboxed_env.from_string(override["html_body"]).render(**render_context)
            return subject, html
        except Exception as exc:  # noqa: BLE001
            logger.error(
                "Override template email '%s' gagal di-render (%s), memakai template bawaan.",
                template_name, exc,
            )

    html = render_template(f"emails/{template_name}.html", **render_context)
    return default_subject, html


def _notify(
    *,
    observation_request,
    template_name: str,
    subject: str,
    context: dict,
    attachment: dict | None = None,
) -> EmailLog:
    """Helper internal bersama seluruh fungsi `notify_*` di bawah (render -> kirim -> catat log)."""
    recipient = observation_request.student.user.email
    render_context = {"observation_request": observation_request, **context}
    subject, html = _render_with_override(template_name, subject, render_context)

    try:
        result = send_email(to=recipient, subject=subject, html=html, attachment=attachment)
        return EmailLog(
            observation_request_id=observation_request.id,
            recipient_email=recipient,
            subject=subject,
            status=EmailLog.STATUS_SENT,
            provider_message_id=result.get("id") if isinstance(result, dict) else None,
        )
    except EmailServiceError as exc:
        current_app.logger.error(
            "Notifikasi email '%s' untuk pengajuan id=%s gagal: %s",
            template_name, observation_request.id, exc,
        )
        return EmailLog(
            observation_request_id=observation_request.id,
            recipient_email=recipient,
            subject=subject,
            status=EmailLog.STATUS_FAILED,
            error_message=str(exc)[:500],
        )


# ---------- Modul Dosen (Tahap 6): FR-15 lanjutan dari approve/reject dosen ----------

def notify_lecturer_approved(obs, note: str | None = None) -> EmailLog:
    """FR-15/FR-22: dosen menyetujui, pengajuan diteruskan ke Kaprodi."""
    subject = f"Pengajuan Disetujui Dosen — {obs.topic}"
    return _notify(
        observation_request=obs,
        template_name="lecturer_approved",
        subject=subject,
        context={"approval_note": note},
    )


def notify_lecturer_rejected(obs) -> EmailLog:
    """FR-15/FR-23: dosen menolak pengajuan."""
    subject = f"Pengajuan Ditolak Dosen — {obs.topic}"
    return _notify(
        observation_request=obs,
        template_name="lecturer_rejected",
        subject=subject,
        context={"rejection_note": obs.rejection_note},
    )


# ---------- Modul Kaprodi (Tahap 7): FR-15 lanjutan dari approve/reject kaprodi ----------

def notify_head_of_program_rejected(obs) -> EmailLog:
    """FR-15/FR-33: kaprodi menolak pengajuan sebagai persetujuan akhir."""
    subject = f"Pengajuan Ditolak Kaprodi — {obs.topic}"
    return _notify(
        observation_request=obs,
        template_name="head_of_program_rejected",
        subject=subject,
        context={"rejection_note": obs.rejection_note},
    )


def notify_official_letter_issued(obs, pdf_bytes: bytes) -> EmailLog:
    """
    FR-32/FR-52: kaprodi menyetujui -> surat resmi terbit. Mengirim PDF
    sebagai lampiran. WAJIB dipanggil setelah `obs.letter_number` terisi
    (Tahap 8, `letter_number_service.generate_for_request`).
    """
    subject = f"Surat Izin Observasi Resmi Terbit — {obs.letter_number.formatted_number}"
    filename = f"surat-izin-observasi-{obs.student.nim}-{obs.id}.pdf"
    return _notify(
        observation_request=obs,
        template_name="official_letter_issued",
        subject=subject,
        context={"letter_number": obs.letter_number},
        attachment={"filename": filename, "content": pdf_bytes},
    )
