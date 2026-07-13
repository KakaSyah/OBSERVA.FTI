"""
backend/models/study_program.py

Model StudyProgram — program studi (prodi). Memiliki relasi ke
HeadOfProgram (kaprodi) melalui dua arah FK sesuai skema Tahap 1:
- study_programs.head_of_program_id -> head_of_programs.id (siapa kaprodinya)
- head_of_programs.study_program_id -> study_programs.id  (prodi milik kaprodi)

FK pertama dideklarasikan dengan use_alter karena secara DDL membentuk
relasi melingkar dengan tabel head_of_programs (persis seperti pendekatan
ALTER TABLE pada skrip SQL Tahap 1).
"""

from backend.extensions import db, Model, ForeignKey
from backend.models.base import TimestampMixin, SoftDeleteMixin


class StudyProgram(TimestampMixin, SoftDeleteMixin, Model):
    __tablename__ = "study_programs"

    id = db.Column(db.BigInteger, primary_key=True, autoincrement=True)
    name = db.Column(db.String(150), nullable=False)
    code = db.Column(db.String(20), nullable=False, unique=True)
    faculty_name = db.Column(db.String(150), nullable=False)
    head_of_program_id = db.Column(
        db.BigInteger,
        foreign_key=ForeignKey("head_of_programs.id", name="fk_prodi_kaprodi", use_alter=True),
        nullable=True,
    )

    # Kaprodi yang menjabat di prodi ini (post_update memutus siklus FK saat flush)
    head_of_program = db.relationship(
        "HeadOfProgram",
        foreign_keys=[head_of_program_id],
        post_update=True,
    )
    students = db.relationship("Student", back_populates="study_program", lazy="dynamic")
    lecturers = db.relationship("Lecturer", back_populates="study_program", lazy="dynamic")
    observation_requests = db.relationship(
        "ObservationRequest", back_populates="study_program", lazy="dynamic"
    )

    def __repr__(self) -> str:
        return f"<StudyProgram {self.code}>"
