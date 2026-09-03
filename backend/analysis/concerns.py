"""Concern-area rules engine. Reads thresholds.yaml and evaluates each rule
against the computed per-period metrics, producing a flat list of flags.
Every flag is traceable to a named rule and a formula, not a model guess.
"""
from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

import yaml

from backend.analysis.ratios import PeriodMetrics

CONFIG_PATH = Path(__file__).resolve().parent.parent / "config" / "thresholds.yaml"


@dataclass
class ConcernFlag:
    id: str
    severity: str
    title: str
    message: str
    period: str
    metric: str
    value: float | None


def load_rules(path: Path = CONFIG_PATH) -> list[dict]:
    with open(path, "r", encoding="utf-8") as f:
        raw = yaml.safe_load(f)
    return raw.get("rules", [])


def evaluate_concerns(metrics: list[PeriodMetrics], rules: list[dict] | None = None) -> list[ConcernFlag]:
    rules = rules if rules is not None else load_rules()
    flags: list[ConcernFlag] = []

    for rule in rules:
        condition = rule["condition"]
        metric_name = rule["metric"]

        if condition == "declining_trend":
            flags.extend(_check_declining_trend(metrics, rule))
            continue

        for m in metrics:
            if metric_name == "cf_income_mismatch":
                value = m.cf_income_mismatch
            else:
                value = getattr(m, metric_name, None)

            if value is None:
                continue

            triggered = False
            if condition == "less_than" and value < rule["value"]:
                triggered = True
            elif condition == "greater_than" and value > rule["value"]:
                triggered = True
            elif condition == "between":
                lo, hi = rule["value"]
                triggered = lo <= value <= hi
            elif condition == "flag_true" and value is True:
                triggered = True

            if triggered:
                display_value = _format_value(value)
                flags.append(
                    ConcernFlag(
                        id=rule["id"],
                        severity=rule["severity"],
                        title=rule["title"],
                        message=rule["message"].format(value=display_value, period=m.period),
                        period=m.period,
                        metric=metric_name,
                        value=value if isinstance(value, (int, float)) else None,
                    )
                )

    return flags


def _check_declining_trend(metrics: list[PeriodMetrics], rule: dict) -> list[ConcernFlag]:
    min_run = int(rule["value"])
    metric_name = rule["metric"]
    flags: list[ConcernFlag] = []

    run = 1
    for i in range(1, len(metrics)):
        prev_val = getattr(metrics[i - 1], metric_name, None)
        curr_val = getattr(metrics[i], metric_name, None)
        if prev_val is not None and curr_val is not None and curr_val < prev_val:
            run += 1
        else:
            run = 1
        if run >= min_run:
            m = metrics[i]
            flags.append(
                ConcernFlag(
                    id=rule["id"],
                    severity=rule["severity"],
                    title=rule["title"],
                    message=rule["message"].format(value=run, period=m.period),
                    period=m.period,
                    metric=metric_name,
                    value=getattr(m, metric_name, None),
                )
            )
            run = 1  # avoid duplicate overlapping flags

    return flags


def _format_value(value) -> str:
    if isinstance(value, bool):
        return str(value)
    if isinstance(value, float):
        return f"{value:.2f}"
    return str(value)
