"""
backend/forms/mahasiswa_forms.py

Form Flask-WTF untuk modul Mahasiswa (Tahap 5, disesuaikan Tahap 14 untuk
alur kiosk):
- ObservationRequestForm -> FR-10, isi/ubah pengajuan surat observasi.
  Sejak Tahap 14, akun mahasiswa bersifat kiosk (satu login dipakai
  bersama, lihat app/cli.py `create-kiosk-mahasiswa`), sehingga identitas
  pemohon (NIM, Prodi) TIDAK lagi diambil dari profil user yang login,
  melainkan diisi manual di form ini dan divalidasi ke tabel `students`
  oleh controller/service (lihat mahasiswa_controller.new_observation_request
  & observation_service.find_student_by_nim).
- ProfileForm -> FR-05 / UC-07, lihat & perbarui profil mahasiswa
  (dipertahankan untuk akun individual non-kiosk di luar lingkup Tahap 14).
"""

from datetime import date

from flask_wtf import FlaskForm
from wtforms import DateField, IntegerField, SelectField, StringField, SubmitField, TextAreaField
from wtforms.validators import DataRequired, Length, NumberRange, Optional

from backend.forms import phone_validator


class ObservationRequestForm(FlaskForm):
    """Form pengajuan surat observasi. Choices `study_program_id` & `lecturer_id`
    diisi dinamis oleh controller (lihat mahasiswa_controller._populate_form_choices)."""

    nim = StringField(
        "NIM Pemohon",
        validators=[
            DataRequired(message="NIM pemohon wajib diisi."),
            Length(max=30, message="Maksimal 30 karakter."),
        ],
    )
    study_program_id = SelectField(
        "Pilih Prodi",
        coerce=int,
        validators=[DataRequired(message="Program studi wajib dipilih.")],
    )
    lecturer_id = SelectField(
        "Dosen Pembimbing",
        coerce=int,
        validators=[DataRequired(message="Dosen pembimbing wajib dipilih.")],
    )
    destination_institution = StringField(
        "Instansi Tujuan",
        validators=[
            DataRequired(message="Instansi tujuan wajib diisi."),
            Length(max=255, message="Maksimal 255 karakter."),
        ],
    )
    institution_address = TextAreaField(
        "Alamat Instansi",
        validators=[
            DataRequired(message="Alamat instansi wajib diisi."),
            Length(max=255, message="Maksimal 255 karakter."),
        ],
    )
    topic = StringField(
        "Topik Observasi",
        validators=[
            DataRequired(message="Topik observasi wajib diisi."),
            Length(max=255, message="Maksimal 255 karakter."),
        ],
    )
    course_name = StringField(
        "Mata Kuliah",
        validators=[
            DataRequired(message="Mata kuliah wajib diisi."),
            Length(max=150, message="Maksimal 150 karakter."),
        ],
    )
    submission_date = DateField(
        "Tanggal Rencana Observasi",
        default=date.today,
        validators=[DataRequired(message="Tanggal rencana observasi wajib diisi.")],
    )
    submit = SubmitField("Simpan Draft")


class ProfileForm(FlaskForm):
    """Form kelola profil mahasiswa: nama & no. HP (di tabel users) serta
    semester (di tabel students). NIM, email, dan prodi bersifat baku
    (dikelola Admin pada Tahap 10) sehingga tidak diedit di sini."""

    name = StringField(
        "Nama Lengkap",
        validators=[DataRequired(message="Nama wajib diisi."), Length(max=150)],
    )
    phone = StringField("No. HP", validators=[Optional(), Length(max=20), phone_validator()])
    semester = IntegerField(
        "Semester",
        validators=[
            DataRequired(message="Semester wajib diisi."),
            NumberRange(min=1, max=24, message="Semester harus antara 1 - 24."),
        ],
    )
    submit = SubmitField("Simpan Perubahan")
