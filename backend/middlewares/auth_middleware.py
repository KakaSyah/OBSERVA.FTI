from functools import wraps

from flask import abort
from flask_login import current_user, login_required


ROLE_DASHBOARD_ENDPOINT = {
    "admin": "admin.dashboard",
    "dosen": "dosen.dashboard",
    "kaprodi": "kaprodi.dashboard",
    "kiosk": "mahasiswa.welcome",
}

ROLE_ALIASES = {
    "mahasiswa": {"mahasiswa", "kiosk"},
}


def _allowed_role_names(allowed_roles):
    names = set()
    for role in allowed_roles:
        role_name = getattr(role, "name", None) or str(role)
        names.update(ROLE_ALIASES.get(role_name, {role_name}))
    return names


def role_required(*allowed_roles):
    def decorator(view_func):
        @wraps(view_func)
        @login_required
        def wrapped_view(*args, **kwargs):
            user_role_name = getattr(current_user, "role_name", None)
            if user_role_name not in _allowed_role_names(allowed_roles):
                abort(403)
            return view_func(*args, **kwargs)

        return wrapped_view

    return decorator


def dashboard_endpoint_for(user) -> str:
    if user is None or not getattr(user, "is_authenticated", False):
        return "auth.login"
    return ROLE_DASHBOARD_ENDPOINT.get(getattr(user, "role_name", None), "auth.login")
