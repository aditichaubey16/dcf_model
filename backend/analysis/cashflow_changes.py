"""Cash-flow change / quality-of-earnings analysis.

Deterministic, formula-based — no inference. Computes period-over-period
deltas across the cash flow statement, FCF conversion quality, and flags the
kind of divergences a PE analyst checks for (earnings growing while cash
generation lags, capex-heavy years, cash flow driven by financing rather
than operations, etc.).
"""
from __future__ import annotations

from dataclasses import dataclass, asdict

from backend.analysis.ratios import PeriodMetrics


@dataclass
class PeriodChange:
    period: str
    prior_period: str | None

    operating_cf: float | None = None
    operating_cf_change_pct: float | None = None
    investing_cf: float | None = None
    investing_cf_change_pct: float | None = None
    financing_cf: float | None = None
    financing_cf_change_pct: float | None = None
    free_cash_flow: float | None = None
    free_cash_flow_change_pct: float | None = None

    revenue_growth_pct: float | None = None
    fcf_growth_pct: float | None = None
    fcf_vs_revenue_divergence: float | None = None  # fcf growth - revenue growth

    fcf_conversion: float | None = None       # FCF / Net income
    ocf_to_ni: float | None = None            # Operating CF / Net income

    def to_dict(self):
        return asdict(self)


@dataclass
class CashFlowChangeFlag:
    severity: str  # "red" | "amber" | "info"
    period: str
    title: str
    message: str


def _pct_change(curr: float | None, prev: float | None) -> float | None:
    if curr is None or prev is None or prev == 0:
        return None
    return round((curr - prev) / abs(prev) * 100, 2)


def compute_cashflow_changes(metrics: list[PeriodMetrics]) -> list[PeriodChange]:
    changes: list[PeriodChange] = []
    for i, m in enumerate(metrics):
        prev = metrics[i - 1] if i > 0 else None

        fcf_conversion = None
        if m.free_cash_flow is not None and m.net_income not in (None, 0):
            fcf_conversion = round(m.free_cash_flow / m.net_income, 2)

        ocf_to_ni = None
        if m.operating_cash_flow is not None and m.net_income not in (None, 0):
            ocf_to_ni = round(m.operating_cash_flow / m.net_income, 2)

        fcf_growth = _pct_change(m.free_cash_flow, prev.free_cash_flow) if prev else None
        divergence = None
        if fcf_growth is not None and m.revenue_growth is not None:
            divergence = round(fcf_growth - m.revenue_growth, 2)

        changes.append(
            PeriodChange(
                period=m.period,
                prior_period=prev.period if prev else None,
                operating_cf=m.operating_cash_flow,
                operating_cf_change_pct=_pct_change(m.operating_cash_flow, prev.operating_cash_flow) if prev else None,
                investing_cf=m.investing_cash_flow,
                investing_cf_change_pct=_pct_change(m.investing_cash_flow, prev.investing_cash_flow) if prev else None,
                financing_cf=m.financing_cash_flow,
                financing_cf_change_pct=_pct_change(m.financing_cash_flow, prev.financing_cash_flow) if prev else None,
                free_cash_flow=m.free_cash_flow,
                free_cash_flow_change_pct=fcf_growth,
                revenue_growth_pct=m.revenue_growth,
                fcf_growth_pct=fcf_growth,
                fcf_vs_revenue_divergence=divergence,
                fcf_conversion=fcf_conversion,
                ocf_to_ni=ocf_to_ni,
            )
        )
    return changes


def flag_cashflow_changes(changes: list[PeriodChange]) -> list[CashFlowChangeFlag]:
    flags: list[CashFlowChangeFlag] = []

    for c in changes:
        if c.prior_period is None:
            continue

        if c.ocf_to_ni is not None and c.ocf_to_ni < 0.8:
            flags.append(CashFlowChangeFlag(
                severity="red" if c.ocf_to_ni < 0.5 else "amber",
                period=c.period,
                title="Weak earnings-to-cash conversion",
                message=(
                    f"Operating cash flow is only {c.ocf_to_ni:.2f}x net income in {c.period} — "
                    "reported earnings are not translating into cash at a healthy rate."
                ),
            ))

        if c.fcf_vs_revenue_divergence is not None and c.fcf_vs_revenue_divergence < -15:
            flags.append(CashFlowChangeFlag(
                severity="amber",
                period=c.period,
                title="Free cash flow lagging revenue growth",
                message=(
                    f"In {c.period}, revenue grew {c.revenue_growth_pct:.1f}% but FCF grew "
                    f"{c.fcf_growth_pct:.1f}% ({c.fcf_vs_revenue_divergence:+.1f} pts gap) — "
                    "check capex, working capital, or margin pressure."
                ),
            ))

        if c.free_cash_flow_change_pct is not None and c.free_cash_flow_change_pct <= -25:
            flags.append(CashFlowChangeFlag(
                severity="red",
                period=c.period,
                title="Sharp free cash flow decline",
                message=f"Free cash flow fell {c.free_cash_flow_change_pct:.1f}% versus {c.prior_period}.",
            ))

        if (
            c.financing_cf is not None and c.operating_cf is not None
            and c.financing_cf > 0 and c.operating_cf < 0
        ):
            flags.append(CashFlowChangeFlag(
                severity="red",
                period=c.period,
                title="Cash sustained by financing, not operations",
                message=(
                    f"In {c.period}, operating cash flow was negative while financing activity was "
                    "positive — the business is being kept afloat by external funding, not operations."
                ),
            ))

        if c.fcf_conversion is not None and c.fcf_conversion > 1.5:
            flags.append(CashFlowChangeFlag(
                severity="info",
                period=c.period,
                title="High free cash flow conversion",
                message=(
                    f"FCF is {c.fcf_conversion:.2f}x net income in {c.period} — favorable for cash "
                    "generation, but worth checking for one-off working-capital releases."
                ),
            ))

    return flags
