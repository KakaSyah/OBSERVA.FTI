"""
backend/utils/formatters.py

Helper pemformatan tampilan (tanggal Indonesia, kelas warna badge status,
angka romawi bulan) yang dipakai lintas modul (mahasiswa/dosen/kaprodi/
letter_number_service & pdf_service pada Tahap 8).
"""

_BULAN_INDONESIA = [
    "Januari", "Februari", "Maret", "April", "Mei", "Juni",
    "Juli", "Agustus", "September", "Oktober", "November", "Desember",
]

# Dipakai letter_number_service untuk format nomor surat FR-50
# ("{urutan}/{kode_fakultas}/OBS/{bulan_romawi}/{tahun}").
BULAN_ROMAWI = [
    "I", "II", "III", "IV", "V", "VI", "VII", "VIII", "IX", "X", "XI", "XII",
]


def bulan_ke_romawi(month: int) -> str:
    """Konversi nomor bulan (1-12) menjadi angka romawi. Raise ValueError jika di luar rentang."""
    if not 1 <= month <= 12:
        raise ValueError(f"Nomor bulan tidak valid: {month}")
    return BULAN_ROMAWI[month - 1]

# Warna badge Bootstrap per status alur ObservationRequest (Tahap 1 bagian 6).
STATUS_BADGE_CLASS = {
    "Draft": "secondary",
    "Menunggu Persetujuan Dosen": "warning text-dark",
    "Disetujui Dosen": "info text-dark",
    "Ditolak Dosen": "danger",
    "Menunggu Persetujuan Kaprodi": "warning text-dark",
    "Disetujui Kaprodi": "info text-dark",
    "Ditolak Kaprodi": "danger",
    "Surat Dikirim": "primary",
    "Selesai": "success",
}


def format_tanggal_indonesia(value) -> str:
    """Format objek date/datetime menjadi mis. '3 Juli 2026'. '-' jika kosong."""
    if value is None:
        return "-"
    return f"{value.day} {_BULAN_INDONESIA[value.month - 1]} {value.year}"


def status_badge_class(status: str) -> str:
    """Kelas warna badge Bootstrap sesuai status alur ObservationRequest."""
    return STATUS_BADGE_CLASS.get(status, "secondary")
