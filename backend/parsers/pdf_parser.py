"""Best-effort table extraction from PDF financial statements using
pdfplumber (local, no external OCR/service). Works well for text-based
(not scanned-image) PDFs with reasonably tabular layouts.
"""
from __future__ import annotations

import io
import re

import pdfplumber

from backend.parsers.tabular import RawTable, _coerce_number

# A header cell this long, or containing a line break, is almost always a
# mis-extracted paragraph/notes block rather than a genuine period label
# (year, quarter, date) — reject the whole table rather than pollute the
# dashboard's period list with unreadable noise.
_MAX_HEADER_LEN = 30
_HAS_LETTER = re.compile(r"[A-Za-z]")


def parse_pdf(file_bytes: bytes) -> list[RawTable]:
    tables: list[RawTable] = []
    with pdfplumber.open(io.BytesIO(file_bytes)) as pdf:
        for page_num, page in enumerate(pdf.pages, start=1):
            for t_idx, raw_table in enumerate(page.extract_tables()):
                rows = _extract_rows(raw_table)
                if rows:
                    tables.append(RawTable(sheet_name=f"page {page_num} table {t_idx + 1}", rows=rows))
    return tables


def _extract_rows(raw_table: list[list]) -> list[tuple[str, dict[str, float]]]:
    if not raw_table or len(raw_table) < 2:
        return []

    header = raw_table[0]
    period_labels = []
    for i, h in enumerate(header[1:], start=1):
        text = str(h).strip() if h else ""
        if not text:
            period_labels.append(f"col{i}")
            continue
        if "\n" in text or len(text) > _MAX_HEADER_LEN:
            return []  # garbled header row — whole table is unreliable
        period_labels.append(text)

    rows: list[tuple[str, dict[str, float]]] = []
    for row in raw_table[1:]:
        if not row or row[0] is None:
            continue
        label = str(row[0]).strip()
        if not label or not _HAS_LETTER.search(label):
            # a numeric/punctuation-only "label" means columns were
            # misaligned during extraction — not a real line item
            continue
        values: dict[str, float] = {}
        for period, cell in zip(period_labels, row[1:]):
            num = _coerce_number(cell)
            if num is not None:
                values[period] = num
        if values:
            rows.append((label, values))
    return rows
