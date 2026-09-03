# PE DCF Analyzer

Local, offline DCF valuation and cash flow analysis tool. Upload a
company's financials (Excel, CSV, or PDF) — or use the bundled sample data
— and get:

- A financial dashboard (KPIs, trend charts, ratio-based concern flags)
- **Cash flow change analysis**: period-over-period deltas across
  operating/investing/financing/free cash flow, FCF conversion (OCF/NI),
  and flags for things a PE analyst checks for (weak earnings-to-cash
  conversion, FCF lagging revenue growth, cash sustained by financing
  rather than operations, sharp FCF declines)
- A **DCF valuation** with adjustable assumptions (growth rate, FCF margin,
  WACC, terminal growth, net debt, shares outstanding) and a WACC ×
  terminal-growth sensitivity grid
- A downloadable **Excel model** and a **PDF report** in a PE deal-memo
  style (cover page, executive summary, cash flow analysis, valuation,
  sensitivity, risk flags)

Everything runs on your machine — no external APIs, no cloud services.

## Run it

```bash
venv\Scripts\python.exe pe-dcf-analyzer\app.py
```

(or, from inside `pe-dcf-analyzer/`, with the venv activated: `python app.py`)

Opens `http://127.0.0.1:8030`. Click **Use sample data instead** to try it
immediately with an illustrative 5-year dataset, or drop in a real file.

## Notes

- No login — this is a single local instance. Point different clients at
  their own uploads by running separate copies of this app, or by not
  persisting the `data/local/` folder between sessions if that matters to
  you.
- Uploaded files and generated reports are saved to `data/local/` for
  reference; nothing leaves the machine.
- Same parsing/normalization approach as the standalone `findash` project
  in this workspace, but kept as a fully separate codebase — this one adds
  the DCF engine, cash-flow-change analysis, and Excel/PDF report
  generation.
- Expected file shape: first column = line-item label, remaining columns =
  periods, one sheet per statement (Income Statement / Balance Sheet /
  Cash Flow) works best. Unrecognized labels show up under "Review
  unmapped items" instead of being guessed.
