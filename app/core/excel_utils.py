"""Pembaca file Excel untuk fitur import (.xlsx via openpyxl, .xls lama via xlrd).

Export Fingerspot / Excel lama sering berformat .xls (BIFF) yang tidak bisa dibaca openpyxl.
"""
import io
from typing import Any, List, Optional

import openpyxl
import xlrd

# Batas baris format .xls (BIFF8). Fingerspot Personnel tetap menulis lebih dari ini sehingga
# file rusak (baris ke-65.537 menimpa baris awal); Excel memotongnya diam-diam saat membuka/konversi.
XLS_MAX_ROWS = 65536
SPLIT_HINT = "Export ulang dari Fingerspot Personnel dengan rentang tanggal lebih pendek (misalnya per minggu)."


class ExcelReadError(ValueError):
    """File Excel tidak bisa dibaca; pesannya siap ditampilkan ke pengguna."""


def _normalize_xls_cell(cell, datemode: int) -> Any:
    if cell.ctype == xlrd.XL_CELL_EMPTY or cell.ctype == xlrd.XL_CELL_BLANK:
        return None
    if cell.ctype == xlrd.XL_CELL_DATE:
        return xlrd.xldate_as_datetime(cell.value, datemode)
    if cell.ctype == xlrd.XL_CELL_NUMBER:
        # Angka bulat di .xls selalu float (PIN 1001 -> 1001.0); kembalikan sebagai int
        return int(cell.value) if float(cell.value).is_integer() else cell.value
    if cell.ctype == xlrd.XL_CELL_BOOLEAN:
        return bool(cell.value)
    return cell.value


def read_excel_rows(content: bytes, filename: str) -> List[List[Any]]:
    """Semua baris sheet pertama/aktif sebagai list nilai (baris kosong ikut dikembalikan)."""
    if filename.lower().endswith('.xls'):
        try:
            # logfile: redam peringatan "No CODEPAGE record" dari export Fingerspot
            wb = xlrd.open_workbook(file_contents=content, logfile=io.StringIO())
        except Exception as e:
            raise ExcelReadError(
                "File .xls tidak bisa dibaca: rusak atau melebihi 65.536 baris (batas format .xls). " + SPLIT_HINT
            ) from e
        sheet = wb.sheet_by_index(0)
        return [
            [_normalize_xls_cell(sheet.cell(r, c), wb.datemode) for c in range(sheet.ncols)]
            for r in range(sheet.nrows)
        ]
    try:
        wb = openpyxl.load_workbook(io.BytesIO(content), data_only=True, read_only=True)
    except Exception as e:
        raise ExcelReadError("File Excel tidak bisa dibaca (rusak atau bukan file Excel).") from e
    try:
        return [list(r) for r in wb.active.iter_rows(values_only=True)]
    finally:
        wb.close()


def truncation_warning(rows: List[List[Any]]) -> Optional[str]:
    """Peringatan jika jumlah baris (termasuk baris kosong) menyentuh batas .xls: data hampir pasti terpotong."""
    if len(rows) >= XLS_MAX_ROWS:
        return (
            "File berisi 65.536 baris, tepat batas format .xls. Data kemungkinan besar terpotong "
            "(scan di akhir periode hilang). Periksa tanggal terakhir yang masuk. " + SPLIT_HINT
        )
    return None


def is_blank_row(row) -> bool:
    return not row or all(c is None or str(c).strip() == '' for c in row)
