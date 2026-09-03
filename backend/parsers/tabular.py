"""Parses Excel (.xlsx/.xls) and CSV files into raw (label, {period: value}) tables.

Expected shape (flexible): first column holds line-item labels, remaining
columns hold periods (years/quarters/dates) as headers. Excel workbooks may
have multiple sheets (e.g. "Income Statement", "Balance Sheet"); each sheet
is parsed independently and later merged by the normalization layer.
"""
from __future__ import annotations

import io
import re
from dataclasses import dataclass

import pandas as pd


@dataclass
class RawTable:
    sheet_name: str
    rows: list[tuple[str, dict[str, float]]]  # (label, {period_label: value})


def _clean_period_header(col) -> str:
    if isinstance(col, (pd.Timestamp,)):
        return str(col.year)
    text = str(col).strip()
    return text


def _coerce_number(val) -> float | None:
    if val is None:
        return None
    if isinstance(val, (int, float)):
        if pd.isna(val):
            return None
        return float(val)
    text = str(val).strip()
    if text == "" or text.lower() in ("nan", "none", "-", "—"):
        return None
    negative = text.startswith("(") and text.endswith(")")
    text = text.strip("()")
    text = re.sub(r"[,\s₹$€£]", "", text)
    text = text.replace("%", "")
    if text == "" or not re.match(r"^-?\d+(\.\d+)?$", text):
        return None
    num = float(text)
    return -num if negative else num


def _df_to_rawtable(df: pd.DataFrame, sheet_name: str) -> RawTable:
    if df.empty or df.shape[1] < 2:
        return RawTable(sheet_name=sheet_name, rows=[])

    label_col = df.columns[0]
    period_cols = list(df.columns[1:])
    period_labels = [_clean_period_header(c) for c in period_cols]

    rows: list[tuple[str, dict[str, float]]] = []
    for _, row in df.iterrows():
        label = row[label_col]
        if label is None or (isinstance(label, float) and pd.isna(label)):
            continue
        label = str(label).strip()
        if not label:
            continue
        values: dict[str, float] = {}
        for col, period in zip(period_cols, period_labels):
            num = _coerce_number(row[col])
            if num is not None:
                values[period] = num
        if values:
            rows.append((label, values))

    return RawTable(sheet_name=sheet_name, rows=rows)


def parse_excel(file_bytes: bytes) -> list[RawTable]:
    xls = pd.ExcelFile(io.BytesIO(file_bytes))
    tables = []
    for sheet_name in xls.sheet_names:
        df = xls.parse(sheet_name, header=0)
        df = df.dropna(axis=1, how="all").dropna(axis=0, how="all")
        if df.empty:
            continue
        tables.append(_df_to_rawtable(df, sheet_name))
    return [t for t in tables if t.rows]


def parse_csv(file_bytes: bytes) -> list[RawTable]:
    df = pd.read_csv(io.BytesIO(file_bytes))
    df = df.dropna(axis=1, how="all").dropna(axis=0, how="all")
    return [_df_to_rawtable(df, sheet_name="csv")]
