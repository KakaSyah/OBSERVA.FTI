"""
backend/models/cloudinary_file.py

Model CloudinaryFile — metadata seluruh file yang diunggah ke Cloudinary
(kop surat, logo fakultas/universitas, template surat, dsb). File fisik
tersimpan di Cloudinary; tabel ini hanya menyimpan referensinya (FR-41,
FR-42, digunakan oleh app/services/cloudinary_service.py pada Tahap 8).

Catatan: tabel ini hanya punya created_at (tanpa updated_at) sesuai SQL
Tahap 1, sehingga tidak memakai TimestampMixin.
"""

from backend.extensions import db, Model, ForeignKey, func
from backend.models.base import SoftDeleteMixin


class CloudinaryFile(SoftDeleteMixin, Model):
    __tablename__ = "cloudinary_files"

    # Kategori file (dipakai untuk validasi di service layer)
    TYPE_KOP_SURAT = "kop_surat"
    TYPE_LOGO_FAKULTAS = "logo_fakultas"
    TYPE_LOGO_UNIVERSITAS = "logo_universitas"
    TYPE_TEMPLATE_SURAT = "template_surat"
    TYPE_LAINNYA = "lainnya"

    id = db.Column(db.BigInteger, primary_key=True, autoincrement=True)
    uploader_id = db.Column(
        db.BigInteger,
        foreign_key=ForeignKey("users.id", name="fk_files_uploader"),
        nullable=False,
    )
    file_type = db.Column(db.String(50), nullable=False, index=True)
    public_id = db.Column(db.String(255), nullable=False)
    secure_url = db.Column(db.String(500), nullable=False)
    original_filename = db.Column(db.String(255), nullable=True)
    file_size = db.Column(db.Integer, nullable=True)
    created_at = db.Column(
        db.TIMESTAMP, server_default=func.current_timestamp(), nullable=False
    )

    uploader = db.relationship("User", back_populates="uploaded_files")

    def __repr__(self) -> str:
        return f"<CloudinaryFile {self.file_type}:{self.public_id}>"
