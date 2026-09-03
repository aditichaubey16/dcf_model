"""Professional PE-style PDF report generator using reportlab.

Structure mirrors a typical deal-team valuation memo: cover, executive
summary, cash flow analysis & key changes, DCF valuation, sensitivity,
scenario analysis (with a bear/base/bull chart), risk/concern flags,
disclaimer — with a branded header/footer and page numbers on every page.
Serif (Times) typeface and a continuous flow (sections separated by rules,
not forced page breaks) for a tighter, print-shop finish. Every figure is
pulled from the same deterministic computations behind the dashboard/Excel
export — nothing here is generated or phrased by a model.
"""
from __future__ import annotations

import io
from datetime import date

from reportlab.lib import colors
from reportlab.lib.pagesizes import letter
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.lib.units import inch
from reportlab.platypus import (
    SimpleDocTemplate, Paragraph, Spacer, Table, TableStyle, PageBreak, HRFlowable,
    KeepTogether,
)
from reportlab.lib.enums import TA_CENTER
from reportlab.graphics.shapes import Drawing, String
from reportlab.graphics.charts.barcharts import VerticalBarChart

SERIF = "Times-Roman"
SERIF_BOLD = "Times-Bold"
SERIF_ITALIC = "Times-Italic"

NAVY = colors.HexColor("#1F2A44")
ACCENT = colors.HexColor("#2A78D6")
AQUA = colors.HexColor("#1BAF7A")
GREY = colors.HexColor("#667085")
ZEBRA = colors.HexColor("#F7F9FC")
RED = colors.HexColor("#C0392B")
AMBER = colors.HexColor("#B8860B")
GREEN_BG = colors.HexColor("#EAF7F0")
BLUE_BG = colors.HexColor("#EAF2FB")
RED_BG = colors.HexColor("#FBEAEA")
RULE_GREY = colors.HexColor("#D0D5DD")

PAGE_W, PAGE_H = letter


def _styles():
    ss = getSampleStyleSheet()
    for name in ("Normal", "Title", "Heading1", "Heading2"):
        ss[name].fontName = SERIF
    ss.add(ParagraphStyle("CoverTitle", fontName=SERIF_BOLD, fontSize=27, leading=32, textColor=colors.white, spaceAfter=8, alignment=TA_CENTER))
    ss.add(ParagraphStyle("CoverSub", fontName=SERIF, fontSize=12, leading=16, textColor=colors.white, alignment=TA_CENTER))
    ss.add(ParagraphStyle("CoverMeta", fontName=SERIF, fontSize=10, leading=15, textColor=colors.HexColor("#C9D6EA"), alignment=TA_CENTER))
    ss.add(ParagraphStyle("Section", fontName=SERIF_BOLD, fontSize=15, leading=19, textColor=NAVY, spaceBefore=2, spaceAfter=6))
    ss.add(ParagraphStyle("SubSection", fontName=SERIF_BOLD, fontSize=11, leading=14, textColor=ACCENT, spaceBefore=6, spaceAfter=4))
    ss.add(ParagraphStyle("Body", fontName=SERIF, fontSize=10, leading=13))
    ss.add(ParagraphStyle("Small", fontName=SERIF, fontSize=8, leading=11, textColor=GREY))
    ss.add(ParagraphStyle("FlagRed", fontName=SERIF, fontSize=9.5, leading=13, textColor=RED))
    ss.add(ParagraphStyle("FlagAmber", fontName=SERIF, fontSize=9.5, leading=13, textColor=AMBER))
    ss.add(ParagraphStyle("FlagInfo", fontName=SERIF, fontSize=9.5, leading=13, textColor=GREY))
    ss.add(ParagraphStyle("HeadlineNum", fontName=SERIF_BOLD, fontSize=18, leading=22, textColor=NAVY))
    ss.add(ParagraphStyle("HeadlineLabel", fontName=SERIF, fontSize=8.5, leading=11, textColor=GREY))
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


def _divider():
    return HRFlowable(width="100%", thickness=0.6, color=RULE_GREY, spaceBefore=10, spaceAfter=10)


def _table(data, col_widths=None, header=True, zebra=True, highlight_last=False, neg_cols=None):
    """neg_cols: column indices whose values should render red when the cell
    text starts with '-' (used for %-change and delta columns)."""
    t = Table(data, colWidths=col_widths, repeatRows=1 if header else 0)
    style = [
        ("FONTNAME", (0, 0), (-1, -1), SERIF),
        ("FONTSIZE", (0, 0), (-1, -1), 8.5),
        ("GRID", (0, 0), (-1, -1), 0.4, RULE_GREY),
        ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
        ("TOPPADDING", (0, 0), (-1, -1), 3.5),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 3.5),
    ]
    body_start = 1 if header else 0
    if header:
        style += [
            ("BACKGROUND", (0, 0), (-1, 0), NAVY),
            ("TEXTCOLOR", (0, 0), (-1, 0), colors.white),
            ("FONTNAME", (0, 0), (-1, 0), SERIF_BOLD),
        ]
    if zebra:
        for i in range(body_start, len(data)):
            if (i - body_start) % 2 == 1:
                style.append(("BACKGROUND", (0, i), (-1, i), ZEBRA))
    if highlight_last:
        style += [
            ("BACKGROUND", (0, -1), (-1, -1), BLUE_BG),
            ("FONTNAME", (0, -1), (-1, -1), SERIF_BOLD),
        ]
    if neg_cols:
        for r in range(body_start, len(data)):
            for c in neg_cols:
                if c < len(data[r]) and isinstance(data[r][c], str) and data[r][c].strip().startswith("-"):
                    style.append(("TEXTCOLOR", (c, r), (c, r), RED))
    t.setStyle(TableStyle(style))
    return t


def _scenario_chart(bear_ev, base_ev, bull_ev):
    d = Drawing(400, 165)
    chart = VerticalBarChart()
    chart.x = 40
    chart.y = 15
    chart.height = 120
    chart.width = 320
    chart.data = [[bear_ev or 0, base_ev or 0, bull_ev or 0]]
    chart.categoryAxis.categoryNames = ["Bear", "Base", "Bull"]
    chart.categoryAxis.labels.fontSize = 9.5
    chart.categoryAxis.labels.fontName = SERIF_BOLD
    chart.valueAxis.valueMin = 0
    chart.valueAxis.labelTextFormat = lambda v: _fmt_num(v)
    chart.valueAxis.labels.fontSize = 7.5
    chart.valueAxis.labels.fontName = SERIF
    chart.barWidth = 10
    chart.groupSpacing = 20
    chart.bars.strokeColor = None
    chart.bars[(0, 0)].fillColor = RED
    chart.bars[(0, 1)].fillColor = ACCENT
    chart.bars[(0, 2)].fillColor = AQUA
    d.add(chart)
    d.add(String(chart.x, chart.y + chart.height + 12, "Enterprise Value by Scenario",
                  fontSize=9.5, fontName=SERIF_BOLD, fillColor=NAVY))
    return d


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
    report_title = f"{company_name} — DCF Valuation Report"

    def _cover_background(canvas, _doc):
        canvas.saveState()
        canvas.setFillColor(NAVY)
        canvas.rect(0, 0, PAGE_W, PAGE_H, fill=1, stroke=0)
        canvas.setFillColor(colors.HexColor("#2A4A7D"))
        canvas.rect(0, PAGE_H - 2.6 * inch, PAGE_W, 2.6 * inch, fill=1, stroke=0)
        canvas.setStrokeColor(ACCENT)
        canvas.setLineWidth(2)
        canvas.line(1 * inch, PAGE_H - 2.8 * inch, PAGE_W - 1 * inch, PAGE_H - 2.8 * inch)
        canvas.restoreState()

    def _header_footer(canvas, doc):
        canvas.saveState()
        # Header
        canvas.setFillColor(NAVY)
        canvas.rect(0, PAGE_H - 0.5 * inch, PAGE_W, 0.5 * inch, fill=1, stroke=0)
        canvas.setFillColor(colors.white)
        canvas.setFont(SERIF_BOLD, 9.5)
        canvas.drawString(0.7 * inch, PAGE_H - 0.33 * inch, company_name)
        canvas.setFont(SERIF, 8.5)
        canvas.setFillColor(colors.HexColor("#C9D6EA"))
        canvas.drawRightString(PAGE_W - 0.7 * inch, PAGE_H - 0.33 * inch, "DCF Valuation Report · Confidential")
        # Footer
        canvas.setStrokeColor(RULE_GREY)
        canvas.setLineWidth(0.5)
        canvas.line(0.7 * inch, 0.55 * inch, PAGE_W - 0.7 * inch, 0.55 * inch)
        canvas.setFont(SERIF, 8)
        canvas.setFillColor(GREY)
        canvas.drawString(0.7 * inch, 0.38 * inch, f"Generated {date.today().strftime('%B %d, %Y')} · Prepared by {analyst}")
        canvas.drawRightString(PAGE_W - 0.7 * inch, 0.38 * inch, f"Page {doc.page}")
        canvas.restoreState()

    doc = SimpleDocTemplate(
        buf, pagesize=letter,
        topMargin=0.75 * inch, bottomMargin=0.6 * inch,
        leftMargin=0.7 * inch, rightMargin=0.7 * inch,
        title=report_title,
    )
    story = []

    # ---------------- Cover ----------------
    story.append(Spacer(1, 1.0 * inch))
    story.append(Paragraph(company_name, ss["CoverTitle"]))
    story.append(Paragraph("Discounted Cash Flow Valuation &amp; Cash Flow Analysis", ss["CoverSub"]))
    story.append(Spacer(1, 0.9 * inch))
    story.append(Paragraph(f"Prepared by {analyst}", ss["CoverMeta"]))
    story.append(Paragraph(date.today().strftime("%B %d, %Y"), ss["CoverMeta"]))
    story.append(Spacer(1, 6))
    story.append(Paragraph("STRICTLY PRIVATE &amp; CONFIDENTIAL", ss["CoverMeta"]))
    story.append(PageBreak())

    # ---------------- Executive Summary ----------------
    story.append(Paragraph("Executive Summary", ss["Section"]))
    ev = dcf.get("enterprise_value")
    eq = dcf.get("equity_value")
    vps = dcf.get("value_per_share")

    headline_cells = [
        [Paragraph("Enterprise Value", ss["HeadlineLabel"]), Paragraph("Equity Value", ss["HeadlineLabel"]),
         Paragraph("WACC", ss["HeadlineLabel"]), Paragraph("Terminal Growth", ss["HeadlineLabel"])],
        [Paragraph(_fmt_num(ev), ss["HeadlineNum"]), Paragraph(_fmt_num(eq), ss["HeadlineNum"]),
         Paragraph(f"{assumptions.get('wacc', 0) * 100:.1f}%", ss["HeadlineNum"]),
         Paragraph(f"{assumptions.get('terminal_growth', 0) * 100:.1f}%", ss["HeadlineNum"])],
    ]
    headline_table = Table(headline_cells, colWidths=[1.6 * inch] * 4)
    headline_table.setStyle(TableStyle([
        ("BACKGROUND", (0, 0), (-1, -1), BLUE_BG),
        ("BOX", (0, 0), (-1, -1), 0.6, colors.HexColor("#C9D6EA")),
        ("INNERGRID", (0, 0), (-1, -1), 0.4, colors.HexColor("#C9D6EA")),
        ("TOPPADDING", (0, 0), (-1, -1), 8),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 8),
        ("ALIGN", (0, 0), (-1, -1), "CENTER"),
    ]))
    story.append(headline_table)
    story.append(Spacer(1, 10))

    summary_txt = (
        f"Based on a discounted cash flow analysis using a {assumptions.get('wacc', 0) * 100:.1f}% WACC and "
        f"{assumptions.get('terminal_growth', 0) * 100:.1f}% terminal growth rate, {company_name} is valued at an "
        f"enterprise value of {_fmt_num(ev)} and an implied equity value of {_fmt_num(eq)}"
        + (f" ({_fmt_num(vps)} per share)." if vps else ".")
    )
    story.append(Paragraph(summary_txt, ss["Body"]))
    story.append(Spacer(1, 4))

    red_flags = [f for f in change_flags if f.get("severity") == "red"]
    amber_flags = [f for f in change_flags if f.get("severity") == "amber"]
    story.append(Paragraph(
        f"The cash flow review identified <b>{len(red_flags)} critical flag(s)</b> and "
        f"<b>{len(amber_flags)} watch-item(s)</b> across {len(periods)} periods of historical data. Key findings "
        "are detailed in the Cash Flow Analysis section below.",
        ss["Body"],
    ))
    story.append(Spacer(1, 8))

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
    story.append(_divider())

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
    story.append(_table(rows, neg_cols=[2, 6]))
    story.append(Spacer(1, 8))

    story.append(Paragraph("Flagged Changes", ss["SubSection"]))
    if not change_flags:
        story.append(Paragraph("No material cash flow divergences flagged by the configured rules.", ss["Body"]))
    for fl in change_flags:
        style = {"red": ss["FlagRed"], "amber": ss["FlagAmber"]}.get(fl.get("severity"), ss["FlagInfo"])
        badge = {"red": "CRITICAL", "amber": "WATCH", "info": "NOTE"}.get(fl.get("severity"), "NOTE")
        story.append(KeepTogether([
            Paragraph(f"<b>[{badge}] {fl.get('title')}</b> ({fl.get('period')})", style),
            Paragraph(fl.get("message", ""), ss["Body"]),
            Spacer(1, 3),
        ]))

    story.append(_divider())

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
    story.append(Spacer(1, 8))

    story.append(Paragraph("Projected Free Cash Flow", ss["SubSection"]))
    proj_rows = [["Year", "Revenue", "Free Cash Flow", "Discount Factor", "Present Value"]]
    for p in dcf.get("projections", []):
        proj_rows.append([
            p.get("year"), _fmt_num(p.get("revenue")), _fmt_num(p.get("free_cash_flow")),
            p.get("discount_factor"), _fmt_num(p.get("present_value")),
        ])
    story.append(_table(proj_rows))
    story.append(Spacer(1, 8))

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
    story.append(_table(valuation_rows, col_widths=[3 * inch, 2.5 * inch], header=False, zebra=False, highlight_last=True))

    if dcf.get("warnings"):
        story.append(Spacer(1, 6))
        for w in dcf["warnings"]:
            story.append(Paragraph(f"⚠ {w}", ss["FlagAmber"]))

    story.append(_divider())

    # ---------------- Sensitivity ----------------
    story.append(Paragraph("Sensitivity Analysis — Enterprise Value", ss["Section"]))
    story.append(Paragraph("WACC (rows) vs. Terminal Growth Rate (columns)", ss["Body"]))
    story.append(Spacer(1, 4))
    sens = dcf.get("sensitivity", {})
    wacc_axis = sens.get("wacc_axis", [])
    g_axis = sens.get("terminal_growth_axis", [])
    ev_grid = sens.get("enterprise_values", [])
    header = ["WACC \\ g"] + [f"{g * 100:.2f}%" for g in g_axis]
    rows = [header]
    base_wacc_idx = None
    for i, w in enumerate(wacc_axis):
        row = [f"{w * 100:.2f}%"]
        for val in (ev_grid[i] if i < len(ev_grid) else []):
            row.append(_fmt_num(val) if val is not None else "n/a")
        rows.append(row)
        if abs(w - assumptions.get("wacc", 0)) < 1e-6:
            base_wacc_idx = i + 1
    sens_table = _table(rows)
    if base_wacc_idx is not None:
        sens_table.setStyle(TableStyle([("BACKGROUND", (0, base_wacc_idx), (-1, base_wacc_idx), BLUE_BG)]))
    story.append(sens_table)
    story.append(_divider())

    # ---------------- Scenario Analysis ----------------
    if scenarios:
        story.append(Paragraph("Scenario Analysis — Bear / Base / Bull", ss["Section"]))
        story.append(Paragraph(
            "Revenue growth and FCF margin are flexed by ±4pts / ±2pts respectively around the base case; "
            "WACC and terminal growth are held constant so the spread isolates operating-case risk.",
            ss["Body"],
        ))
        story.append(Spacer(1, 6))
        bear, base, bull = scenarios.get("bear", {}), scenarios.get("base", {}), scenarios.get("bull", {})

        story.append(_scenario_chart(bear.get("enterprise_value"), base.get("enterprise_value"), bull.get("enterprise_value")))
        story.append(Spacer(1, 8))

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

        scen_table = _table(scen_rows, zebra=False)
        scen_table.setStyle(TableStyle([
            ("BACKGROUND", (1, 0), (1, 0), RED),
            ("BACKGROUND", (2, 0), (2, 0), ACCENT),
            ("BACKGROUND", (3, 0), (3, 0), AQUA),
            ("BACKGROUND", (1, 1), (1, -1), RED_BG),
            ("BACKGROUND", (2, 1), (2, -1), BLUE_BG),
            ("BACKGROUND", (3, 1), (3, -1), GREEN_BG),
        ]))
        story.append(scen_table)
        story.append(_divider())

    # ---------------- Risk / Concern Flags ----------------
    story.append(Paragraph("Risk Flags &amp; Concern Areas", ss["Section"]))
    if not concerns:
        story.append(Paragraph("No concern signals triggered by the configured rules.", ss["Body"]))
    for c in concerns:
        style = ss["FlagRed"] if c.get("severity") == "red" else ss["FlagAmber"]
        badge = "CRITICAL" if c.get("severity") == "red" else "WATCH"
        story.append(KeepTogether([
            Paragraph(f"<b>[{badge}] {c.get('title')}</b> ({c.get('period')})", style),
            Paragraph(c.get("message", ""), ss["Body"]),
            Spacer(1, 3),
        ]))

    story.append(Spacer(1, 10))
    story.append(HRFlowable(width="100%", thickness=0.5, color=RULE_GREY))
    story.append(Spacer(1, 5))
    story.append(Paragraph(
        "This report is generated from a deterministic model over the uploaded financial data for internal "
        "analysis purposes only. It does not constitute investment advice, an offer, or a solicitation. All "
        "figures are estimates based on the stated assumptions and historical data provided; actual results may "
        "differ materially.",
        ss["Small"],
    ))

    def _on_first_page(canvas, doc_):
        _cover_background(canvas, doc_)

    def _on_later_pages(canvas, doc_):
        _header_footer(canvas, doc_)

    doc.build(story, onFirstPage=_on_first_page, onLaterPages=_on_later_pages)
    return buf.getvalue()
