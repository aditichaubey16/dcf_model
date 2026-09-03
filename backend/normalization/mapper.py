"""Maps raw parsed labels onto the canonical financial schema.

Strategy:
1. Normalize label text (lowercase, strip punctuation/whitespace).
2. Exact match against the alias dictionary (config/aliases.yaml).
3. Fallback to fuzzy match (rapidfuzz) against all known aliases; accept
   above a confidence threshold, otherwise leave unmapped for user review.
"""
from __future__ import annotations

import re
from dataclasses import dataclass, field
from pathlib import Path

import yaml
from rapidfuzz import fuzz, process

from backend.parsers.tabular import RawTable

CONFIG_PATH = Path(__file__).resolve().parent.parent / "config" / "aliases.yaml"
FUZZY_ACCEPT_THRESHOLD = 87  # 0-100, rapidfuzz token_sort_ratio
FUZZY_REVIEW_THRESHOLD = 75  # below this, don't even suggest


def _normalize(text: str) -> str:
    text = text.lower().strip()
    text = re.sub(r"[^a-z0-9\s&]", " ", text)
    text = re.sub(r"\s+", " ", text)
    return text.strip()


@dataclass
class AliasIndex:
    # normalized alias text -> (statement, field)
    exact: dict[str, tuple[str, str]] = field(default_factory=dict)
    # list of (normalized alias text, statement, field) for fuzzy search
    all_aliases: list[tuple[str, str, str]] = field(default_factory=list)

    @classmethod
    def load(cls, path: Path = CONFIG_PATH) -> "AliasIndex":
        with open(path, "r", encoding="utf-8") as f:
            raw = yaml.safe_load(f)
        idx = cls()
        for statement, fields in raw.items():
            for canonical_field, aliases in fields.items():
                for alias in aliases:
                    norm = _normalize(alias)
                    idx.exact[norm] = (statement, canonical_field)
                    idx.all_aliases.append((norm, statement, canonical_field))
                # also index the field name itself
                norm_field = _normalize(canonical_field.replace("_", " "))
                idx.exact.setdefault(norm_field, (statement, canonical_field))
                idx.all_aliases.append((norm_field, statement, canonical_field))
        return idx

    def match(self, label: str) -> tuple[tuple[str, str] | None, int]:
        norm = _normalize(label)
        if norm in self.exact:
            return self.exact[norm], 100
        if not self.all_aliases:
            return None, 0
        choices = [a[0] for a in self.all_aliases]
        result = process.extractOne(norm, choices, scorer=fuzz.token_sort_ratio)
        if result is None:
            return None, 0
        _, score, idx = result
        if score >= FUZZY_ACCEPT_THRESHOLD:
            _, statement, canonical_field = self.all_aliases[idx]
            return (statement, canonical_field), int(score)
        if score >= FUZZY_REVIEW_THRESHOLD:
            _, statement, canonical_field = self.all_aliases[idx]
            return (statement, canonical_field), int(score)
        return None, int(score)


@dataclass
class UnmappedItem:
    label: str
    sheet: str
    suggestion: tuple[str, str] | None
    score: int


@dataclass
class NormalizedData:
    # statement -> canonical_field -> period -> value
    statements: dict[str, dict[str, dict[str, float]]]
    periods: list[str]
    unmapped: list[UnmappedItem]
    needs_review: list[UnmappedItem]  # mapped but below full-confidence


def normalize_tables(tables: list[RawTable], alias_index: AliasIndex | None = None) -> NormalizedData:
    alias_index = alias_index or AliasIndex.load()

    statements: dict[str, dict[str, dict[str, float]]] = {
        "income_statement": {},
        "balance_sheet": {},
        "cash_flow": {},
    }
    unmapped: list[UnmappedItem] = []
    needs_review: list[UnmappedItem] = []
    all_periods: set[str] = set()

    for table in tables:
        for label, values in table.rows:
            match, score = alias_index.match(label)
            all_periods.update(values.keys())

            if match is None:
                unmapped.append(UnmappedItem(label=label, sheet=table.sheet_name, suggestion=None, score=score))
                continue

            statement, canonical_field = match
            bucket = statements[statement].setdefault(canonical_field, {})
            for period, value in values.items():
                # first mapping wins for a given (field, period); avoids
                # silently overwriting with a worse duplicate-labeled row
                bucket.setdefault(period, value)

            if score < FUZZY_ACCEPT_THRESHOLD:
                needs_review.append(
                    UnmappedItem(label=label, sheet=table.sheet_name, suggestion=match, score=score)
                )

    periods = sorted(all_periods, key=_period_sort_key)
    return NormalizedData(
        statements=statements, periods=periods, unmapped=unmapped, needs_review=needs_review
    )


def _period_sort_key(period: str):
    # Always return a same-shaped tuple so mixed year/non-year period labels
    # (e.g. "FY2024" alongside a stray "col5" from a messy table) remain
    # mutually comparable instead of crashing sorted() on int-vs-str.
    m = re.search(r"(\d{4})", period)
    if m:
        return (0, int(m.group(1)), period)
    return (1, 0, period)
