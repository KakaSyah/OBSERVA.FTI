from flask_wtf import FlaskForm
from wtforms import BooleanField, PasswordField, StringField, SubmitField
from wtforms.validators import DataRequired, Length


class LoginForm(FlaskForm):
    username = StringField(
        "Username",
        validators=[
            DataRequired(message="Username wajib diisi."),
            Length(min=3, max=100, message="Username harus 3-100 karakter."),
        ],
    )
    password = PasswordField(
        "Password",
        validators=[
            DataRequired(message="Password wajib diisi."),
            Length(min=6, max=128, message="Password minimal 6 karakter."),
        ],
    )
    remember_me = BooleanField("Ingat saya")
    submit = SubmitField("Masuk")
