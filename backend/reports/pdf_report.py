"""Professional PE-style PDF report generator using reportlab.

Structure mirrors a typical deal-team valuation memo: cover, executive
summary, cash flow analysis & key changes, DCF valuation, sensitivity,
risk/concern flags, disclaimer. Every figure is pulled from the same
deterministic computations behind the dashboard/Excel export — nothing here
is generated or phrased by a model.
"""
from __future__ import annotations

import io
from datetime import date

from reportlab.lib import colors
from reportlab.lib.pagesizes import letter
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.lib.units import inch
from reportlab.platypus import (
    SimpleDocTemplate, Paragraph, Spacer, Table, TableStyle, PageBreak, HRFlowable
)
from reportlab.lib.enums import TA_CENTER

NAVY = colors.HexColor("#1F2A44")
ACCENT = colors.HexColor("#2A78D6")
GREY = colors.HexColor("#667085")
LIGHT_GREY = colors.HexColor("#F2F4F7")
RED = colors.HexColor("#C0392B")
AMBER = colors.HexColor("#B8860B")


def _styles():
    ss = getSampleStyleSheet()
    ss.add(ParagraphStyle("CoverTitle", parent=ss["Title"], fontSize=26, textColor=NAVY, spaceAfter=6))
    ss.add(ParagraphStyle("CoverSub", parent=ss["Normal"], fontSize=12, textColor=GREY, alignment=TA_CENTER))
    ss.add(ParagraphStyle("Section", parent=ss["Heading1"], fontSize=15, textColor=NAVY, spaceBefore=18, spaceAfter=8))
    ss.add(ParagraphStyle("SubSection", parent=ss["Heading2"], fontSize=12, textColor=ACCENT, spaceBefore=10, spaceAfter=6))
    ss.add(ParagraphStyle("Body", parent=ss["Normal"], fontSize=10, leading=14))
    ss.add(ParagraphStyle("Small", parent=ss["Normal"], fontSize=8, textColor=GREY))
    ss.add(ParagraphStyle("FlagRed", parent=ss["Normal"], fontSize=10, textColor=RED, leading=14))
    ss.add(ParagraphStyle("FlagAmber", parent=ss["Normal"], fontSize=10, textColor=AMBER, leading=14))
    ss.add(ParagraphStyle("FlagInfo", parent=ss["Normal"], fontSize=10, textColor=GREY, leading=14))
    return ss


def _fmt_num(v, pct=False):
    if v is None:
        return "—"
    if pct:
        return f"{v * 100:.1f}%" if abs(v) <= 3 else f"{v:.1f}%"
    if isinstance(v, (int, float)):
        abs_v = abs(v)
        if abs_v >= 1e9:
            return f"{v / 1e9:.2f}B"
        if abs_v >= 1e6:
            return f"{v / 1e6:.2f}M"
        if abs_v >= 1e3:
            return f"{v / 1e3:.1f}K"
        return f"{v:,.2f}"
    return str(v)


def _table(data, col_widths=None, header=True):
    t = Table(data, colWidths=col_widths, repeatRows=1 if header else 0)
    style = [
        ("FONTSIZE", (0, 0), (-1, -1), 8.5),
        ("GRID", (0, 0), (-1, -1), 0.4, colors.HexColor("#D0D5DD")),
        ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
        ("TOPPADDING", (0, 0), (-1, -1), 4),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 4),
    ]
    if header:
        style += [
            ("BACKGROUND", (0, 0), (-1, 0), NAVY),
            ("TEXTCOLOR", (0, 0), (-1, 0), colors.white),
            ("FONTNAME", (0, 0), (-1, 0), "Helvetica-Bold"),
        ]
    t.setStyle(TableStyle(style))
    return t


def build_pdf_report(
    *,
    company_name: str,
    analyst: str,
    periods: list[str],
    metrics: list[dict],
    changes: list[dict],
    change_flags: list[dict],
    concerns: list[dict],
    dcf: dict,
    assumptions: dict,
    scenarios: dict | None = None,
) -> bytes:
    ss = _styles()
    buf = io.BytesIO()
    doc = SimpleDocTemplate(
        buf, pagesize=letter,
        topMargin=0.75 * inch, bottomMargin=0.75 * inch,
        leftMargin=0.75 * inch, rightMargin=0.75 * inch,
        title=f"{company_name} — DCF Valuation Report",
    )
    story = []

    # ---------------- Cover ----------------
    story.append(Spacer(1, 1.6 * inch))
    story.append(Paragraph(company_name, ss["CoverTitle"]))
    story.append(Paragraph("Discounted Cash Flow Valuation &amp; Cash Flow Analysis", ss["CoverSub"]))
    story.append(Spacer(1, 0.4 * inch))
    story.append(HRFlowable(width="60%", thickness=1, color=ACCENT, hAlign="CENTER"))
    story.append(Spacer(1, 0.3 * inch))
    story.append(Paragraph(f"Prepared by: {analyst}", ss["CoverSub"]))
    story.append(Paragraph(f"Date: {date.today().strftime('%B %d, %Y')}", ss["CoverSub"]))
    story.append(Paragraph("Strictly Private &amp; Confidential", ss["CoverSub"]))
    story.append(PageBreak())

    # ---------------- Executive Summary ----------------
    story.append(Paragraph("Executive Summary", ss["Section"]))
    ev = dcf.get("enterprise_value")
    eq = dcf.get("equity_value")
    vps = dcf.get("value_per_share")
    summary_txt = (
        f"Based on a discounted cash flow analysis using a {assumptions.get('wacc', 0) * 100:.1f}% WACC and "
        f"{assumptions.get('terminal_growth', 0) * 100:.1f}% terminal growth rate, {company_name} is valued at an "
        f"enterprise value of {_fmt_num(ev)} and an implied equity value of {_fmt_num(eq)}"
        + (f" ({_fmt_num(vps)} per share)." if vps else ".")
    )
    story.append(Paragraph(summary_txt, ss["Body"]))
    story.append(Spacer(1, 8))

    red_flags = [f for f in change_flags if f.get("severity") == "red"]
    amber_flags = [f for f in change_flags if f.get("severity") == "amber"]
    story.append(Paragraph(
        f"The cash flow review identified {len(red_flags)} critical flag(s) and {len(amber_flags)} watch-item(s) "
        f"across {len(periods)} periods of historical data. Key findings are detailed in the Cash Flow Analysis "
        "section below.",
        ss["Body"],
    ))

    # ---------------- Key Metrics Snapshot ----------------
    story.append(Paragraph("Key Financial Metrics", ss["SubSection"]))
    header = ["Period", "Revenue", "Net Income", "Op. CF", "Free CF", "Net Margin", "ROE"]
    rows = [header]
    for m in metrics:
        rows.append([
            m.get("period"),
            _fmt_num(m.get("revenue")),
            _fmt_num(m.get("net_income")),
            _fmt_num(m.get("operating_cash_flow")),
            _fmt_num(m.get("free_cash_flow")),
            _fmt_num(m.get("net_margin"), pct=True),
            _fmt_num(m.get("roe"), pct=True),
        ])
    story.append(_table(rows))
    story.append(PageBreak())

    # ---------------- Cash Flow Change Analysis ----------------
    story.append(Paragraph("Cash Flow Analysis — Period-over-Period Changes", ss["Section"]))
    header = ["Period", "Op. CF", "Op. CF %chg", "Inv. CF", "Fin. CF", "Free CF", "FCF %chg", "OCF/NI"]
    rows = [header]
    for c in changes:
        rows.append([
            c.get("period"),
            _fmt_num(c.get("operating_cf")),
            f"{c.get('operating_cf_change_pct')}%" if c.get("operating_cf_change_pct") is not None else "—",
            _fmt_num(c.get("investing_cf")),
            _fmt_num(c.get("financing_cf")),
            _fmt_num(c.get("free_cash_flow")),
            f"{c.get('free_cash_flow_change_pct')}%" if c.get("free_cash_flow_change_pct") is not None else "—",
            f"{c.get('ocf_to_ni')}x" if c.get("ocf_to_ni") is not None else "—",
        ])
    story.append(_table(rows))
    story.append(Spacer(1, 12))

    story.append(Paragraph("Flagged Changes", ss["SubSection"]))
    if not change_flags:
        story.append(Paragraph("No material cash flow divergences flagged by the configured rules.", ss["Body"]))
    for fl in change_flags:
        style = {"red": ss["FlagRed"], "amber": ss["FlagAmber"]}.get(fl.get("severity"), ss["FlagInfo"])
        badge = {"red": "CRITICAL", "amber": "WATCH", "info": "NOTE"}.get(fl.get("severity"), "NOTE")
        story.append(Paragraph(f"<b>[{badge}] {fl.get('title')}</b> ({fl.get('period')})", style))
        story.append(Paragraph(fl.get("message", ""), ss["Body"]))
        story.append(Spacer(1, 4))

    story.append(PageBreak())

    # ---------------- DCF Valuation ----------------
    story.append(Paragraph("DCF Valuation", ss["Section"]))
    assum_rows = [
        ["Assumption", "Value"],
        ["Projection Years", assumptions.get("projection_years")],
        ["Revenue Growth Rate", f"{assumptions.get('revenue_growth_rate', 0) * 100:.1f}%"],
        ["Assumed FCF Margin", f"{dcf.get('assumed_fcf_margin', 0) * 100:.1f}%"],
        ["Historical Avg FCF Margin", _fmt_num(dcf.get("historical_fcf_margin"), pct=True) if dcf.get("historical_fcf_margin") is not None else "—"],
        ["WACC", f"{assumptions.get('wacc', 0) * 100:.1f}%"],
        ["Terminal Growth Rate", f"{assumptions.get('terminal_growth', 0) * 100:.1f}%"],
        ["Net Debt", _fmt_num(assumptions.get("net_debt"))],
    ]
    story.append(_table(assum_rows, col_widths=[2.5 * inch, 2.5 * inch]))
    story.append(Spacer(1, 12))

    story.append(Paragraph("Projected Free Cash Flow", ss["SubSection"]))
    proj_rows = [["Year", "Revenue", "Free Cash Flow", "Discount Factor", "Present Value"]]
    for p in dcf.get("projections", []):
        proj_rows.append([
            p.get("year"), _fmt_num(p.get("revenue")), _fmt_num(p.get("free_cash_flow")),
            p.get("discount_factor"), _fmt_num(p.get("present_value")),
        ])
    story.append(_table(proj_rows))
    story.append(Spacer(1, 12))

    valuation_rows = [
        ["Sum of PV of FCF", _fmt_num(dcf.get("sum_pv_fcf"))],
        ["Terminal Value", _fmt_num(dcf.get("terminal_value"))],
        ["PV of Terminal Value", _fmt_num(dcf.get("pv_terminal_value"))],
        ["Enterprise Value", _fmt_num(dcf.get("enterprise_value"))],
        ["Less: Net Debt", _fmt_num(assumptions.get("net_debt"))],
        ["Equity Value", _fmt_num(dcf.get("equity_value"))],
    ]
    if dcf.get("value_per_share") is not None:
        valuation_rows.append(["Value per Share", _fmt_num(dcf.get("value_per_share"))])
    story.append(_table(valuation_rows, col_widths=[3 * inch, 2.5 * inch], header=False))

    if dcf.get("warnings"):
        story.append(Spacer(1, 10))
        for w in dcf["warnings"]:
            story.append(Paragraph(f"⚠ {w}", ss["FlagAmber"]))

    story.append(PageBreak())

    # ---------------- Sensitivity ----------------
    story.append(Paragraph("Sensitivity Analysis — Enterprise Value", ss["Section"]))
    story.append(Paragraph("WACC (rows) vs. Terminal Growth Rate (columns)", ss["Body"]))
    sens = dcf.get("sensitivity", {})
    wacc_axis = sens.get("wacc_axis", [])
    g_axis = sens.get("terminal_growth_axis", [])
    ev_grid = sens.get("enterprise_values", [])
    header = ["WACC \\ g"] + [f"{g * 100:.2f}%" for g in g_axis]
    rows = [header]
    for i, w in enumerate(wacc_axis):
        row = [f"{w * 100:.2f}%"]
        for val in (ev_grid[i] if i < len(ev_grid) else []):
            row.append(_fmt_num(val) if val is not None else "n/a")
        rows.append(row)
    story.append(_table(rows))
    story.append(PageBreak())

    # ---------------- Scenario Analysis ----------------
    if scenarios:
        story.append(Paragraph("Scenario Analysis — Bear / Base / Bull", ss["Section"]))
        story.append(Paragraph(
            "Revenue growth and FCF margin are flexed by ±4pts / ±2pts respectively around the base case; "
            "WACC and terminal growth are held constant so the spread isolates operating-case risk.",
            ss["Body"],
        ))
        story.append(Spacer(1, 8))
        bear, base, bull = scenarios.get("bear", {}), scenarios.get("base", {}), scenarios.get("bull", {})
        scen_rows = [
            ["Metric", "Bear", "Base", "Bull"],
            ["Revenue Growth Rate",
             f"{bear.get('revenue_growth_rate', 0) * 100:.1f}%",
             f"{base.get('revenue_growth_rate', 0) * 100:.1f}%",
             f"{bull.get('revenue_growth_rate', 0) * 100:.1f}%"],
            ["Assumed FCF Margin",
             f"{bear.get('assumed_fcf_margin', 0) * 100:.1f}%",
             f"{base.get('assumed_fcf_margin', 0) * 100:.1f}%",
             f"{bull.get('assumed_fcf_margin', 0) * 100:.1f}%"],
            ["Enterprise Value", _fmt_num(bear.get("enterprise_value")), _fmt_num(base.get("enterprise_value")), _fmt_num(bull.get("enterprise_value"))],
            ["Equity Value", _fmt_num(bear.get("equity_value")), _fmt_num(base.get("equity_value")), _fmt_num(bull.get("equity_value"))],
        ]
        if base.get("value_per_share") is not None:
            scen_rows.append(["Value per Share", _fmt_num(bear.get("value_per_share")), _fmt_num(base.get("value_per_share")), _fmt_num(bull.get("value_per_share"))])
        story.append(_table(scen_rows))
        story.append(PageBreak())

    # ---------------- Risk / Concern Flags ----------------
    story.append(Paragraph("Risk Flags &amp; Concern Areas", ss["Section"]))
    if not concerns:
        story.append(Paragraph("No concern signals triggered by the configured rules.", ss["Body"]))
    for c in concerns:
        style = ss["FlagRed"] if c.get("severity") == "red" else ss["FlagAmber"]
        badge = "CRITICAL" if c.get("severity") == "red" else "WATCH"
        story.append(Paragraph(f"<b>[{badge}] {c.get('title')}</b> ({c.get('period')})", style))
        story.append(Paragraph(c.get("message", ""), ss["Body"]))
        story.append(Spacer(1, 4))

    story.append(Spacer(1, 20))
    story.append(HRFlowable(width="100%", thickness=0.5, color=colors.HexColor("#D0D5DD")))
    story.append(Spacer(1, 6))
    story.append(Paragraph(
        "This report is generated from a deterministic model over the uploaded financial data for internal "
        "analysis purposes only. It does not constitute investment advice, an offer, or a solicitation. All "
        "figures are estimates based on the stated assumptions and historical data provided; actual results may "
        "differ materially.",
        ss["Small"],
    ))

    doc.build(story)
    return buf.getvalue()
