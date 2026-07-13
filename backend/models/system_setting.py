"""
backend/models/system_setting.py

Model SystemSetting — pengaturan sistem berbentuk key-value (mis. margin
surat default) yang disimpan sebagai string JSON pada setting_value
(FR-43, dikonsumsi oleh pdf_service).
"""

from backend.extensions import db, Model, ForeignKey
from backend.models.base import TimestampMixin


class SystemSetting(TimestampMixin, Model):
    __tablename__ = "system_settings"

    # Key baku yang dipakai sistem
    KEY_LETTER_MARGIN = "letter_margin"

    id = db.Column(db.BigInteger, primary_key=True, autoincrement=True)
    setting_key = db.Column(db.String(100), nullable=False, unique=True)
    setting_value = db.Column(db.Text, nullable=False)  # disimpan sebagai string JSON
    description = db.Column(db.String(255), nullable=True)
    updated_by = db.Column(
        db.BigInteger,
        foreign_key=ForeignKey("users.id", name="fk_settings_user"),
        nullable=True,
    )

    updated_by_user = db.relationship("User", foreign_keys=[updated_by])

    def __repr__(self) -> str:
        return f"<SystemSetting {self.setting_key}>"
