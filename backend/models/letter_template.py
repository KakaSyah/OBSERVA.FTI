"""
backend/models/letter_template.py

Model LetterTemplate — template surat resmi (file + pengaturan margin
default) yang dikonsumsi oleh pdf_service saat generate PDF (FR-42,
FR-43, Tahap 8).
"""

from backend.extensions import db, Model, ForeignKey
from backend.models.base import TimestampMixin, SoftDeleteMixin


class LetterTemplate(TimestampMixin, SoftDeleteMixin, Model):
    __tablename__ = "letter_templates"

    id = db.Column(db.BigInteger, primary_key=True, autoincrement=True)
    name = db.Column(db.String(150), nullable=False)
    cloudinary_file_id = db.Column(
        db.BigInteger,
        foreign_key=ForeignKey("cloudinary_files.id", name="fk_template_file"),
        nullable=True,
    )
    margin_top = db.Column(db.Numeric(5, 2), nullable=False, default=2.5)
    margin_bottom = db.Column(db.Numeric(5, 2), nullable=False, default=2.5)
    margin_left = db.Column(db.Numeric(5, 2), nullable=False, default=3.0)
    margin_right = db.Column(db.Numeric(5, 2), nullable=False, default=2.5)
    is_active = db.Column(db.Boolean, nullable=False, default=True)

    cloudinary_file = db.relationship("CloudinaryFile", foreign_keys=[cloudinary_file_id])
    observation_requests = db.relationship(
        "ObservationRequest", back_populates="letter_template", lazy="dynamic"
    )

    def __repr__(self) -> str:
        return f"<LetterTemplate {self.name}>"
