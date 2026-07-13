"""
backend/services/cloudinary_service.py

Konfigurasi koneksi Cloudinary SDK, serta fungsi upload/delete generik
(Tahap 8) yang dipakai observation_service untuk menyimpan PDF surat
resmi dari frontend (FR-51/FR-52 storage). Fungsi upload/kelola file
KHUSUS Kop Surat, Template Surat, Logo, dsb. beserta validasi tipe/ukuran
file-nya (FR-41, FR-42) menyusul pada Modul Admin (Tahap 10) — modul itu
dapat memakai ulang `upload_bytes`/`delete_resource` di bawah ini.
"""

import io
import logging
import time

import cloudinary
import cloudinary.uploader
import requests
from flask import current_app

from backend.extensions import db

logger = logging.getLogger(__name__)


class CloudinaryServiceError(Exception):
    """Error domain upload/delete Cloudinary (dipetakan observation_service ke pesan gagal approve)."""


def init_cloudinary(app):
    """
    Konfigurasi Cloudinary SDK menggunakan kredensial dari environment
    variable (.env). Dipanggil sekali saat app factory dijalankan.
    """
    cloud_name = app.config.get("CLOUDINARY_CLOUD_NAME")
    api_key = app.config.get("CLOUDINARY_API_KEY")
    api_secret = app.config.get("CLOUDINARY_API_SECRET")

    if not all([cloud_name, api_key, api_secret]):
        logger.warning(
            "Konfigurasi Cloudinary belum lengkap. "
            "Fitur upload file (kop surat/template/logo) belum dapat digunakan."
        )
        return

    cloudinary.config(
        cloud_name=cloud_name,
        api_key=api_key,
        api_secret=api_secret,
        secure=app.config.get("CLOUDINARY_SECURE", True),
    )
    logger.info("Cloudinary berhasil dikonfigurasi (cloud_name=%s).", cloud_name)


def _ensure_configured() -> None:
    if not cloudinary.config().cloud_name:
        raise CloudinaryServiceError(
            "Cloudinary belum dikonfigurasi (CLOUDINARY_CLOUD_NAME/API_KEY/API_SECRET "
            "kosong di .env)."
        )


def upload_bytes(
    data: bytes,
    *,
    public_id: str,
    folder: str | None = None,
    resource_type: str = "raw",
    overwrite: bool = True,
) -> dict:
    """
    Upload data biner (mis. PDF yang dibuat frontend) ke Cloudinary.

    `resource_type="raw"` dipakai untuk PDF surat resmi agar diunduh apa
    adanya (bukan dikonversi Cloudinary layaknya gambar). Mengembalikan
    dict hasil API Cloudinary (memuat `secure_url`, `public_id`, dst).
    Melempar `CloudinaryServiceError` jika konfigurasi kosong atau upload
    gagal, agar observation_service dapat me-rollback transaksi approval.
    """
    _ensure_configured()
    target_folder = folder or current_app.config.get("CLOUDINARY_UPLOAD_FOLDER")

    try:
        result = cloudinary.uploader.upload(
            io.BytesIO(data),
            public_id=public_id,
            folder=target_folder,
            resource_type=resource_type,
            overwrite=overwrite,
        )
    except Exception as exc:  # noqa: BLE001 - dibungkus jadi error domain yang seragam
        logger.error("Upload Cloudinary gagal (public_id=%s): %s", public_id, exc)
        raise CloudinaryServiceError(f"Gagal mengunggah file ke Cloudinary: {exc}") from exc

    return result


def delete_resource(public_id: str, resource_type: str = "raw") -> dict:
    """Hapus satu resource Cloudinary berdasarkan public_id (dipakai saat rollback/replace file)."""
    _ensure_configured()
    try:
        return cloudinary.uploader.destroy(public_id, resource_type=resource_type)
    except Exception as exc:  # noqa: BLE001
        logger.error("Hapus Cloudinary gagal (public_id=%s): %s", public_id, exc)
        raise CloudinaryServiceError(f"Gagal menghapus file di Cloudinary: {exc}") from exc


def _insert_cloudinary_file_record(observation_request_id: int, result: dict) -> int:
    try:
        return db.insert(
            "INSERT INTO `file_cloudinary` (`nama_file`, `public_id`, `secure_url`, `resource_type`) "
            "VALUES (%s, %s, %s, %s)",
            (
                f"surat-izin-observasi-{observation_request_id}.pdf",
                result.get("public_id"),
                result["secure_url"],
                result.get("resource_type", "raw"),
            ),
        )
    except Exception as exc:  # noqa: BLE001 - ubah ke error domain service
        raise CloudinaryServiceError(f"Gagal menyimpan metadata PDF Cloudinary: {exc}") from exc


def generate_signed_upload_params(observation_request_id: int) -> dict:
    """Buat parameter signed upload Cloudinary agar browser mengunggah PDF langsung ke Cloudinary."""
    _ensure_configured()
    public_id = f"surat-resmi/observation-request-{observation_request_id}"
    folder = current_app.config.get("CLOUDINARY_UPLOAD_FOLDER")
    timestamp = int(time.time())
    params_to_sign = {
        "public_id": public_id,
        "folder": folder,
        "resource_type": "raw",
        "timestamp": timestamp,
    }
    signature = cloudinary.utils.api_sign_request(params_to_sign, cloudinary.config().api_secret)
    cloud_name = cloudinary.config().cloud_name
    return {
        "timestamp": timestamp,
        "signature": signature,
        "api_key": cloudinary.config().api_key,
        "cloud_name": cloud_name,
        "public_id": public_id,
        "folder": folder,
        "resource_type": "raw",
        "upload_url": f"https://api.cloudinary.com/v1_1/{cloud_name}/raw/upload",
    }


def fetch_uploaded_bytes(secure_url: str, *, max_bytes: int) -> bytes:
    """Unduh bytes PDF dari Cloudinary secara server-side dengan batas maksimal."""
    _ensure_configured()
    if max_bytes <= 0:
        raise CloudinaryServiceError("Batas ukuran attachment email tidak valid.")

    try:
        response = requests.get(secure_url, stream=True, timeout=15)
        response.raise_for_status()
    except requests.RequestException as exc:
        raise CloudinaryServiceError(f"Gagal mengambil PDF dari Cloudinary: {exc}") from exc

    total_bytes = 0
    chunks = []
    try:
        for chunk in response.iter_content(chunk_size=1024 * 64):
            if not chunk:
                continue
            total_bytes += len(chunk)
            if total_bytes > max_bytes:
                raise CloudinaryServiceError("Ukuran PDF yang diunduh melebihi batas maksimum yang diizinkan.")
            chunks.append(chunk)
    finally:
        response.close()

    return b"".join(chunks)


def upload_official_letter_pdf(pdf_bytes: bytes, observation_request_id: int) -> dict:
    """
    FR-51/FR-52: unggah PDF surat resmi yang dibuat oleh browser.
    Dipakai observation_service saat endpoint upload PDF final Kaprodi dipanggil.
    """
    public_id = f"surat-resmi/observation-request-{observation_request_id}"
    result = upload_bytes(pdf_bytes, public_id=public_id, resource_type="raw", overwrite=True)
    file_id = _insert_cloudinary_file_record(observation_request_id, result)
    return {**result, "file_id": file_id}


def record_official_letter_pdf(cloudinary_result: dict, observation_request_id: int) -> dict:
    """Catat metadata PDF yang sudah diunggah client langsung ke Cloudinary."""
    _ensure_configured()
    expected_public_id = f"surat-resmi/observation-request-{observation_request_id}"
    public_id = cloudinary_result.get("public_id")
    if public_id != expected_public_id:
        raise CloudinaryServiceError(
            f"Public ID Cloudinary tidak sesuai dengan pengajuan ini: expected {expected_public_id}, got {public_id}."
        )

    try:
        cloudinary.api.resource(public_id, resource_type="raw")
    except Exception as exc:  # noqa: BLE001
        raise CloudinaryServiceError(f"Resource Cloudinary tidak ditemukan/valid: {exc}") from exc

    result = {
        "public_id": public_id,
        "secure_url": cloudinary_result["secure_url"],
        "resource_type": cloudinary_result.get("resource_type", "raw"),
    }
    file_id = _insert_cloudinary_file_record(observation_request_id, result)
    return {**result, "file_id": file_id}
