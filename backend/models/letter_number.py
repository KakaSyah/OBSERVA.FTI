"""
backend/models/letter_number.py

Model LetterNumber — nomor surat resmi hasil generate otomatis (FR-50)
saat Kaprodi menyetujui pengajuan. Relasi 1:(0..1) dengan
ObservationRequest, dikelola oleh letter_number_service (Tahap 8) yang
mengunci baris counter per (bulan, tahun) untuk mencegah duplikasi.
"""


from backend.extensions import db, Model, ForeignKey, func


class LetterNumber(Model):
    __tablename__ = "letter_numbers"

    id = db.Column(db.BigInteger, primary_key=True, autoincrement=True)
    observation_request_id = db.Column(
        db.BigInteger,
        foreign_key=ForeignKey("observation_requests.id", name="fk_letnum_request"),
        nullable=False,
        unique=True,
    )
    sequence_number = db.Column(db.Integer, nullable=False)
    month_roman = db.Column(db.String(10), nullable=False)
    year = db.Column(db.Integer, nullable=False, index=True)
    formatted_number = db.Column(db.String(100), nullable=False, unique=True)
    created_at = db.Column(
        db.TIMESTAMP, server_default=func.current_timestamp(), nullable=False
    )

    observation_request = db.relationship("ObservationRequest", back_populates="letter_number")

    def __repr__(self) -> str:
        return f"<LetterNumber {self.formatted_number}>"
