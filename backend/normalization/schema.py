"""Canonical financial schema — the fixed set of fields every parsed
statement gets mapped onto, regardless of source format or original wording.
"""

INCOME_STATEMENT_FIELDS = [
    "revenue",
    "cost_of_goods_sold",
    "gross_profit",
    "operating_expenses",
    "operating_income",
    "interest_expense",
    "depreciation_amortization",
    "net_income",
]

BALANCE_SHEET_FIELDS = [
    "cash_and_equivalents",
    "current_assets",
    "inventory",
    "accounts_receivable",
    "total_assets",
    "current_liabilities",
    "accounts_payable",
    "short_term_debt",
    "long_term_debt",
    "total_liabilities",
    "total_equity",
]

CASH_FLOW_FIELDS = [
    "operating_cash_flow",
    "investing_cash_flow",
    "financing_cash_flow",
    "capital_expenditure",
    "free_cash_flow",
]

ALL_STATEMENTS = {
    "income_statement": INCOME_STATEMENT_FIELDS,
    "balance_sheet": BALANCE_SHEET_FIELDS,
    "cash_flow": CASH_FLOW_FIELDS,
}
