from types import SimpleNamespace

from flask_login import UserMixin

from backend.extensions import login_manager, db


def _coerce_bool(value) -> bool:
    if isinstance(value, bool):
        return value
    if value is None:
        return False
    if isinstance(value, (int, float)):
        return bool(value)
    if isinstance(value, str):
        return value.strip().lower() not in {"", "0", "false", "no", "off", "none", "null"}
    return bool(value)


class User(UserMixin):
    __tablename__ = "pengguna"

    def __init__(self, **kwargs):
        self.id_pengguna = kwargs.get("id_pengguna")
        self.id = self.id_pengguna
        self.nama = kwargs.get("nama")
        self.name = self.nama
        self.username = kwargs.get("username")
        self.nid = self.username
        self.email = self.username
        self.password = kwargs.get("password")
        self.password_hash = self.password
        self.role_name = kwargs.get("role")
        self.role = SimpleNamespace(name=self.role_name) if self.role_name else None
        self.status_aktif = _coerce_bool(kwargs.get("status_aktif", True))
        self.is_active_flag = self.status_aktif
        self.deleted_at = None

    def get_id(self) -> str:
        return str(self.id_pengguna)

    @property
    def is_active(self) -> bool:
        return bool(self.status_aktif)

    @property
    def is_deleted(self) -> bool:
        return False

    def has_role(self, role_name: str) -> bool:
        return self.role_name == role_name

    def __repr__(self) -> str:
        return f"<Pengguna {self.username}>"


def build_auth_user_from_row(row):
    if row is None:
        return None
    return User(**dict(row))


@login_manager.user_loader
def load_user(user_id: str):
    row = db.fetchone(
        "SELECT `id_pengguna`, `nama`, `username`, `password`, `role`, `status_aktif` "
        "FROM `pengguna` WHERE `id_pengguna` = %s LIMIT 1",
        (int(user_id),),
    )
    return build_auth_user_from_row(row)
