"""Generates data/dummy/dummy_financials.xlsx — a 5-year illustrative
target-company dataset with deliberate cash flow dynamics (a capex-heavy
year, a working-capital-driven FCF dip, then recovery) so the demo has
something real to flag and discuss.
"""
from pathlib import Path

import pandas as pd

OUT = Path(__file__).resolve().parent.parent / "data" / "dummy" / "dummy_financials.xlsx"

YEARS = ["FY2021", "FY2022", "FY2023", "FY2024", "FY2025"]

income_statement = {
    "Revenue":                         [420_000_000, 468_000_000, 512_000_000, 549_000_000, 601_000_000],
    "Cost of Goods Sold":              [252_000_000, 285_000_000, 322_000_000, 340_000_000, 366_000_000],
    "Operating Expenses":              [92_000_000, 101_000_000, 112_000_000, 121_000_000, 129_000_000],
    "Operating Income":                [76_000_000, 82_000_000, 78_000_000, 88_000_000, 106_000_000],
    "Interest Expense":                [8_500_000, 9_200_000, 11_800_000, 10_400_000, 9_600_000],
    "Depreciation and Amortization":   [14_000_000, 15_500_000, 18_200_000, 17_000_000, 17_800_000],
    "Net Income":                      [50_000_000, 54_500_000, 46_000_000, 58_500_000, 73_500_000],
}

balance_sheet = {
    "Cash and Cash Equivalents":       [38_000_000, 41_000_000, 29_000_000, 35_000_000, 52_000_000],
    "Total Current Assets":            [145_000_000, 162_000_000, 188_000_000, 196_000_000, 210_000_000],
    "Inventory":                       [48_000_000, 55_000_000, 71_000_000, 68_000_000, 66_000_000],
    "Trade Receivables":               [42_000_000, 48_000_000, 64_000_000, 60_000_000, 58_000_000],
    "Total Assets":                    [390_000_000, 425_000_000, 468_000_000, 495_000_000, 535_000_000],
    "Total Current Liabilities":       [98_000_000, 108_000_000, 129_000_000, 122_000_000, 118_000_000],
    "Trade Payables":                  [36_000_000, 40_000_000, 47_000_000, 44_000_000, 43_000_000],
    "Short-term Debt":                 [15_000_000, 18_000_000, 26_000_000, 20_000_000, 16_000_000],
    "Long-term Debt":                  [92_000_000, 98_000_000, 118_000_000, 108_000_000, 96_000_000],
    "Total Liabilities":               [205_000_000, 224_000_000, 273_000_000, 250_000_000, 234_000_000],
    "Total Equity":                    [185_000_000, 201_000_000, 195_000_000, 245_000_000, 301_000_000],
}

cash_flow = {
    "Net Cash from Operating Activities": [68_000_000, 74_000_000, 35_000_000, 79_000_000, 98_000_000],
    "Net Cash from Investing Activities": [-22_000_000, -26_000_000, -58_000_000, -31_000_000, -29_000_000],
    "Net Cash from Financing Activities": [-31_000_000, -35_000_000, 15_000_000, -42_000_000, -52_000_000],
    "Capital Expenditure":                [-20_000_000, -24_000_000, -55_000_000, -29_000_000, -27_000_000],
}


def _sheet(d: dict) -> pd.DataFrame:
    df = pd.DataFrame(d).T
    df.columns = YEARS
    df.insert(0, "Line Item", df.index)
    df = df.reset_index(drop=True)
    return df


def main():
    OUT.parent.mkdir(parents=True, exist_ok=True)
    with pd.ExcelWriter(OUT, engine="openpyxl") as writer:
        _sheet(income_statement).to_excel(writer, sheet_name="Income Statement", index=False)
        _sheet(balance_sheet).to_excel(writer, sheet_name="Balance Sheet", index=False)
        _sheet(cash_flow).to_excel(writer, sheet_name="Cash Flow", index=False)
    print(f"Wrote {OUT}")


if __name__ == "__main__":
    main()
