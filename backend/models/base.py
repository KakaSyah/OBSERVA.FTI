"""
backend/models/base.py

Mixin bersama yang dipakai oleh seluruh model pada Tahap 3,
sesuai konvensi yang sudah disebutkan di README Tahap 1 & 2:
- TimestampMixin  -> kolom created_at & updated_at otomatis.
- SoftDeleteMixin -> kolom deleted_at (nullable) + helper soft delete.

Model yang butuh keduanya cukup mewarisi (TimestampMixin, SoftDeleteMixin, Model).
"""

from datetime import datetime

from backend.extensions import db, func


class TimestampMixin:
    """Menambahkan kolom created_at & updated_at yang diisi otomatis oleh DB."""

    created_at = db.Column(
        db.TIMESTAMP,
        server_default=func.current_timestamp(),
        nullable=False,
    )
    updated_at = db.Column(
        db.TIMESTAMP,
        server_default=func.current_timestamp(),
        onupdate=func.current_timestamp(),
        nullable=False,
    )


class SoftDeleteMixin:
    """
    Menambahkan mekanisme soft delete melalui kolom deleted_at (nullable),
    sesuai catatan pada Tahap 1 bagian 8 (SoftDeleteMixin). Baris yang
    di-soft-delete TIDAK dihapus fisik dari database, hanya ditandai.
    """

    deleted_at = db.Column(db.TIMESTAMP, nullable=True)

    @property
    def is_deleted(self) -> bool:
        return self.deleted_at is not None

    def soft_delete(self) -> None:
        """Tandai baris sebagai terhapus (dipakai oleh service layer, bukan hard delete)."""
        self.deleted_at = datetime.utcnow()

    def restore(self) -> None:
        """Kembalikan baris yang sebelumnya di-soft-delete."""
        self.deleted_at = None
