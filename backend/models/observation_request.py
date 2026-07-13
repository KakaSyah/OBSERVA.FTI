"""
backend/models/observation_request.py

Model ObservationRequest — entitas inti sistem: pengajuan surat izin
observasi mahasiswa beserta status alurnya. Status mengikuti Activity
Diagram pada Tahap 1 bagian 6:

    Draft -> Menunggu Persetujuan Dosen
          -> (Disetujui Dosen ->) Menunggu Persetujuan Kaprodi
          -> (Disetujui Kaprodi ->) Surat Dikirim -> Selesai
          -> Ditolak Dosen / Ditolak Kaprodi (alur berhenti)
"""

from backend.extensions import db, Model, ForeignKey
from backend.models.base import TimestampMixin, SoftDeleteMixin


class ObservationRequest(TimestampMixin, SoftDeleteMixin, Model):
    __tablename__ = "observation_requests"

    # ---------- Konstanta status alur ----------
    STATUS_DRAFT = "Draft"
    STATUS_MENUNGGU_DOSEN = "Menunggu Persetujuan Dosen"
    STATUS_DISETUJUI_DOSEN = "Disetujui Dosen"
    STATUS_DITOLAK_DOSEN = "Ditolak Dosen"
    STATUS_MENUNGGU_KAPRODI = "Menunggu Persetujuan Kaprodi"
    STATUS_DISETUJUI_KAPRODI = "Disetujui Kaprodi"
    STATUS_DITOLAK_KAPRODI = "Ditolak Kaprodi"
    STATUS_SURAT_DIKIRIM = "Surat Dikirim"
    STATUS_SELESAI = "Selesai"

    # Dipakai untuk dropdown filter riwayat (Tahap 5) & validasi umum.
    ALL_STATUSES = [
        STATUS_DRAFT,
        STATUS_MENUNGGU_DOSEN,
        STATUS_DISETUJUI_DOSEN,
        STATUS_DITOLAK_DOSEN,
        STATUS_MENUNGGU_KAPRODI,
        STATUS_DISETUJUI_KAPRODI,
        STATUS_DITOLAK_KAPRODI,
        STATUS_SURAT_DIKIRIM,
        STATUS_SELESAI,
    ]

    id = db.Column(db.BigInteger, primary_key=True, autoincrement=True)
    student_id = db.Column(
        db.BigInteger,
        foreign_key=ForeignKey("students.id", name="fk_req_student"),
        nullable=False,
        index=True,
    )
    lecturer_id = db.Column(
        db.BigInteger,
        foreign_key=ForeignKey("lecturers.id", name="fk_req_lecturer"),
        nullable=False,
        index=True,
    )
    study_program_id = db.Column(
        db.BigInteger,
        foreign_key=ForeignKey("study_programs.id", name="fk_req_prodi"),
        nullable=False,
    )
    letter_template_id = db.Column(
        db.BigInteger,
        foreign_key=ForeignKey("letter_templates.id", name="fk_req_template"),
        nullable=True,
    )

    destination_institution = db.Column(db.String(255), nullable=False)
    institution_address = db.Column(db.String(255), nullable=False)
    topic = db.Column(db.String(255), nullable=False)
    course_name = db.Column(db.String(150), nullable=False)
    submission_date = db.Column(db.Date, nullable=False)
    status = db.Column(db.String(50), nullable=False, default=STATUS_DRAFT, index=True)
    rejection_note = db.Column(db.String(500), nullable=True)
    pdf_draft_url = db.Column(db.String(500), nullable=True)
    pdf_final_url = db.Column(db.String(500), nullable=True)

    student = db.relationship("Student", back_populates="observation_requests")
    lecturer = db.relationship("Lecturer", back_populates="observation_requests")
    study_program = db.relationship("StudyProgram", back_populates="observation_requests")
    letter_template = db.relationship("LetterTemplate", back_populates="observation_requests")

    approval_logs = db.relationship(
        "ApprovalLog",
        back_populates="observation_request",
        lazy="dynamic",
        cascade="all, delete-orphan",
    )
    email_logs = db.relationship(
        "EmailLog", back_populates="observation_request", lazy="dynamic"
    )
    letter_number = db.relationship(
        "LetterNumber",
        back_populates="observation_request",
        uselist=False,
        cascade="all, delete-orphan",
    )

    # ---------- Helper status (dipakai Tahap 5 di controller/template) ----------
    @property
    def is_draft(self) -> bool:
        return self.status == self.STATUS_DRAFT

    @property
    def is_editable(self) -> bool:
        """Mahasiswa hanya dapat mengubah/mencetak-draft/mengirim selama masih Draft."""
        return self.status == self.STATUS_DRAFT

    @property
    def is_waiting_lecturer(self) -> bool:
        """Dosen hanya dapat menyetujui/menolak selama status masih Menunggu Persetujuan Dosen (FR-20/21)."""
        return self.status == self.STATUS_MENUNGGU_DOSEN

    @property
    def is_waiting_head_of_program(self) -> bool:
        """Kaprodi hanya dapat menyetujui/menolak selama status masih Menunggu Persetujuan Kaprodi (Tahap 7)."""
        return self.status == self.STATUS_MENUNGGU_KAPRODI

    @property
    def is_finished(self) -> bool:
        return self.status == self.STATUS_SELESAI

    @property
    def is_rejected(self) -> bool:
        return self.status in (self.STATUS_DITOLAK_DOSEN, self.STATUS_DITOLAK_KAPRODI)

    def __repr__(self) -> str:
        return f"<ObservationRequest id={self.id} status={self.status}>"
