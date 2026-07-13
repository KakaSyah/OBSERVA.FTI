"""
backend/models/student.py

Model Student — profil mahasiswa, relasi 1:1 dengan User (login) dan
N:1 dengan StudyProgram.
"""

from backend.extensions import db, Model, ForeignKey
from backend.models.base import TimestampMixin, SoftDeleteMixin


class Student(TimestampMixin, SoftDeleteMixin, Model):
    __tablename__ = "students"

    id = db.Column(db.BigInteger, primary_key=True, autoincrement=True)
    user_id = db.Column(
        db.BigInteger,
        foreign_key=ForeignKey("users.id", name="fk_students_user"),
        nullable=False,
        unique=True,
    )
    nim = db.Column(db.String(30), nullable=False, unique=True, index=True)
    semester = db.Column(db.Integer, nullable=False)
    study_program_id = db.Column(
        db.BigInteger,
        foreign_key=ForeignKey("study_programs.id", name="fk_students_prodi"),
        nullable=False,
    )

    user = db.relationship("User", back_populates="student_profile")
    study_program = db.relationship("StudyProgram", back_populates="students")
    observation_requests = db.relationship(
        "ObservationRequest", back_populates="student", lazy="dynamic"
    )

    def __repr__(self) -> str:
        return f"<Student {self.nim}>"
