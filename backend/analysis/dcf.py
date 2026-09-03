"""Discounted Cash Flow valuation engine.

Deterministic DCF over historical FCF: builds an explicit projection period
off a revenue-growth / FCF-margin assumption pair, discounts it at WACC, adds
a Gordon-growth terminal value, and derives enterprise/equity value. Also
produces a WACC x terminal-growth sensitivity grid, the standard PE output.
"""
from __future__ import annotations

from dataclasses import dataclass, field, asdict

from backend.analysis.ratios import PeriodMetrics


@dataclass
class DCFAssumptions:
    projection_years: int = 5
    revenue_growth_rate: float = 0.08          # annual, decimal (0.08 = 8%)
    fcf_margin: float | None = None            # FCF / revenue; None = use historical avg
    wacc: float = 0.10
    terminal_growth: float = 0.025
    net_debt: float = 0.0                      # total debt - cash, as of latest period
    shares_outstanding: float | None = None


@dataclass
class ProjectedYear:
    year: int
    revenue: float
    free_cash_flow: float
    discount_factor: float
    present_value: float


@dataclass
class DCFResult:
    base_revenue: float
    historical_fcf_margin: float | None
    assumed_fcf_margin: float
    projections: list[ProjectedYear] = field(default_factory=list)
    sum_pv_fcf: float = 0.0
    terminal_value: float = 0.0
    pv_terminal_value: float = 0.0
    enterprise_value: float = 0.0
    net_debt: float = 0.0
    equity_value: float = 0.0
    value_per_share: float | None = None
    sensitivity: dict = field(default_factory=dict)
    warnings: list[str] = field(default_factory=list)

    def to_dict(self):
        d = asdict(self)
        return d


def _historical_fcf_margin(metrics: list[PeriodMetrics]) -> float | None:
    pairs = [
        (m.free_cash_flow, m.revenue)
        for m in metrics
        if m.free_cash_flow is not None and m.revenue not in (None, 0)
    ]
    if not pairs:
        return None
    margins = [fcf / rev for fcf, rev in pairs]
    return sum(margins) / len(margins)


def _latest_revenue(metrics: list[PeriodMetrics]) -> float | None:
    for m in reversed(metrics):
        if m.revenue is not None:
            return m.revenue
    return None


def _project(
    base_revenue: float,
    fcf_margin: float,
    growth: float,
    wacc: float,
    terminal_growth: float,
    years: int,
) -> tuple[list[ProjectedYear], float, float, float]:
    projections: list[ProjectedYear] = []
    revenue = base_revenue
    sum_pv = 0.0
    for y in range(1, years + 1):
        revenue = revenue * (1 + growth)
        fcf = revenue * fcf_margin
        discount_factor = 1 / ((1 + wacc) ** y)
        pv = fcf * discount_factor
        sum_pv += pv
        projections.append(
            ProjectedYear(
                year=y,
                revenue=round(revenue, 2),
                free_cash_flow=round(fcf, 2),
                discount_factor=round(discount_factor, 4),
                present_value=round(pv, 2),
            )
        )
    terminal_fcf = projections[-1].free_cash_flow * (1 + terminal_growth)
    terminal_value = terminal_fcf / (wacc - terminal_growth)
    pv_terminal = terminal_value / ((1 + wacc) ** years)
    return projections, sum_pv, terminal_value, pv_terminal


def run_dcf(metrics: list[PeriodMetrics], assumptions: DCFAssumptions) -> DCFResult:
    warnings: list[str] = []

    base_revenue = _latest_revenue(metrics)
    if base_revenue is None:
        warnings.append("No revenue found in historicals — using 0 as base revenue.")
        base_revenue = 0.0

    hist_margin = _historical_fcf_margin(metrics)
    fcf_margin = assumptions.fcf_margin if assumptions.fcf_margin is not None else hist_margin
    if fcf_margin is None:
        warnings.append("No historical FCF margin available — defaulted assumed FCF margin to 10%.")
        fcf_margin = 0.10

    if assumptions.wacc <= assumptions.terminal_growth:
        warnings.append(
            "WACC must exceed terminal growth for the model to converge — "
            "terminal value cannot be computed reliably as configured."
        )

    projections, sum_pv, tv, pv_tv = _project(
        base_revenue,
        fcf_margin,
        assumptions.revenue_growth_rate,
        assumptions.wacc,
        assumptions.terminal_growth,
        assumptions.projection_years,
    )

    enterprise_value = sum_pv + pv_tv
    equity_value = enterprise_value - assumptions.net_debt
    value_per_share = (
        equity_value / assumptions.shares_outstanding
        if assumptions.shares_outstanding
        else None
    )

    result = DCFResult(
        base_revenue=round(base_revenue, 2),
        historical_fcf_margin=round(hist_margin, 4) if hist_margin is not None else None,
        assumed_fcf_margin=round(fcf_margin, 4),
        projections=projections,
        sum_pv_fcf=round(sum_pv, 2),
        terminal_value=round(tv, 2),
        pv_terminal_value=round(pv_tv, 2),
        enterprise_value=round(enterprise_value, 2),
        net_debt=round(assumptions.net_debt, 2),
        equity_value=round(equity_value, 2),
        value_per_share=round(value_per_share, 2) if value_per_share is not None else None,
        warnings=warnings,
    )
    result.sensitivity = build_sensitivity(base_revenue, fcf_margin, assumptions)
    return result


def build_sensitivity(base_revenue: float, fcf_margin: float, assumptions: DCFAssumptions) -> dict:
    wacc_range = [assumptions.wacc + d for d in (-0.02, -0.01, 0.0, 0.01, 0.02)]
    g_range = [assumptions.terminal_growth + d for d in (-0.01, -0.005, 0.0, 0.005, 0.01)]

    rows = []
    for wacc in wacc_range:
        row = []
        for g in g_range:
            if wacc <= g:
                row.append(None)
                continue
            _, sum_pv, _, pv_tv = _project(
                base_revenue, fcf_margin, assumptions.revenue_growth_rate, wacc, g, assumptions.projection_years
            )
            ev = sum_pv + pv_tv
            row.append(round(ev, 2))
        rows.append(row)

    return {
        "wacc_axis": [round(w, 4) for w in wacc_range],
        "terminal_growth_axis": [round(g, 4) for g in g_range],
        "enterprise_values": rows,
    }


# Standard PE case spreads applied to the base-case revenue growth and FCF
# margin assumptions. Bear trims both; bull lifts both; base is unchanged.
SCENARIO_SPREADS = {
    "bear": {"growth_delta": -0.04, "margin_delta": -0.02},
    "base": {"growth_delta": 0.0, "margin_delta": 0.0},
    "bull": {"growth_delta": 0.04, "margin_delta": 0.02},
}


def run_scenarios(metrics: list[PeriodMetrics], assumptions: DCFAssumptions) -> dict:
    """Runs bear/base/bull cases off the same base assumptions, varying only
    revenue growth and FCF margin — WACC and terminal growth stay fixed so
    the spread reflects operating-case uncertainty, not discount-rate risk.
    """
    hist_margin = _historical_fcf_margin(metrics)
    base_fcf_margin = assumptions.fcf_margin if assumptions.fcf_margin is not None else (hist_margin or 0.10)

    results = {}
    for case, spread in SCENARIO_SPREADS.items():
        case_assumptions = DCFAssumptions(
            projection_years=assumptions.projection_years,
            revenue_growth_rate=assumptions.revenue_growth_rate + spread["growth_delta"],
            fcf_margin=max(base_fcf_margin + spread["margin_delta"], 0.001),
            wacc=assumptions.wacc,
            terminal_growth=assumptions.terminal_growth,
            net_debt=assumptions.net_debt,
            shares_outstanding=assumptions.shares_outstanding,
        )
        result = run_dcf(metrics, case_assumptions)
        result.sensitivity = {}  # redundant per-case; the base case already carries the full grid
        result_dict = result.to_dict()
        result_dict["revenue_growth_rate"] = round(case_assumptions.revenue_growth_rate, 4)
        results[case] = result_dict

    return results
