(() => {
  const shell = document.getElementById("app-shell");

  function friendlyError(err) {
    if (err instanceof TypeError) {
      return "Could not reach the server. Make sure the app is still running (python app.py) and reload this page.";
    }
    return err.message || String(err);
  }

  // ---------- screens ----------
  const uploadScreen = document.getElementById("upload-screen");
  const dashboardScreen = document.getElementById("dashboard-screen");

  // ---------- upload ----------
  const fileInput = document.getElementById("file-input");
  const dropzone = document.getElementById("dropzone");
  const selectedFileBox = document.getElementById("selected-file");
  const selectedFileName = document.getElementById("selected-file-name");
  const analyzeBtn = document.getElementById("analyze-btn");
  const useDummyBtn = document.getElementById("use-dummy-btn");
  const pipelineProgress = document.getElementById("pipeline-progress");
  const errorBox = document.getElementById("error-box");
  const fileLabel = document.getElementById("file-label");
  const newFileBtn = document.getElementById("new-file-btn");
  const themeToggle = document.getElementById("theme-toggle");
  const periodSelect = document.getElementById("period-select");
  const kpiRow = document.getElementById("kpi-row");
  const concernsList = document.getElementById("concerns-list");
  const tableToggleBtn = document.getElementById("table-toggle-btn");
  const tableView = document.getElementById("table-view");
  const metricsTable = document.getElementById("metrics-table");
  const reviewBtn = document.getElementById("review-btn");
  const reviewPanel = document.getElementById("review-panel");
  const reviewTable = document.getElementById("review-table");
  const cfChangesTable = document.getElementById("cf-changes-table");
  const cfFlagsList = document.getElementById("cf-flags-list");

  let selectedFile = null;
  let lastResult = null;
  let lastDcf = null;
  let charts = {};

  const savedTheme = localStorage.getItem("pedcf-theme");
  if (savedTheme) shell.setAttribute("data-theme", savedTheme);
  themeToggle.addEventListener("click", () => {
    const current = shell.getAttribute("data-theme") || "light";
    const next = current === "dark" ? "light" : "dark";
    shell.setAttribute("data-theme", next);
    localStorage.setItem("pedcf-theme", next);
    if (lastResult) renderCharts(lastResult, periodSelect.value);
  });

  dropzone.addEventListener("click", (e) => { if (e.target !== fileInput) fileInput.click(); });
  dropzone.addEventListener("dragover", (e) => { e.preventDefault(); dropzone.classList.add("drag-over"); });
  dropzone.addEventListener("dragleave", () => dropzone.classList.remove("drag-over"));
  dropzone.addEventListener("drop", (e) => {
    e.preventDefault();
    dropzone.classList.remove("drag-over");
    if (e.dataTransfer.files.length) {
      fileInput.files = e.dataTransfer.files;
      handleFileSelected(e.dataTransfer.files[0]);
    }
  });
  fileInput.addEventListener("change", () => { if (fileInput.files.length) handleFileSelected(fileInput.files[0]); });

  function handleFileSelected(file) {
    selectedFile = file;
    selectedFileName.textContent = file.name;
    selectedFileBox.hidden = false;
    errorBox.hidden = true;
  }

  analyzeBtn.addEventListener("click", () => runAnalysis());
  useDummyBtn.addEventListener("click", () => runAnalysis(true));
  newFileBtn.addEventListener("click", resetToUpload);

  function resetToUpload() {
    selectedFile = null;
    fileInput.value = "";
    selectedFileBox.hidden = true;
    pipelineProgress.hidden = true;
    errorBox.hidden = true;
    dashboardScreen.hidden = true;
    uploadScreen.hidden = false;
    newFileBtn.hidden = true;
    fileLabel.textContent = "";
  }

  const PIPELINE_STEPS = ["detect", "extract", "normalize", "analyze", "concerns", "render"];

  async function runAnalysis(useDummy) {
    if (!useDummy && !selectedFile) return;
    errorBox.hidden = true;
    pipelineProgress.hidden = false;
    selectedFileBox.hidden = true;
    analyzeBtn.disabled = true;
    useDummyBtn.disabled = true;

    resetPipelineUI();
    animateStep("detect");

    try {
      await tick(180);
      animateStep("extract", "detect");

      let resp;
      if (useDummy) {
        resp = await fetch("/api/analyze-dummy", { method: "POST" });
      } else {
        const formData = new FormData();
        formData.append("file", selectedFile);
        resp = await fetch("/api/analyze", { method: "POST", body: formData });
      }

      await tick(150);
      animateStep("normalize", "extract");
      const data = await resp.json();
      if (!resp.ok) throw new Error(data.detail || "Analysis failed.");

      await tick(150);
      animateStep("analyze", "normalize");
      await tick(150);
      animateStep("concerns", "analyze");
      await tick(150);
      animateStep("render", "concerns");
      await tick(120);
      markDone("render");

      lastResult = data;
      showDashboard(data);
    } catch (err) {
      pipelineProgress.hidden = true;
      if (!useDummy) selectedFileBox.hidden = false;
      errorBox.hidden = false;
      errorBox.textContent = friendlyError(err);
    } finally {
      analyzeBtn.disabled = false;
      useDummyBtn.disabled = false;
    }
  }

  function tick(ms) { return new Promise((r) => setTimeout(r, ms)); }
  function resetPipelineUI() {
    PIPELINE_STEPS.forEach((s) => {
      const el = pipelineProgress.querySelector(`[data-step="${s}"]`);
      el.classList.remove("active", "done");
    });
  }
  function animateStep(step, prevDone) {
    if (prevDone) markDone(prevDone);
    pipelineProgress.querySelector(`[data-step="${step}"]`).classList.add("active");
  }
  function markDone(step) {
    const el = pipelineProgress.querySelector(`[data-step="${step}"]`);
    el.classList.remove("active");
    el.classList.add("done");
  }

  // ---------- dashboard rendering ----------
  function showDashboard(data) {
    uploadScreen.hidden = true;
    dashboardScreen.hidden = false;
    newFileBtn.hidden = false;
    fileLabel.textContent = data.filename;

    periodSelect.innerHTML = "";
    data.periods.forEach((p) => {
      const opt = document.createElement("option");
      opt.value = p; opt.textContent = p;
      periodSelect.appendChild(opt);
    });
    periodSelect.value = data.periods[data.periods.length - 1];
    periodSelect.onchange = () => {
      renderKpis(data, periodSelect.value);
      renderConcerns(data, periodSelect.value);
    };

    renderKpis(data, periodSelect.value);
    renderConcerns(data, periodSelect.value);
    renderCharts(data, periodSelect.value);
    renderTable(data);
    renderReview(data);
    renderCashFlowChanges(data);

    document.getElementById("dcf-results").hidden = true;
    document.getElementById("dcf-company").value = data.filename.replace(/\.[a-z0-9]+$/i, "").replace(/\(sample data\)/i, "").trim() || "Target Company";
  }

  function metricAt(data, period) { return data.metrics.find((m) => m.period === period); }

  const KPI_DEFS = [
    { key: "revenue", label: "Revenue", fmt: fmtCurrency },
    { key: "net_income", label: "Net Income", fmt: fmtCurrency },
    { key: "net_margin", label: "Net Margin", fmt: fmtPct },
    { key: "current_ratio", label: "Current Ratio", fmt: fmtRatio },
    { key: "debt_to_equity", label: "Debt / Equity", fmt: fmtRatio },
    { key: "roe", label: "Return on Equity", fmt: fmtPct },
  ];

  function renderKpis(data, period) {
    const idx = data.periods.indexOf(period);
    const curr = metricAt(data, period);
    const prev = idx > 0 ? metricAt(data, data.periods[idx - 1]) : null;

    kpiRow.innerHTML = "";
    KPI_DEFS.forEach((def) => {
      const value = curr ? curr[def.key] : null;
      const prevValue = prev ? prev[def.key] : null;
      const card = document.createElement("div");
      card.className = "kpi-card";
      let deltaHtml = "";
      if (value != null && prevValue != null && prevValue !== 0) {
        const delta = value - prevValue;
        const pctDelta = (delta / Math.abs(prevValue)) * 100;
        const dir = delta > 0.0001 ? "up" : delta < -0.0001 ? "down" : "flat";
        const arrow = dir === "up" ? "▲" : dir === "down" ? "▼" : "•";
        deltaHtml = `<div class="kpi-delta ${dir}">${arrow} ${pctDelta.toFixed(1)}% vs prior period</div>`;
      }
      card.innerHTML = `<div class="kpi-label">${def.label}</div><div class="kpi-value">${value != null ? def.fmt(value) : "—"}</div>${deltaHtml}`;
      kpiRow.appendChild(card);
    });
  }

  function renderConcerns(data, period) {
    concernsList.innerHTML = "";
    const order = { red: 0, amber: 1 };
    const items = [...data.concerns].sort((a, b) => (order[a.severity] ?? 2) - (order[b.severity] ?? 2));
    if (!items.length) {
      concernsList.innerHTML = `<div class="concerns-empty">No concern signals triggered by the configured rules.</div>`;
      return;
    }
    items.forEach((c) => {
      const div = document.createElement("div");
      div.className = "concern-item" + (c.severity === "amber" ? " amber" : "");
      const badge = c.severity === "amber" ? "Watch" : "Critical";
      div.innerHTML = `<div class="concern-item-title"><span class="dot"></span>${escapeHtml(c.title)} — ${badge}</div><div class="concern-item-msg">${escapeHtml(c.message)}</div><div class="concern-item-meta">${escapeHtml(c.period)} · rule: ${escapeHtml(c.id)}</div>`;
      concernsList.appendChild(div);
    });
  }

  function renderCashFlowChanges(data) {
    const fields = ["period", "operating_cf", "operating_cf_change_pct", "investing_cf", "financing_cf",
      "free_cash_flow", "free_cash_flow_change_pct", "fcf_vs_revenue_divergence", "ocf_to_ni", "fcf_conversion"];
    const labels = {
      period: "Period", operating_cf: "Operating CF", operating_cf_change_pct: "Op. CF %chg",
      investing_cf: "Investing CF", financing_cf: "Financing CF", free_cash_flow: "Free CF",
      free_cash_flow_change_pct: "FCF %chg", fcf_vs_revenue_divergence: "FCF vs Rev Growth (pts)",
      ocf_to_ni: "OCF / NI", fcf_conversion: "FCF / NI",
    };
    let html = "<thead><tr>" + fields.map((f) => `<th>${labels[f]}</th>`).join("") + "</tr></thead><tbody>";
    (data.changes || []).forEach((c) => {
      html += "<tr>" + fields.map((f) => {
        if (f === "period") return `<td>${escapeHtml(c[f])}</td>`;
        const v = c[f];
        return `<td class="num">${v == null ? "—" : (Number.isInteger(v) ? v : Number(v).toFixed(2))}</td>`;
      }).join("") + "</tr>";
    });
    html += "</tbody>";
    cfChangesTable.innerHTML = html;

    cfFlagsList.innerHTML = "";
    const flags = data.change_flags || [];
    if (!flags.length) {
      cfFlagsList.innerHTML = `<div class="concerns-empty">No material cash flow divergences flagged.</div>`;
      return;
    }
    flags.forEach((f) => {
      const div = document.createElement("div");
      div.className = "cf-flag" + (f.severity === "amber" ? " amber" : f.severity === "info" ? " info" : "");
      const badge = f.severity === "red" ? "Critical" : f.severity === "amber" ? "Watch" : "Note";
      div.innerHTML = `<div class="cf-flag-title">${escapeHtml(f.title)} — ${badge} (${escapeHtml(f.period)})</div><div class="cf-flag-msg">${escapeHtml(f.message)}</div>`;
      cfFlagsList.appendChild(div);
    });
  }

  function cssVar(name) { return getComputedStyle(shell).getPropertyValue(name).trim(); }

  function baseChartOptions(yLabel) {
    return {
      responsive: true, maintainAspectRatio: false,
      interaction: { mode: "index", intersect: false },
      plugins: {
        legend: { display: true, labels: { color: cssVar("--text-secondary"), boxWidth: 12, font: { size: 11 } } },
        tooltip: { backgroundColor: cssVar("--surface-1"), titleColor: cssVar("--text-primary"), bodyColor: cssVar("--text-secondary"), borderColor: cssVar("--border"), borderWidth: 1 },
      },
      scales: {
        x: { grid: { color: cssVar("--gridline") }, ticks: { color: cssVar("--text-muted"), font: { size: 11 } } },
        y: { grid: { color: cssVar("--gridline") }, ticks: { color: cssVar("--text-muted"), font: { size: 11 } }, title: yLabel ? { display: true, text: yLabel, color: cssVar("--text-muted"), font: { size: 11 } } : undefined },
      },
    };
  }

  function destroyCharts() { Object.values(charts).forEach((c) => c && c.destroy()); charts = {}; }

  function renderCharts(data, period) {
    destroyCharts();
    const labels = data.periods;
    const series1 = cssVar("--series-1"), series2 = cssVar("--series-2"), series3 = cssVar("--series-3"), critical = cssVar("--status-critical");

    charts.revenue = new Chart(document.getElementById("chart-revenue"), {
      type: "bar", data: { labels, datasets: [
        { label: "Revenue", data: pick(data, "revenue"), backgroundColor: series1, borderRadius: 4, maxBarThickness: 36 },
        { label: "Net Income", data: pick(data, "net_income"), backgroundColor: series2, borderRadius: 4, maxBarThickness: 36 },
      ] }, options: baseChartOptions("Amount"),
    });
    charts.margins = new Chart(document.getElementById("chart-margins"), {
      type: "line", data: { labels, datasets: [
        { label: "Gross Margin", data: pctSeries(data, "gross_margin"), borderColor: series1, backgroundColor: series1, tension: 0.25, pointRadius: 3, borderWidth: 2 },
        { label: "Operating Margin", data: pctSeries(data, "operating_margin"), borderColor: series2, backgroundColor: series2, tension: 0.25, pointRadius: 3, borderWidth: 2 },
        { label: "Net Margin", data: pctSeries(data, "net_margin"), borderColor: series3, backgroundColor: series3, tension: 0.25, pointRadius: 3, borderWidth: 2 },
      ] }, options: baseChartOptions("%"),
    });
    charts.liquidity = new Chart(document.getElementById("chart-liquidity"), {
      type: "line", data: { labels, datasets: [
        { label: "Current Ratio", data: pick(data, "current_ratio"), borderColor: series1, backgroundColor: series1, tension: 0.25, pointRadius: 3, borderWidth: 2 },
        { label: "Quick Ratio", data: pick(data, "quick_ratio"), borderColor: series2, backgroundColor: series2, tension: 0.25, pointRadius: 3, borderWidth: 2 },
      ] }, options: baseChartOptions("Ratio (x)"),
    });
    charts.leverage = new Chart(document.getElementById("chart-leverage"), {
      type: "bar", data: { labels, datasets: [{ label: "Debt / Equity", data: pick(data, "debt_to_equity"), backgroundColor: critical, borderRadius: 4, maxBarThickness: 36 }] },
      options: { ...baseChartOptions("Ratio (x)"), plugins: { ...baseChartOptions().plugins, legend: { display: false } } },
    });
    charts.position = new Chart(document.getElementById("chart-position"), {
      type: "bar", data: { labels, datasets: [
        { label: "Total Assets", data: pick(data, "total_assets"), backgroundColor: series1, borderRadius: 4, maxBarThickness: 28 },
        { label: "Total Liabilities", data: pick(data, "total_liabilities"), backgroundColor: series2, borderRadius: 4, maxBarThickness: 28 },
        { label: "Total Equity", data: pick(data, "total_equity"), backgroundColor: series3, borderRadius: 4, maxBarThickness: 28 },
      ] }, options: baseChartOptions("Amount"),
    });
    charts.cashflow = new Chart(document.getElementById("chart-cashflow"), {
      type: "line", data: { labels, datasets: [
        { label: "Operating CF", data: pick(data, "operating_cash_flow"), borderColor: series1, backgroundColor: series1, tension: 0.25, pointRadius: 3, borderWidth: 2 },
        { label: "Investing CF", data: pick(data, "investing_cash_flow"), borderColor: series2, backgroundColor: series2, tension: 0.25, pointRadius: 3, borderWidth: 2 },
        { label: "Financing CF", data: pick(data, "financing_cash_flow"), borderColor: series3, backgroundColor: series3, tension: 0.25, pointRadius: 3, borderWidth: 2 },
      ] }, options: baseChartOptions("Amount"),
    });
  }

  function pick(data, key) { return data.periods.map((p) => { const m = metricAt(data, p); return m ? m[key] : null; }); }
  function pctSeries(data, key) { return pick(data, key).map((v) => (v == null ? null : Math.round(v * 10000) / 100)); }

  function renderTable(data) {
    const fields = ["period", "revenue", "net_income", "gross_margin", "operating_margin", "net_margin",
      "current_ratio", "quick_ratio", "debt_to_equity", "interest_coverage", "roe", "roa", "asset_turnover",
      "revenue_growth", "net_income_growth", "total_assets", "total_liabilities", "total_equity", "working_capital",
      "operating_cash_flow", "investing_cash_flow", "financing_cash_flow", "free_cash_flow"];
    const labels = { period: "Period", revenue: "Revenue", net_income: "Net Income", gross_margin: "Gross Margin",
      operating_margin: "Op. Margin", net_margin: "Net Margin", current_ratio: "Current Ratio", quick_ratio: "Quick Ratio",
      debt_to_equity: "Debt/Equity", interest_coverage: "Interest Cov.", roe: "ROE", roa: "ROA", asset_turnover: "Asset Turnover",
      revenue_growth: "Rev. Growth %", net_income_growth: "NI Growth %", total_assets: "Total Assets",
      total_liabilities: "Total Liabilities", total_equity: "Total Equity", working_capital: "Working Capital",
      operating_cash_flow: "Operating CF", investing_cash_flow: "Investing CF", financing_cash_flow: "Financing CF", free_cash_flow: "Free CF" };
    let html = "<thead><tr>" + fields.map((f) => `<th>${labels[f]}</th>`).join("") + "</tr></thead><tbody>";
    data.metrics.forEach((m) => {
      html += "<tr>" + fields.map((f) => {
        if (f === "period") return `<td>${escapeHtml(m[f])}</td>`;
        const v = m[f];
        return `<td class="num">${v == null ? "—" : Number.isInteger(v) ? v : v.toFixed(2)}</td>`;
      }).join("") + "</tr>";
    });
    html += "</tbody>";
    metricsTable.innerHTML = html;
  }

  tableToggleBtn.addEventListener("click", () => {
    tableView.hidden = !tableView.hidden;
    tableToggleBtn.textContent = tableView.hidden ? "View as table" : "Hide table";
  });

  function renderReview(data) {
    const items = [...(data.needs_review || []), ...(data.unmapped || [])];
    if (!items.length) { reviewBtn.hidden = true; reviewPanel.hidden = true; return; }
    reviewBtn.hidden = false;
    let html = "<thead><tr><th>Label (from file)</th><th>Sheet</th><th>Best guess</th><th>Confidence</th></tr></thead><tbody>";
    items.forEach((it) => {
      const guess = it.suggestion ? `${it.suggestion[0]} / ${it.suggestion[1]}` : "—";
      html += `<tr><td>${escapeHtml(it.label)}</td><td>${escapeHtml(it.sheet)}</td><td>${escapeHtml(guess)}</td><td class="num">${it.score}</td></tr>`;
    });
    html += "</tbody>";
    reviewTable.innerHTML = html;
  }
  reviewBtn.addEventListener("click", () => { reviewPanel.hidden = !reviewPanel.hidden; });

  // ---------- DCF ----------
  const runDcfBtn = document.getElementById("run-dcf-btn");
  const dcfResults = document.getElementById("dcf-results");

  function collectAssumptions() {
    const pct = (id) => {
      const v = parseFloat(document.getElementById(id).value);
      return Number.isFinite(v) ? v / 100 : null;
    };
    const marginRaw = document.getElementById("dcf-margin").value;
    const sharesRaw = document.getElementById("dcf-shares").value;
    return {
      projection_years: parseInt(document.getElementById("dcf-years").value, 10) || 5,
      revenue_growth_rate: pct("dcf-growth") ?? 0.08,
      fcf_margin: marginRaw ? parseFloat(marginRaw) / 100 : null,
      wacc: pct("dcf-wacc") ?? 0.10,
      terminal_growth: pct("dcf-tgr") ?? 0.025,
      net_debt: parseFloat(document.getElementById("dcf-netdebt").value) || 0,
      shares_outstanding: sharesRaw ? parseFloat(sharesRaw) : null,
    };
  }

  runDcfBtn.addEventListener("click", async () => {
    if (!lastResult) return;
    runDcfBtn.disabled = true;
    try {
      const assumptions = collectAssumptions();
      const resp = await fetch("/api/dcf", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ metrics: lastResult.metrics, ...assumptions }),
      });
      const dcf = await resp.json();
      if (!resp.ok) throw new Error(dcf.detail || "DCF failed.");
      lastDcf = dcf;
      renderDcf(dcf);
    } catch (err) {
      alert(friendlyError(err));
    } finally {
      runDcfBtn.disabled = false;
    }
  });

  function renderDcf(dcf) {
    dcfResults.hidden = false;
    document.getElementById("dcf-ev").textContent = fmtCurrency(dcf.enterprise_value);
    document.getElementById("dcf-eq").textContent = fmtCurrency(dcf.equity_value);
    document.getElementById("dcf-vps").textContent = dcf.value_per_share != null ? dcf.value_per_share.toFixed(2) : "—";
    document.getElementById("dcf-margin-out").textContent = (dcf.assumed_fcf_margin * 100).toFixed(1) + "%";

    const warnBox = document.getElementById("dcf-warnings");
    warnBox.innerHTML = "";
    (dcf.warnings || []).forEach((w) => {
      const div = document.createElement("div");
      div.className = "dcf-warning";
      div.textContent = "⚠ " + w;
      warnBox.appendChild(div);
    });

    let ph = "<thead><tr><th>Year</th><th>Revenue</th><th>Free Cash Flow</th><th>Discount Factor</th><th>Present Value</th></tr></thead><tbody>";
    dcf.projections.forEach((p) => {
      ph += `<tr><td>${p.year}</td><td class="num">${fmtCurrency(p.revenue)}</td><td class="num">${fmtCurrency(p.free_cash_flow)}</td><td class="num">${p.discount_factor}</td><td class="num">${fmtCurrency(p.present_value)}</td></tr>`;
    });
    ph += "</tbody>";
    document.getElementById("dcf-projection-table").innerHTML = ph;

    const sens = dcf.sensitivity || {};
    let sh = "<thead><tr><th>WACC \\ g</th>" + (sens.terminal_growth_axis || []).map((g) => `<th>${(g * 100).toFixed(2)}%</th>`).join("") + "</tr></thead><tbody>";
    (sens.wacc_axis || []).forEach((w, i) => {
      sh += `<tr><td>${(w * 100).toFixed(2)}%</td>` + (sens.enterprise_values[i] || []).map((v) => `<td class="num">${v == null ? "n/a" : fmtCurrency(v)}</td>`).join("") + "</tr>";
    });
    sh += "</tbody>";
    document.getElementById("dcf-sensitivity-table").innerHTML = sh;

    document.getElementById("scenario-results").hidden = true;
  }

  // ---------- Scenario analysis ----------
  const runScenariosBtn = document.getElementById("run-scenarios-btn");
  runScenariosBtn.addEventListener("click", async () => {
    if (!lastResult) return;
    runScenariosBtn.disabled = true;
    try {
      const assumptions = collectAssumptions();
      const resp = await fetch("/api/dcf/scenarios", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ metrics: lastResult.metrics, ...assumptions }),
      });
      const scenarios = await resp.json();
      if (!resp.ok) throw new Error(scenarios.detail || "Scenario analysis failed.");
      renderScenarios(scenarios);
    } catch (err) {
      alert(friendlyError(err));
    } finally {
      runScenariosBtn.disabled = false;
    }
  });

  function renderScenarios(scenarios) {
    const rows = [
      ["Revenue Growth Rate", (s) => fmtPct(s.revenue_growth_rate)],
      ["Assumed FCF Margin", (s) => fmtPct(s.assumed_fcf_margin)],
      ["Enterprise Value", (s) => fmtCurrency(s.enterprise_value)],
      ["Equity Value", (s) => fmtCurrency(s.equity_value)],
      ["Value per Share", (s) => (s.value_per_share != null ? s.value_per_share.toFixed(2) : "—")],
    ];
    let html = "<thead><tr><th>Metric</th><th>Bear</th><th>Base</th><th>Bull</th></tr></thead><tbody>";
    rows.forEach(([label, fmt]) => {
      html += `<tr><td>${label}</td><td class="num">${fmt(scenarios.bear || {})}</td><td class="num">${fmt(scenarios.base || {})}</td><td class="num">${fmt(scenarios.bull || {})}</td></tr>`;
    });
    html += "</tbody>";
    document.getElementById("scenario-table").innerHTML = html;
    document.getElementById("scenario-results").hidden = false;
  }

  // ---------- Reports ----------
  document.getElementById("download-excel-btn").addEventListener("click", () => downloadReport("excel"));
  document.getElementById("download-pdf-btn").addEventListener("click", () => downloadReport("pdf"));

  async function downloadReport(kind) {
    if (!lastResult) return;
    const assumptions = collectAssumptions();
    const companyName = document.getElementById("dcf-company").value || "Target Company";
    const btn = document.getElementById(kind === "excel" ? "download-excel-btn" : "download-pdf-btn");
    btn.disabled = true;
    try {
      const resp = await fetch(`/api/report/${kind}`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          metrics: lastResult.metrics,
          periods: lastResult.periods,
          concerns: lastResult.concerns,
          company_name: companyName,
          filename: companyName.replace(/[^a-z0-9]+/gi, "_").toLowerCase() || "company",
          ...assumptions,
        }),
      });
      if (!resp.ok) {
        const data = await resp.json().catch(() => ({}));
        throw new Error(data.detail || "Report generation failed.");
      }
      const blob = await resp.blob();
      const disposition = resp.headers.get("Content-Disposition") || "";
      const match = disposition.match(/filename="?([^"]+)"?/);
      const filename = match ? match[1] : `report.${kind === "excel" ? "xlsx" : "pdf"}`;
      const url = URL.createObjectURL(blob);
      const a = document.createElement("a");
      a.href = url; a.download = filename;
      document.body.appendChild(a); a.click(); a.remove();
      URL.revokeObjectURL(url);
    } catch (err) {
      alert(friendlyError(err));
    } finally {
      btn.disabled = false;
    }
  }

  // ---------- formatting ----------
  function fmtCurrency(v) {
    if (v == null) return "—";
    const abs = Math.abs(v);
    let s;
    if (abs >= 1e9) s = (v / 1e9).toFixed(2) + "B";
    else if (abs >= 1e6) s = (v / 1e6).toFixed(2) + "M";
    else if (abs >= 1e3) s = (v / 1e3).toFixed(1) + "K";
    else s = v.toFixed(0);
    return s;
  }
  function fmtPct(v) { return v == null ? "—" : (v * 100).toFixed(1) + "%"; }
  function fmtRatio(v) { return v == null ? "—" : v.toFixed(2) + "x"; }
  function escapeHtml(s) {
    return String(s ?? "").replace(/[&<>"']/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c]));
  }
})();
