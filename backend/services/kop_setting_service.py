"""Sumber tunggal pengaturan KOP untuk preview dan PDF surat."""

from decimal import Decimal

from backend.extensions import db


DEFAULT_MARGIN = Decimal("20")
HIDDEN_PREVIEW_OFFSET = Decimal("20")
# Pengaturan margin Admin lama masih disimpan dalam sentimeter. Konstanta ini
# dipisahkan dari margin preview (milimeter) agar tidak bergantung pada
# service generator PDF server.
DEFAULT_LETTER_MARGIN_CM = {
    "top": Decimal("2.5"),
    "bottom": Decimal("2.5"),
    "left": Decimal("3.0"),
    "right": Decimal("2.5"),
}


def get_active_kop_setting() -> dict:
    """Ambil KOP aktif beserta margin dalam mm; aman saat belum dikonfigurasi."""
    row = db.fetchone(
        "SELECT pk.`margin_atas`, pk.`margin_kiri`, pk.`margin_kanan`, pk.`margin_bawah`, pk.`ruang_aman_kop`, "
        "fc.`secure_url` "
        "FROM `pengaturan_kop` AS pk "
        "LEFT JOIN `file_cloudinary` AS fc ON fc.`id_file` = pk.`id_background` "
        "ORDER BY pk.`id_pengaturan` DESC LIMIT 1"
    )

    if row is None:
        preview_top_value = DEFAULT_MARGIN - HIDDEN_PREVIEW_OFFSET
        return {
            "top": DEFAULT_MARGIN,
            "preview_top": preview_top_value if preview_top_value > 0 else DEFAULT_MARGIN,
            "left": DEFAULT_MARGIN,
            "right": DEFAULT_MARGIN,
            "bottom": DEFAULT_MARGIN,
            "header_clearance": DEFAULT_MARGIN,
            "background_url": None,
        }

    raw_top = row["margin_atas"] if row["margin_atas"] is not None else DEFAULT_MARGIN
    preview_top_value = raw_top - HIDDEN_PREVIEW_OFFSET
    return {
        "top": raw_top,
        "preview_top": preview_top_value if preview_top_value > 0 else raw_top,
        "left": row["margin_kiri"] if row["margin_kiri"] is not None else DEFAULT_MARGIN,
        "right": row["margin_kanan"] if row["margin_kanan"] is not None else DEFAULT_MARGIN,
        "bottom": row["margin_bawah"] if row["margin_bawah"] is not None else DEFAULT_MARGIN,
        "header_clearance": row["ruang_aman_kop"] if row["ruang_aman_kop"] is not None else DEFAULT_MARGIN,
        "background_url": row.get("secure_url"),
    }
