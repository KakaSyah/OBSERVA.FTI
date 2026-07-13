"""
backend/models/head_of_program.py

Model HeadOfProgram — akun Kaprodi (Ketua Program Studi). Relasi 1:1
dengan User (login) dan 1:1 dengan StudyProgram (satu prodi hanya
memiliki satu kaprodi aktif).
"""

from backend.extensions import db, Model, ForeignKey
from backend.models.base import TimestampMixin, SoftDeleteMixin


class HeadOfProgram(TimestampMixin, SoftDeleteMixin, Model):
    __tablename__ = "head_of_programs"

    id = db.Column(db.BigInteger, primary_key=True, autoincrement=True)
    user_id = db.Column(
        db.BigInteger,
        foreign_key=ForeignKey("users.id", name="fk_hop_user"),
        nullable=False,
        unique=True,
    )
    # NIDN Kaprodi (Tahap 15 — Revisi Login): dipakai sebagai NID login
    # (disamakan perlakuannya dengan NIDN dosen di tabel lecturers).
    nidn = db.Column(db.String(30), nullable=False, unique=True)
    study_program_id = db.Column(
        db.BigInteger,
        foreign_key=ForeignKey("study_programs.id", name="fk_hop_prodi"),
        nullable=False,
        unique=True,
    )

    user = db.relationship("User", back_populates="head_of_program_profile")
    # foreign_keys wajib ditentukan karena ada dua jalur relasi berbeda
    # antara study_programs <-> head_of_programs (lihat study_program.py).
    study_program = db.relationship("StudyProgram", foreign_keys=[study_program_id])

    def __repr__(self) -> str:
        return f"<HeadOfProgram user_id={self.user_id}>"
