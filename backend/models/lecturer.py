"""
backend/models/lecturer.py

Model Lecturer — profil dosen, relasi 1:1 dengan User (login) dan
N:1 dengan StudyProgram. Seorang dosen dapat menjadi pembimbing pada
banyak ObservationRequest.
"""

from backend.extensions import db, Model, ForeignKey
from backend.models.base import TimestampMixin, SoftDeleteMixin


class Lecturer(TimestampMixin, SoftDeleteMixin, Model):
    __tablename__ = "lecturers"

    id = db.Column(db.BigInteger, primary_key=True, autoincrement=True)
    user_id = db.Column(
        db.BigInteger,
        foreign_key=ForeignKey("users.id", name="fk_lecturers_user"),
        nullable=False,
        unique=True,
    )
    nidn = db.Column(db.String(30), nullable=False, unique=True)
    study_program_id = db.Column(
        db.BigInteger,
        foreign_key=ForeignKey("study_programs.id", name="fk_lecturers_prodi"),
        nullable=False,
    )

    user = db.relationship("User", back_populates="lecturer_profile")
    study_program = db.relationship("StudyProgram", back_populates="lecturers")
    observation_requests = db.relationship(
        "ObservationRequest", back_populates="lecturer", lazy="dynamic"
    )

    def __repr__(self) -> str:
        return f"<Lecturer {self.nidn}>"
