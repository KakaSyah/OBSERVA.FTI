"""
backend/forms/admin_forms.py

Form Flask-WTF untuk modul Admin (Tahap 10): FR-40..FR-46 / UC-20..UC-31.
Mengikuti pola form modul lain (Tahap 5-7): validasi server-side + CSRF
otomatis lewat FlaskForm, pesan error berbahasa Indonesia.
"""

from flask_wtf import FlaskForm
from flask_wtf.file import FileAllowed, FileField, FileRequired
from wtforms import (
    BooleanField,
    DecimalField,
    IntegerField,
    PasswordField,
    SelectField,
    StringField,
    SubmitField,
    TextAreaField,
)
from wtforms.validators import DataRequired, Email, Length, NumberRange, Optional

from backend.forms import identifier_validator, password_complexity_validator, phone_validator


# ---------- Master Data: Program Studi (FR-40 / UC-24) ----------

class StudyProgramForm(FlaskForm):
    """Kelola Program Studi. `head_of_program_id` TIDAK diisi di sini karena
    kaprodi baru bisa dipilih setelah akunnya dibuat (relasi 1:1, lihat
    HeadOfProgramForm) — mencegah siklus ayam-telur saat prodi baru dibuat."""

    name = StringField(
        "Nama Program Studi",
        validators=[DataRequired(message="Nama prodi wajib diisi."), Length(max=150)],
    )
    code = StringField(
        "Kode Prodi",
        validators=[DataRequired(message="Kode prodi wajib diisi."), Length(max=20)],
    )
    faculty_name = StringField(
        "Nama Fakultas",
        validators=[DataRequired(message="Nama fakultas wajib diisi."), Length(max=150)],
    )
    submit = SubmitField("Simpan")


# ---------- Master Data: Mahasiswa (FR-40 / UC-21) ----------

class StudentForm(FlaskForm):
    """Create/edit akun mahasiswa (User + Student sekaligus, satu transaksi
    di admin_service). Password opsional saat edit (kosong = tidak diubah)."""

    name = StringField("Nama Lengkap", validators=[DataRequired(), Length(max=150)])
    email = StringField(
        "Email", validators=[DataRequired(), Email(message="Format email tidak valid."), Length(max=150)]
    )
    phone = StringField("No. HP", validators=[Optional(), Length(max=20), phone_validator()])
    password = PasswordField(
        "Password",
        validators=[Optional(), Length(min=8, max=128, message="Password minimal 8 karakter."), password_complexity_validator()],
    )
    nim = StringField("NIM", validators=[DataRequired(message="NIM wajib diisi."), Length(max=30), identifier_validator("NIM")])
    semester = IntegerField(
        "Semester",
        validators=[DataRequired(), NumberRange(min=1, max=24, message="Semester harus antara 1 - 24.")],
    )
    study_program_id = SelectField("Program Studi", coerce=int, validators=[DataRequired()])
    is_active_flag = BooleanField("Akun Aktif", default=True)
    submit = SubmitField("Simpan")


# ---------- Master Data: Dosen (FR-40 / UC-22) ----------

class LecturerForm(FlaskForm):
    """Create/edit akun dosen (User + Lecturer sekaligus)."""

    name = StringField("Nama Lengkap", validators=[DataRequired(), Length(max=150)])
    email = StringField(
        "Email", validators=[DataRequired(), Email(message="Format email tidak valid."), Length(max=150)]
    )
    phone = StringField("No. HP", validators=[Optional(), Length(max=20), phone_validator()])
    password = PasswordField(
        "Password",
        validators=[Optional(), Length(min=8, max=128, message="Password minimal 8 karakter."), password_complexity_validator()],
    )
    nidn = StringField("NIDN", validators=[DataRequired(message="NIDN wajib diisi."), Length(max=30), identifier_validator("NIDN")])
    study_program_id = SelectField("Program Studi", coerce=int, validators=[DataRequired()])
    is_active_flag = BooleanField("Akun Aktif", default=True)
    submit = SubmitField("Simpan")


# ---------- Master Data: Kaprodi (FR-40 / UC-23) ----------

class HeadOfProgramForm(FlaskForm):
    """Create/edit akun kaprodi (User + HeadOfProgram sekaligus). Satu prodi
    hanya boleh memiliki satu kaprodi aktif (unique study_program_id,
    divalidasi di admin_service)."""

    name = StringField("Nama Lengkap", validators=[DataRequired(), Length(max=150)])
    email = StringField(
        "Email", validators=[DataRequired(), Email(message="Format email tidak valid."), Length(max=150)]
    )
    phone = StringField("No. HP", validators=[Optional(), Length(max=20), phone_validator()])
    password = PasswordField(
        "Password",
        validators=[Optional(), Length(min=8, max=128, message="Password minimal 8 karakter."), password_complexity_validator()],
    )
    nidn = StringField(
        "NIDN Kaprodi",
        validators=[DataRequired(message="NIDN wajib diisi."), Length(max=30), identifier_validator("NIDN")],
    )
    study_program_id = SelectField("Program Studi", coerce=int, validators=[DataRequired()])
    is_active_flag = BooleanField("Akun Aktif", default=True)
    submit = SubmitField("Simpan")


# ---------- Akun Login Mahasiswa / Kiosk (Tahap 15 — Revisi Login) ----------

class KioskAccountForm(FlaskForm):
    """Create/edit akun login kiosk mahasiswa: NID bebas (mis. 'MHS001') +
    password, dipakai bersama di komputer TU. TIDAK terkait profil Student
    individual (NIM tetap dikelola terpisah lewat menu 'Mahasiswa')."""

    name = StringField(
        "Nama Akun", validators=[DataRequired(message="Nama akun wajib diisi."), Length(max=150)]
    )
    nid = StringField(
        "NID / Kode Login",
        validators=[
            DataRequired(message="NID wajib diisi."),
            Length(max=30),
            identifier_validator("NID"),
        ],
    )
    password = PasswordField(
        "Password",
        validators=[Optional(), Length(min=8, max=128, message="Password minimal 8 karakter."), password_complexity_validator()],
    )
    is_active_flag = BooleanField("Akun Aktif", default=True)
    submit = SubmitField("Simpan")


# ---------- Konfigurasi Surat: Kop Surat & Logo (FR-41 / UC-25) ----------

class LetterheadUploadForm(FlaskForm):
    """Upload satu file kop surat / logo fakultas / logo universitas ke
    Cloudinary (FR-41). `file_type` dikunci per-form oleh controller (tidak
    dipilih user) supaya satu form == satu kategori file yang jelas."""

    file = FileField(
        "Pilih File Gambar",
        validators=[
            FileRequired(message="File wajib dipilih."),
            FileAllowed(["png", "jpg", "jpeg"], "Hanya file PNG/JPG/JPEG yang diperbolehkan."),
        ],
    )
    submit = SubmitField("Unggah")


# ---------- Konfigurasi Surat: Template Surat (FR-42 / UC-26) ----------

class LetterTemplateForm(FlaskForm):
    """Create/edit metadata Template Surat. Upload file template bersifat
    opsional saat edit (kosong = file lama dipertahankan)."""

    name = StringField(
        "Nama Template", validators=[DataRequired(message="Nama template wajib diisi."), Length(max=150)]
    )
    file = FileField(
        "File Template (opsional saat edit)",
        validators=[FileAllowed(["pdf", "docx"], "Hanya file PDF/DOCX yang diperbolehkan.")],
    )
    margin_top = DecimalField("Margin Atas (cm)", places=2, validators=[DataRequired(), NumberRange(min=0, max=10)])
    margin_bottom = DecimalField(
        "Margin Bawah (cm)", places=2, validators=[DataRequired(), NumberRange(min=0, max=10)]
    )
    margin_left = DecimalField("Margin Kiri (cm)", places=2, validators=[DataRequired(), NumberRange(min=0, max=10)])
    margin_right = DecimalField(
        "Margin Kanan (cm)", places=2, validators=[DataRequired(), NumberRange(min=0, max=10)]
    )
    is_active = BooleanField("Jadikan Aktif")
    submit = SubmitField("Simpan Template")


# ---------- Konfigurasi Surat: Setting Margin Default (FR-43 / UC-27) ----------

class MarginSettingForm(FlaskForm):
    """Margin surat default sistem (dipakai `pdf_service` saat TIDAK ada
    Template Surat aktif) — disimpan di `system_settings` key `letter_margin`."""

    margin_top = DecimalField("Margin Atas (cm)", places=2, validators=[DataRequired(), NumberRange(min=0, max=10)])
    margin_bottom = DecimalField(
        "Margin Bawah (cm)", places=2, validators=[DataRequired(), NumberRange(min=0, max=10)]
    )
    margin_left = DecimalField("Margin Kiri (cm)", places=2, validators=[DataRequired(), NumberRange(min=0, max=10)])
    margin_right = DecimalField(
        "Margin Kanan (cm)", places=2, validators=[DataRequired(), NumberRange(min=0, max=10)]
    )
    submit = SubmitField("Simpan Pengaturan")


# ---------- Konfigurasi Surat: Template Email (FR-44 / UC-28) ----------

class EmailTemplateForm(FlaskForm):
    """Edit subjek & isi HTML satu jenis notifikasi email. Isi HTML boleh
    memakai variabel Jinja yang sama seperti template bawaan (mis.
    `{{ observation_request.topic }}`), lihat `app/services/email_service.py`."""

    subject = StringField(
        "Subjek Email", validators=[DataRequired(message="Subjek wajib diisi."), Length(max=255)]
    )
    html_body = TextAreaField(
        "Isi HTML Email", validators=[DataRequired(message="Isi email wajib diisi.")]
    )
    submit = SubmitField("Simpan Template")


# ---------- Profil Admin (FR-05 / UC-31) ----------

class ProfileForm(FlaskForm):
    name = StringField("Nama Lengkap", validators=[DataRequired(message="Nama wajib diisi."), Length(max=150)])
    phone = StringField("No. HP", validators=[Optional(), Length(max=20), phone_validator()])
    submit = SubmitField("Simpan Perubahan")


# ---------- Filter Log Aktivitas (FR-45 / UC-29) ----------

class ActivityLogFilterForm(FlaskForm):
    """Form GET sederhana (tanpa CSRF, tanpa submit tombol default) untuk
    memfilter log aktivitas berdasarkan jenis aksi."""

    class Meta:
        csrf = False

    action = SelectField("Jenis Aksi", validators=[Optional()])


class ObservationRequestFilterForm(FlaskForm):
    """Form GET sederhana untuk memfilter riwayat pengajuan berdasarkan status."""

    class Meta:
        csrf = False

    status = SelectField("Status Pengajuan", validators=[Optional()])
