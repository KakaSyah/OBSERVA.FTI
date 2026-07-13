"""
backend/services/letter_number_service.py

Penomoran surat otomatis menggunakan counter di system_settings.
"""

import json
from datetime import date

from flask import current_app
from pymysql import IntegrityError

from backend.extensions import db
from backend.models.letter_number import LetterNumber
from backend.models.system_setting import SystemSetting
from backend.utils.formatters import bulan_ke_romawi


class LetterNumberError(Exception):
    """Error domain penomoran surat."""


def _insert_instance(instance) -> int:
    model = instance.__class__
    pk_name = model._primary_key
    columns = []
    values = []
    for name, column in model._columns.items():
        if name == pk_name:
            continue
        value = getattr(instance, name, None)
        if value is None and column.kwargs.get("server_default") is not None:
            continue
        if name in {"created_at", "updated_at", "deleted_at"} and value is None:
            continue
        columns.append(f"`{column.column_name}`")
        values.append(value)
    placeholders = ", ".join(["%s"] * len(columns))
    sql = f"INSERT INTO `{model.__tablename__}` ({', '.join(columns)}) VALUES ({placeholders})"
    lastrowid = db.insert(sql, values)
    if pk_name and getattr(instance, pk_name, None) is None:
        setattr(instance, pk_name, lastrowid)
    return lastrowid


def _update_instance(instance) -> int:
    model = instance.__class__
    pk_name = model._primary_key
    pk_value = getattr(instance, pk_name, None)
    if pk_value is None:
        raise ValueError("Cannot update model without primary key value.")
    fields = []
    values = []
    for name, column in model._columns.items():
        if name == pk_name:
            continue
        value = getattr(instance, name, None)
        if name in {"created_at", "updated_at", "deleted_at"} and value is None:
            continue
        fields.append(f"`{column.column_name}` = %s")
        values.append(value)
    if not fields:
        return 0
    values.append(pk_value)
    sql = f"UPDATE `{model.__tablename__}` SET {', '.join(fields)} WHERE `{model._columns[pk_name].column_name}` = %s"
    cursor = db.execute(sql, values)
    return cursor.rowcount


def _counter_key(year: int, month: int) -> str:
    return f"letter_counter_{year}_{month:02d}"


def _get_or_create_counter_row_locked(year: int, month: int) -> SystemSetting:
    key = _counter_key(year, month)
    setting = db.fetchone(
        "SELECT * FROM `system_settings` WHERE `setting_key` = %s FOR UPDATE",
        (key,),
    )
    if setting is not None:
        return SystemSetting.from_row(setting)

    try:
        with db.begin_nested():
            setting = SystemSetting(
                setting_key=key,
                setting_value=json.dumps({"counter": 0}),
                description=f"Counter nomor surat observasi periode {month:02d}/{year}",
            )
            _insert_instance(setting)
    except IntegrityError:
        setting = db.fetchone(
            "SELECT * FROM `system_settings` WHERE `setting_key` = %s FOR UPDATE",
            (key,),
        )
        if setting is None:
            raise LetterNumberError("Gagal menyiapkan counter nomor surat untuk periode ini.")
    return SystemSetting.from_row(setting)


def generate_for_request(obs, when=None) -> LetterNumber:
    if obs.letter_number is not None:
        raise LetterNumberError("Pengajuan ini sudah memiliki nomor surat.")

    reference_date = when or date.today()
    year = reference_date.year
    month = reference_date.month

    counter_row = _get_or_create_counter_row_locked(year, month)
    data = json.loads(counter_row.setting_value)
    next_sequence = int(data.get("counter", 0)) + 1
    data["counter"] = next_sequence
    counter_row.setting_value = json.dumps(data)
    _update_instance(counter_row)

    kode_fakultas = current_app.config.get("FACULTY_CODE", "FAK")
    bulan_romawi = bulan_ke_romawi(month)
    formatted_number = f"{next_sequence}/{kode_fakultas}/OBS/{bulan_romawi}/{year}"

    letter_number = LetterNumber(
        observation_request=obs,
        sequence_number=next_sequence,
        month_roman=bulan_romawi,
        year=year,
        formatted_number=formatted_number,
    )
    _insert_instance(letter_number)
    return letter_number
