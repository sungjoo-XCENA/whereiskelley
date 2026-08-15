(function () {
  const state = {
    guidePayload: null,
    shopPayload: null,
    databaseMode: "restaurants",
    collectionMode: "restaurants",
    dashboardMap: null,
    dashboardMapEl: null,
    dashboardInfoWindow: null,
    dashboardDataLayer: null,
    dashboardDataClickBound: false,
    dashboardMapSignature: "",
    dashboardMarkers: new Map(),
    dashboardMapHasFit: false,
    dashboardMapPromise: null,
    activeTargetId: null,
    guideLoadInFlight: false,
    localGuideSeen: false,
    lastLocalGuidePayload: null,
    activeView: "search",
    guideLoadedOnce: false,
    guideActionInFlight: false,
    guideActionMessage: "",
    guideActionKind: "",
    shopActionInFlight: false,
    shopActionMessage: "",
    lastRefreshAt: ""
  };

  const css = document.createElement("style");
  css.textContent = `
    .source-strip,
    #watchlistView {
      display: none !important;
    }
    .dashboard-grid {
      display: grid;
      grid-template-columns: repeat(4, minmax(0, 1fr));
      gap: 12px;
    }
    .dashboard-card,
    .dash-panel {
      border: 1px solid var(--line);
      border-radius: 10px;
      background: var(--surface);
      box-shadow: var(--shadow);
    }
    .dashboard-card {
      display: grid;
      gap: 7px;
      min-height: 112px;
      padding: 15px;
    }
    .dashboard-card span,
    .dash-kicker {
      color: var(--muted);
      font-size: 11px;
      font-weight: 900;
      text-transform: uppercase;
    }
    .dashboard-card b {
      font-size: 28px;
      line-height: 1;
      font-weight: 950;
    }
    .dashboard-card small {
      color: var(--muted);
      font-weight: 750;
      line-height: 1.35;
    }
    .dash-panel {
      padding: 16px;
      margin-top: 14px;
    }
    .database-mode-control {
      display: inline-flex;
      gap: 4px;
      padding: 4px;
      border: 1px solid var(--line);
      border-radius: 8px;
      background: #f5f7fa;
    }
    .database-mode-control button {
      min-height: 34px;
      padding: 0 12px;
      border: 0;
      border-radius: 6px;
      background: transparent;
      color: var(--muted);
      font-weight: 800;
      cursor: pointer;
    }
    .database-mode-control button.active {
      background: #111418;
      color: #fff;
    }
    .database-summary-copy {
      margin: 7px 0 14px;
      color: var(--muted);
      font-weight: 750;
      line-height: 1.4;
    }
    .collection-switch-panel {
      display: flex;
      align-items: center;
      justify-content: space-between;
      gap: 18px;
    }
    .collection-switch-panel h2,
    .collection-stage h2 {
      margin: 2px 0 0;
    }
    .collection-stage-grid {
      display: grid;
      grid-template-columns: repeat(2, minmax(0, 1fr));
      gap: 14px;
      margin-top: 14px;
    }
    .collection-stage {
      margin-top: 0;
    }
    .collection-stage-copy {
      min-height: 42px;
      margin: 8px 0 0;
      color: var(--muted);
      font-weight: 750;
      line-height: 1.4;
    }
    .collection-stage-number {
      display: inline-grid;
      place-items: center;
      width: 24px;
      height: 24px;
      margin-right: 8px;
      border-radius: 50%;
      background: #111418;
      color: #fff;
      font-size: 12px;
      font-weight: 900;
    }
    .collection-stage-schedule {
      display: flex;
      justify-content: space-between;
      gap: 12px;
      margin-top: 12px;
      padding-top: 12px;
      border-top: 1px solid var(--line);
      color: var(--muted);
      font-size: 12px;
      font-weight: 800;
    }
    .collection-head {
      display: flex;
      align-items: start;
      justify-content: space-between;
      gap: 14px;
    }
    .dash-progress {
      height: 14px;
      overflow: hidden;
      border-radius: 999px;
      background: #e5e7eb;
      margin: 14px 0;
    }
    .dash-progress > i {
      display: block;
      width: var(--dash-progress, 0%);
      height: 100%;
      border-radius: inherit;
      background: var(--accent);
    }
    .collection-pipeline {
      display: grid;
      grid-template-columns: repeat(4, minmax(0, 1fr));
      gap: 10px;
      margin: 14px 0;
    }
    .pipeline-step {
      min-height: 112px;
      padding: 13px;
      border: 1px solid var(--line);
      border-radius: 8px;
      background: #f8fafc;
    }
    .pipeline-step.active {
      border-color: #b0123f;
      background: #fff7f9;
      box-shadow: inset 3px 0 0 #b0123f;
    }
    .pipeline-step.complete {
      border-color: #a7d8c3;
      background: #f0fdf7;
    }
    .pipeline-step.failed {
      border-color: #fecaca;
      background: #fff1f2;
    }
    .pipeline-step-head {
      display: flex;
      align-items: center;
      justify-content: space-between;
      gap: 8px;
      margin-bottom: 9px;
    }
    .pipeline-step-number {
      display: inline-grid;
      place-items: center;
      width: 24px;
      height: 24px;
      border-radius: 50%;
      background: #dfe4ea;
      color: #475569;
      font-size: 12px;
      font-weight: 950;
    }
    .pipeline-step.active .pipeline-step-number {
      background: #b0123f;
      color: #fff;
    }
    .pipeline-step.complete .pipeline-step-number {
      background: #059669;
      color: #fff;
    }
    .pipeline-step-state {
      color: var(--muted);
      font-size: 11px;
      font-weight: 900;
      text-transform: uppercase;
    }
    .pipeline-step.active .pipeline-step-state { color: #b0123f; }
    .pipeline-step.complete .pipeline-step-state { color: #047857; }
    .pipeline-step h3 {
      margin: 0 0 6px;
      font-size: 15px;
      line-height: 1.25;
    }
    .pipeline-step p {
      margin: 0;
      color: var(--muted);
      font-size: 12px;
      font-weight: 750;
      line-height: 1.4;
    }
    .pipeline-step strong {
      display: block;
      margin-top: 8px;
      font-size: 13px;
      line-height: 1.35;
    }
    .collection-metrics,
    .db-health-grid {
      display: grid;
      grid-template-columns: repeat(6, minmax(0, 1fr));
      gap: 10px;
    }
    .collection-stage .collection-metrics {
      grid-template-columns: repeat(2, minmax(0, 1fr));
    }
    .metric-box {
      min-height: 74px;
      padding: 11px;
      border: 1px solid var(--line);
      border-radius: 8px;
      background: #fff;
    }
    .metric-box span {
      display: block;
      margin-bottom: 8px;
      color: var(--muted);
      font-size: 11px;
      font-weight: 900;
      text-transform: uppercase;
    }
    .metric-box b {
      display: block;
      overflow-wrap: anywhere;
      font-size: 16px;
      line-height: 1.25;
      font-weight: 950;
    }
    .dash-pill {
      display: inline-flex;
      align-items: center;
      min-height: 24px;
      padding: 0 8px;
      border-radius: 999px;
      background: #f1f5f9;
      color: var(--muted);
      font-size: 12px;
      font-weight: 850;
      white-space: nowrap;
    }
    .dash-pill.good {
      background: #ecfdf5;
      color: #047857;
    }
    .dash-pill.bad {
      background: #fff1f2;
      color: #be123c;
    }
    .dash-pill.warn {
      background: #fff7ed;
      color: #b45309;
    }
    .dashboard-refresh {
      display: inline-flex;
      align-items: center;
      min-height: 34px;
      border: 1px solid var(--line);
      border-radius: 8px;
      padding: 0 12px;
      background: #fff;
      color: var(--ink);
      font-weight: 850;
      cursor: pointer;
    }
    .dashboard-refresh:disabled {
      opacity: 0.55;
      cursor: progress;
    }
    .dashboard-action-note {
      flex-basis: 100%;
      color: var(--muted);
      font-size: 12px;
      font-weight: 800;
    }
    .dashboard-progress-actions {
      justify-content: flex-end;
      margin-left: auto;
      max-width: min(760px, 60vw);
      text-align: right;
    }
    .dashboard-action-note.good {
      color: #047857;
    }
    .dashboard-action-note.warn,
    .dashboard-action-note.bad {
      color: #b45309;
    }
    .dashboard-map-wrap {
      position: relative;
      height: 430px;
      overflow: hidden;
      border: 1px solid var(--line);
      border-radius: 8px;
      background: #eef2f6;
    }
    #dashboardDbMap {
      position: absolute;
      inset: 0;
    }
    .dashboard-map-fallback {
      position: absolute;
      inset: 0;
      display: grid;
      place-content: center;
      gap: 10px;
      padding: 24px;
      text-align: center;
      color: var(--muted);
      background: #f8fafc;
    }
    .dashboard-map-fallback.hidden {
      display: none;
    }
    .map-legend {
      display: flex;
      flex-wrap: wrap;
      gap: 10px;
      margin-top: 12px;
      color: var(--muted);
      font-size: 12px;
      font-weight: 800;
    }
    .selected-target-actions button.world-view-button {
      display: inline-flex;
      align-items: center;
      justify-content: center;
      gap: 8px;
      min-height: 38px;
      border: 1px solid #0f766e;
      border-radius: 8px;
      padding: 0 13px;
      background: #0f766e;
      color: #fff;
      font-weight: 900;
      cursor: pointer;
    }
    .selected-target-actions button.world-view-button:hover {
      border-color: #115e59;
      background: #115e59;
    }
    .selected-target-actions button.world-view-button:focus-visible {
      outline: 3px solid rgba(15, 118, 110, 0.24);
      outline-offset: 2px;
    }
    .world-view-icon {
      font-size: 18px;
      line-height: 1;
    }
    .legend-dot {
      display: inline-flex;
      align-items: center;
      gap: 6px;
    }
    .legend-dot::before {
      content: "";
      width: 10px;
      height: 10px;
      border-radius: 999px;
      background: var(--dot);
    }
    .dashboard-split {
      display: grid;
      grid-template-columns: minmax(0, 1.1fr) minmax(360px, 0.9fr);
      gap: 14px;
      align-items: start;
    }
    .selected-target {
      display: grid;
      gap: 14px;
      padding: 16px;
      border: 1px solid var(--line);
      border-radius: 8px;
      background: #fff;
    }
    .selected-target.empty {
      color: var(--muted);
    }
    .selected-target h3 {
      font-size: 24px;
    }
    .selected-target p {
      color: var(--muted);
      font-weight: 750;
    }
    .selected-target-grid {
      display: grid;
      grid-template-columns: repeat(2, minmax(0, 1fr));
      gap: 10px;
    }
    .selected-target-actions {
      display: flex;
      flex-wrap: wrap;
      gap: 10px;
    }
    .selected-target-actions a,
    .selected-target-actions button {
      display: inline-flex;
      align-items: center;
      min-height: 36px;
      border: 1px solid var(--accent);
      border-radius: 8px;
      padding: 0 12px;
      background: var(--accent);
      color: #fff;
      font-weight: 850;
      text-decoration: none;
    }
    .selected-target-actions a.secondary,
    .selected-target-actions button.secondary {
      border-color: var(--line);
      background: #fff;
      color: var(--ink);
    }
    .resource-grid {
      display: grid;
      grid-template-columns: repeat(3, minmax(0, 1fr));
      gap: 12px;
      margin-top: 14px;
    }
    .resource-policy {
      display: flex;
      flex-wrap: wrap;
      gap: 8px;
      margin-top: 12px;
    }
    .resource-policy span {
      border: 1px solid var(--line);
      border-radius: 999px;
      padding: 6px 9px;
      background: #f8fafc;
      color: var(--muted);
      font-size: 11px;
      font-weight: 800;
    }
    .resource-policy span.warn {
      border-color: #fed7aa;
      background: #fff7ed;
      color: #9a3412;
    }
    .resource-policy b {
      margin-right: 4px;
      color: var(--ink);
    }
    .resource-card {
      min-width: 0;
      border: 1px solid var(--line);
      border-radius: 8px;
      padding: 13px;
      background: #fff;
    }
    .resource-card-head {
      display: flex;
      align-items: flex-start;
      justify-content: space-between;
      gap: 12px;
      min-height: 45px;
      margin-bottom: 8px;
    }
    .resource-card-head span {
      color: var(--muted);
      font-size: 11px;
      font-weight: 900;
      text-transform: uppercase;
    }
    .resource-card-head b {
      display: block;
      margin-top: 4px;
      font-size: 18px;
      line-height: 1.15;
      overflow-wrap: anywhere;
    }
    .resource-card-head small {
      color: var(--muted);
      font-size: 11px;
      font-weight: 800;
      text-align: right;
    }
    .resource-chart {
      display: block;
      width: 100%;
      height: 150px;
      overflow: visible;
    }
    .resource-chart .grid-line {
      stroke: #e5e7eb;
      stroke-width: 1;
      vector-effect: non-scaling-stroke;
    }
    .resource-chart .axis-label {
      fill: #64748b;
      font-size: 10px;
      font-weight: 700;
    }
    .resource-chart polyline {
      fill: none;
      stroke-linecap: round;
      stroke-linejoin: round;
      stroke-width: 2.5;
      vector-effect: non-scaling-stroke;
    }
    .resource-chart-empty {
      display: grid;
      place-items: center;
      height: 150px;
      color: var(--muted);
      font-size: 12px;
      font-weight: 800;
      text-align: center;
      border: 1px dashed var(--line);
      border-radius: 6px;
      background: #f8fafc;
    }
    .resource-legend {
      display: flex;
      flex-wrap: wrap;
      gap: 10px;
      margin-top: 8px;
      color: var(--muted);
      font-size: 11px;
      font-weight: 800;
    }
    .resource-legend i {
      display: inline-block;
      width: 14px;
      height: 3px;
      margin-right: 5px;
      border-radius: 2px;
      vertical-align: middle;
      background: var(--series);
    }
    @media (max-width: 980px) {
      .dashboard-grid,
      .dashboard-split,
      .collection-stage-grid,
      .collection-pipeline,
      .resource-grid {
        grid-template-columns: 1fr;
      }
      .collection-metrics,
      .db-health-grid {
        grid-template-columns: repeat(2, minmax(0, 1fr));
      }
    }
    @media (max-width: 640px) {
      .collection-head {
        display: grid;
      }
      .collection-switch-panel {
        align-items: stretch;
        flex-direction: column;
      }
      .dashboard-progress-actions {
        justify-content: flex-start;
        margin-left: 0;
        max-width: 100%;
        text-align: left;
      }
      .collection-metrics,
      .db-health-grid {
        grid-template-columns: 1fr;
      }
      .dashboard-map-wrap {
        height: 340px;
      }
    }
  `;
  document.head.appendChild(css);

  function html(value) {
    const div = document.createElement("div");
    div.textContent = value == null ? "" : String(value);
    return div.innerHTML;
  }

  function number(value) {
    const parsed = Number(value);
    return Number.isFinite(parsed) ? parsed : 0;
  }

  function fmtInt(value) {
    return new Intl.NumberFormat("en-US").format(number(value));
  }

  function secondsBetween(start, finish) {
    if (!start) return null;
    const startMs = Date.parse(String(start).replace("+00:00", "Z"));
    const finishMs = finish ? Date.parse(String(finish).replace("+00:00", "Z")) : Date.now();
    if (!Number.isFinite(startMs) || !Number.isFinite(finishMs)) return null;
    return Math.max(0, Math.round((finishMs - startMs) / 1000));
  }

  function formatDuration(seconds) {
    if (seconds == null || seconds === "" || Number.isNaN(Number(seconds))) return "-";
    const value = Math.max(0, Math.round(Number(seconds)));
    const hours = Math.floor(value / 3600);
    const minutes = Math.floor((value % 3600) / 60);
    const secs = value % 60;
    if (hours) return `${hours}h ${minutes}m`;
    if (minutes) return `${minutes}m ${secs}s`;
    return `${secs}s`;
  }

  function formatTime(value) {
    if (!value) return "-";
    const date = new Date(String(value).replace("+00:00", "Z"));
    if (Number.isNaN(date.getTime())) return String(value);
    return date.toLocaleString();
  }

  function formatBytes(value) {
    let size = Math.max(0, number(value));
    const units = ["B", "KB", "MB", "GB", "TB"];
    let index = 0;
    while (size >= 1024 && index < units.length - 1) {
      size /= 1024;
      index += 1;
    }
    const digits = index >= 3 ? 1 : 0;
    return `${size.toFixed(digits)} ${units[index]}`;
  }

  function shortTime(value) {
    if (!value) return "-";
    const date = new Date(String(value).replace("+00:00", "Z"));
    if (Number.isNaN(date.getTime())) return "-";
    return date.toLocaleTimeString([], { hour: "2-digit", minute: "2-digit" });
  }

  function chartSamples(payload) {
    const samples = Array.isArray(payload?.resourceHistory?.samples)
      ? payload.resourceHistory.samples
      : [];
    if (samples.length <= 240) return samples;
    const step = (samples.length - 1) / 239;
    return Array.from({ length: 240 }, (_value, index) => samples[Math.round(index * step)]);
  }

  function latestSample(samples) {
    return samples.length ? samples[samples.length - 1] : {};
  }

  function recentPhaseEta(payload, progress) {
    const allSamples = Array.isArray(payload?.resourceHistory?.samples)
      ? payload.resourceHistory.samples
      : [];
    const phase = progress.phase || "";
    const samples = allSamples
      .filter((sample) => !phase || sample.phase === phase)
      .slice(-30)
      .map((sample) => {
        const phaseTotal = number(sample.phaseTotal);
        return {
          at: new Date(String(sample.at || "").replace("+00:00", "Z")).getTime(),
          processed: phaseTotal > 0 ? number(sample.phaseProcessed) : number(sample.sourceCandidatesProcessed),
          total: phaseTotal > 0 ? phaseTotal : number(sample.sourceCandidatesTotal)
        };
      })
      .filter((sample) => Number.isFinite(sample.at) && sample.total > 0);
    if (samples.length < 2) return null;

    const latest = samples[samples.length - 1];
    const earliest = samples.find((sample) => sample.processed < latest.processed);
    if (!earliest) return null;
    const elapsedSeconds = (latest.at - earliest.at) / 1000;
    const completed = latest.processed - earliest.processed;
    if (elapsedSeconds <= 0 || completed <= 0) return null;

    const seconds = Math.round((latest.total - latest.processed) / (completed / elapsedSeconds));
    if (!Number.isFinite(seconds) || seconds < 0) return null;
    return {
      seconds,
      finishAt: new Date(Date.now() + (seconds * 1000)).toISOString()
    };
  }

  function seriesPoints(samples, key, width = 600, height = 126) {
    if (!samples.length) return "";
    const left = 34;
    const right = 8;
    const top = 8;
    const bottom = 20;
    const plotWidth = width - left - right;
    const plotHeight = height - top - bottom;
    return samples.map((sample, index) => {
      const raw = Number(sample?.[key]);
      if (!Number.isFinite(raw)) return null;
      const x = left + (samples.length === 1 ? plotWidth : index / (samples.length - 1) * plotWidth);
      const y = top + (1 - Math.max(0, Math.min(100, raw)) / 100) * plotHeight;
      return `${x.toFixed(1)},${y.toFixed(1)}`;
    }).filter(Boolean).join(" ");
  }

  function resourceChart(samples, series) {
    if (!samples.length) {
      return `<div class="resource-chart-empty">Resource samples will appear during collection.</div>`;
    }
    const start = shortTime(samples[0]?.at);
    const end = shortTime(samples[samples.length - 1]?.at);
    const lines = series.map(item => {
      const points = seriesPoints(samples, item.key);
      return points ? `<polyline points="${points}" stroke="${item.color}"></polyline>` : "";
    }).join("");
    return `<svg class="resource-chart" viewBox="0 0 600 126" role="img" aria-label="Resource usage over time">
      <line class="grid-line" x1="34" y1="8" x2="592" y2="8"></line>
      <line class="grid-line" x1="34" y1="57" x2="592" y2="57"></line>
      <line class="grid-line" x1="34" y1="106" x2="592" y2="106"></line>
      <text class="axis-label" x="1" y="12">100%</text>
      <text class="axis-label" x="14" y="61">50%</text>
      <text class="axis-label" x="20" y="110">0%</text>
      ${lines}
      <text class="axis-label" x="34" y="123">${html(start)}</text>
      <text class="axis-label" x="592" y="123" text-anchor="end">${html(end)}</text>
    </svg>`;
  }

  function resourcePanelMarkup(payload, options = {}) {
    const samples = chartSamples(payload);
    const latest = latestSample(samples);
    const cpu = Number.isFinite(Number(latest.cpuPercent)) ? `${number(latest.cpuPercent).toFixed(1)}%` : "-";
    const collectorCpu = Number.isFinite(Number(latest.collectorCpuPercent))
      ? `${number(latest.collectorCpuPercent).toFixed(1)}% collector`
      : "Collector warming up";
    const memory = Number.isFinite(Number(latest.memoryPercent)) ? `${number(latest.memoryPercent).toFixed(1)}%` : "-";
    const disk = Number.isFinite(Number(latest.diskPercent)) ? `${number(latest.diskPercent).toFixed(1)}%` : "-";
    const interval = number(payload?.resourceHistory?.intervalSeconds) || 30;
    const workers = payload?.progress?.workerConfig || {};
    const governor = payload?.progress?.resourceGovernor || {};
    const isShop = options.kind === "shops";
    const shopPhase = String(payload?.progress?.phase || "");
    const workerText = isShop
      ? shopPhase.startsWith("overture_")
        ? `${fmtInt(payload?.progress?.threads || 4)} Overture import threads`
        : shopPhase.startsWith("inventory")
          ? "Wine-shop inventory workers"
          : "Waiting for shop collection"
      : workers.discovery
        ? `${fmtInt(workers.discovery)} discovery / ${fmtInt(workers.html)} HTML / ${fmtInt(workers.pdf)} PDF`
        : "Waiting for collection";
    const limitText = isShop
      ? `Memory limit ${payload?.progress?.memoryLimit || "18GB"} / Disk 85%`
      : workers.targetCpuPercent
        ? `CPU ${fmtInt(workers.targetCpuPercent)}% / Memory ${fmtInt(workers.maxMemoryPercent)}% / Disk ${fmtInt(workers.maxDiskPercent)}%`
        : "CPU 80% / Memory 80% / Disk 85%";
    const controllerText = governor.throttled
      ? `${governor.reason || "Resource limit active"} / dispatch ${fmtInt(governor.pendingLimit)}`
      : governor.configuredWorkers
        ? `Full capacity / dispatch ${fmtInt(governor.pendingLimit)}`
        : "Ready";
    return `<section class="dash-panel" data-dashboard-section="resources">
      <div class="collection-head">
        <div>
          <p class="dash-kicker">Server resources</p>
          <h2>Collection resource usage</h2>
        </div>
        <span class="dash-pill">${html(fmtInt(samples.length))} samples / every ${html(fmtInt(interval))}s</span>
      </div>
      <div class="resource-policy">
        <span><b>Workers</b>${html(workerText)}</span>
        <span><b>Safety limits</b>${html(limitText)}</span>
        <span class="${governor.throttled ? "warn" : ""}"><b>Controller</b>${html(controllerText)}</span>
      </div>
      <div class="resource-grid">
        <article class="resource-card">
          <div class="resource-card-head"><div><span>CPU</span><b>${html(cpu)}</b></div><small>${html(collectorCpu)}<br>${html(fmtInt(latest.cores || 0))} cores</small></div>
          ${resourceChart(samples, [
            { key: "cpuPercent", color: "#b0123f" },
            { key: "collectorCpuPercent", color: "#2563eb" }
          ])}
          <div class="resource-legend"><span><i style="--series:#b0123f"></i>Server</span><span><i style="--series:#2563eb"></i>${html(isShop ? "Wine-shop collector" : "Collector + PDF workers")}</span></div>
        </article>
        <article class="resource-card">
          <div class="resource-card-head"><div><span>Memory</span><b>${html(memory)}</b></div><small>${html(formatBytes(latest.memoryUsedBytes))} / ${html(formatBytes(latest.memoryTotalBytes))}<br>Collector ${html(formatBytes(latest.collectorMemoryBytes))}</small></div>
          ${resourceChart(samples, [{ key: "memoryPercent", color: "#0f766e" }])}
          <div class="resource-legend"><span><i style="--series:#0f766e"></i>Server memory</span></div>
        </article>
        <article class="resource-card">
          <div class="resource-card-head"><div><span>Storage</span><b>${html(disk)}</b></div><small>${html(formatBytes(latest.diskUsedBytes))} / ${html(formatBytes(latest.diskTotalBytes))}<br>${html(formatBytes(latest.diskFreeBytes))} free</small></div>
          ${resourceChart(samples, [{ key: "diskPercent", color: "#d97706" }])}
          <div class="resource-legend"><span><i style="--series:#d97706"></i>Disk used</span></div>
        </article>
      </div>
    </section>`;
  }

  async function fetchJson(path, fallback) {
    try {
      const response = await fetch(path, { cache: "no-store" });
      return response.ok ? response.json() : fallback;
    } catch (_error) {
      return fallback;
    }
  }

  function isEmptyGuidePayload(payload) {
    if (!payload || payload.error) return true;
    const progress = payload.progress || {};
    const counts = payload.counts || {};
    return !progress.status && !number(counts.targets || counts.wineLines || counts.wineListSources);
  }

  async function fetchLiveGuideCollection() {
    const [proxied, shops, resourceHistory] = await Promise.all([
      fetchJson("/api/guide-collection", null),
      fetchJson("/api/shop-collection", null),
      fetchJson("/data/resource-history.json", null)
    ]);
    state.shopPayload = shops;
    if (proxied && resourceHistory?.samples) proxied.resourceHistory = resourceHistory;
    if (!isEmptyGuidePayload(proxied)) return proxied;
    return proxied;
  }

  async function startShopCollection(phase) {
    if (state.shopActionInFlight) return;
    const label = phase === "overture"
      ? "global Overture wine-shop discovery"
      : phase === "merchant_scan"
        ? "one-time merchant registry scan"
        : "wine-shop inventory refresh";
    const password = window.prompt(`Enter the admin password to start the ${label}.`);
    if (!password) return;
    state.shopActionInFlight = true;
    state.shopActionMessage = `Starting ${label}...`;
    renderCollection();
    try {
      const response = await fetch("/api/shop-collection", {
        method: "POST",
        headers: { "content-type": "application/json" },
        cache: "no-store",
        body: JSON.stringify({ password, phase })
      });
      const payload = await response.json().catch(() => ({}));
      state.shopActionMessage = payload.message || payload.error || `HTTP ${response.status}`;
      if (response.ok && payload.ok !== false) {
        window.setTimeout(() => loadGuideStats({ force: true }), 1500);
      }
    } catch (error) {
      state.shopActionMessage = `Could not start wine-shop collection: ${error.message || error}`;
    } finally {
      state.shopActionInFlight = false;
      renderCollection();
    }
  }

  async function startGuideRecollection(phase = "inventory") {
    if (state.guideActionInFlight) return;
    const directory = phase === "directory";
    const label = directory ? "restaurant directory update" : "restaurant wine-list scan";
    const password = window.prompt(`Enter the admin password to start the ${label}.`);
    if (!password) return;
    state.guideActionInFlight = true;
    state.guideActionKind = "";
    state.guideActionMessage = `Starting ${label}...`;
    renderCollection();
    try {
      const response = await fetch("/api/guide-collection", {
        method: "POST",
        headers: { "content-type": "application/json" },
        cache: "no-store",
        body: JSON.stringify({ password, phase })
      });
      const payload = await response.json().catch(() => ({}));
      if (!response.ok || payload.ok === false) {
        state.guideActionKind = "bad";
        state.guideActionMessage = payload.error || `Could not start recollection. HTTP ${response.status}`;
        return;
      }
      state.guideActionKind = "good";
      state.guideActionMessage = payload.message || `${label} started.`;
      state.guideLoadedOnce = false;
      await loadGuideStats({ force: true });
      window.setTimeout(() => loadGuideStats({ force: true }), 2500);
      window.setTimeout(() => loadGuideStats({ force: true }), 8000);
    } catch (error) {
      state.guideActionKind = "bad";
      state.guideActionMessage = `Could not reach the collection API: ${error.message || error}`;
    } finally {
      state.guideActionInFlight = false;
      if (state.activeView === "collection") renderCollection();
    }
  }

  function ensureDataViews() {
    const commandBar = document.querySelector(".command-bar");
    let databaseView = document.querySelector("#databaseView");
    if (!databaseView) {
      databaseView = document.querySelector("#dashboardView") || document.createElement("section");
      databaseView.id = "databaseView";
      databaseView.className = "app-view";
      databaseView.dataset.viewPanel = "database";
      if (!databaseView.isConnected) commandBar?.insertAdjacentElement("beforebegin", databaseView);
    }

    let collectionView = document.querySelector("#collectionView");
    if (!collectionView) {
      collectionView = document.createElement("section");
      collectionView.id = "collectionView";
      collectionView.className = "app-view";
      collectionView.dataset.viewPanel = "collection";
      commandBar?.insertAdjacentElement("beforebegin", collectionView);
    }
    return { databaseView, collectionView };
  }

  function cleanTabs() {
    let nav = document.querySelector(".view-tabs");
    if (!nav) {
      nav = document.createElement("nav");
      nav.className = "view-tabs";
      document.querySelector(".app-header")?.insertAdjacentElement("afterend", nav);
    }
    nav.innerHTML = [
      ["search", "Wine Search"],
      ["database", "Database Map"],
      ["collection", "Collection"]
    ].map(([key, label]) => `<button class="view-tab" type="button" data-view="${key}">${label}</button>`).join("");
    document.querySelector("#watchlistView")?.remove();
    document.querySelectorAll(".source-strip").forEach((node) => node.remove());
    return nav;
  }

  function activate(view) {
    state.activeView = view;
    ensureDataViews();
    document.querySelectorAll(".view-tab").forEach((tab) => {
      tab.classList.toggle("active", tab.dataset.view === view);
    });
    document.querySelectorAll(".app-view").forEach((panel) => {
      panel.classList.toggle("active", panel.dataset.viewPanel === view);
    });
    const showSearch = view === "search";
    document.querySelector(".command-bar")?.classList.toggle("hidden", !showSearch);
    document.querySelector(".workspace")?.classList.toggle("hidden", !showSearch);
    document.querySelector(".map-panel")?.classList.toggle("hidden", !showSearch);
    if (view === "database") {
      renderDatabase();
      if (!state.guideLoadedOnce) loadGuideStats({ force: true });
    }
    if (view === "collection") {
      renderCollection();
      if (!state.guideLoadedOnce) loadGuideStats({ force: true });
    }
    if (showSearch) {
      try {
        if (typeof renderMap === "function") renderMap(typeof latestResults === "undefined" ? [] : latestResults);
      } catch (_error) {}
    }
  }

  function progressValues(payload) {
    const savedProgress = payload?.progress || {};
    const counts = payload?.counts || {};
    const latestRun = payload?.lastInventoryCollection || payload?.latestRuns?.[0] || {};
    const summary = payload?.collectionSummary || {};
    const progressTime = Date.parse(savedProgress.generatedAt || savedProgress.finishedAt || savedProgress.startedAt || "") || 0;
    const latestFinishTime = Date.parse(latestRun.finished_at || "") || 0;
    const progressSuperseded = Boolean(latestFinishTime && latestFinishTime > progressTime && savedProgress.status !== "running");
    const progress = progressSuperseded
      ? {
          ...savedProgress,
          status: "completed",
          phase: "completed",
          stale: false,
          staleSeconds: 0,
          runId: latestRun.id,
          startedAt: latestRun.started_at,
          finishedAt: latestRun.finished_at,
          processedTargets: latestRun.websites_checked,
          websitesChecked: latestRun.websites_checked,
          totalWebsites: latestRun.target_count,
          wineListsFound: latestRun.wine_lists_found,
          wineLinesFound: latestRun.wine_lines_found,
          errors: latestRun.errors,
          currentTarget: "",
          currentUrl: "",
          elapsedSeconds: secondsBetween(latestRun.started_at, latestRun.finished_at),
          durationSeconds: secondsBetween(latestRun.started_at, latestRun.finished_at),
          progressPercent: 100,
        }
      : savedProgress;
    const running = progress.status === "running" && !progress.stale;
    const stopped = progress.status === "stalled" || Boolean(progress.stale);
    const completed = !running && (progress.status === "completed" || latestRun.status === "completed");
    const summaryTotal = number(summary.totalTargets || counts.targets || latestRun.target_count);
    const summaryChecked = number(summary.checkedTargets || latestRun.websites_checked);
    const restaurantFinalized = number(progress.processedTargets ?? progress.websitesChecked ?? latestRun.websites_checked);
    const restaurantTotal = number(progress.totalWebsites || summary.totalTargets || counts.targets || latestRun.target_count);
    const phaseProcessed = number(progress.phaseProcessed);
    const phaseTotal = number(progress.phaseTotal);
    const pipelineProcessed = number(progress.sourceCandidatesProcessed);
    const pipelineTotal = number(progress.sourceCandidatesTotal);
    const hasPhaseWork = running && phaseTotal > 0;
    const hasPipelineWork = running && !hasPhaseWork && pipelineTotal > 0;
    const rawProcessed = hasPhaseWork ? phaseProcessed : hasPipelineWork ? pipelineProcessed : restaurantFinalized;
    const rawTotal = hasPhaseWork ? phaseTotal : hasPipelineWork ? pipelineTotal : restaurantTotal;
    const useSummaryProgress = !running && completed && summaryTotal && summaryChecked && (!rawTotal || rawTotal < summaryTotal);
    const processed = useSummaryProgress ? summaryChecked : rawProcessed;
    const total = useSummaryProgress ? summaryTotal : rawTotal;
    const reportedPercent = hasPhaseWork
      ? number(progress.phaseProgressPercent)
      : number(progress.progressPercent);
    const percent = total ? Math.min(100, Math.max(0, useSummaryProgress ? ((processed / total) * 100) : (reportedPercent || ((processed / total) * 100)))) : 0;
    return {
      progress,
      counts,
      latestRun,
      summary,
      progressSuperseded,
      running,
      stopped,
      processed,
      total,
      remaining: total ? Math.max(0, total - processed) : 0,
      restaurantFinalized,
      restaurantTotal,
      workLabel: hasPhaseWork ? "Current phase" : hasPipelineWork ? "Pipeline items" : "Restaurants",
      percent,
      elapsed: progress.elapsedSeconds ?? secondsBetween(progress.startedAt || latestRun.started_at, progress.finishedAt || latestRun.finished_at),
      duration: progress.durationSeconds ?? secondsBetween(progress.startedAt || latestRun.started_at, progress.finishedAt || latestRun.finished_at),
      status: running ? "Collecting" : stopped ? "Stopped" : latestRun.status === "completed" ? "Done" : "Ready"
    };
  }

  function statusLabel(status) {
    const labels = {
      found: "Verified wine list",
      no_wine_list: "No wine list",
      not_checked: "Not checked yet",
      missing_website: "Website missing",
      review: "Needs review",
      error: "Error"
    };
    return labels[status] || status || "Unknown";
  }

  function targetKind(target) {
    const status = target?.status || "";
    if (number(target.verifiedWineListCount) > 0 || (
      target.wineListStatus === "found" &&
      target.wineListParserStatus === "parsed" &&
      number(target.chosenWineLineCount) > 0 &&
      !String(target.wineListLastError || "").trim()
    )) return "found";
    if (status === "no_wine_list") return "none";
    return "pending";
  }

  function targetPill(target) {
    const kind = targetKind(target);
    const cls = kind === "found" ? "good" : kind === "none" ? "bad" : "warn";
    const label = kind === "found" ? "Verified wine list" : kind === "none" ? "No wine list" : "Needs review";
    return `<span class="dash-pill ${cls}">${html(label)}</span>`;
  }

  function visibleMapTargets(payload) {
    return (payload?.mapTargets || [])
      .filter((target) => target.lat !== null && target.lng !== null && target.lat !== "" && target.lng !== "")
      .filter((target) => String(target.websiteUrl || "").trim() !== "")
      .map((target) => ({ ...target, lat: Number(target.lat), lng: Number(target.lng) }))
      .filter((target) => Number.isFinite(target.lat) && Number.isFinite(target.lng));
  }

  function shopDatabasePayload() {
    const payload = state.shopPayload || {};
    return {
      mapTargets: (payload.mapMerchants || []).map((merchant) => {
        const status = merchant.inventoryStatus === "found"
          ? "found"
          : merchant.inventoryStatus === "no_wine_list"
            ? "no_wine_list"
            : "review";
        return {
          id: `shop-${merchant.id}`,
          name: merchant.name,
          merchantType: merchant.merchantType || "Wine Shop",
          country: merchant.country,
          city: merchant.city,
          address: merchant.address,
          lat: merchant.lat,
          lng: merchant.lng,
          websiteUrl: merchant.websiteUrl || merchant.wineSearcherUrl,
          wineListUrl: merchant.inventoryUrl || merchant.websiteUrl || merchant.wineSearcherUrl,
          wineListType: "inventory",
          lastCheckedAt: merchant.lastCheckedAt,
          status,
          verifiedWineListCount: status === "found" ? Number(merchant.sourceCount || 1) : 0,
          chosenWineLineCount: Number(merchant.productCount || 0),
          productCount: Number(merchant.productCount || 0),
          sourceCount: Number(merchant.sourceCount || 0)
        };
      })
    };
  }

  function activeDatabasePayload() {
    return state.databaseMode === "shops" ? shopDatabasePayload() : (state.guidePayload || {});
  }

  function markerColor(kind) {
    if (kind === "found") return "#16a34a";
    if (kind === "none") return "#dc2626";
    return "#f59e0b";
  }

  function markerLabel(kind) {
    if (kind === "found") return "F";
    if (kind === "none") return "N";
    return "R";
  }

  function markerZIndex(kind) {
    if (kind === "found") return 300;
    if (kind === "none") return 200;
    return 100;
  }

  function getGoogleMapsKey() {
    return window.STARWINE_CONFIG?.googleMapsApiKey || localStorage.getItem("googleMapsApiKey") || "";
  }

  function loadDashboardGoogleMaps() {
    if (window.google?.maps) return Promise.resolve(window.google.maps);
    const key = getGoogleMapsKey();
    if (!key) return Promise.resolve(null);
    if (state.dashboardMapPromise) return state.dashboardMapPromise;
    state.dashboardMapPromise = new Promise((resolve, reject) => {
      const callbackName = `initDashboardMap${Date.now()}`;
      const previousAuthFailure = window.gm_authFailure;
      let settled = false;
      window.gm_authFailure = () => {
        window.gm_authFailure = previousAuthFailure;
        if (typeof previousAuthFailure === "function") previousAuthFailure();
        if (!settled) {
          settled = true;
          reject(new Error(`Google Maps rejected ${window.location.origin}. Add ${window.location.origin}/* to this API key's Website restrictions and make sure Maps JavaScript API and billing are enabled.`));
        }
      };
      window[callbackName] = () => {
        delete window[callbackName];
        window.gm_authFailure = previousAuthFailure;
        if (!settled) {
          settled = true;
          resolve(window.google.maps);
        }
      };
      const script = document.createElement("script");
      script.src = `https://maps.googleapis.com/maps/api/js?key=${encodeURIComponent(key)}&callback=${callbackName}&v=weekly&loading=async`;
      script.async = true;
      script.defer = true;
      script.onerror = () => {
        window.gm_authFailure = previousAuthFailure;
        if (!settled) {
          settled = true;
          reject(new Error("Google Maps failed to load. Check the API key, billing, and allowed Website restrictions."));
        }
      };
      document.head.appendChild(script);
    });
    return state.dashboardMapPromise;
  }

  function markerIcon(maps, color, label = "") {
    const svg = `<svg xmlns="http://www.w3.org/2000/svg" width="30" height="38" viewBox="0 0 30 38">
      <path fill="${color}" stroke="#ffffff" stroke-width="2.2" d="M15 2C8.1 2 2.5 7.6 2.5 14.5 2.5 24 15 36 15 36s12.5-12 12.5-21.5C27.5 7.6 21.9 2 15 2Z"/>
      <circle cx="15" cy="14.5" r="6" fill="rgba(255,255,255,0.95)"/>
      <text x="15" y="18.2" text-anchor="middle" font-family="Arial, sans-serif" font-size="9" font-weight="800" fill="${color}">${label}</text>
    </svg>`;
    return {
      url: `data:image/svg+xml;charset=UTF-8,${encodeURIComponent(svg)}`,
      scaledSize: new maps.Size(24, 30),
      anchor: new maps.Point(12, 30)
    };
  }

  function mapSignature(targets) {
    return `${state.databaseMode}|${targets
      .map((target) => [
        target.id,
        target.status,
        target.lat,
        target.lng,
        target.wineListCount,
        target.wineLineCount,
        target.verifiedWineListCount,
        target.reviewSourceCount,
        target.wineListParserStatus,
        target.chosenWineLineCount
      ].join(":"))
      .join("|")}`;
  }

  function targetFeature(target) {
    return {
      type: "Feature",
      geometry: {
        type: "Point",
        coordinates: [Number(target.lng), Number(target.lat)]
      },
      properties: {
        id: String(target.id),
        kind: targetKind(target),
        name: target.name || "Restaurant"
      }
    };
  }

  function infoHtml(target) {
    const location = [target.city, target.country].filter(Boolean).join(", ");
    const kind = targetKind(target);
    const wineListLabel = kind === "found" ? "Wine list" : "Review source";
    const wineList = target.wineListUrl
      ? `<br><a href="${html(target.wineListUrl)}" target="_blank" rel="noreferrer">${html(wineListLabel)}</a>`
      : "";
    const website = target.websiteUrl && target.websiteUrl !== target.wineListUrl
      ? `<br><a href="${html(target.websiteUrl)}" target="_blank" rel="noreferrer">Official website</a>`
      : "";
    return `<strong>${html(target.name || "Unknown")}</strong><br>${html(location || "Unknown location")}<br>${targetPill(target)}${wineList}${website}`;
  }

  async function renderDashboardMap(payload, options = {}) {
    const mapEl = document.querySelector("#dashboardDbMap");
    const fallbackEl = document.querySelector("#dashboardMapFallback");
    if (!mapEl || !fallbackEl) return;
    if (state.activeView !== "database") return;
    const targets = visibleMapTargets(payload);
    if (!targets.length) {
      const noun = state.databaseMode === "shops" ? "wine shops" : "restaurants";
      if (state.dashboardMarkers.size) return;
      for (const marker of state.dashboardMarkers.values()) marker.setMap(null);
      state.dashboardMarkers.clear();
      fallbackEl.classList.remove("hidden");
      fallbackEl.innerHTML = `<b>No mapped ${noun} yet</b><span>Coordinates will appear as the collector resolves ${noun}.</span>`;
      return;
    }
    try {
      const maps = await loadDashboardGoogleMaps();
      if (!maps) {
        fallbackEl.classList.remove("hidden");
        fallbackEl.innerHTML = `<b>Map unavailable</b><span>Google Maps key is not available in this browser.</span>`;
        return;
      }
      fallbackEl.classList.add("hidden");
      if (!state.dashboardMap || state.dashboardMapEl !== mapEl) {
        state.dashboardDataLayer?.setMap(null);
        state.dashboardDataLayer = null;
        state.dashboardDataClickBound = false;
        state.dashboardMapEl = mapEl;
        state.dashboardMap = new maps.Map(mapEl, {
          center: { lat: 30, lng: 8 },
          zoom: 2,
          mapTypeControl: false,
          streetViewControl: false,
          fullscreenControl: true,
          clickableIcons: false,
          styles: [
            { featureType: "poi", stylers: [{ visibility: "off" }] },
            { featureType: "transit", stylers: [{ visibility: "off" }] }
          ]
        });
        state.dashboardInfoWindow = new maps.InfoWindow();
        state.dashboardMapHasFit = false;
      }
      const signature = mapSignature(targets);
      const bounds = new maps.LatLngBounds();
      targets.forEach((target) => bounds.extend({ lat: target.lat, lng: target.lng }));
      if (!state.dashboardDataLayer) {
        state.dashboardDataLayer = new maps.Data({ map: state.dashboardMap });
        state.dashboardDataLayer.setStyle((feature) => ({
          icon: markerIcon(maps, markerColor(feature.getProperty("kind")), markerLabel(feature.getProperty("kind"))),
          zIndex: markerZIndex(feature.getProperty("kind")),
          title: feature.getProperty("name") || "Restaurant"
        }));
      }
      if (!state.dashboardDataClickBound) {
        state.dashboardDataLayer.addListener("click", (event) => {
          selectDashboardTarget(event.feature.getProperty("id"), true, event.latLng);
        });
        state.dashboardDataClickBound = true;
      }
      if (signature !== state.dashboardMapSignature) {
        state.dashboardDataLayer.forEach((feature) => state.dashboardDataLayer.remove(feature));
        state.dashboardDataLayer.addGeoJson({
          type: "FeatureCollection",
          features: targets.map(targetFeature)
        });
        state.dashboardMapSignature = signature;
      }
      if (!state.dashboardMapHasFit || options.fit) {
        state.dashboardMap.fitBounds(bounds, 56);
        if (targets.length === 1) state.dashboardMap.setZoom(12);
        state.dashboardMapHasFit = true;
      }
      if (state.activeTargetId) selectDashboardTarget(state.activeTargetId, false);
    } catch (error) {
      fallbackEl.classList.remove("hidden");
      fallbackEl.innerHTML = `<b>Map unavailable</b><span>${html(error.message)}</span>`;
    }
  }

  function selectDashboardTarget(id, shouldScroll = true, clickedLatLng = null) {
    state.activeTargetId = String(id || "");
    const payload = activeDatabasePayload();
    const target = (payload.mapTargets || []).find((item) => String(item.id) === state.activeTargetId);
    if (!target) return;
    const marker = state.dashboardMarkers.get(String(target.id));
    const position = clickedLatLng || (Number.isFinite(Number(target.lat)) && Number.isFinite(Number(target.lng))
      ? new google.maps.LatLng(Number(target.lat), Number(target.lng))
      : null);
    if (state.dashboardMap && position) {
      state.dashboardMap.panTo(position);
      if (state.dashboardMap.getZoom() < 8) state.dashboardMap.setZoom(8);
      state.dashboardInfoWindow?.setContent(infoHtml(target));
      state.dashboardInfoWindow?.setPosition(position);
      state.dashboardInfoWindow?.open({ map: state.dashboardMap });
    }
    renderSelectedTarget(payload);
    if (shouldScroll) {
      document.querySelector("#selectedRestaurant")?.scrollIntoView({ behavior: "smooth", block: "start" });
    }
  }

  function clearDashboardSelection() {
    state.activeTargetId = null;
    state.dashboardInfoWindow?.close();
    const payload = activeDatabasePayload();
    renderSelectedTarget(payload);
    renderDashboardMap(payload, { fit: true });
    document.querySelector('[data-dashboard-section="map"]')?.scrollIntoView({ behavior: "smooth", block: "start" });
  }

  function selectedTargetMarkup(payload) {
    const target = (payload?.mapTargets || []).find((item) => String(item.id) === String(state.activeTargetId || ""));
    if (!target) {
      const noun = state.databaseMode === "shops" ? "wine shop" : "restaurant";
      return `<div class="selected-target empty">
        <h3>No ${noun} selected</h3>
        <p>Click a marker on the map to inspect one ${noun}.</p>
      </div>`;
    }
    const location = [target.city, target.country].filter(Boolean).join(", ");
    const googleMapUrl = `https://www.google.com/maps/search/?api=1&query=${encodeURIComponent([target.name, target.city, target.country].filter(Boolean).join(" "))}`;
    const kind = targetKind(target);
    const wineListLabel = kind !== "found"
      ? "Review source"
      : /pdf|file/i.test(String(target.wineListType || target.wineListUrl || ""))
      ? "Wine list file"
      : "Wine list";
    return `<div class="selected-target">
      <div>
        <p class="dash-kicker">Selected ${state.databaseMode === "shops" ? "wine shop" : "restaurant"}</p>
        <h3>${html(target.name || "Unknown")}</h3>
        <p>${html(location || "Unknown location")}</p>
      </div>
      <div class="selected-target-grid">
        <div class="metric-box"><span>Status</span><b>${targetPill(target)}</b></div>
        <div class="metric-box"><span>Last checked</span><b>${html(target.lastCheckedAt || "-")}</b></div>
        ${state.databaseMode === "shops" ? `<div class="metric-box"><span>Saved products</span><b>${html(fmtInt(target.productCount))}</b></div>` : ""}
      </div>
      <div class="selected-target-actions">
        ${target.wineListUrl ? `<a class="${kind === "found" ? "" : "secondary"}" href="${html(target.wineListUrl)}" target="_blank" rel="noreferrer">${html(wineListLabel)}</a>` : ""}
        ${target.websiteUrl && target.websiteUrl !== target.wineListUrl ? `<a class="secondary" href="${html(target.websiteUrl)}" target="_blank" rel="noreferrer">Official website</a>` : ""}
        <a class="secondary" href="${html(googleMapUrl)}" target="_blank" rel="noreferrer">Google Maps</a>
        <button class="world-view-button" type="button" data-clear-dashboard-selection title="Reset the map to show every restaurant">
          <span class="world-view-icon" aria-hidden="true">&#8592;</span>
          Back to world map
        </button>
      </div>
    </div>`;
  }

  function renderSelectedTarget(payload) {
    const container = document.querySelector("#selectedRestaurant");
    if (container) container.innerHTML = selectedTargetMarkup(payload);
  }

  function guideMetrics(input) {
    const payload = input || {};
    const values = progressValues(payload);
    const summary = values.summary;
    const progress = values.progress;
    const mapped = visibleMapTargets(payload).length;
    const mappedWithWebsite = number(summary.mappedWithWebsite) || mapped;
    const progressCounts = progress.dbCounts || {};
    const savedLines = number(payload.counts?.wineLines)
      || number(progressCounts.wineLines)
      || number(progress.wineLinesFound);
    const parsedSources = number(summary.parsedSources);
    const reviewSources = number(summary.parseReviewSources);
    const found = number(summary.foundWineList);
    const none = number(summary.noWineList);
    const pending = number(summary.pending) + number(summary.missingWebsite);
    const errorCount = number(summary.errors || values.progress.errors);
    const lastCollectionAt = payload.lastInventoryCollection?.finished_at || payload.lastCollection?.finished_at || "";
    const lastCollectionText = lastCollectionAt ? formatTime(lastCollectionAt) : "Not scanned yet";
    const hasPhaseEta = progress.phaseEstimatedRemainingSeconds !== undefined
      && progress.phaseEstimatedRemainingSeconds !== null;
    const recentEta = hasPhaseEta ? null : recentPhaseEta(payload, progress);
    const etaSeconds = hasPhaseEta
      ? progress.phaseEstimatedRemainingSeconds
      : recentEta?.seconds ?? progress.estimatedRemainingSeconds;
    const etaFinishAt = hasPhaseEta
      ? progress.phaseEstimatedFinishAt
      : recentEta?.finishAt || progress.estimatedFinishAt;
    const etaLabel = hasPhaseEta
      ? "Current phase ETA"
      : recentEta
        ? "Recent-rate ETA"
        : "Rough pipeline ETA";
    const etaText = values.running
      ? `${formatDuration(etaSeconds)}${etaFinishAt ? ` / ${formatTime(etaFinishAt)}` : ""}`
      : formatDuration(values.duration);
    const collectionText = values.running
      ? "The local PC collector is running now."
      : values.stopped
        ? "The local PC collector stopped reporting progress."
        : "No background collection is running right now.";
    const progressTitle = values.running
      ? phaseLabel(progress.phase)
      : values.stopped
        ? "Collection stopped"
        : "Collection status";
    const progressPillClass = values.running ? "good" : values.stopped ? "warn" : "";

    return {
      payload,
      values,
      summary,
      progress,
      mappedWithWebsite,
      savedLines,
      parsedSources,
      reviewSources,
      found,
      none,
      pending,
      errorCount,
      lastCollectionText,
      etaText,
      etaLabel,
      collectionText,
      progressTitle,
      progressPillClass
    };
  }

  function phaseLabel(value) {
    const labels = {
      discovering_wine_sources: "Discovering wine-list links",
      validating_html_sources: "Validating HTML wine-list sources",
      extracting_pdf_sources: "Extracting PDF wine-list sources",
      collecting_wine_pipeline: "Crawling and validating wine lists",
      publishing: "Publishing completed database"
    };
    return labels[value] || "Collecting restaurant wine lists";
  }

  function renderDatabase() {
    const root = ensureDataViews().databaseView;
    const payload = activeDatabasePayload();
    const noun = state.databaseMode === "shops" ? "wine shops" : "restaurants";

    const mapHtml = `<section class="dash-panel" data-dashboard-section="map">
      <div class="collection-head">
        <div>
          <p class="dash-kicker">Built database</p>
          <h2>Database map</h2>
        </div>
        <div>
          <div class="database-mode-control" aria-label="Database type">
            <button type="button" data-database-mode="restaurants" class="${state.databaseMode === "restaurants" ? "active" : ""}">Restaurants</button>
            <button type="button" data-database-mode="shops" class="${state.databaseMode === "shops" ? "active" : ""}">Wine shops</button>
          </div>
          <div class="map-legend">
            <span class="legend-dot" style="--dot:#16a34a">Inventory found</span>
            <span class="legend-dot" style="--dot:#dc2626">No wine list</span>
            <span class="legend-dot" style="--dot:#f59e0b">Pending / review</span>
          </div>
        </div>
      </div>
      <div class="dashboard-map-wrap">
        <div id="dashboardDbMap"></div>
        <div id="dashboardMapFallback" class="dashboard-map-fallback"><b>Loading map</b><span>${html(noun)} coordinates are being prepared.</span></div>
      </div>
    </section>`;

    const selectedHtml = `<section class="dash-panel" id="selectedRestaurant">
      ${selectedTargetMarkup(payload)}
    </section>`;

    const mapAlreadyMounted = Boolean(root.querySelector("#dashboardDbMap")) && root.dataset.databaseMode === state.databaseMode;
    if (!mapAlreadyMounted) {
      root.dataset.databaseMode = state.databaseMode;
      root.innerHTML = `${mapHtml}${selectedHtml}`;
      state.dashboardMapSignature = "";
      state.dashboardMapHasFit = false;
      renderDashboardMap(payload, { fit: true });
      return;
    }
    renderSelectedTarget(payload);
    renderDashboardMap(payload, { fit: false });
  }

  function renderCollection() {
    const root = ensureDataViews().collectionView;
    if (state.collectionMode === "shops") renderShopCollection(root);
    else renderRestaurantCollection(root);
  }

  function collectionSwitchMarkup() {
    const restaurants = state.collectionMode === "restaurants";
    return `<section class="dash-panel collection-switch-panel">
      <div>
        <p class="dash-kicker">Collection</p>
        <h2>${html(restaurants ? "Restaurant wine lists" : "Wine-shop inventories")}</h2>
        <p class="collection-stage-copy">First maintain the place directory, then scan the saved official websites for wine-list content.</p>
      </div>
      <div class="database-mode-control" aria-label="Collection type">
        <button type="button" data-collection-mode="restaurants" class="${restaurants ? "active" : ""}">Restaurants</button>
        <button type="button" data-collection-mode="shops" class="${restaurants ? "" : "active"}">Wine shops</button>
      </div>
    </section>`;
  }

  function renderRestaurantCollection(root) {
    const metrics = guideMetrics(state.guidePayload || {});
    const {
      payload, values, summary, progress, savedLines, parsedSources,
      reviewSources, found, errorCount, lastCollectionText, etaText,
      etaLabel, progressTitle, progressPillClass
    } = metrics;
    const directoryRun = payload.lastDirectoryUpdate
      || (payload.latestRuns || []).find((run) => String(run.sources_requested || "").includes("michelin"))
      || {};
    const inventoryRun = payload.lastInventoryCollection || {};
    const directoryRunning = values.running && ["reading_guides", "saving_targets"].includes(progress.phase);
    const inventoryRunning = values.running && !directoryRunning;
    const directoryUpdated = directoryRun.finished_at ? formatTime(directoryRun.finished_at) : "Not updated yet";
    const withWebsite = number(payload.counts?.withWebsite);

    const stagesHtml = `<div class="collection-stage-grid">
      <section class="dash-panel collection-stage">
        <p class="dash-kicker"><span class="collection-stage-number">1</span>Candidate directory</p>
        <h2>Update restaurant candidates</h2>
        <p class="collection-stage-copy">Save the current Michelin, La Liste, and World's 50 Best restaurants before scanning their websites.</p>
        <div class="collection-metrics">
          <div class="metric-box"><span>Restaurants saved</span><b>${html(fmtInt(payload.counts?.targets))}</b></div>
          <div class="metric-box"><span>Website URLs</span><b>${html(fmtInt(withWebsite))}</b></div>
          <div class="metric-box"><span>Guide sources</span><b>3</b></div>
          <div class="metric-box"><span>Last update</span><b>${html(directoryUpdated)}</b></div>
        </div>
        <div class="collection-stage-schedule"><span>Recommended: once a year</span><button class="dashboard-refresh" type="button" data-start-guide-directory ${values.running || state.guideActionInFlight ? "disabled" : ""}>${html(directoryRunning ? "Updating..." : "Update candidates")}</button></div>
      </section>
      <section class="dash-panel collection-stage">
        <p class="dash-kicker"><span class="collection-stage-number">2</span>Wine-list scan</p>
        <h2>Scan restaurant websites</h2>
        <p class="collection-stage-copy">Revisit saved websites, verify wine-list pages and files, and update searchable wine text.</p>
        <div class="collection-metrics">
          <div class="metric-box"><span>Restaurants scanned</span><b>${html(fmtInt(inventoryRunning ? values.processed : inventoryRun.websites_checked))} / ${html(fmtInt(inventoryRunning ? values.total : inventoryRun.target_count || payload.counts?.targets))}</b></div>
          <div class="metric-box"><span>Verified lists</span><b>${html(fmtInt(found))}</b></div>
          <div class="metric-box"><span>Saved wine lines</span><b>${html(fmtInt(savedLines))}</b></div>
          <div class="metric-box"><span>Last scan</span><b>${html(lastCollectionText)}</b></div>
        </div>
        <div class="collection-stage-schedule"><span>Every 2 weeks</span><button class="dashboard-refresh" type="button" data-start-guide-collection ${values.running || state.guideActionInFlight ? "disabled" : ""}>${html(inventoryRunning ? "Scanning..." : "Scan wine lists")}</button></div>
      </section>
    </div>`;

    const progressHtml = `<section class="dash-panel" data-dashboard-section="progress">
      <div class="collection-head">
        <div><p class="dash-kicker">Current run</p><h2>${html(progressTitle)}</h2></div>
        <div class="selected-target-actions dashboard-progress-actions">
          <span class="dash-pill ${progressPillClass}">${html(values.status)}</span>
          <button class="dashboard-refresh" type="button" data-refresh-collection ${state.guideLoadInFlight ? "disabled" : ""}>${html(state.guideLoadInFlight ? "Refreshing..." : "Refresh")}</button>
          ${state.guideActionMessage ? `<span class="dashboard-action-note ${html(state.guideActionKind)}">${html(state.guideActionMessage)}</span>` : ""}
          ${state.lastRefreshAt ? `<span class="dashboard-action-note">Last refreshed ${html(state.lastRefreshAt)}</span>` : ""}
        </div>
      </div>
      ${restaurantPipelineMarkup(payload, metrics, { directoryRun, inventoryRun, directoryRunning, inventoryRunning })}
      <div class="dash-progress" style="--dash-progress:${html(values.percent)}%"><i></i></div>
      <div class="collection-metrics">
        <div class="metric-box"><span>${html(values.workLabel)}</span><b>${html(fmtInt(values.processed))} / ${html(fmtInt(values.total))}</b></div>
        <div class="metric-box"><span>Elapsed</span><b>${html(formatDuration(values.elapsed))}</b></div>
        <div class="metric-box"><span>${values.running ? etaLabel : "Total time"}</span><b>${html(etaText)}</b></div>
        <div class="metric-box"><span>Current restaurant</span><b>${html(progress.currentTarget || "-")}</b></div>
        <div class="metric-box"><span>Needs review</span><b>${html(fmtInt(number(summary.needsReview)))}</b></div>
        <div class="metric-box"><span>Errors</span><b>${html(fmtInt(errorCount))}</b></div>
      </div>
      <p class="dashboard-action-note">${html(fmtInt(parsedSources))} exact sources verified; ${html(fmtInt(reviewSources))} inconclusive sources remain.</p>
    </section>`;
    root.innerHTML = `${collectionSwitchMarkup()}${stagesHtml}${progressHtml}${resourcePanelMarkup(payload)}`;
  }

  function restaurantPipelineMarkup(payload, metrics, flags) {
    const { values, progress, summary, savedLines, parsedSources, lastCollectionText } = metrics;
    const phase = String(progress.phase || "");
    const failed = ["failed", "error"].includes(String(progress.status || "").toLowerCase())
      || phase === "collection_failed";
    const inventoryComplete = String(flags.inventoryRun?.status || "").toLowerCase() === "completed"
      && Boolean(flags.inventoryRun?.finished_at);
    let activeStage = (values.running || failed) ? number(progress.stageIndex) : 0;
    if (!activeStage && flags.directoryRunning) activeStage = 1;
    if (!activeStage && values.running) {
      if (phase === "preparing_staging") activeStage = 2;
      else if (phase === "publishing") activeStage = 4;
      else activeStage = 3;
    }

    const targets = number(payload.counts?.targets || summary.totalTargets);
    const websites = number(payload.counts?.withWebsite);
    const pipelineFinished = inventoryComplete && !values.running;
    const crawled = number(progress.discoveryProcessed ?? progress.websitesChecked ?? flags.inventoryRun?.websites_checked);
    const crawlTotal = number(progress.discoveryTotal ?? (pipelineFinished ? websites : progress.totalWebsites) ?? flags.inventoryRun?.target_count ?? websites);
    const sourcesChecked = number(progress.sourceCandidatesProcessed ?? summary.totalSources);
    const sourceTotal = number(progress.sourceCandidatesTotal ?? summary.totalSources);
    const stageLabel = progress.stageLabel || (
      activeStage === 1 ? "Update restaurant directory"
        : activeStage === 2 ? "Prepare safe scan database"
          : activeStage === 3 ? "Crawl websites and verify wine-list sources"
            : activeStage === 4 ? "Publish completed database"
              : pipelineFinished ? `Last scan published ${lastCollectionText}`
                : "No restaurant collection is running"
    );

    const steps = [
      {
        index: 1,
        title: "Maintain restaurant directory",
        detail: "Save and merge Michelin, La Liste, and World's 50 Best restaurant candidates.",
        value: `${fmtInt(targets)} restaurants / ${fmtInt(websites)} website URLs`,
        complete: targets > 0 && activeStage !== 1,
      },
      {
        index: 2,
        title: "Prepare safe scan database",
        detail: "Copy the live database to staging so the published search stays available during collection.",
        value: activeStage === 2 ? "Preparing staging database" : pipelineFinished || activeStage > 2 ? "Staging database prepared" : "Waiting for a scan",
        complete: pipelineFinished || activeStage > 2,
      },
      {
        index: 3,
        title: "Crawl and verify wine lists",
        detail: "Crawl official websites while HTML and PDF candidates are verified and saved in parallel.",
        value: `${fmtInt(crawled)} / ${fmtInt(crawlTotal)} websites / ${fmtInt(sourcesChecked)} / ${fmtInt(sourceTotal)} sources`,
        complete: pipelineFinished || activeStage > 3,
      },
      {
        index: 4,
        title: "Publish completed database",
        detail: "Replace the live database only after the full scan succeeds, then expose it to search.",
        value: pipelineFinished ? `${fmtInt(parsedSources)} verified sources / ${fmtInt(savedLines)} searchable lines` : activeStage === 4 ? "Publishing verified snapshot" : "Waiting for completed scan",
        complete: pipelineFinished,
      },
    ];

    const cards = steps.map((step) => {
      const active = activeStage === step.index && (values.running || failed);
      const status = failed && active ? "failed" : active ? "active" : step.complete ? "complete" : "waiting";
      const label = status === "complete" ? "Done" : status === "active" ? "In progress" : status === "failed" ? "Failed" : "Waiting";
      return `<article class="pipeline-step ${status}">
        <div class="pipeline-step-head"><span class="pipeline-step-number">${step.index}</span><span class="pipeline-step-state">${html(label)}</span></div>
        <h3>${html(step.title)}</h3>
        <p>${html(step.detail)}</p>
        <strong>${html(step.value)}</strong>
      </article>`;
    }).join("");

    return `<p class="dashboard-action-note"><strong>${html(activeStage ? `Current step ${activeStage} of 4` : pipelineFinished ? "Pipeline complete" : "Pipeline status")}</strong> / ${html(stageLabel)}</p>
      <div class="collection-pipeline" aria-label="Restaurant collection pipeline">${cards}</div>`;
  }

  function shopPipelineMarkup(shop, flags) {
    const progress = shop.progress || {};
    const counts = shop.counts || {};
    const discoveryRun = flags.discoveryRun || {};
    const inventoryRun = flags.inventoryRun || {};
    const phase = String(progress.phase || "");
    const finishedStatuses = new Set(["complete", "completed", "done"]);
    const discoveryComplete = finishedStatuses.has(String(discoveryRun.status || "").toLowerCase())
      || phase === "overture_complete";
    const inventoryComplete = Boolean(inventoryRun.finished_at)
      && finishedStatuses.has(String(inventoryRun.status || "").toLowerCase());
    let activeStage = number(progress.stageIndex);
    if (!activeStage && flags.overtureRunning) {
      activeStage = phase === "overture_preparing" ? 1 : phase === "overture_reconciling" ? 3 : 2;
    }
    if (!activeStage && flags.inventoryRunning) activeStage = 4;

    const sourceRows = number(progress.source_rows);
    const candidates = number(progress.candidates || counts.overturePlaces);
    const websites = number(counts.overtureWebsites);
    const checked = number(progress.checked || inventoryRun.checked || inventoryRun.processed);
    const inventoryTotal = number(progress.total || inventoryRun.total || counts.withWebsite);
    const found = number(progress.found || counts.inventoryFound);
    const products = number(progress.products || counts.products);
    const failed = String(progress.status || "").toLowerCase() === "failed";

    const steps = [
      {
        index: 1,
        title: "Prepare Overture release",
        detail: "Select and connect to the latest global Places release.",
        value: progress.release || discoveryRun.provider_release || "Waiting for release",
        complete: activeStage > 1 || discoveryComplete || Boolean(discoveryRun.provider_release),
      },
      {
        index: 2,
        title: "Import and merge shops",
        detail: "Read places, keep wine retailers, and merge duplicate businesses.",
        value: `${fmtInt(sourceRows)} read / ${fmtInt(candidates)} candidates saved`,
        complete: discoveryComplete || activeStage > 2,
      },
      {
        index: 3,
        title: "Finalize website queue",
        detail: "Save official website URLs and reconcile shops missing from the new release.",
        value: `${fmtInt(websites)} website URLs ready`,
        complete: discoveryComplete,
      },
      {
        index: 4,
        title: "Scan and save inventories",
        detail: "Visit shop websites, verify catalogues or files, and save searchable wine text.",
        value: `${fmtInt(checked)} / ${fmtInt(inventoryTotal)} checked / ${fmtInt(found)} inventories / ${fmtInt(products)} products`,
        complete: inventoryComplete,
      },
    ];

    return `<div class="collection-pipeline" aria-label="Wine-shop collection pipeline">${steps.map((step) => {
      const active = activeStage === step.index && (flags.anyRunning || failed);
      const status = failed && active
        ? "failed"
        : active
          ? "active"
          : step.complete
            ? "complete"
            : "waiting";
      const label = status === "complete" ? "Done" : status === "active" ? "In progress" : status === "failed" ? "Failed" : "Waiting";
      return `<article class="pipeline-step ${status}">
        <div class="pipeline-step-head"><span class="pipeline-step-number">${step.index}</span><span class="pipeline-step-state">${html(label)}</span></div>
        <h3>${html(step.title)}</h3>
        <p>${html(step.detail)}</p>
        <strong>${html(step.value)}</strong>
      </article>`;
    }).join("")}</div>`;
  }

  function renderShopCollection(root) {
    const shop = state.shopPayload || {};
    const progress = shop.progress || {};
    const counts = shop.counts || {};
    const discoveryRun = (shop.latestDiscoveryRuns || [])[0] || {};
    const inventoryRun = (shop.latestRuns || []).find((run) => run.phase === "inventory") || {};
    const overtureRunning = Boolean(shop.running?.overture || (progress.status === "running" && String(progress.phase || "").startsWith("overture_")));
    const inventoryRunning = Boolean(shop.running?.inventory || (progress.status === "running" && String(progress.phase || "").startsWith("inventory")));
    const anyRunning = overtureRunning || inventoryRunning || Boolean(shop.running?.merchantScan);
    const checked = number(inventoryRunning ? progress.checked : (inventoryRun.checked || inventoryRun.processed));
    const total = number(inventoryRunning ? progress.total : (inventoryRun.total || counts.withWebsite));
    const percent = total ? Math.min(100, (checked / total) * 100) : 0;
    const discoveryUpdated = discoveryRun.finished_at ? formatTime(discoveryRun.finished_at) : "Not imported yet";
    const inventoryUpdated = inventoryRun.finished_at ? formatTime(inventoryRun.finished_at) : "Not scanned yet";

    const stagesHtml = `<div class="collection-stage-grid">
      <section class="dash-panel collection-stage">
        <p class="dash-kicker"><span class="collection-stage-number">1</span>Candidate directory</p>
        <h2>Update global wine shops</h2>
        <p class="collection-stage-copy">Import global retail candidates and available website URLs from the latest Overture Places release.</p>
        <div class="collection-metrics">
          <div class="metric-box"><span>Shop candidates</span><b>${html(fmtInt(counts.overturePlaces))}</b></div>
          <div class="metric-box"><span>Website candidates</span><b>${html(fmtInt(counts.overtureWebsites))}</b></div>
          <div class="metric-box"><span>Overture release</span><b>${html(discoveryRun.provider_release || "-")}</b></div>
          <div class="metric-box"><span>Last update</span><b>${html(discoveryUpdated)}</b></div>
        </div>
        <div class="collection-stage-schedule"><span>When a new monthly release is available</span><button class="dashboard-refresh" type="button" data-start-shop-collection="overture" ${anyRunning || state.shopActionInFlight ? "disabled" : ""}>${html(overtureRunning ? "Importing..." : "Update shop directory")}</button></div>
      </section>
      <section class="dash-panel collection-stage">
        <p class="dash-kicker"><span class="collection-stage-number">2</span>Inventory scan</p>
        <h2>Scan wine-shop websites</h2>
        <p class="collection-stage-copy">Visit saved shop websites, find catalogue pages or files, and save searchable product text.</p>
        <div class="collection-metrics">
          <div class="metric-box"><span>Websites ready</span><b>${html(fmtInt(counts.withWebsite))}</b></div>
          <div class="metric-box"><span>Inventories found</span><b>${html(fmtInt(counts.inventoryFound))}</b></div>
          <div class="metric-box"><span>Searchable products</span><b>${html(fmtInt(counts.products))}</b></div>
          <div class="metric-box"><span>Last scan</span><b>${html(inventoryUpdated)}</b></div>
        </div>
        <div class="collection-stage-schedule"><span>Every 2 weeks</span><button class="dashboard-refresh" type="button" data-start-shop-collection="inventory" ${anyRunning || state.shopActionInFlight || !number(counts.withWebsite) ? "disabled" : ""}>${html(inventoryRunning ? "Scanning..." : "Scan shop inventories")}</button></div>
      </section>
    </div>`;

    const activeStage = number(progress.stageIndex) || (overtureRunning ? 2 : inventoryRunning ? 4 : 0);
    const activeStageLabel = progress.stageLabel || (overtureRunning ? "Import and merge shop directory" : inventoryRunning ? "Scan websites and save inventories" : "No collection is running");
    const pipelinePercent = inventoryRunning && total
      ? 75 + (percent * 0.25)
      : activeStage
        ? Math.max(0, (activeStage - 1) * 25)
        : inventoryRun.finished_at
          ? 100
          : discoveryRun.finished_at
            ? 75
            : 0;
    const progressHtml = `<section class="dash-panel" data-dashboard-section="shop-collection">
      <div class="collection-head">
        <div><p class="dash-kicker">Current run</p><h2>${html(anyRunning ? (overtureRunning ? "Updating wine-shop candidates" : "Scanning wine-shop inventories") : "Wine-shop collection status")}</h2></div>
        <div class="selected-target-actions dashboard-progress-actions">
          <span class="dash-pill ${anyRunning ? "good" : ""}">${html(anyRunning ? "Collecting" : (progress.status || "Ready"))}</span>
          <button class="dashboard-refresh" type="button" data-refresh-collection ${state.guideLoadInFlight ? "disabled" : ""}>Refresh</button>
          ${state.shopActionMessage ? `<span class="dashboard-action-note">${html(state.shopActionMessage)}</span>` : ""}
        </div>
      </div>
      <p class="dashboard-action-note"><strong>${html(anyRunning ? `Current step ${activeStage} of 4` : "Pipeline status")}</strong> / ${html(activeStageLabel)}</p>
      ${progress.message ? `<p class="dashboard-action-note">${html(progress.message)}</p>` : ""}
      ${shopPipelineMarkup(shop, { discoveryRun, inventoryRun, overtureRunning, inventoryRunning, anyRunning })}
      <div class="dash-progress" title="Completed pipeline stages" style="--dash-progress:${html(pipelinePercent)}%"><i></i></div>
      <div class="collection-metrics">
        <div class="metric-box"><span>${html(overtureRunning ? "Candidates saved" : "Websites checked")}</span><b>${html(fmtInt(overtureRunning ? progress.candidates : checked))}${overtureRunning || !total ? "" : ` / ${html(fmtInt(total))}`}</b></div>
        <div class="metric-box"><span>Shops saved</span><b>${html(fmtInt(counts.merchants))}</b></div>
        <div class="metric-box"><span>Inventory sources</span><b>${html(fmtInt(counts.sources))}</b></div>
        <div class="metric-box"><span>Needs review</span><b>${html(fmtInt(counts.openReviews))}</b></div>
      </div>
    </section>`;
    root.innerHTML = `${collectionSwitchMarkup()}${stagesHtml}${progressHtml}${resourcePanelMarkup(shop, { kind: "shops" })}`;
  }

  function renderActiveGuideView() {
    if (state.activeView === "database") renderDatabase();
    if (state.activeView === "collection") renderCollection();
  }

  async function loadGuideStats(options = {}) {
    if (state.guideLoadInFlight) return;
    if (state.guideLoadedOnce && !options.force) return;
    state.guideLoadInFlight = true;
    if (options.force) {
      state.guideActionKind = "";
      state.guideActionMessage = "Refreshing saved data...";
      renderActiveGuideView();
    }
    try {
      const payload = await fetchLiveGuideCollection();
      if (isEmptyGuidePayload(payload) && state.guidePayload) return;
      state.guidePayload = payload;
      state.guideLoadedOnce = true;
      state.lastRefreshAt = new Date().toLocaleTimeString();
      if (options.force && !state.guideActionMessage.includes("started")) {
        state.guideActionKind = "good";
        state.guideActionMessage = "Saved data refreshed.";
      }
      renderActiveGuideView();
    } catch (error) {
      state.guideActionKind = "bad";
      state.guideActionMessage = `Refresh failed: ${error.message || error}`;
    } finally {
      state.guideLoadInFlight = false;
      renderActiveGuideView();
    }
  }

  function boot() {
    const nav = cleanTabs();
    ensureDataViews();
    nav.addEventListener("click", (event) => {
      const button = event.target.closest("[data-view]");
      if (!button) return;
      window.setTimeout(() => activate(button.dataset.view), 0);
    }, true);
    document.body.addEventListener("click", (event) => {
      if (!event.target.closest("[data-clear-dashboard-selection]")) return;
      event.preventDefault();
      clearDashboardSelection();
    });
    document.body.addEventListener("click", (event) => {
      if (!event.target.closest("[data-refresh-collection]")) return;
      event.preventDefault();
      loadGuideStats({ force: true });
    });
    document.body.addEventListener("click", (event) => {
      if (!event.target.closest("[data-start-guide-collection]")) return;
      event.preventDefault();
      startGuideRecollection("inventory");
    });
    document.body.addEventListener("click", (event) => {
      if (!event.target.closest("[data-start-guide-directory]")) return;
      event.preventDefault();
      startGuideRecollection("directory");
    });
    document.body.addEventListener("click", (event) => {
      const button = event.target.closest("[data-start-shop-collection]");
      if (!button) return;
      event.preventDefault();
      startShopCollection(button.dataset.startShopCollection);
    });
    document.body.addEventListener("click", (event) => {
      const button = event.target.closest("[data-collection-mode]");
      if (!button || button.dataset.collectionMode === state.collectionMode) return;
      event.preventDefault();
      state.collectionMode = button.dataset.collectionMode;
      renderCollection();
    });
    document.body.addEventListener("click", (event) => {
      const button = event.target.closest("[data-database-mode]");
      if (!button || button.dataset.databaseMode === state.databaseMode) return;
      event.preventDefault();
      state.databaseMode = button.dataset.databaseMode;
      state.activeTargetId = null;
      state.dashboardInfoWindow?.close();
      state.dashboardMapSignature = "";
      state.dashboardMapHasFit = false;
      renderDatabase();
    });
    activate("search");
  }

  if (document.readyState === "loading") {
    document.addEventListener("DOMContentLoaded", boot);
  } else {
    boot();
  }
})();
