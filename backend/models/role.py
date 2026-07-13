"""
backend/models/role.py

Model Role — merepresentasikan peran pengguna sistem (mahasiswa, dosen,
kaprodi, admin) yang menjadi dasar RBAC (role_required middleware, Tahap 4).
"""

from backend.extensions import db, Model
from backend.models.base import TimestampMixin


class Role(TimestampMixin, Model):
    __tablename__ = "roles"

    # Konstanta nama role agar tidak ada "magic string" tersebar di modul lain
    MAHASISWA = "mahasiswa"
    DOSEN = "dosen"
    KAPRODI = "kaprodi"
    ADMIN = "admin"

    id = db.Column(db.BigInteger, primary_key=True, autoincrement=True)
    name = db.Column(db.String(50), nullable=False, unique=True)
    description = db.Column(db.String(255), nullable=True)

    users = db.relationship("User", back_populates="role", lazy="dynamic")

    def __repr__(self) -> str:
        return f"<Role {self.name}>"
