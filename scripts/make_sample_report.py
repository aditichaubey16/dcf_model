"""Pre-generates a sample Excel model + PDF report from the dummy dataset
and drops them under frontend/static/sample/ so the home page can offer an
instant "view a sample report" link that's a plain static file — no API
call, no dependency on the analysis pipeline being warm.
"""
import sys
from dataclasses import asdict
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from backend.main import _run_pipeline
from backend.analysis.dcf import run_dcf, run_scenarios, DCFAssumptions
from backend.analysis.ratios import PeriodMetrics
from backend.analysis.cashflow_changes import compute_cashflow_changes, flag_cashflow_changes
from backend.reports.excel_report import build_excel_report
from backend.reports.pdf_report import build_pdf_report

DUMMY_FILE = ROOT / "data" / "dummy" / "dummy_financials.xlsx"
OUT_DIR = ROOT / "frontend" / "static" / "sample"


def main():
    content = DUMMY_FILE.read_bytes()
    result = _run_pipeline(DUMMY_FILE.name, content)

    metrics = [PeriodMetrics(**{k: v for k, v in d.items() if k in PeriodMetrics.__dataclass_fields__}) for d in result["metrics"]]
    assumptions = DCFAssumptions()
    dcf = run_dcf(metrics, assumptions).to_dict()
    scenarios = run_scenarios(metrics, assumptions)
    changes = [c.to_dict() for c in compute_cashflow_changes(metrics)]
    change_flags = [asdict(f) for f in flag_cashflow_changes(compute_cashflow_changes(metrics))]

    xlsx_bytes = build_excel_report(
        company_name="Sample Target Co.",
        periods=result["periods"],
        metrics=result["metrics"],
        changes=changes,
        change_flags=change_flags,
        concerns=result["concerns"],
        dcf=dcf,
        assumptions=asdict(assumptions),
        scenarios=scenarios,
    )
    pdf_bytes = build_pdf_report(
        company_name="Sample Target Co.",
        analyst="Analyst",
        periods=result["periods"],
        metrics=result["metrics"],
        changes=changes,
        change_flags=change_flags,
        concerns=result["concerns"],
        dcf=dcf,
        assumptions=asdict(assumptions),
        scenarios=scenarios,
    )

    OUT_DIR.mkdir(parents=True, exist_ok=True)
    (OUT_DIR / "sample_dcf_report.xlsx").write_bytes(xlsx_bytes)
    (OUT_DIR / "sample_dcf_report.pdf").write_bytes(pdf_bytes)
    print(f"Wrote {OUT_DIR / 'sample_dcf_report.xlsx'} ({len(xlsx_bytes)} bytes)")
    print(f"Wrote {OUT_DIR / 'sample_dcf_report.pdf'} ({len(pdf_bytes)} bytes)")


if __name__ == "__main__":
    main()
