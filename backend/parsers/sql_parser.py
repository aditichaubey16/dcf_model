"""Parses SQL sources: SQLite database files (.db/.sqlite/.sqlite3) or
plain .sql dump/script files. Loaded into an in-memory sqlite3 database
(local, no external DB service) and each table is read as a candidate
financial table: first text column = line item label, remaining numeric
columns = periods.

.sql scripts are expected to be SQLite-compatible. Common MySQL-dump-only
syntax (ENGINE=, AUTO_INCREMENT, conditional /*! */ comments, LOCK TABLES,
etc.) is stripped on a best-effort basis so typical `mysqldump` exports of
a simple financials table also load, without needing an actual MySQL/
Postgres server (which would violate the no-external-service constraint).
"""
from __future__ import annotations

import re
import sqlite3
import tempfile
from pathlib import Path

from backend.parsers.tabular import RawTable, _coerce_number


def parse_sql(file_bytes: bytes, filename: str) -> list[RawTable]:
    suffix = Path(filename).suffix.lower()

    if suffix in (".db", ".sqlite", ".sqlite3"):
        with tempfile.NamedTemporaryFile(suffix=suffix, delete=False) as tmp:
            tmp.write(file_bytes)
            tmp_path = tmp.name
        conn = sqlite3.connect(tmp_path)
    else:
        conn = sqlite3.connect(":memory:")
        script = file_bytes.decode("utf-8", errors="ignore")
        _load_script(conn, script)

    tables: list[RawTable] = []
    try:
        cur = conn.cursor()
        cur.execute("SELECT name FROM sqlite_master WHERE type='table'")
        table_names = [row[0] for row in cur.fetchall()]

        for table_name in table_names:
            rows = _read_table(conn, table_name)
            if rows:
                tables.append(RawTable(sheet_name=table_name, rows=rows))
    finally:
        conn.close()

    return tables


def _load_script(conn: sqlite3.Connection, script: str) -> None:
    """Try the script as-is first; if it doesn't parse under SQLite, retry
    with common MySQL-dump-only syntax stripped. Raises the original error
    (with a clear hint) if neither works."""
    try:
        conn.executescript(script)
        return
    except sqlite3.Error:
        pass

    sanitized = _sanitize_mysql_dump(script)
    try:
        conn.executescript(sanitized)
    except sqlite3.Error as exc:
        raise ValueError(
            "This .sql file isn't valid SQLite syntax and couldn't be auto-converted "
            "from a MySQL/Postgres dump either. Export a SQLite-compatible .sql script, "
            "or upload a .db/.sqlite file instead. "
            f"(underlying error: {exc})"
        ) from exc


def _sanitize_mysql_dump(script: str) -> str:
    # Drop MySQL "conditional comments" like /*!40101 ... */;
    script = re.sub(r"/\*!.*?\*/;?", "", script, flags=re.DOTALL)
    # Drop full-line -- comments and MySQL session/lock statements.
    lines = []
    skip_prefixes = ("--", "SET ", "LOCK TABLES", "UNLOCK TABLES", "START TRANSACTION", "USE ")
    for line in script.splitlines():
        stripped = line.strip()
        if any(stripped.upper().startswith(p.upper()) for p in skip_prefixes):
            continue
        lines.append(line)
    script = "\n".join(lines)

    # Backticks -> double quotes (SQLite identifier quoting).
    script = script.replace("`", '"')
    # Strip MySQL table-option suffixes after the closing paren of CREATE TABLE.
    script = re.sub(r"\)\s*ENGINE=\w+[^;]*;", ");", script, flags=re.IGNORECASE)
    # Strip AUTO_INCREMENT / UNSIGNED keywords and int(11)-style widths.
    script = re.sub(r"\bAUTO_INCREMENT\b", "", script, flags=re.IGNORECASE)
    script = re.sub(r"\bUNSIGNED\b", "", script, flags=re.IGNORECASE)
    script = re.sub(r"\bint\(\d+\)", "INTEGER", script, flags=re.IGNORECASE)
    script = re.sub(r"\bvarchar\((\d+)\)", r"VARCHAR(\1)", script, flags=re.IGNORECASE)
    return script


def _read_table(conn: sqlite3.Connection, table_name: str) -> list[tuple[str, dict[str, float]]]:
    cur = conn.cursor()
    cur.execute(f'PRAGMA table_info("{table_name}")')
    # pragma columns: (cid, name, type, notnull, dflt_value, pk)
    pragma_cols = cur.fetchall()

    # Skip an auto-increment-style surrogate key ("id" + INTEGER + PRIMARY KEY) —
    # otherwise it gets mistaken for the label column and its 1,2,3.. values
    # for a bogus "period". A natural text primary key (the real label column)
    # is untouched since it won't be named "id"/INTEGER.
    columns = [
        row[1]
        for row in pragma_cols
        if not (row[1].lower() in ("id", "pk", "rowid") and row[5] == 1 and "int" in row[2].lower())
    ]
    if len(columns) < 2:
        return []

    label_col = columns[0]
    period_cols = columns[1:]
    col_list_sql = ", ".join(f'"{c}"' for c in columns)

    cur.execute(f'SELECT {col_list_sql} FROM "{table_name}"')
    rows: list[tuple[str, dict[str, float]]] = []
    for record in cur.fetchall():
        label = record[0]
        if label is None:
            continue
        label = str(label).strip()
        if not label:
            continue
        values: dict[str, float] = {}
        for col_name, cell in zip(period_cols, record[1:]):
            num = _coerce_number(cell)
            if num is not None:
                values[col_name] = num
        if values:
            rows.append((label, values))
    return rows
