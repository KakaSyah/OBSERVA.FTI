from backend import create_app
from backend.extensions import db
from backend.models.user import build_auth_user_from_row, load_user
from backend.services.admin_service import build_insert_sql_and_params


def test_build_auth_user_from_row_supports_is_active_column():
    row = {
        "id": 1,
        "role_id": 2,
        "name": "Alice",
        "nid": "NID001",
        "email": "alice@example.com",
        "password_hash": "hash",
        "phone": "08123456789",
        "is_active": 1,
        "is_deleted": 0,
        "role_name": "admin",
    }

    user = build_auth_user_from_row(row)

    assert user is not None
    assert user.id == 1
    assert user.is_active is True
    assert user.is_deleted is False
    assert user.role.name == "admin"


def test_build_insert_sql_and_params_uses_raw_sql_columns():
    user = type("UserStub", (), {})()
    user.__class__ = type("UserStub", (), {"__tablename__": "users", "_primary_key": "id", "_columns": {"id": type("C", (), {"column_name": "id", "kwargs": {}})(), "name": type("C", (), {"column_name": "name", "kwargs": {}})(), "email": type("C", (), {"column_name": "email", "kwargs": {}})()}, "__module__": __name__})
    user.name = "Alice"
    user.email = "alice@example.com"

    sql, params = build_insert_sql_and_params(user)

    assert "INSERT INTO `users`" in sql
    assert "`name`" in sql
    assert "`email`" in sql
    assert params == ["Alice", "alice@example.com"]


def test_load_user_rehydrates_role_from_sql():
    app = create_app()
    with app.app_context():
        user = load_user(1)

    assert user is not None
    assert user.nid == "administrator"
    assert getattr(user.role, "name", None) == "admin"
