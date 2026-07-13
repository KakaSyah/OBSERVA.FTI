"""
backend/models/approval_log.py

Model ApprovalLog — riwayat persetujuan/penolakan oleh Dosen & Kaprodi
pada setiap ObservationRequest (FR-53).
"""

from backend.extensions import db, Model, ForeignKey, func


class ApprovalLog(Model):
    __tablename__ = "approval_logs"

    ACTION_APPROVE = "approve"
    ACTION_REJECT = "reject"

    ROLE_DOSEN = "dosen"
    ROLE_KAPRODI = "kaprodi"

    id = db.Column(db.BigInteger, primary_key=True, autoincrement=True)
    observation_request_id = db.Column(
        db.BigInteger,
        foreign_key=ForeignKey("observation_requests.id", name="fk_approval_request"),
        nullable=False,
        index=True,
    )
    actor_user_id = db.Column(
        db.BigInteger,
        foreign_key=ForeignKey("users.id", name="fk_approval_actor"),
        nullable=False,
    )
    role_at_approval = db.Column(db.String(50), nullable=False)  # dosen / kaprodi
    action = db.Column(db.String(20), nullable=False)  # approve / reject
    note = db.Column(db.String(500), nullable=True)
    created_at = db.Column(
        db.TIMESTAMP, server_default=func.current_timestamp(), nullable=False
    )

    observation_request = db.relationship("ObservationRequest", back_populates="approval_logs")
    actor = db.relationship("User")

    def __repr__(self) -> str:
        return f"<ApprovalLog {self.action} by user_id={self.actor_user_id}>"
