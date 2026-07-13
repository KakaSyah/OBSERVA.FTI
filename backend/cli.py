"""
backend/cli.py

Perintah Flask CLI kustom untuk kebutuhan setup awal. Modul CRUD user
sesungguhnya baru dibangun pada Modul Admin (Tahap 10); command di sini
hanya untuk membuat data minimum agar modul autentikasi (Tahap 4) dapat
langsung diuji end-to-end (seed role & satu akun admin pertama).
"""

import click
from flask.cli import with_appcontext

from backend.extensions import db, func
from backend.models.role import Role
from backend.utils.security import hash_password

ROLE_SEED_DATA = [
    (Role.MAHASISWA, "Mahasiswa - pengaju surat izin observasi"),
    (Role.DOSEN, "Dosen pembimbing - penyetuju tahap pertama"),
    (Role.KAPRODI, "Ketua Program Studi - penyetuju tahap akhir"),
    (Role.ADMIN, "Administrator sistem"),
]


def _get_role_row(name: str):
    return db.fetchone(
        "SELECT * FROM `roles` WHERE `name` = %s LIMIT 1", (name,)
    )


def _user_row_by_nid(nid: str):
    return db.fetchone(
        "SELECT * FROM `users` WHERE LOWER(`nid`) = LOWER(%s) LIMIT 1", (nid,)
    )


def _user_row_by_email(email: str):
    return db.fetchone(
        "SELECT * FROM `users` WHERE LOWER(`email`) = LOWER(%s) LIMIT 1", (email,)
    )


@click.command("seed-roles")
@with_appcontext
def seed_roles_command():
    """Membuat 4 role dasar (mahasiswa, dosen, kaprodi, admin) jika belum ada."""
    created = 0
    for name, description in ROLE_SEED_DATA:
        if _get_role_row(name) is None:
            db.execute(
                "INSERT INTO `roles` (`name`, `description`) VALUES (%s, %s)",
                (name, description),
            )
            created += 1
    db.commit()
    click.echo(f"Selesai. {created} role baru dibuat (total seharusnya {len(ROLE_SEED_DATA)}).")


@click.command("create-admin")
@click.option("--name", prompt="Nama admin", help="Nama lengkap admin.")
@click.option("--nid", prompt="Username/NID admin", help="Username/NID login admin (Tahap 15).")
@click.option("--email", prompt="Email admin", help="Email kontak admin (tidak dipakai untuk login).")
@click.option(
    "--password",
    prompt="Password admin",
    hide_input=True,
    confirmation_prompt=True,
    help="Password login admin.",
)
@with_appcontext
def create_admin_command(name, nid, email, password):
    """Membuat akun admin pertama (FR-01) untuk keperluan setup awal sistem.

    Tahap 15 (Revisi Login): admin login dengan --nid (username) + password,
    BUKAN email. Email tetap disimpan sebagai kontak.
    """
    role_row = _get_role_row(Role.ADMIN)
    if role_row is None:
        click.echo("Role 'admin' belum ada. Jalankan `flask seed-roles` terlebih dahulu.")
        return

    nid = nid.strip()
    email = email.strip().lower()
    if _user_row_by_nid(nid):
        click.echo(f"User dengan NID '{nid}' sudah terdaftar.")
        return
    if _user_row_by_email(email):
        click.echo(f"User dengan email '{email}' sudah terdaftar.")
        return

    db.execute(
        "INSERT INTO `users` (`role_id`, `name`, `nid`, `email`, `password_hash`, `is_active`) "
        "VALUES (%s, %s, %s, %s, %s, %s)",
        (
            role_row["id"],
            name,
            nid,
            email,
            hash_password(password),
            True,
        ),
    )
    db.commit()
    click.echo(f"Akun admin dengan NID '{nid}' berhasil dibuat.")


@click.command("create-kiosk-mahasiswa")
@click.option(
    "--nid",
    default="MHS001",
    show_default=True,
    help="NID/kode login bersama untuk kiosk mahasiswa (Tahap 15).",
)
@click.option(
    "--password",
    prompt="Password kiosk mahasiswa",
    hide_input=True,
    confirmation_prompt=True,
    help="Password login bersama untuk kiosk mahasiswa.",
)
@with_appcontext
def create_kiosk_mahasiswa_command(nid, password):
    """
    Membuat SATU akun login mahasiswa bersama (Tahap 14 — mode kiosk).

    Sejak Tahap 15, akun ini juga bisa dibuat/diedit langsung lewat menu
    Admin > Akun Login Mahasiswa di web (tidak wajib lewat CLI lagi).
    Login memakai NID (kode unik buatan admin, mis. "MHS001") + password,
    BUKAN email.

    Berbeda dari role dosen/kaprodi/admin, mahasiswa TIDAK login per-individu:
    satu kredensial ini dipakai bergantian oleh siapa pun yang memakai
    komputer kiosk di ruang TU untuk membuka form pengajuan. Identitas
    mahasiswa yang sebenarnya (NIM, nama, prodi) tetap diverifikasi per
    pengajuan lewat NIM yang diketik manual pada form "Ajukan Surat" --
    dicocokkan ke data `students` yang sudah didaftarkan Admin (UC-21) --
    BUKAN dari akun yang sedang login. Karena itu akun ini sengaja TIDAK
    memiliki baris `students` terkait (`user.student_profile` akan None).
    """
    role_row = _get_role_row(Role.MAHASISWA)
    if role_row is None:
        click.echo("Role 'mahasiswa' belum ada. Jalankan `flask seed-roles` terlebih dahulu.")
        return

    nid = nid.strip()
    if _user_row_by_nid(nid):
        click.echo(f"Akun kiosk dengan NID '{nid}' sudah ada. Tidak ada perubahan.")
        return

    db.execute(
        "INSERT INTO `users` (`role_id`, `name`, `nid`, `email`, `password_hash`, `is_active`) "
        "VALUES (%s, %s, %s, %s, %s, %s)",
        (
            role_row["id"],
            "Mahasiswa (Kiosk)",
            nid,
            f"{nid.lower()}@kiosk.local",
            hash_password(password),
            True,
        ),
    )
    db.commit()
    click.echo(
        f"Akun kiosk mahasiswa dengan NID '{nid}' berhasil dibuat. "
        "Bagikan kredensial ini ke komputer kiosk di ruang TU, bukan ke mahasiswa perorangan."
    )


def register_cli_commands(app):
    """Mendaftarkan seluruh custom Flask CLI command ke instance aplikasi."""
    app.cli.add_command(seed_roles_command)
    app.cli.add_command(create_admin_command)
    app.cli.add_command(create_kiosk_mahasiswa_command)
