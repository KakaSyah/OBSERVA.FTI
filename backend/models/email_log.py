"""
backend/models/email_log.py

Model EmailLog — riwayat pengiriman email via Resend, termasuk retry
sederhana pada Tahap 9 (FR-54, NFR Reliability).
"""

from backend.extensions import db, Model, ForeignKey, func


class EmailLog(Model):
    __tablename__ = "email_logs"

    STATUS_SENT = "sent"
    STATUS_FAILED = "failed"

    id = db.Column(db.BigInteger, primary_key=True, autoincrement=True)
    observation_request_id = db.Column(
        db.BigInteger,
        foreign_key=ForeignKey("observation_requests.id", name="fk_email_request"),
        nullable=True,
        index=True,
    )
    recipient_email = db.Column(db.String(150), nullable=False)
    subject = db.Column(db.String(255), nullable=False)
    status = db.Column(db.String(20), nullable=False, index=True)  # sent / failed
    provider_message_id = db.Column(db.String(255), nullable=True)
    error_message = db.Column(db.String(500), nullable=True)
    created_at = db.Column(
        db.TIMESTAMP, server_default=func.current_timestamp(), nullable=False
    )

    observation_request = db.relationship("ObservationRequest", back_populates="email_logs")

    def __repr__(self) -> str:
        return f"<EmailLog to={self.recipient_email} status={self.status}>"
