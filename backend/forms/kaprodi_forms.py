"""
backend/forms/kaprodi_forms.py

Form Flask-WTF untuk modul Kaprodi (Tahap 7):
- ApprovalNoteForm -> FR-31, dipakai baik untuk aksi Setujui (UC-16) maupun
  Tolak (UC-17) pada halaman detail persetujuan akhir. Catatan bersifat
  opsional sesuai FR-31 ("disertai catatan opsional"); dua instance form ini
  dipasang pada dua <form> terpisah (action berbeda: .../setujui dan
  .../tolak) di `kaprodi/detail_surat.html`, hanya untuk mendapatkan
  proteksi CSRF + validasi panjang catatan di sisi server — pola yang sama
  persis dengan `ApprovalNoteForm` milik modul Dosen (Tahap 6).
- ProfileForm -> FR-05 / UC-19, lihat & perbarui profil kaprodi. Program
  studi bersifat baku (dikelola Admin, Tahap 10) sehingga tidak diedit di
  sini — sama seperti pola ProfileForm dosen (Tahap 6).
"""

from flask_wtf import FlaskForm
from wtforms import StringField, SubmitField, TextAreaField
from wtforms.validators import DataRequired, Length, Optional

from backend.forms import phone_validator


class ApprovalNoteForm(FlaskForm):
    """Form catatan opsional untuk aksi Setujui/Tolak (FR-31)."""

    note = TextAreaField(
        "Catatan (opsional)",
        validators=[Optional(), Length(max=500, message="Maksimal 500 karakter.")],
    )


class ProfileForm(FlaskForm):
    """Form kelola profil kaprodi: nama & no. HP (di tabel users). Program
    studi bersifat baku (dikelola Admin pada Tahap 10)."""

    name = StringField(
        "Nama Lengkap",
        validators=[DataRequired(message="Nama wajib diisi."), Length(max=150)],
    )
    phone = StringField("No. HP", validators=[Optional(), Length(max=20), phone_validator()])
    submit = SubmitField("Simpan Perubahan")
