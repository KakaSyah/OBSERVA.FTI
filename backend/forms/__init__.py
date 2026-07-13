"""
backend/forms/__init__.py

Package berisi form Flask-WTF. Setiap form yang mewarisi FlaskForm secara
otomatis membawa proteksi CSRF (token disertakan lewat form.hidden_tag()
atau form.csrf_token di template).

Tahap 13 (Hardening & Validasi Menyeluruh): validator format yang dipakai
lintas form (No. HP, NIM/NIDN, kompleksitas password) dikumpulkan di sini
agar aturan validasinya konsisten di semua modul (Mahasiswa, Dosen,
Kaprodi, Admin) dan tidak terduplikasi/berbeda-beda per file form.
"""

from wtforms.validators import Regexp

# No. HP: hanya angka, spasi, tanda "+" (kode negara), dan "-" (pemisah),
# panjang wajar 8-20 karakter. Mencegah input yang bukan nomor telepon
# (mis. skrip/markup) lolos ke kolom phone tanpa membatasi format lokal.
PHONE_REGEX = r"^\+?[0-9][0-9\-\s]{7,19}$"


def phone_validator():
    return Regexp(PHONE_REGEX, message="Format No. HP tidak valid (hanya angka, spasi, '+', '-').")


# NIM/NIDN: huruf & angka umum dipakai beberapa kampus untuk kode prodi/
# angkatan pada NIM, sehingga tidak dibatasi angka murni -- cukup pastikan
# tidak ada karakter berbahaya (spasi/simbol) yang bisa dipakai untuk
# menyisipkan payload pada pencarian/log.
IDENTIFIER_REGEX = r"^[A-Za-z0-9\-\.]{3,30}$"


def identifier_validator(label: str = "NIM/NIDN"):
    return Regexp(
        IDENTIFIER_REGEX,
        message=f"Format {label} tidak valid (hanya huruf, angka, '-', '.', 3-30 karakter).",
    )


# Password: minimal satu huruf dan satu angka (NFR Security: kebijakan
# password sederhana namun tidak trivial). Panjang minimal/maksimal tetap
# divalidasi terpisah lewat `Length` seperti sebelumnya (Tahap 4/10) agar
# pesan error panjang & kompleksitas tidak bercampur dalam satu pesan.
PASSWORD_COMPLEXITY_REGEX = r"^(?=.*[A-Za-z])(?=.*\d).+$"


def password_complexity_validator():
    return Regexp(
        PASSWORD_COMPLEXITY_REGEX,
        message="Password harus mengandung minimal satu huruf dan satu angka.",
    )
