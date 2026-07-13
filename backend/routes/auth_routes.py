from flask import Blueprint, current_app, flash, redirect, render_template, request, url_for
from flask_login import current_user, login_required, login_user, logout_user

from backend.extensions import bcrypt, db
from backend.forms.auth_forms import LoginForm
from backend.middlewares.auth_middleware import dashboard_endpoint_for
from backend.models.user import build_auth_user_from_row
from backend.utils.security import is_safe_redirect_url

auth_bp = Blueprint("auth", __name__, url_prefix="/auth")


def check_password_hash(password_hash: str, password: str) -> bool:
    if not password_hash or not password:
        return False
    return bcrypt.check_password_hash(password_hash, password)


@auth_bp.route("/login", methods=["GET", "POST"])
def login():
    if current_user.is_authenticated:
        return redirect(url_for(dashboard_endpoint_for(current_user)))

    form = LoginForm()

    if form.validate_on_submit():
        username = form.username.data.strip()
        row = db.fetchone(
            "SELECT `id_pengguna`, `nama`, `username`, `password`, `role`, `status_aktif` "
            "FROM `pengguna` WHERE LOWER(`username`) = LOWER(%s) LIMIT 1",
            (username,),
        )
        user = build_auth_user_from_row(row)

        if user is None or not check_password_hash(user.password, form.password.data):
            current_app.logger.warning(
                "Login gagal untuk username='%s' dari IP=%s",
                username,
                request.remote_addr,
            )
            flash("Username atau password salah.", "danger")
            return render_template("auth/login.html", form=form), 401

        if not user.is_active:
            current_app.logger.warning("Login ditolak untuk akun nonaktif username='%s'", username)
            flash("Akun Anda nonaktif. Silakan hubungi admin.", "warning")
            return render_template("auth/login.html", form=form), 403

        login_user(user, remember=False)
        current_app.logger.info("Pengguna '%s' (role=%s) berhasil login.", user.username, user.role_name)
        flash(f"Selamat datang, {user.nama}!", "success")

        next_url = request.args.get("next")
        if next_url and is_safe_redirect_url(next_url):
            return redirect(next_url)
        return redirect(url_for(dashboard_endpoint_for(user)))

    return render_template("auth/login.html", form=form)


@auth_bp.route("/logout", methods=["POST"])
@login_required
def logout():
    current_app.logger.info("Pengguna '%s' logout.", current_user.username)
    logout_user()
    flash("Anda telah berhasil logout.", "info")
    return redirect(url_for("auth.login"))
