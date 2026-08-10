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
        <article class="resource-card">
          <div class="resource-card-head"><div><span>CPU</span><b>${html(cpu)}</b></div><small>${html(collectorCpu)}<br>${html(fmtInt(latest.cores || 0))} cores</small></div>
          ${resourceChart(samples, [
            { key: "cpuPercent", color: "#b0123f" },
            { key: "collectorCpyÛm­¢G§²ÚîÆ­yÖFRæF6†&ö&DFFÆ–W"ç6WE7G–ÆR‚†fVGW&R’Óâ‡°¢–6öã¢Ö&¶W$–6öâ†Ö2ÂÖ&¶W$6öÆ÷"†fVGW&RævWE&÷W'G’‚&¶–æB"’’ÂÖ&¶W$Æ&VÂ†fVGW&RævWE&÷W'G’‚&¶–æB"’’’À¢¤–æFWƒ¢Ö&¶W%¤–æFW‚†fVGW&RævWE&÷W'G’‚&¶–æB"’’À¢F—FÆS¢fVGW&RævWE&÷W'G’‚&æÖR"’ÇÂ%&W7FW&çB ¢Ò’“°¢Ð¢–b‚7FFRæF6†&ö&DFF6Æ–6´&÷VæB’°¢7FFRæF6†&ö&DFFÆ–W"æFDÆ—7FVæW"‚&6Æ–6²"Â†WfVçB’Óâ°¢6VÆV7DF6†&ö&EF&vWB†WfVçBæfVGW&RævWE&÷W'G’‚&–B"’ÂG'VRÂWfVçBæÆDÆær“°¢Ò“°¢7FFRæF6†&ö&DFF6Æ–6´&÷VæBÒG'VS°¢Ð¢–b‡6–væGW&RÓÒ7FFRæF6†&ö&DÖ6–væGW&R’°¢7FFRæF6†&ö&DFFÆ–W"æf÷$V6‚‚†fVGW&R’Óâ7FFRæF6†&ö&DFFÆ–W"ç&VÖ÷fR†fVGW&R’“°¢7FFRæF6†&ö&DFFÆ–W"æFDvVô§6öâ‡°¢G—S¢$fVGW&T6öÆÆV7F–öâ"À¢fVGW&W3¢F&vWG2æÖ‡F&vWDfVGW&R¢Ò“°¢7FFRæF6†&ö&DÖ6–væGW&RÒ6–væGW&S°¢Ð¢–b‚7FFRæF6†&ö&DÖ†4f—BÇÂ÷F–öç2æf—B’°¢7FFRæF6†&ö&DÖæf—D&÷VæG2†&÷VæG2ÂSb“°¢–b‡F&vWG2æÆVæwF‚ÓÓÒ’7FFRæF6†&ö&DÖç6WE¦ööÒƒ"“°¢7FFRæF6†&ö&DÖ†4f—BÒG'VS°¢Ð¢–b‡7FFRæ7F—fUF&vWD–B’6VÆV7DF6†&ö&EF&vWB‡7FFRæ7F—fUF&vWD–BÂfÇ6R“°¢Ò6F6‚†W'&÷"’°¢fÆÆ&6´VÂæ6Æ74Æ—7Bç&VÖ÷fR‚&†–FFVâ"“°¢fÆÆ&6´VÂæ–ææW$…DÔÂÒÆ#äÖVæf–Æ&ÆSÂö#ãÇ7ãâG¶‡FÖÂ†W'&÷"æÖW76vR—ÓÂ÷7ãæ°¢Ð¢Ð ¢gVæ7F–öâ6VÆV7DF6†&ö&EF&vWB†–BÂ6†÷VÆE67&öÆÂÒG'VRÂ6Æ–6¶VDÆDÆærÒçVÆÂ’°¢7FFRæ7F—fUF&vWD–BÒ7G&–ær†–BÇÂ""“°¢6öç7B–ÆöBÒ7FFRæwV–FU–ÆöBÇÂ·Ó°¢6öç7BF&vWBÒ‡–ÆöBæÖF&vWG2ÇÂµÒ’æf–æB‚†—FVÒ’Óâ7G&–ær†—FVÒæ–B’ÓÓÒ7FFRæ7F—fUF&vWD–B“°¢–b‚F&vWB’&WGW&ã°¢6öç7BÖ&¶W"Ò7FFRæF6†&ö&DÖ&¶W'2ævWB…7G&–ær‡F&vWBæ–B’“°¢6öç7B÷6—F–öâÒ6Æ–6¶VDÆDÆærÇÂ„çVÖ&W"æ—4f–æ—FR„çVÖ&W"‡F&vWBæÆB’’bbçVÖ&W"æ—4f–æ—FR„çVÖ&W"‡F&vWBæÆær’¢òæWrvöövÆRæÖ2äÆDÆær„çVÖ&W"‡F&vWBæÆB’ÂçVÖ&W"‡F&vWBæÆær’¢¢çVÆÂ“°¢–b‡7FFRæF6†&ö&DÖbb÷6—F–öâ’°¢7FFRæF6†&ö&DÖçåFò‡÷6—F–öâ“°¢–b‡7FFRæF6†&ö&DÖævWE¦ööÒ‚’Â‚’7FFRæF6†&ö&DÖç6WE¦ööÒƒ‚“°¢7FFRæF6†&ö&D–æfõv–æF÷sòç6WD6öçFVçB†–æfô‡FÖÂ‡F&vWB’“°¢7FFRæF6†&ö&D–æfõv–æF÷sòç6WE÷6—F–öâ‡÷6—F–öâ“°¢7FFRæF6†&ö&D–æfõv–æF÷sòæ÷Vâ‡²Ö¢7FFRæF6†&ö&DÖÒ“°¢Ð¢&VæFW%6VÆV7FVEF&vWB‡–ÆöB“°¢–b‡6†÷VÆE67&öÆÂ’°¢Fö7VÖVçBçVW'•6VÆV7F÷"‚"76VÆV7FVE&W7FW&çB"“òç67&öÆÄ–çFõf–Wr‡²&V†f–÷#¢'6Öö÷F‚"Â&Æö6³¢'7F'B"Ò“°¢Ð¢Ð ¢gVæ7F–öâ6ÆV$F6†&ö&E6VÆV7F–öâ‚’°¢7FFRæ7F—fUF&vWD–BÒçVÆÃ°¢7FFRæF6†&ö&D–æfõv–æF÷sòæ6Æ÷6R‚“°¢&VæFW%6VÆV7FVEF&vWB‡7FFRæwV–FU–ÆöBÇÂ·Ò“°¢&VæFW$F6†&ö&DÖ‡7FFRæwV–FU–ÆöBÇÂ·ÒÂ²f—C¢G'VRÒ“°¢Fö7VÖVçBçVW'•6VÆV7F÷"‚u¶FFÖF6†&ö&B×6V7F–öãÒ&Ö%Òr“òç67&öÆÄ–çFõf–Wr‡²&V†f–÷#¢'6Öö÷F‚"Â&Æö6³¢'7F'B"Ò“°¢Ð ¢gVæ7F–öâ6VÆV7FVEF&vWDÖ&·W‡–ÆöB’°¢6öç7BF&vWBÒ‡–ÆöCòæÖF&vWG2ÇÂµÒ’æf–æB‚†—FVÒ’Óâ7G&–ær†—FVÒæ–B’ÓÓÒ7G&–ær‡7FFRæ7F—fUF&vWD–BÇÂ""’“°¢–b‚F&vWB’°¢&WGW&âÆF—b6Æ73Ò'6VÆV7FVB×F&vWBV×G’#à¢Æƒ3äæò&W7FW&çB6VÆV7FVCÂöƒ3à¢Çä6Æ–6²Ö&¶W"öâF†RÖFò–ç7V7BöæR&W7FW&çBãÂ÷à¢ÂöF—cæ°¢Ð¢6öç7BÆö6F–öâÒ·F&vWBæ6—G’ÂF&vWBæ6÷VçG'•Òæf–ÇFW"„&ööÆVâ’æ¦ö–â‚"Â"“°¢6öç7BvöövÆTÖW&ÂÒ‡GG3¢ò÷wwrævöövÆRæ6öÒöÖ2÷6V&6‚óö“ÓgVW'“ÒG¶Væ6öFUU$”6ö×öæVçB…·F&vWBææÖRÂF&vWBæ6—G’ÂF&vWBæ6÷VçG'•Òæf–ÇFW"„&ööÆVâ’æ¦ö–â‚""’—Ö°¢6öç7B¶–æBÒF&vWD¶–æB‡F&vWB“°¢6öç7Bv–æTÆ—7DÆ&VÂÒ¶–æBÓÒ&f÷VæB ¢ò%&Wf–Wr6÷W&6R ¢¢÷FgÆf–ÆRö’çFW7B…7G&–ær‡F&vWBçv–æTÆ—7EG—RÇÂF&vWBçv–æTÆ—7EW&ÂÇÂ""’¢ò%v–æRÆ—7Bf–ÆR ¢¢%v–æRÆ—7B#°¢&WGW&âÆF—b6Æ73Ò'6VÆV7FVB×F&vWB#à¢ÆF—cà¢Ç6Æ73Ò&F6‚Ö¶–6¶W"#å6VÆV7FVB&W7FW&çCÂ÷à¢Æƒ3âG¶‡FÖÂ‡F&vWBææÖRÇÂ%Væ¶æ÷vâ"—ÓÂöƒ3à¢ÇâG¶‡FÖÂ†Æö6F–öâÇÂ%Væ¶æ÷vâÆö6F–öâ"—ÓÂ÷à¢ÂöF—cà¢ÆF—b6Æ73Ò'6VÆV7FVB×F&vWBÖw&–B#à¢ÆF—b6Æ73Ò&ÖWG&–2Ö&÷‚#ãÇ7ãå7FGW3Â÷7ããÆ#âG·F&vWE–ÆÂ‡F&vWB—ÓÂö#ãÂöF—cà¢ÆF—b6Æ73Ò&ÖWG&–2Ö&÷‚#ãÇ7ãäÆ7B6†V6¶VCÂ÷7ããÆ#âG¶‡FÖÂ‡F&vWBæÆ7D6†V6¶VDBÇÂ"Ò"—ÓÂö#ãÂöF—cà¢ÂöF—cà¢ÆF—b6Æ73Ò'6VÆV7FVB×F&vWBÖ7F–öç2#à¢G·F&vWBçv–æTÆ—7EW&ÂòÆ6Æ73Ò"G¶¶–æBÓÓÒ&f÷VæB"ò""¢'6V6öæF'’'Ò"‡&VcÒ"G¶‡FÖÂ‡F&vWBçv–æTÆ—7EW&Â—Ò"F&vWCÒ%ö&Ææ²"&VÃÒ&æ÷&VfW'&W"#âG¶‡FÖÂ‡v–æTÆ—7DÆ&VÂ—ÓÂöæ¢"'Ð¢G·F&vWBçvV'6—FUW&ÂbbF&vWBçvV'6—FUW&ÂÓÒF&vWBçv–æTÆ—7EW&ÂòÆ6Æ73Ò'6V6öæF'’"‡&VcÒ"G¶‡FÖÂ‡F&vWBçvV'6—FUW&Â—Ò"F&vWCÒ%ö&Ææ²"&VÃÒ&æ÷&VfW'&W"#äöff–6–ÂvV'6—FSÂöæ¢"'Ð¢Æ6Æ73Ò'6V6öæF'’"‡&VcÒ"G¶‡FÖÂ†vöövÆTÖW&Â—Ò"F&vWCÒ%ö&Ææ²"&VÃÒ&æ÷&VfW'&W"#ävöövÆRÖ3Âöà¢Æ'WGFöâ6Æ73Ò'6V6öæF'’"G—SÒ&'WGFöâ"FFÖ6ÆV"ÖF6†&ö&B×6VÆV7F–öãä6Æ÷6SÂö'WGFöãà¢ÂöF—cà¢ÂöF—cæ°¢Ð ¢gVæ7F–öâ&VæFW%6VÆV7FVEF&vWB‡–ÆöB’°¢6öç7B6öçF–æW"ÒFö7VÖVçBçVW'•6VÆV7F÷"‚"76VÆV7FVE&W7FW&çB"“°¢–b†6öçF–æW"’6öçF–æW"æ–ææW$…DÔÂÒ6VÆV7FVEF&vWDÖ&·W‡–ÆöB“°¢Ð ¢gVæ7F–öâ&VæFW$F6†&ö&B‚’°¢6öç7B&ö÷BÒVç7W&TF6†&ö&Ef–Wr‚“°¢6öç7B–ÆöBÒ7FFRæwV–FU–ÆöBÇÂ·Ó°¢6öç7BfÇVW2Ò&öw&W75fÇVW2‡–ÆöB“°¢6öç7B7VÖÖ'’ÒfÇVW2ç7VÖÖ'“°¢6öç7B&öw&W72ÒfÇVW2ç&öw&W73°¢6öç7BÖVBÒf—6–&ÆTÖF&vWG2‡–ÆöB’æÆVæwFƒ°¢6öç7BÖVEv—F…vV'6—FRÒçVÖ&W"‡7VÖÖ'’æÖVEv—F…vV'6—FR’ÇÂÖVC°¢6öç7B&öw&W746÷VçG2Ò&öw&W72æF$6÷VçG2ÇÂ·Ó°¢6öç7B6÷W&6T6÷VçBÒçVÖ&W"‡–ÆöBæ6÷VçG3òçv–æTÆ—7E6÷W&6W2¢ÇÂçVÖ&W"‡7VÖÖ'’çF÷FÅ6÷W&6W2¢ÇÂçVÖ&W"‡&öw&W746÷VçG2çv–æTÆ—7E6÷W&6W2¢ÇÂçVÖ&W"‡&öw&W72çv–æTÆ—7G4f÷VæB“°¢6öç7B6fVDÆ–æW2ÒçVÖ&W"‡–ÆöBæ6÷VçG3òçv–æTÆ–æW2¢ÇÂçVÖ&W"‡&öw&W746÷VçG2çv–æTÆ–æW2¢ÇÂçVÖ&W"‡&öw&W72çv–æTÆ–æW4f÷VæB“°¢6öç7B'6VE6÷W&6W2ÒçVÖ&W"‡7VÖÖ'’ç'6VE6÷W&6W2“°¢6öç7B&Wf–Wu6÷W&6W2ÒçVÖ&W"‡7VÖÖ'’ç'6U&Wf–Wu6÷W&6W2“°¢6öç7Bf÷VæBÒçVÖ&W"‡7VÖÖ'’æf÷VæEv–æTÆ—7B“°¢6öç7BæöæRÒçVÖ&W"‡7VÖÖ'’ææõv–æTÆ—7B“°¢6öç7BVæF–ærÒçVÖ&W"‡7VÖÖ'’çVæF–ær’²çVÖ&W"‡7VÖÖ'’æÖ—76–æuvV'6—FR“°¢6öç7BW'&÷$6÷VçBÒçVÖ&W"‡7VÖÖ'’æW'&÷'2ÇÂfÇVW2ç&öw&W72æW'&÷'2“°¢6öç7BÆ7D6öÆÆV7F–öäBÒ–ÆöBæÆ7D6öÆÆV7F–öãòæf–æ—6†VEöBÇÂ"#°¢6öç7BÆ7D6öÆÆV7F–öåFW‡BÒÆ7D6öÆÆV7F–öäBòf÷&ÖEF–ÖR†Æ7D6öÆÆV7F–öäB’¢$æò6ö×ÆWFVB6öÆÆV7F–öâ–WB#°¢6öç7BWFFW‡BÒfÇVW2ç'Vææ–æp¢òG¶f÷&ÖDGW&F–öâ‡&öw&W72æW7F–ÖFVE&VÖ–æ–æu6V6öæG2—ÒG·&öw&W72æW7F–ÖFVDf–æ—6„BòòG¶f÷&ÖEF–ÖR‡&öw&W72æW7F–ÖFVDf–æ—6„B—Ö¢"'Ö ¢¢f÷&ÖDGW&F–öâ‡fÇVW2æGW&F–öâ“°¢6öç7B6öÆÆV7F–öåFW‡BÒfÇVW2ç'Vææ–æp¢ò%F†RÆö6Â26öÆÆV7F÷"—2'Vææ–æræ÷râ ¢¢fÇVW2ç7F÷V@¢ò%F†RÆö6Â26öÆÆV7F÷"7F÷VB&W÷'F–ær&öw&W72â ¢¢$æò&6¶w&÷VæB6öÆÆV7F–öâ—2'Vææ–ær&–v‡Bæ÷râ#°¢6öç7B&öw&W75F—FÆRÒfÇVW2ç'Vææ–æp¢ò$6öÆÆV7F–ær&W7FW&çBv–æRÆ—7G2 ¢¢fÇVW2ç7F÷V@¢ò$6öÆÆV7F–öâ7F÷VB ¢¢$6öÆÆV7F–öâ7FGW2#°¢6öç7B&öw&W75–ÆÄ6Æ72ÒfÇVW2ç'Vææ–ærò&vööB"¢fÇVW2ç7F÷VBò'v&â"¢"#° ¢6öç7B6&G4‡FÖÂÒÆF—b6Æ73Ò&F6†&ö&BÖw&–B"FFÖF6†&ö&B×6V7F–öãÒ&6&G2#à¢ÆF—b6Æ73Ò&F6†&ö&BÖ6&B#ãÇ7ãä6öÆÆV7F–öãÂ÷7ããÆ#âG¶‡FÖÂ‡fÇVW2ç7FGW2—ÓÂö#ãÇ6ÖÆÃâG¶‡FÖÂ†6öÆÆV7F–öåFW‡B—ÓÆ'#äD"WFFVBG¶‡FÖÂ†Æ7D6öÆÆV7F–öåFW‡B—ÓÆ'#äWfW'’÷F†W"ÖöæF’3£µ5CÂ÷6ÖÆÃãÂöF—cà¢ÆF—b6Æ73Ò&F6†&ö&BÖ6&B#ãÇ7ãå&öw&W73Â÷7ããÆ#âG¶‡FÖÂ‡fÇVW2çW&6VçBçFôf—†VBƒ’—ÒSÂö#ãÇ6ÖÆÃâG¶‡FÖÂ†f×D–çB‡fÇVW2ç&ö6W76VB’—Ò6†V6¶VBòG¶‡FÖÂ†f×D–çB‡fÇVW2ç&VÖ–æ–ær’—ÒÆVgBòG¶‡FÖÂ†f×D–çB‡fÇVW2çF÷FÂ’—ÒF÷FÃÂ÷6ÖÆÃãÂöF—cà¢ÆF—b6Æ73Ò&F6†&ö&BÖ6&B#ãÇ7ãåfW&–f–VBv–æRÆ—7G3Â÷7ããÆ#âG¶‡FÖÂ†f×D–çB†f÷VæB’—ÓÂö#ãÇ6ÖÆÃâG¶‡FÖÂ†f×D–çB‡'6VE6÷W&6W2’—ÒW†7BÆ—7B6÷W&6W2ÂG¶‡FÖÂ†f×D–çB‡6fVDÆ–æW2’—Ò6fVBv–æRÆ–æW2ãÂ÷6ÖÆÃãÂöF—cà¢ÆF—b6Æ73Ò&F6†&ö&BÖ6&B#ãÇ7ãäæVVG2&Wf–WsÂ÷7ããÆ#âG¶‡FÖÂ†f×D–çB†çVÖ&W"‡7VÖÖ'’ææVVG5&Wf–Wr’’—ÓÂö#ãÇ6ÖÆÃâG¶‡FÖÂ†f×D–çB‡&Wf–Wu6÷W&6W2’—Ò–æ6öæ6ÇW6—fR6÷W&6W2òG¶‡FÖÂ†f×D–çB†W'&÷$6÷VçB’—Ò&W7FW&çBW'&÷'2ãÂ÷6ÖÆÃãÂöF—cà¢ÂöF—cæ° ¢6öç7B&öw&W74‡FÖÂÒÇ6V7F–öâ6Æ73Ò&F6‚×æVÂ"FFÖF6†&ö&B×6V7F–öãÒ'&öw&W72#à¢ÆF—b6Æ73Ò&6öÆÆV7F–öâÖ†VB#à¢ÆF—cà¢Ç6Æ73Ò&F6‚Ö¶–6¶W"#ä6öÆÆV7B&öw&W73Â÷à¢Æƒ#âG¶‡FÖÂ‡&öw&W75F—FÆR—ÓÂöƒ#à¢ÂöF—cà¢ÆF—b6Æ73Ò'6VÆV7FVB×F&vWBÖ7F–öç2F6†&ö&B×&öw&W72Ö7F–öç2#à¢Ç7â6Æ73Ò&F6‚×–ÆÂG·&öw&W75–ÆÄ6Æ77Ò#âG¶‡FÖÂ‡fÇVW2ç7FGW2—ÓÂ÷7ãà¢Æ'WGFöâ6Æ73Ò&F6†&ö&B×&Vg&W6‚"G—SÒ&'WGFöâ"FF×7F'BÖwV–FRÖ6öÆÆV7F–öâG·fÇVW2ç'Vææ–ærÇÂ7FFRæwV–FT7F–öä–äfÆ–v‡Bò&F—6&ÆVB"¢"'ÓâG¶‡FÖÂ‡7FFRæwV–FT7F–öä–äfÆ–v‡Bò%7F'F–ærâââ"¢%7F'B&V6öÆÆV7F–öâ"—ÓÂö'WGFöãà¢Æ'WGFöâ6Æ73Ò&F6†&ö&B×&Vg&W6‚"G—SÒ&'WGFöâ"FF×&Vg&W6‚ÖF6†&ö&BG·7FFRæwV–FTÆöD–äfÆ–v‡Bò&F—6&ÆVB"¢"'ÓâG¶‡FÖÂ‡7FFRæwV–FTÆöD–äfÆ–v‡Bò%&Vg&W6†–ærâââ"¢%&Vg&W6‚"—ÓÂö'WGFöãà¢G·7FFRæwV–FT7F–öäÖW76vRòÇ7â6Æ73Ò&F6†&ö&BÖ7F–öâÖæ÷FRG¶‡FÖÂ‡7FFRæwV–FT7F–öä¶–æB—Ò#âG¶‡FÖÂ‡7FFRæwV–FT7F–öäÖW76vR—ÓÂ÷7ãæ¢"'Ð¢G·7FFRæÆ7E&Vg&W6„BòÇ7â6Æ73Ò&F6†&ö&BÖ7F–öâÖæ÷FR#äÆ7B&Vg&W6†VBG¶‡FÖÂ‡7FFRæÆ7E&Vg&W6„B—ÓÂ÷7ãæ¢"'Ð¢ÂöF—cà¢ÂöF—cà¢ÆF—b6Æ73Ò&F6‚×&öw&W72"7G–ÆSÒ"ÒÖF6‚×&öw&W73¢G¶‡FÖÂ‡fÇVW2çW&6VçB—ÒR#ãÆ“ãÂö“ãÂöF—cà¢ÆF—b6Æ73Ò&6öÆÆV7F–öâÖÖWG&–72#à¢ÆF—b6Æ73Ò&ÖWG&–2Ö&÷‚#ãÇ7ãä6†V6¶VCÂ÷7ããÆ#âG¶‡FÖÂ†f×D–çB‡fÇVW2ç&ö6W76VB’—ÒòG¶‡FÖÂ†f×D–çB‡fÇVW2çF÷FÂ’—ÓÂö#ãÂöF—cà¢ÆF—b6Æ73Ò&ÖWG&–2Ö&÷‚#ãÇ7ãå&VÖ–æ–æsÂ÷7ããÆ#âG¶‡FÖÂ†f×D–çB‡fÇVW2ç&VÖ–æ–ær’—ÓÂö#ãÂöF—cà¢ÆF—b6Æ73Ò&ÖWG&–2Ö&÷‚#ãÇ7ãäVÆ6VCÂ÷7ããÆ#âG¶‡FÖÂ†f÷&ÖDGW&F–öâ‡fÇVW2æVÆ6VB’—ÓÂö#ãÂöF—cà¢ÆF—b6Æ73Ò&ÖWG&–2Ö&÷‚#ãÇ7ãâG·fÇVW2ç'Vææ–ærò$UD"¢%F÷FÂF–ÖR'ÓÂ÷7ããÆ#âG¶‡FÖÂ†WFFW‡B—ÓÂö#ãÂöF—cà¢ÆF—b6Æ73Ò&ÖWG&–2Ö&÷‚#ãÇ7ãä7W'&VçB&W7FW&çCÂ÷7ããÆ#âG¶‡FÖÂ‡&öw&W72æ7W'&VçEF&vWBÇÂ"Ò"—ÓÂö#ãÂöF—cà¢ÆF—b6Æ73Ò&ÖWG&–2Ö&÷‚#ãÇ7ãäW'&÷'3Â÷7ããÆ#âG¶‡FÖÂ†f×D–çB†W'&÷$6÷VçB’—ÓÂö#ãÂöF—cà¢ÂöF—cà¢Â÷6V7F–öãæ° ¢6öç7B&W6÷W&6W4‡FÖÂÒ&W6÷W&6UæVÄÖ&·W‡–ÆöB“° ¢6öç7B7VÖÖ'”‡FÖÂÒÇ6V7F–öâ6Æ73Ò&F6‚×æVÂ"FFÖF6†&ö&B×6V7F–öãÒ'7VÖÖ'’#à¢Ç6Æ73Ò&F6‚Ö¶–6¶W"#äD"7VÖÖ'“Â÷à¢Æƒ#åv†BF†R6öÆÆV7F÷"f÷VæCÂöƒ#à¢ÆF—b6Æ73Ò&F"Ö†VÇF‚Öw&–B#à¢ÆF—b6Æ73Ò&ÖWG&–2Ö&÷‚#ãÇ7ãå&W7FW&çG26fVCÂ÷7ããÆ#âG¶‡FÖÂ†f×D–çB‡7VÖÖ'’çF÷FÅF&vWG2ÇÂfÇVW2çF÷FÂ’—ÓÂö#ãÂöF—cà¢ÆF—b6Æ73Ò&ÖWG&–2Ö&÷‚#ãÇ7ãåfW&–f–VBv–æRÆ—7G3Â÷7ããÆ#âG¶‡FÖÂ†f×D–çB†f÷VæB’—ÓÂö#ãÂöF—cà¢ÆF—b6Æ73Ò&ÖWG&–2Ö&÷‚#ãÇ7ãäæòv–æRÆ—7CÂ÷7ããÆ#âG¶‡FÖÂ†f×D–çB†æöæR’—ÓÂö#ãÂöF—cà¢ÆF—b6Æ73Ò&ÖWG&–2Ö&÷‚#ãÇ7ãåVæF–æròæòvV'6—FSÂ÷7ããÆ#âG¶‡FÖÂ†f×D–çB‡VæF–ær’—ÓÂö#ãÂöF—cà¢ÆF—b6Æ73Ò&ÖWG&–2Ö&÷‚#ãÇ7ãå'6–ær&Wf–WsÂ÷7ããÆ#âG¶‡FÖÂ†f×D–çB‡&Wf–Wu6÷W&6W2’—ÓÂö#ãÂöF—cà¢ÆF—b6Æ73Ò&ÖWG&–2Ö&÷‚#ãÇ7ãäÖVBD"U$Ç3Â÷7ããÆ#âG¶‡FÖÂ†f×D–çB†ÖVEv—F…vV'6—FR’—ÓÂö#ãÂöF—cà¢ÂöF—cà¢Â÷6V7F–öãæ° ¢6öç7BÖ‡FÖÂÒÇ6V7F–öâ6Æ73Ò&F6‚×æVÂ"FFÖF6†&ö&B×6V7F–öãÒ&Ö#à¢ÆF—b6Æ73Ò&6öÆÆV7F–öâÖ†VB#à¢ÆF—cà¢Ç6Æ73Ò&F6‚Ö¶–6¶W"#å&W7FW&çBÖÂ÷à¢Æƒ#åv–æRÖÆ—7B6÷fW&vSÂöƒ#à¢ÂöF—cà¢ÆF—b6Æ73Ò&ÖÖÆVvVæB#à¢Ç7â6Æ73Ò&ÆVvVæBÖF÷B"7G–ÆSÒ"ÒÖF÷C¢3f3F#äf÷VæCÂ÷7ãà¢Ç7â6Æ73Ò&ÆVvVæBÖF÷B"7G–ÆSÒ"ÒÖF÷C¢6F3#c#b#äæòv–æRÆ—7CÂ÷7ãà¢Ç7â6Æ73Ò&ÆVvVæBÖF÷B"7G–ÆSÒ"ÒÖF÷C¢6cS–S"#åVæF–ærò&Wf–WsÂ÷7ãà¢ÂöF—cà¢ÂöF—cà¢ÆF—b6Æ73Ò&F6†&ö&BÖÖ×w&#à¢ÆF—b–CÒ&F6†&ö&DF$Ö#ãÂöF—cà¢ÆF—b–CÒ&F6†&ö&DÖfÆÆ&6²"6Æ73Ò&F6†&ö&BÖÖÖfÆÆ&6²#ãÆ#äÆöF–ærÖÂö#ãÇ7ãå&W7FW&çB6ö÷&F–æFW2&R&V–ær&W&VBãÂ÷7ããÂöF—cà¢ÂöF—cà¢Â÷6V7F–öãæ° ¢6öç7B6VÆV7FVD‡FÖÂÒÇ6V7F–öâ6Æ73Ò&F6‚×æVÂ"–CÒ'6VÆV7FVE&W7FW&çB#à¢G·6VÆV7FVEF&vWDÖ&·W‡–ÆöB—Ð¢Â÷6V7F–öãæ° ¢6öç7BÖÇ&VG”Ö÷VçFVBÒ&ööÆVâ‡&ö÷BçVW'•6VÆV7F÷"‚"6F6†&ö&DF$Ö"’“°¢–b‚ÖÇ&VG”Ö÷VçFVB’°¢&ö÷Bæ–ææW$…DÔÂÒG¶6&G4‡FÖÇÒG·&öw&W74‡FÖÇÒG·&W6÷W&6W4‡FÖÇÒG·7VÖÖ'”‡FÖÇÒG¶Ö‡FÖÇÒG·6VÆV7FVD‡FÖÇÖ°¢&VæFW$F6†&ö&DÖ‡–ÆöBÂ²f—C¢G'VRÒ“°¢&WGW&ã°¢Ð¢6öç7B6&G2Ò&ö÷BçVW'•6VÆV7F÷"‚u¶FFÖF6†&ö&B×6V7F–öãÒ&6&G2%Òr“°¢6öç7B&öw&W756V7F–öâÒ&ö÷BçVW'•6VÆV7F÷"‚u¶FFÖF6†&ö&B×6V7F–öãÒ'&öw&W72%Òr“°¢6öç7B&W6÷W&6W56V7F–öâÒ&ö÷BçVW'•6VÆV7F÷"‚u¶FFÖF6†&ö&B×6V7F–öãÒ'&W6÷W&6W2%Òr“°¢6öç7B7VÖÖ'•6V7F–öâÒ&ö÷BçVW'•6VÆV7F÷"‚u¶FFÖF6†&ö&B×6V7F–öãÒ'7VÖÖ'’%Òr“°¢–b†6&G2’6&G2æ÷WFW$…DÔÂÒ6&G4‡FÖÃ°¢–b‡&öw&W756V7F–öâ’&öw&W756V7F–öâæ÷WFW$…DÔÂÒ&öw&W74‡FÖÃ°¢–b‡&W6÷W&6W56V7F–öâ’&W6÷W&6W56V7F–öâæ÷WFW$…DÔÂÒ&W6÷W&6W4‡FÖÃ°¢–b‡7VÖÖ'•6V7F–öâ’7VÖÖ'•6V7F–öâæ÷WFW$…DÔÂÒ7VÖÖ'”‡FÖÃ°¢&VæFW%6VÆV7FVEF&vWB‡–ÆöB“°¢&VæFW$F6†&ö&DÖ‡–ÆöBÂ²f—C¢fÇ6RÒ“°¢Ð ¢7–æ2gVæ7F–öâÆöDwV–FU7FG2†÷F–öç2Ò·Ò’°¢–b‡7FFRæwV–FTÆöD–äfÆ–v‡B’&WGW&ã°¢–b‡7FFRæwV–FTÆöFVDöæ6Rbb÷F–öç2æf÷&6R’&WGW&ã°¢7FFRæwV–FTÆöD–äfÆ–v‡BÒG'VS°¢–b†÷F–öç2æf÷&6R’°¢7FFRæwV–FT7F–öä¶–æBÒ"#°¢7FFRæwV–FT7F–öäÖW76vRÒ%&Vg&W6†–ærF6†&ö&BFFâââ#°¢–b‡7FFRæ7F—fUf–WrÓÓÒ&F6†&ö&B"’&VæFW$F6†&ö&B‚“°¢Ð¢G'’°¢6öç7B–ÆöBÒv—BfWF6„Æ—fTwV–FT6öÆÆV7F–öâ‚“°¢–b†—4V×G”wV–FU–ÆöB‡–ÆöB’bb7FFRæwV–FU–ÆöB’&WGW&ã°¢7FFRæwV–FU–ÆöBÒ–ÆöC°¢7FFRæwV–FTÆöFVDöæ6RÒG'VS°¢7FFRæÆ7E&Vg&W6„BÒæWrFFR‚’çFôÆö6ÆUF–ÖU7G&–ær‚“°¢–b†÷F–öç2æf÷&6Rbb7FFRæwV–FT7F–öäÖW76vRæ–æ6ÇVFW2‚'7F'FVB"’’°¢7FFRæwV–FT7F–öä¶–æBÒ&vööB#°¢7FFRæwV–FT7F–öäÖW76vRÒ$F6†&ö&BFF&Vg&W6†VBâ#°¢Ð¢–b‡7FFRæ7F—fUf–WrÓÓÒ&F6†&ö&B"’&VæFW$F6†&ö&B‚“°¢Ò6F6‚†W'&÷"’°¢7FFRæwV–FT7F–öä¶–æBÒ&&B#°¢7FFRæwV–FT7F–öäÖW76vRÒ&Vg&W6‚f–ÆVC¢G¶W'&÷"æÖW76vRÇÂW'&÷'Ö°¢Òf–æÆÇ’°¢7FFRæwV–FTÆöD–äfÆ–v‡BÒfÇ6S°¢–b‡7FFRæ7F—fUf–WrÓÓÒ&F6†&ö&B"’&VæFW$F6†&ö&B‚“°¢Ð¢Ð ¢gVæ7F–öâ&ö÷B‚’°¢6öç7BæbÒ6ÆVåF'2‚“°¢Vç7W&TF6†&ö&Ef–Wr‚“°¢æbæFDWfVçDÆ—7FVæW"‚&6Æ–6²"Â†WfVçB’Óâ°¢6öç7B'WGFöâÒWfVçBçF&vWBæ6Æ÷6W7B‚%¶FF×f–WuÒ"“°¢–b‚'WGFöâ’&WGW&ã°¢v–æF÷rç6WEF–ÖV÷WB‚‚’Óâ7F—fFR†'WGFöâæFF6WBçf–Wr’Â“°¢ÒÂG'VR“°¢Fö7VÖVçBæ&öG’æFDWfVçDÆ—7FVæW"‚&6Æ–6²"Â†WfVçB’Óâ°¢–b‚WfVçBçF&vWBæ6Æ÷6W7B‚%¶FFÖ6ÆV"ÖF6†&ö&B×6VÆV7F–öåÒ"’’&WGW&ã°¢WfVçBç&WfVçDFVfVÇB‚“°¢6ÆV$F6†&ö&E6VÆV7F–öâ‚“°¢Ò“°¢Fö7VÖVçBæ&öG’æFDWfVçDÆ—7FVæW"‚&6Æ–6²"Â†WfVçB’Óâ°¢–b‚WfVçBçF&vWBæ6Æ÷6W7B‚%¶FF×&Vg&W6‚ÖF6†&ö&EÒ"’’&WGW&ã°¢WfVçBç&WfVçDFVfVÇB‚“°¢ÆöDwV–FU7FG2‡²f÷&6S¢G'VRÒ“°¢Ò“°¢Fö7VÖVçBæ&öG’æFDWfVçDÆ—7FVæW"‚&6Æ–6²"Â†WfVçB’Óâ°¢–b‚WfVçBçF&vWBæ6Æ÷6W7B‚%¶FF×7F'BÖwV–FRÖ6öÆÆV7F–öåÒ"’’&WGW&ã°¢WfVçBç&WfVçDFVfVÇB‚“°¢7F'DwV–FU&V6öÆÆV7F–öâ‚“°¢Ò“°¢7F—fFR‚'6V&6‚"“°¢Ð ¢–b†Fö7VÖVçBç&VG•7FFRÓÓÒ&ÆöF–ær"’°¢Fö7VÖVçBæFDWfVçDÆ—7FVæW"‚$DôÔ6öçFVçDÆöFVB"Â&ö÷B“°¢ÒVÇ6R°¢&ö÷B‚“°¢Ð§Ò’‚“°