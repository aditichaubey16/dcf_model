"""PE DCF Analyzer — local DCF + cash flow analysis tool. A client uploads
their financials (or loads the bundled dummy dataset) and gets a dashboard,
a DCF valuation, and a professional Excel/PDF report — all computed
locally, nothing external. No login: every upload is processed statelessly
and saved under data/local/ for reference.
"""
from __future__ import annotations

from dataclasses import asdict
from pathlib import Path

from fastapi import FastAPI, UploadFile, File, HTTPException
from fastapi.concurrency import run_in_threadpool
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import Response
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel

from backend.parsers.tabular import parse_excel, parse_csv, RawTable
from backend.parsers.pdf_parser import parse_pdf
from backend.parsers.sql_parser import parse_sql
from backend.normalization.mapper import normalize_tables, AliasIndex
from backend.analysis.ratios import compute_metrics, PeriodMetrics
from backend.analysis.concerns import evaluate_concerns, load_rules
from backend.analysis.dcf import run_dcf, run_scenarios, DCFAssumptions
from backend.analysis.cashflow_changes import compute_cashflow_changes, flag_cashflow_changes
from backend.reports.excel_report import build_excel_report
from backend.reports.pdf_report import build_pdf_report

BASE_DIR = Path(__file__).resolve().parent.parent
FRONTEND_DIR = BASE_DIR / "frontend" / "static"
DUMMY_FILE = BASE_DIR / "data" / "dummy" / "dummy_financials.xlsx"
LOCAL_DIR = BASE_DIR / "data" / "local"
LOCAL_DIR.mkdir(parents=True, exist_ok=True)

app = FastAPI(title="PE DCF Analyzer")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://127.0.0.1:8030", "http://localhost:8030"],
    allow_methods=["*"],
    allow_headers=["*"],
)

_alias_index = AliasIndex.load()
_rules = load_rules()


class DCFBody(BaseModel):
    metrics: list[dict]
    projection_years: int = 5
    revenue_growth_rate: float = 0.08
    fcf_margin: float | None = None
    wacc: float = 0.10
    terminal_growth: float = 0.025
    net_debt: float = 0.0
    shares_outstanding: float | None = None


class ReportBody(DCFBody):
    company_name: str = "Target Company"
    filename: str = "analysis"
    periods: list[str]
    concerns: list[dict] = []


# ---------------- Analysis pipeline ----------------

def _parse_by_extension(filename: str, content: bytes) -> list[RawTable]:
    suffix = Path(filename).suffix.lower()
    if suffix in (".xlsx", ".xls"):
        return parse_excel(content)
    if suffix == ".csv":
        return parse_csv(content)
    if suffix == ".pdf":
        return parse_pdf(content)
    if suffix in (".sql", ".db", ".sqlite", ".sqlite3"):
        return parse_sql(content, filename)
    raise HTTPException(status_code=400, detail=f"Unsupported file type: {suffix}")


def _run_pipeline(filename: str, content: bytes) -> dict:
    if not content:
        raise HTTPException(status_code=400, detail="Uploaded file is empty.")

    try:
        raw_tables = _parse_by_extension(filename, content)
    except HTTPException:
        raise
    except Exception as exc:
        raise HTTPException(status_code=422, detail=f"Could not parse file: {exc}") from exc

    if not raw_tables or not any(t.rows for t in raw_tables):
        raise HTTPException(
            status_code=422,
            detail="No usable tabular data found in the file. Expect a label column plus period columns.",
        )

    normalized = normalize_tables(raw_tables, _alias_index)
    if not normalized.periods:
        raise HTTPException(status_code=422, detail="Could not detect any time periods (columns) in the file.")

    metrics = compute_metrics(normalized)
    concerns = evaluate_concerns(metrics, _rules)
    changes = compute_cashflow_changes(metrics)
    change_flags = flag_cashflow_changes(changes)

    return {
        "filename": filename,
        "periods": normalized.periods,
        "metrics": [m.to_dict() for m in metrics],
        "concerns": [asdict(c) for c in concerns],
        "changes": [c.to_dict() for c in changes],
        "change_flags": [asdict(f) for f in change_flags],
        "unmapped": [asdict(u) for u in normalized.unmapped],
        "needs_review": [asdict(u) for u in normalized.needs_review],
        "sheets_found": [t.sheet_name for t in raw_tables],
    }


@app.post("/api/analyze")
async def analyze(file: UploadFile = File(...)):
    content = await file.read()
    (LOCAL_DIR / file.filename).write_bytes(content)
    result = await run_in_threadpool(_run_pipeline, file.filename, content)
    return result


@app.post("/api/analyze-dummy")
async def analyze_dummy():
    content = DUMMY_FILE.read_bytes()
    result = await run_in_threadpool(_run_pipeline, DUMMY_FILE.name, content)
    result["filename"] = "dummy_financials.xlsx (sample data)"
    return result


# ---------------- DCF ----------------

def _metrics_from_dicts(raw: list[dict]) -> list[PeriodMetrics]:
    return [PeriodMetrics(**{k: v for k, v in d.items() if k in PeriodMetrics.__dataclass_fields__}) for d in raw]


@app.post("/api/dcf")
async def dcf_endpoint(body: DCFBody):
    metrics = _metrics_from_dicts(body.metrics)
    assumptions = DCFAssumptions(
        projection_years=body.projection_years,
        revenue_growth_rate=body.revenue_growth_rate,
        fcf_margin=body.fcf_margin,
        wacc=body.wacc,
        terminal_growth=body.terminal_growth,
        net_debt=body.net_debt,
        shares_outstanding=body.shares_outstanding,
    )
    result = run_dcf(metrics, assumptions)
    return result.to_dict()


@app.post("/api/dcf/scenarios")
async def dcf_scenarios_endpoint(body: DCFBody):
    metrics = _metrics_from_dicts(body.metrics)
    assumptions = DCFAssumptions(
        projection_years=body.projection_years,
        revenue_growth_rate=body.revenue_growth_rate,
        fcf_margin=body.fcf_margin,
        wacc=body.wacc,
        terminal_growth=body.terminal_growth,
        net_debt=body.net_debt,
        shares_outstanding=body.shares_outstanding,
    )
    return run_scenarios(metrics, assumptions)


# ---------------- Reports ----------------

@app.post("/api/report/excel")
async def report_excel(body: ReportBody):
    metrics = _metrics_from_dicts(body.metrics)
    assumptions = DCFAssumptions(
        projection_years=body.projection_years,
        revenue_growth_rate=body.revenue_growth_rate,
        fcf_margin=body.fcf_margin,
        wacc=body.wacc,
        terminal_growth=body.terminal_growth,
        net_debt=body.net_debt,
        shares_outstanding=body.shares_outstanding,
    )
    dcf = run_dcf(metrics, assumptions).to_dict()
    scenarios = run_scenarios(metrics, assumptions)
    changes = [c.to_dict() for c in compute_cashflow_changes(metrics)]
    change_flags = [asdict(f) for f in flag_cashflow_changes(compute_cashflow_changes(metrics))]

    xlsx_bytes = build_excel_report(
        company_name=body.company_name,
        periods=body.periods,
        metrics=body.metrics,
        changes=changes,
        change_flags=change_flags,
        concerns=body.concerns,
        dcf=dcf,
        assumptions=asdict(assumptions),
        scenarios=scenarios,
    )
    (LOCAL_DIR / f"{body.filename}_dcf_report.xlsx").write_bytes(xlsx_bytes)
    return Response(
        content=xlsx_bytes,
        media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        headers={"Content-Disposition": f'attachment; filename="{body.filename}_dcf_report.xlsx"'},
    )


@app.post("/api/report/pdf")
async def report_pdf(body: ReportBody):
    metrics = _metrics_from_dicts(body.metrics)
    assumptions = DCFAssumptions(
        projection_years=body.projection_years,
        revenue_growth_rate=body.revenue_growth_rate,
        fcf_margin=body.fcf_margin,
        wacc=body.wacc,
        terminal_growth=body.terminal_growth,
        net_debt=body.net_debt,
        shares_outstanding=body.shares_outstanding,
    )
    dcf = run_dcf(metrics, assumptions).to_dict()
    scenarios = run_scenarios(metrics, assumptions)
    changes = [c.to_dict() for c in compute_cashflow_changes(metrics)]
    change_flags = [asdict(f) for f in flag_cashflow_changes(compute_cashflow_changes(metrics))]

    pdf_bytes = build_pdf_report(
        company_name=body.company_name,
        analyst="Analyst",
        periods=body.periods,
        metrics=body.metrics,
        changes=changes,
        change_flags=change_flags,
        concerns=body.concerns,
        dcf=dcf,
        assumptions=asdict(assumptions),
        scenarios=scenarios,
    )
    (LOCAL_DIR / f"{body.filename}_dcf_report.pdf").write_bytes(pdf_bytes)
    return Response(
        content=pdf_bytes,
        media_type="application/pdf",
        headers={"Content-Disposition": f'attachment; filename="{body.filename}_dcf_report.pdf"'},
    )


@app.get("/api/health")
async def health():
    return {"status": "ok"}


app.mount("/", StaticFiles(directory=str(FRONTEND_DIR), html=True), name="static")
