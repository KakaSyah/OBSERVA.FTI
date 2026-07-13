"""
backend/utils/stats.py

Helper statistik bersama untuk dashboard seluruh role (Tahap 11: Dashboard
& Statistik). Dipakai oleh `app/services/observation_service.py`
(Mahasiswa/Dosen/Kaprodi) dan `app/services/admin_service.py` (Admin) agar
logika hitung tren bulanan & rata-rata waktu respon konsisten dan tidak
diduplikasi di kedua service tsb.

Perhitungan dilakukan di sisi Python (bukan `GROUP BY`/fungsi tanggal SQL)
supaya portable lintas backend DB (TiDB/MySQL saat produksi, SQLite saat
pengujian lokal) dan konsisten dengan pola "logic domain di Python" yang
sudah dipakai seluruh service pada proyek ini.
"""

from datetime import date

TREND_MONTHS = 6  # jumlah bulan ke belakang yang ditampilkan pada grafik tren dashboard

_BULAN_SINGKAT_ID = [
    "Jan", "Feb", "Mar", "Apr", "Mei", "Jun", "Jul", "Agu", "Sep", "Okt", "Nov", "Des",
]


def month_sequence(months: int = TREND_MONTHS) -> list[tuple[int, int]]:
    """Daftar (tahun, bulan) `months` bulan terakhir termasuk bulan berjalan, urut menaik."""
    today = date.today()
    sequence = []
    year, month = today.year, today.month
    for _ in range(months):
        sequence.append((year, month))
        month -= 1
        if month == 0:
            month = 12
            year -= 1
    return list(reversed(sequence))


def monthly_trend(items, date_getter, months: int = TREND_MONTHS) -> list[dict]:
    """
    Hitung jumlah `items` per bulan untuk `months` bulan terakhir, dipakai
    untuk grafik batang tren pada dashboard.

    `date_getter(item)` mengembalikan `datetime`/`date` item tsb (atau None,
    yang akan diabaikan dari hitungan).
    """
    sequence = month_sequence(months)
    counter = {ym: 0 for ym in sequence}
    for item in items:
        dt = date_getter(item)
        if dt is None:
            continue
        ym = (dt.year, dt.month)
        if ym in counter:
            counter[ym] += 1
    return [
        {"label": f"{_BULAN_SINGKAT_ID[m - 1]} {y}", "count": counter[(y, m)]} for (y, m) in sequence
    ]


def avg_response_hours(pairs: list[tuple]) -> float | None:
    """Rata-rata selisih jam antar dua timestamp `(mulai, selesai)` pada setiap
    pasangan di `pairs`. Mengembalikan None bila tidak ada data valid, sehingga
    dashboard dapat menampilkan '-' alih-alih 0 yang bisa menyesatkan."""
    diffs = [(selesai - mulai).total_seconds() / 3600 for mulai, selesai in pairs if mulai and selesai]
    if not diffs:
        return None
    return round(sum(diffs) / len(diffs), 1)
