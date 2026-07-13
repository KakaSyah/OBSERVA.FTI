"""
backend/models/activity_log.py

Model ActivityLog — audit trail seluruh aktivitas penting pengguna
(login, logout, approve, reject, upload, generate_pdf, send_email,
error), sesuai FR-55 dan NFR Auditability. Dicatat oleh
activity_log_service pada Tahap 12.
"""

from backend.extensions import db, Model, ForeignKey, func


class ActivityLog(Model):
    __tablename__ = "activity_logs"

    ACTION_LOGIN = "login"
    ACTION_LOGOUT = "logout"
    ACTION_APPROVE = "approve"
    ACTION_REJECT = "reject"
    ACTION_UPLOAD = "upload"
    ACTION_GENERATE_PDF = "generate_pdf"
    ACTION_SEND_EMAIL = "send_email"
    ACTION_ERROR = "error"

    id = db.Column(db.BigInteger, primary_key=True, autoincrement=True)
    user_id = db.Column(
        db.BigInteger,
        foreign_key=ForeignKey("users.id", name="fk_activity_user"),
        nullable=True,
        index=True,
    )
    action = db.Column(db.String(100), nullable=False, index=True)
    description = db.Column(db.String(500), nullable=True)
    ip_address = db.Column(db.String(45), nullable=True)
    created_at = db.Column(
        db.TIMESTAMP,
        server_default=func.current_timestamp(),
        nullable=False,
        index=True,
    )

    user = db.relationship("User", back_populates="activity_logs")

    def __repr__(self) -> str:
        return f"<ActivityLog {self.action} user_id={self.user_id}>"
