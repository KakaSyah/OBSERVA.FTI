"""
backend/forms/dosen_forms.py

Form Flask-WTF untuk modul Dosen (Tahap 6):
- ApprovalNoteForm -> FR-21, dipakai baik untuk aksi Setujui (UC-10) maupun
  Tolak (UC-11) pada halaman detail surat masuk. Catatan bersifat opsional
  sesuai FR-21 ("disertai catatan opsional"); dua instance form ini dipasang
  pada dua <form> terpisah (action berbeda: .../setujui dan .../tolak) di
  `dosen/detail_surat.html`, hanya untuk mendapatkan proteksi CSRF +
  validasi panjang catatan di sisi server.
- ProfileForm -> FR-05 / UC-13, lihat & perbarui profil dosen. NIDN dan
  program studi bersifat baku (dikelola Admin, Tahap 10) sehingga tidak
  diedit di sini — sama seperti pola ProfileForm mahasiswa (Tahap 5).
"""

from flask_wtf import FlaskForm
from wtforms import StringField, SubmitField, TextAreaField
from wtforms.validators import DataRequired, Length, Optional

from backend.forms import phone_validator


class ApprovalNoteForm(FlaskForm):
    """Form catatan opsional untuk aksi Setujui/Tolak (FR-21)."""

    note = TextAreaField(
        "Catatan (opsional)",
        validators=[Optional(), Length(max=500, message="Maksimal 500 karakter.")],
    )


class ProfileForm(FlaskForm):
    """Form kelola profil dosen: nama & no. HP (di tabel users). NIDN dan
    program studi bersifat baku (dikelola Admin pada Tahap 10)."""

    name = StringField(
        "Nama Lengkap",
        validators=[DataRequired(message="Nama wajib diisi."), Length(max=150)],
    )
    phone = StringField("No. HP", validators=[Optional(), Length(max=20), phone_validator()])
    submit = SubmitField("Simpan Perubahan")
