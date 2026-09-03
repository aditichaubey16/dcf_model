"""Deterministic financial ratio engine. No AI/external calls — every number
here is a plain formula over the normalized statement data, computed per
period, so results are always traceable back to a rule.
"""
from __future__ import annotations

from dataclasses import dataclass, asdict

from backend.normalization.mapper import NormalizedData


def _get(statements: dict, statement: str, field: str, period: str) -> float | None:
    return statements.get(statement, {}).get(field, {}).get(period)


def _safe_div(a: float | None, b: float | None) -> float | None:
    if a is None or b is None or b == 0:
        return None
    return a / b


def _round(v: float | None, ndigits: int = 4) -> float | None:
    return None if v is None else round(v, ndigits)


@dataclass
class PeriodMetrics:
    period: str

    revenue: float | None = None
    net_income: float | None = None
    gross_profit: float | None = None
    operating_income: float | None = None

    total_assets: float | None = None
    total_liabilities: float | None = None
    total_equity: float | None = None
    current_assets: float | None = None
    current_liabilities: float | None = None
    cash_and_equivalents: float | None = None

    current_ratio: float | None = None
    quick_ratio: float | None = None
    working_capital: float | None = None

    gross_margin: float | None = None
    operating_margin: float | None = None
    net_margin: float | None = None
    roe: float | None = None
    roa: float | None = None

    debt_to_equity: float | None = None
    debt_to_assets: float | None = None
    interest_coverage: float | None = None

    asset_turnover: float | None = None
    receivables_days: float | None = None
    inventory_days: float | None = None

    revenue_growth: float | None = None
    net_income_growth: float | None = None

    operating_cash_flow: float | None = None
    investing_cash_flow: float | None = None
    financing_cash_flow: float | None = None
    free_cash_flow: float | None = None
    cf_income_mismatch: bool = False

    def to_dict(self):
        return asdict(self)


def compute_metrics(data: NormalizedData) -> list[PeriodMetrics]:
    s = data.statements
    results: list[PeriodMetrics] = []

    for i, period in enumerate(data.periods):
        g = lambda stmt, field: _get(s, stmt, field, period)  # noqa: E731

        revenue = g("income_statement", "revenue")
        cogs = g("income_statement", "cost_of_goods_sold")
        gross_profit = g("income_statement", "gross_profit")
        if gross_profit is None and revenue is not None and cogs is not None:
            gross_profit = revenue - cogs

        operating_income = g("income_statement", "operating_income")
        net_income = g("income_statement", "net_income")
        interest_expense = g("income_statement", "interest_expense")

        cash = g("balance_sheet", "cash_and_equivalents")
        current_assets = g("balance_sheet", "current_assets")
        inventory = g("balance_sheet", "inventory")
        receivables = g("balance_sheet", "accounts_receivable")
        total_assets = g("balance_sheet", "total_assets")
        current_liabilities = g("balance_sheet", "current_liabilities")
        short_term_debt = g("balance_sheet", "short_term_debt")
        long_term_debt = g("balance_sheet", "long_term_debt")
        total_liabilities = g("balance_sheet", "total_liabilities")
        total_equity = g("balance_sheet", "total_equity")

        operating_cf = g("cash_flow", "operating_cash_flow")
        investing_cf = g("cash_flow", "investing_cash_flow")
        financing_cf = g("cash_flow", "financing_cash_flow")
        capex = g("cash_flow", "capital_expenditure")
        free_cf = g("cash_flow", "free_cash_flow")
        if free_cf is None and operating_cf is not None and capex is not None:
            free_cf = operating_cf - abs(capex)

        total_debt = None
        if short_term_debt is not None or long_term_debt is not None:
            total_debt = (short_term_debt or 0) + (long_term_debt or 0)

        current_ratio = _safe_div(current_assets, current_liabilities)
        quick_assets = None
        if current_assets is not None:
            quick_assets = current_assets - (inventory or 0)
        quick_ratio = _safe_div(quick_assets, current_liabilities)
        working_capital = (
            current_assets - current_liabilities
            if current_assets is not None and current_liabilities is not None
            else None
        )

        gross_margin = _safe_div(gross_profit, revenue)
        operating_margin = _safe_div(operating_income, revenue)
        net_margin = _safe_div(net_income, revenue)
        roe = _safe_div(net_income, total_equity)
        roa = _safe_div(net_income, total_assets)

        debt_to_equity = _safe_div(total_debt if total_debt is not None else total_liabilities, total_equity)
        debt_to_assets = _safe_div(total_debt if total_debt is not None else total_liabilities, total_assets)
        interest_coverage = _safe_div(operating_income, interest_expense)

        asset_turnover = _safe_div(revenue, total_assets)
        receivables_days = _safe_div(receivables, revenue)
        if receivables_days is not None:
            receivables_days *= 365
        inventory_days = _safe_div(inventory, cogs)
        if inventory_days is not None:
            inventory_days *= 365

        revenue_growth = None
        net_income_growth = None
        if i > 0:
            prev = results[i - 1]
            if prev.revenue not in (None, 0) and revenue is not None:
                revenue_growth = (revenue - prev.revenue) / abs(prev.revenue) * 100
            if prev.net_income not in (None, 0) and net_income is not None:
                net_income_growth = (net_income - prev.net_income) / abs(prev.net_income) * 100

        cf_mismatch = bool(
            net_income is not None and operating_cf is not None and net_income > 0 and operating_cf < 0
        )

        results.append(
            PeriodMetrics(
                period=period,
                revenue=_round(revenue, 2),
                net_income=_round(net_income, 2),
                gross_profit=_round(gross_profit, 2),
                operating_income=_round(operating_income, 2),
                total_assets=_round(total_assets, 2),
                total_liabilities=_round(total_liabilities, 2),
                total_equity=_round(total_equity, 2),
                current_assets=_round(current_assets, 2),
                current_liabilities=_round(current_liabilities, 2),
                cash_and_equivalents=_round(cash, 2),
                current_ratio=_round(current_ratio),
                quick_ratio=_round(quick_ratio),
                working_capital=_round(working_capital, 2),
                gross_margin=_round(gross_margin),
                operating_margin=_round(operating_margin),
                net_margin=_round(net_margin),
                roe=_round(roe),
                roa=_round(roa),
                debt_to_equity=_round(debt_to_equity),
                debt_to_assets=_round(debt_to_assets),
                interest_coverage=_round(interest_coverage),
                asset_turnover=_round(asset_turnover),
                receivables_days=_round(receivables_days, 1),
                inventory_days=_round(inventory_days, 1),
                revenue_growth=_round(revenue_growth, 2),
                net_income_growth=_round(net_income_growth, 2),
                operating_cash_flow=_round(operating_cf, 2),
                investing_cash_flow=_round(investing_cf, 2),
                financing_cash_flow=_round(financing_cf, 2),
                free_cash_flow=_round(free_cf, 2),
                cf_income_mismatch=cf_mismatch,
            )
        )

    return results
