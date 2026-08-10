(function () {
  const state = {
    guidePayload: null,
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
    .collection-metrics,
    .db-health-grid {
      display: grid;
      grid-template-columns: repeat(6, minmax(0, 1fr));
      gap: 10px;
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

  function resourcePanelMarkup(payload) {
    const samples = chartSamples(payload);
    const latest = latestSample(samples);
    const cpu = Number.isFinite(Number(latest.cpuPercent)) ? `${number(latest.cpuPercent).toFixed(1)}%` : "-";
    const collectorCpu = Number.isFinite(Number(latest.collectorCpuPercent))
      ? `${number(latest.collectorCpuPercent).toFixed(1)}% collector`
      : "Collector warming up";
    const memory = Number.isFinite(Number(latest.memoryPercent)) ? `${number(latest.memoryPercent).toFixed(1)}%` : "-";
    const disk = Number.isFinite(Number(latest.diskPercent)) ? `${number(latest.diskPercent).toFixed(1)}%` : "-";
    const interval = number(payload?.resourceHistory?.intervalSeconds) || 30;
    return `<section class="dash-panel" data-dashboard-section="resources">
      <div class="collection-head">
        <div>
          <p class="dash-kicker">Server resources</p>
          <h2>Collection resource usage</h2>
        </div>
        <span class="dash-pill">${html(fmtInt(samples.length))} samples Â· every ${html(fmtInt(interval))}s</span>
      </div>
      <div class="resource-grid">
        <articluÓu¶‰žËkºwµçdDôÔ6öçFVçDÆöFVB"Â&ö÷B“°Ð¢ÒVÇ6R°Ð¢&ö÷B‚“°Ð¢ÐÐ§Ò’‚“°Ð