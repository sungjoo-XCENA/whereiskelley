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
    @media (max-width: 980px) {
      .dashboard-grid,
      .dashboard-split {
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
    const local = await fetchJson("http://localhost:4317/api/guide-collection", null);
    if (!isEmptyGuidePayload(local)) {
      local.source = "browser_localhost";
      state.localGuideSeen = true;
      state.lastLocalGuidePayload = local;
      return local;
    }
    if (state.localGuideSeen && state.lastLocalGuidePayload) {
      state.lastLocalGuidePayload.source = "browser_localhost_stale";
      return state.lastLocalGuidePayload;
    }
    const proxied = await fetchJson("/api/guide-collection", null);
    if (!isEmptyGuidePayload(proxied)) return proxied;
    return proxied;
  }

  async function startGuideRecollection() {
    if (state.guideActionInFlight) return;
    const password = window.prompt("Enter the recollection password.");
    if (!password) return;
    state.guideActionInFlight = true;
    state.guideActionKind = "";
    state.guideActionMessage = "Starting recollection...";
    renderDashboard();
    try {
      const response = await fetch("/api/guide-collection", {
        method: "POST",
        headers: { "content-type": "application/json" },
        cache: "no-store",
        body: JSON.stringify({ password })
      });
      const payload = await response.json().catch(() => ({}));
      if (!response.ok || payload.ok === false) {
        state.guideActionKind = "bad";
        state.guideActionMessage = payload.error || `Could not start recollection. HTTP ${response.status}`;
        return;
      }
      state.guideActionKind = "good";
      state.guideActionMessage = payload.message || "Recollection started.";
      state.guideLoadedOnce = false;
      await loadGuideStats({ force: true });
      window.setTimeout(() => loadGuideStats({ force: true }), 2500);
      window.setTimeout(() => loadGuideStats({ force: true }), 8000);
    } catch (error) {
      state.guideActionKind = "bad";
      state.guideActionMessage = `Could not reach the collection API: ${error.message || error}`;
    } finally {
      state.guideActionInFlight = false;
      if (state.activeView === "dashboard") renderDashboard();
    }
  }

  function ensureDashboardView() {
    let view = document.querySelector("#dashboardView");
    if (!view) {
      const commandBar = document.querySelector(".command-bar");
      view = document.createElement("section");
      view.id = "dashboardView";
      view.className = "app-view";
      view.dataset.viewPanel = "dashboard";
      commandBar?.insertAdjacentElement("beforebegin", view);
    }
    return view;
  }

  function cleanTabs() {
    let nav = document.querySelector(".view-tabs");
    if (!nav) {
      nav = document.createElement("nav");
      nav.className = "view-tabs";
      document.querySelector(".app-header")?.insertAdjacentElement("afterend", nav);
    }
    nav.innerHTML = [
      ["search", "Search"],
      ["dashboard", "Dashboard"]
    ].map(([key, label]) => `<button class="view-tab" type="button" data-view="${key}">${label}</button>`).join("");
    document.querySelector("#watchlistView")?.remove();
    document.querySelectorAll(".source-strip").forEach((node) => node.remove());
    return nav;
  }

  function activate(view) {
    state.activeView = view;
    ensureDashboardView();
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
    if (view === "dashboard") {
      renderDashboard();
      if (!state.guideLoadedOnce) loadGuideStats({ force: true });
    }
    if (showSearch) {
      try {
        if (typeof renderMap === "function") renderMap(typeof latestResults === "undefined" ? [] : latestResults);
      } catch (_error) {}
    }
  }

  function progressValues(payload) {
    const progress = payload?.progress || {};
    const counts = payload?.counts || {};
    const latestRun = payload?.latestRuns?.[0] || {};
    const summary = payload?.collectionSummary || {};
    const running = progress.status === "running" && !progress.stale;
    const stopped = progress.status === "stalled" || Boolean(progress.stale);
    const completed = progress.status === "completed" || latestRun.status === "completed";
    const summaryTotal = number(summary.totalTargets || counts.targets || latestRun.target_count);
    const summaryChecked = number(summary.checkedTargets || latestRun.websites_checked);
    const rawProcessed = number(progress.processedTargets ?? progress.websitesChecked ?? latestRun.websites_checked);
    const rawTotal = number(progress.totalWebsites || summary.totalTargets || counts.targets || latestRun.target_count);
    const useSummaryProgress = completed && summaryTotal && summaryChecked && (!rawTotal || rawTotal < summaryTotal);
    const processed = useSummaryProgress ? summaryChecked : rawProcessed;
    const total = useSummaryProgress ? summaryTotal : rawTotal;
    const percent = total ? Math.min(100, Math.max(0, useSummaryProgress ? ((processed / total) * 100) : number(progress.progressPercent || ((processed / total) * 100)))) : 0;
    return {
      progress,
      counts,
      latestRun,
      summary,
      running,
      stopped,
      processed,
      total,
      remaining: total ? Math.max(0, total - processed) : 0,
      percent,
      elapsed: progress.elapsedSeconds ?? secondsBetween(progress.startedAt || latestRun.started_at, progress.finishedAt || latestRun.finished_at),
      duration: progress.durationSeconds ?? secondsBetween(progress.startedAt || latestRun.started_at, progress.finishedAt || latestRun.finished_at),
      status: running ? "Collecting" : stopped ? "Stopped" : latestRun.status === "completed" ? "Done" : "Ready"
    };
  }

  function statusLabel(status) {
    const labels = {
      found: "Candidate found",
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
      number(target.chosenWineLineCount) > 0
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
    return targets
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
      .join("|");
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
    if (state.activeView !== "dashboard") return;
    const targets = visibleMapTargets(payload);
    if (!targets.length) {
      if (state.dashboardMarkers.size) return;
      for (const marker of state.dashboardMarkers.values()) marker.setMap(null);
      state.dashboardMarkers.clear();
      fallbackEl.classList.remove("hidden");
      fallbackEl.innerHTML = `<b>No mapped restaurants yet</b><span>Coordinates will appear as the collector resolves restaurants.</span>`;
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
    const payload = state.guidePayload || {};
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
    renderSelectedTarget(state.guidePayload || {});
    renderDashboardMap(state.guidePayload || {}, { fit: true });
    document.querySelector('[data-dashboard-section="map"]')?.scrollIntoView({ behavior: "smooth", block: "start" });
  }

  function selectedTargetMarkup(payload) {
    const target = (payload?.mapTargets || []).find((item) => String(item.id) === String(state.activeTargetId || ""));
    if (!target) {
      return `<div class="selected-target empty">
        <h3>No restaurant selected</h3>
        <p>Click a marker on the map to inspect one restaurant.</p>
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
        <p class="dash-kicker">Selected restaurant</p>
        <h3>${html(target.name || "Unknown")}</h3>
        <p>${html(location || "Unknown location")}</p>
      </div>
      <div class="selected-target-grid">
        <div class="metric-box"><span>Status</span><b>${targetPill(target)}</b></div>
        <div class="metric-box"><span>Last checked</span><b>${html(target.lastCheckedAt || "-")}</b></div>
      </div>
      <div class="selected-target-actions">
        ${target.wineListUrl ? `<a class="${kind === "found" ? "" : "secondary"}" href="${html(target.wineListUrl)}" target="_blank" rel="noreferrer">${html(wineListLabel)}</a>` : ""}
        ${target.websiteUrl && target.websiteUrl !== target.wineListUrl ? `<a class="secondary" href="${html(target.websiteUrl)}" target="_blank" rel="noreferrer">Official website</a>` : ""}
        <a class="secondary" href="${html(googleMapUrl)}" target="_blank" rel="noreferrer">Google Maps</a>
        <button class="secondary" type="button" data-clear-dashboard-selection>Close</button>
      </div>
    </div>`;
  }

  function renderSelectedTarget(payload) {
    const container = document.querySelector("#selectedRestaurant");
    if (container) container.innerHTML = selectedTargetMarkup(payload);
  }

  function renderDashboard() {
    const root = ensureDashboardView();
    const payload = state.guidePayload || {};
    const values = progressValues(payload);
    const summary = values.summary;
    const progress = values.progress;
    const mapped = visibleMapTargets(payload).length;
    const mappedWithWebsite = number(summary.mappedWithWebsite) || mapped;
    const progressCounts = progress.dbCounts || {};
    const sourceCount = Math.max(
      number(summary.totalSources),
      number(payload.counts?.wineListSources),
      number(progressCounts.wineListSources),
      number(progress.wineListsFound)
    );
    const savedLines = Math.max(
      number(payload.counts?.wineLines),
      number(progressCounts.wineLines),
      number(progress.wineLinesFound)
    );
    const parsedSources = number(summary.parsedSources);
    const reviewSources = Math.max(number(summary.parseReviewSources), Math.max(0, sourceCount - parsedSources));
    const found = number(summary.foundWineList);
    const none = number(summary.noWineList);
    const pending = number(summary.pending) + number(summary.missingWebsite);
    const errorCount = number(summary.errors || values.progress.errors);
    const etaText = values.running
      ? `${formatDuration(progress.estimatedRemainingSeconds)}${progress.estimatedFinishAt ? ` / ${formatTime(progress.estimatedFinishAt)}` : ""}`
      : formatDuration(values.duration);
    const collectionText = values.running
      ? "The local PC collector is running now."
      : values.stopped
        ? "The local PC collector stopped reporting progress."
        : "No background collection is running right now.";
    const progressTitle = values.running
      ? "Collecting restaurant wine lists"
      : values.stopped
        ? "Collection stopped"
        : "Collection status";
    const progressPillClass = values.running ? "good" : values.stopped ? "warn" : "";

    const cardsHtml = `<div class="dashboard-grid" data-dashboard-section="cards">
      <div class="dashboard-card"><span>Collection</span><b>${html(values.status)}</b><small>${html(collectionText)}</small></div>
      <div class="dashboard-card"><span>Progress</span><b>${html(values.percent.toFixed(1))}%</b><small>${html(fmtInt(values.processed))} checked / ${html(fmtInt(values.remaining))} left / ${html(fmtInt(values.total))} total</small></div>
      <div class="dashboard-card"><span>Wine-list sources</span><b>${html(fmtInt(sourceCount))}</b><small>${html(fmtInt(parsedSources))} verified sources, ${html(fmtInt(savedLines))} saved wine lines.</small></div>
      <div class="dashboard-card"><span>Needs review</span><b>${html(fmtInt(reviewSources + errorCount))}</b><small>${html(fmtInt(reviewSources))} parser reviews / ${html(fmtInt(errorCount))} restaurant errors.</small></div>
    </div>`;

    const progressHtml = `<section class="dash-panel" data-dashboard-section="progress">
      <div class="collection-head">
        <div>
          <p class="dash-kicker">Collect progress</p>
          <h2>${html(progressTitle)}</h2>
        </div>
        <div class="selected-target-actions dashboard-progress-actions">
          <span class="dash-pill ${progressPillClass}">${html(values.status)}</span>
          <button class="dashboard-refresh" type="button" data-start-guide-collection ${values.running || state.guideActionInFlight ? "disabled" : ""}>${html(state.guideActionInFlight ? "Starting..." : "Start recollection")}</button>
          <button class="dashboard-refresh" type="button" data-refresh-dashboard ${state.guideLoadInFlight ? "disabled" : ""}>${html(state.guideLoadInFlight ? "Refreshing..." : "Refresh")}</button>
          ${state.guideActionMessage ? `<span class="dashboard-action-note ${html(state.guideActionKind)}">${html(state.guideActionMessage)}</span>` : ""}
          ${state.lastRefreshAt ? `<span class="dashboard-action-note">Last refreshed ${html(state.lastRefreshAt)}</span>` : ""}
        </div>
      </div>
      <div class="dash-progress" style="--dash-progress:${html(values.percent)}%"><i></i></div>
      <div class="collection-metrics">
        <div class="metric-box"><span>Checked</span><b>${html(fmtInt(values.processed))} / ${html(fmtInt(values.total))}</b></div>
        <div class="metric-box"><span>Remaining</span><b>${html(fmtInt(values.remaining))}</b></div>
        <div class="metric-box"><span>Elapsed</span><b>${html(formatDuration(values.elapsed))}</b></div>
        <div class="metric-box"><span>${values.running ? "ETA" : "Total time"}</span><b>${html(etaText)}</b></div>
        <div class="metric-box"><span>Current restaurant</span><b>${html(progress.currentTarget || "-")}</b></div>
        <div class="metric-box"><span>Errors</span><b>${html(fmtInt(errorCount))}</b></div>
      </div>
    </section>`;

    const summaryHtml = `<section class="dash-panel" data-dashboard-section="summary">
      <p class="dash-kicker">DB summary</p>
      <h2>What the collector found</h2>
      <div class="db-health-grid">
        <div class="metric-box"><span>Restaurants saved</span><b>${html(fmtInt(summary.totalTargets || values.total))}</b></div>
        <div class="metric-box"><span>Verified wine lists</span><b>${html(fmtInt(found))}</b></div>
        <div class="metric-box"><span>No wine list</span><b>${html(fmtInt(none))}</b></div>
        <div class="metric-box"><span>Pending / no website</span><b>${html(fmtInt(pending))}</b></div>
        <div class="metric-box"><span>Parsing review</span><b>${html(fmtInt(reviewSources))}</b></div>
        <div class="metric-box"><span>Mapped DB URLs</span><b>${html(fmtInt(mappedWithWebsite))}</b></div>
      </div>
    </section>`;

    const mapHtml = `<section class="dash-panel" data-dashboard-section="map">
      <div class="collection-head">
        <div>
          <p class="dash-kicker">Restaurant map</p>
          <h2>Wine-list coverage</h2>
        </div>
        <div class="map-legend">
          <span class="legend-dot" style="--dot:#16a34a">Found</span>
          <span class="legend-dot" style="--dot:#dc2626">No wine list</span>
          <span class="legend-dot" style="--dot:#f59e0b">Pending / review</span>
        </div>
      </div>
      <div class="dashboard-map-wrap">
        <div id="dashboardDbMap"></div>
        <div id="dashboardMapFallback" class="dashboard-map-fallback"><b>Loading map</b><span>Restaurant coordinates are being prepared.</span></div>
      </div>
    </section>`;

    const selectedHtml = `<section class="dash-panel" id="selectedRestaurant">
      ${selectedTargetMarkup(payload)}
    </section>`;

    const mapAlreadyMounted = Boolean(root.querySelector("#dashboardDbMap"));
    if (!mapAlreadyMounted) {
      root.innerHTML = `${cardsHtml}${progressHtml}${summaryHtml}${mapHtml}${selectedHtml}`;
      renderDashboardMap(payload, { fit: true });
      return;
    }
    const cards = root.querySelector('[data-dashboard-section="cards"]');
    const progressSection = root.querySelector('[data-dashboard-section="progress"]');
    const summarySection = root.querySelector('[data-dashboard-section="summary"]');
    if (cards) cards.outerHTML = cardsHtml;
    if (progressSection) progressSection.outerHTML = progressHtml;
    if (summarySection) summarySection.outerHTML = summaryHtml;
    renderSelectedTarget(payload);
    renderDashboardMap(payload, { fit: false });
  }

  async function loadGuideStats(options = {}) {
    if (state.guideLoadInFlight) return;
    if (state.guideLoadedOnce && !options.force) return;
    state.guideLoadInFlight = true;
    if (options.force) {
      state.guideActionKind = "";
      state.guideActionMessage = "Refreshing dashboard data...";
      if (state.activeView === "dashboard") renderDashboard();
    }
    try {
      const payload = await fetchLiveGuideCollection();
      if (isEmptyGuidePayload(payload) && state.guidePayload) return;
      state.guidePayload = payload;
      state.guideLoadedOnce = true;
      state.lastRefreshAt = new Date().toLocaleTimeString();
      if (options.force && !state.guideActionMessage.includes("started")) {
        state.guideActionKind = "good";
        state.guideActionMessage = "Dashboard data refreshed.";
      }
      if (state.activeView === "dashboard") renderDashboard();
    } catch (error) {
      state.guideActionKind = "bad";
      state.guideActionMessage = `Refresh failed: ${error.message || error}`;
    } finally {
      state.guideLoadInFlight = false;
      if (state.activeView === "dashboard") renderDashboard();
    }
  }

  function boot() {
    const nav = cleanTabs();
    ensureDashboardView();
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
      if (!event.target.closest("[data-refresh-dashboard]")) return;
      event.preventDefault();
      loadGuideStats({ force: true });
    });
    document.body.addEventListener("click", (event) => {
      if (!event.target.closest("[data-start-guide-collection]")) return;
      event.preventDefault();
      startGuideRecollection();
    });
    activate("search");
  }

  if (document.readyState === "loading") {
    document.addEventListener("DOMContentLoaded", boot);
  } else {
    boot();
  }
})();
