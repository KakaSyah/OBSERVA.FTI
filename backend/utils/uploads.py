"""
backend/utils/uploads.py

Tahap 13 (Hardening Keamanan & Validasi Menyeluruh) — pelengkap validasi
upload file yang sejak Tahap 10 baru memeriksa EKSTENSI nama file lewat
`FileAllowed` (Flask-WTF, app/forms/admin_forms.py). Ekstensi mudah
dipalsukan (mis. mengganti nama `shell.php.png`), jadi di sini konten file
turut diperiksa sebelum diunggah ke Cloudinary (FR-41/FR-42):

- Tanda tangan biner (magic bytes) dicocokkan dengan kategori file yang
  diharapkan (image/pdf/docx).
- Khusus gambar, turut diverifikasi lewat Pillow (`Image.verify()`) agar
  file yang sekadar punya header PNG/JPEG valid tapi isinya rusak/bukan
  gambar sungguhan tetap ditolak.
- Ukuran per-file dibatasi terpisah dari `MAX_CONTENT_LENGTH` (yang
  membatasi total ukuran request, bukan satu file individual).

Dipakai oleh `app/services/admin_service.py` pada seluruh titik upload
(kop surat/logo, template surat).
"""

from __future__ import annotations

import io


class UploadValidationError(Exception):
    """Error domain: isi file tidak sesuai/tidak valid untuk kategori yang diharapkan."""


# Tanda tangan biner (beberapa byte pertama) per kategori file yang didukung.
_IMAGE_SIGNATURES = (
    b"\x89PNG\r\n\x1a\n",  # PNG
    b"\xff\xd8\xff",  # JPEG
)
_PDF_SIGNATURE = b"%PDF-"
# DOCX adalah arsip ZIP (Office Open XML) -> selalu diawali signature ZIP.
_DOCX_SIGNATURE = b"PK\x03\x04"

CATEGORY_IMAGE = "image"
CATEGORY_PDF = "pdf"
CATEGORY_DOCX = "docx"


def _matches_signature(data: bytes, category: str) -> bool:
    if category == CATEGORY_IMAGE:
        return any(data.startswith(sig) for sig in _IMAGE_SIGNATURES)
    if category == CATEGORY_PDF:
        return data.startswith(_PDF_SIGNATURE)
    if category == CATEGORY_DOCX:
        return data.startswith(_DOCX_SIGNATURE)
    return False


def _verify_image_integrity(data: bytes) -> None:
    """Pastikan data benar-benar dapat didekode sebagai gambar (bukan sekadar
    header yang cocok). Pillow bersifat opsional -- jika belum terpasang,
    lewati verifikasi mendalam ini dan cukup andalkan cocokan signature di
    atas (fail-open pada dependency, bukan pada validasi keamanan intinya)."""
    try:
        from PIL import Image  # import lokal: dependency opsional
    except ImportError:  # pragma: no cover - lingkungan tanpa Pillow terpasang
        return

    try:
        with Image.open(io.BytesIO(data)) as img:
            img.verify()
    except Exception as exc:  # noqa: BLE001 - seluruh error Pillow berarti file korup/bukan gambar
        raise UploadValidationError(
            "File yang diunggah bukan gambar yang valid atau berkasnya rusak."
        ) from exc


def validate_upload_content(
    file_storage,
    *,
    category: str,
    max_size_mb: int = 5,
) -> bytes:
    """
    Validasi isi file upload sebelum dikirim ke Cloudinary.

    Args:
        file_storage: objek `FileStorage` dari Flask-WTF/Werkzeug.
        category: salah satu dari `CATEGORY_IMAGE`, `CATEGORY_PDF`, `CATEGORY_DOCX`.
        max_size_mb: batas ukuran file ini secara spesifik (MB).

    Returns:
        Isi file (bytes) -- dikembalikan agar pemanggil tidak perlu
        membaca stream file dua kali (stream sudah di-consume di sini).

    Raises:
        UploadValidationError: jika file kosong, melebihi batas ukuran,
        atau isinya tidak cocok dengan kategori yang diharapkan.
    """
    data = file_storage.read()
    # Kembalikan posisi stream ke awal untuk jaga-jaga jika pemanggil lain
    # ingin membacanya lagi (mis. re-render form saat validasi form gagal).
    try:
        file_storage.stream.seek(0)
    except (AttributeError, ValueError):
        pass

    if not data:
        raise UploadValidationError("File kosong atau gagal dibaca.")

    max_size_bytes = max_size_mb * 1024 * 1024
    if len(data) > max_size_bytes:
        raise UploadValidationError(f"Ukuran file melebihi batas {max_size_mb} MB.")

    if not _matches_signature(data, category):
        raise UploadValidationError(
            "Isi file tidak sesuai dengan jenis yang diharapkan "
            "(nama/ekstensi file mungkin telah diubah)."
        )

    if category == CATEGORY_IMAGE:
        _verify_image_integrity(data)

    return data
