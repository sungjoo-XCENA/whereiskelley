(function () {
  const state = {
    guide: null,
    guideProgress: null,
    guideTargets: [],
    guideHits: [],
    watchlist: []
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
    .dash-table th,
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
    .dashboard-main {
      display: grid;
      grid-template-columns: minmax(0, 1.05fr) minmax(320px, 0.95fr);
      gap: 14px;
      margin-top: 14px;
    }
    .dash-panel {
      padding: 16px;
    }
    .dash-panel h2 {
      margin: 4px 0 12px;
    }
    .watch-form {
      display: grid;
      grid-template-columns: minmax(220px, 1fr) 110px 96px;
      gap: 10px;
      margin-bottom: 12px;
    }
    .watch-items {
      display: grid;
      gap: 8px;
    }
    .watch-row {
      display: grid;
      grid-template-columns: minmax(0, 1fr) auto auto;
      gap: 10px;
      align-items: center;
      padding: 11px 12px;
      border: 1px solid var(--line);
      border-radius: 8px;
      background: #fff;
    }
    .watch-row b {
      display: block;
      font-weight: 950;
    }
    .watch-row span {
      display: block;
      margin-top: 3px;
      color: var(--muted);
      font-size: 12px;
      font-weight: 750;
    }
    .dash-table {
      width: 100%;
      border-collapse: collapse;
      font-size: 13px;
    }
    .dash-table th,
    .dash-table td {
      padding: 10px 9px;
      border-top: 1px solid var(--line);
      text-align: left;
      vertical-align: middle;
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
    .dash-pill.live {
      background: #ecfdf5;
      color: #047857;
    }
    .dash-pill.review {
      background: #fff7ed;
      color: #b45309;
    }
    .dash-remove {
      min-height: 30px;
      border-color: var(--line);
      background: #fff;
      color: var(--muted);
      font-size: 12px;
    }
    @media (max-width: 980px) {
      .dashboard-grid,
      .dashboard-main,
      .watch-form {
        grid-template-columns: 1fr;
      }
      .watch-row {
        grid-template-columns: minmax(0, 1fr) auto;
      }
    }
  `;
  document.head.appendChild(css);

  function html(value) {
    const div = document.createElement("div");
    div.textContent = value == null ? "" : String(value);
    return div.innerHTML;
  }

  function getResults() {
    try {
      return typeof latestResults === "undefined" ? [] : latestResults || [];
    } catch (_error) {
      return [];
    }
  }

  function getGroups() {
    try {
      return typeof groupedVenues === "function" ? groupedVenues(getResults()) : [];
    } catch (_error) {
      return [];
    }
  }

  function priceIsValid(result) {
    try {
      return typeof hasValidPrice === "function" ? hasValidPrice(result) : Boolean(result?.price);
    } catch (_error) {
      return Boolean(result?.price);
    }
  }

  function lowestResult(group) {
    try {
      return typeof groupLowestPriceResult === "function" ? groupLowestPriceResult(group) : group?.results?.[0];
    } catch (_error) {
      return group?.results?.[0];
    }
  }

  function reviewReason(group) {
    try {
      return typeof groupPdfReviewReason === "function" ? groupPdfReviewReason(group) : "";
    } catch (_error) {
      return "";
    }
  }

  function watchHits(keyword) {
    const needle = String(keyword || "").toLowerCase();
    if (!needle) return [];
    return getResults().filter((result) => String(result.text || "").toLowerCase().includes(needle));
  }

  function loadWatchlist() {
    try {
      state.watchlist = JSON.parse(localStorage.getItem("whereiskelley.watchlist") || "[]");
    } catch (_error) {
      state.watchlist = [];
    }
    if (!state.watchlist.length) {
      state.watchlist = [
        { keyword: "Romanee-Conti", vintage: "" },
        { keyword: "William Kelley", vintage: "" }
      ];
      saveWatchlist();
    }
  }

  function saveWatchlist() {
    localStorage.setItem("whereiskelley.watchlist", JSON.stringify(state.watchlist));
  }

  async function fetchJson(path, fallback) {
    try {
      const response = await fetch(path, { cache: "no-store" });
      return response.ok ? response.json() : fallback;
    } catch (_error) {
      return fallback;
    }
  }

  function progressFromStatus(status) {
    const run = status?.lastRun;
    const counts = status?.counts || {};
    if (!run) return null;
    return {
      generatedAt: status.generatedAt || "",
      status: run.status || "completed",
      phase: run.status || "completed",
      message: run.status === "running" ? "Guide collection is running." : "Latest collection snapshot.",
      runId: run.id || null,
      source: run.sources_requested || "",
      currentTarget: "",
      currentUrl: "",
      targetsCollected: run.target_count || counts.targets || 0,
      websitesChecked: run.websites_checked || 0,
      totalWebsites: run.websites_checked || 0,
      wineListsFound: run.wine_lists_found || counts.sources || 0,
      wineLinesFound: run.wine_lines_found || counts.wineLines || 0,
      errors: run.errors || 0
    };
  }

  async function loadGuideStats() {
    try {
      const [status, progress, targets, hits] = await Promise.all([
        fetchJson("/data/guide-status.json", null),
        fetchJson("/data/guide-progress.json", null),
        fetchJson("/data/guide-targets.json", []),
        fetchJson("/data/guide-watch-hits.json", [])
      ]);
      state.guide = status;
      state.guideProgress = progress || progressFromStatus(status);
      state.guideTargets = Array.isArray(targets) ? targets : [];
      state.guideHits = Array.isArray(hits) ? hits : [];
    } catch (_error) {
      state.guide = null;
      state.guideProgress = null;
      state.guideTargets = [];
      state.guideHits = [];
    }
    renderDashboard();
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
    if (view === "dashboard") renderDashboard();
    if (showSearch) {
      try {
        if (typeof renderMap === "function") renderMap(getResults());
      } catch (_error) {}
    }
  }

  function renderDashboard() {
    const root = ensureDashboardView();
    const guide = state.guide || {};
    const progress = state.guideProgress || {};
    const guideCounts = guide.counts || {};
    const watchHitCount = state.watchlist.reduce((sum, watch) => sum + watchHits(watch.keyword).length, 0);
    const guideHitCount = state.guideHits.length;
    const guideRun = guide.lastRun || null;
    const progressRunning = progress.status === "running";
    const guideStatus = progressRunning ? "running" : guideRun?.status || (guide ? "ready" : "waiting");
    const guideDetail = progressRunning
      ? `${html(progress.phase || "collecting")} - ${html(progress.message || "Collection is running.")}`
      : guideRun
      ? `${html(guideRun.sources_requested || "Guides")} checked. ${html(guideCounts.targets || 0)} restaurant targets, ${html(guideCounts.sources || 0)} wine-list sources.`
      : "Michelin, La Liste, and World's 50 Best collector has not exported a guide snapshot yet.";
    const websiteProgress = progress.totalWebsites
      ? `${html(progress.websitesChecked || 0)} / ${html(progress.totalWebsites)}`
      : html(progress.websitesChecked || 0);
    const progressRows = `<tr><td>Phase</td><td><span class="dash-pill${progressRunning ? " live" : ""}">${html(progress.phase || guideStatus)}</span></td><td>${html(progress.message || "No collection is running right now.")}</td></tr>
      <tr><td>Current place</td><td colspan="2">${html(progress.currentTarget || "-")}</td></tr>
      <tr><td>Current URL</td><td colspan="2">${progress.currentUrl ? `<a href="${html(progress.currentUrl)}" target="_blank" rel="noreferrer">${html(progress.currentUrl)}</a>` : "-"}</td></tr>
      <tr><td>Guide places</td><td colspan="2">${html(progress.targetsCollected || guideCounts.targets || 0)} collected</td></tr>
      <tr><td>Websites checked</td><td colspan="2">${websiteProgress}</td></tr>
      <tr><td>Wine lists / lines</td><td colspan="2">${html(progress.wineListsFound || guideCounts.sources || 0)} lists / ${html(progress.wineLinesFound || guideCounts.wineLines || 0)} lines</td></tr>
      <tr><td>Errors</td><td colspan="2">${html(progress.errors || 0)}</td></tr>`;
    const watchDetail = `${html(state.watchlist.length)} watched keywords. ${html(watchHitCount)} current-search hits / ${html(guideHitCount)} collected-guide hits.`;
    const alertDetail = guideHitCount || watchHitCount
      ? `${html(guideHitCount + watchHitCount)} matches can be reviewed from this dashboard.`
      : "New matches will appear here after a search or after a scheduled guide collection runs.";
    const watchRows = state.watchlist.map((watch, index) => {
      const hits = watchHits(watch.keyword);
      return `<div class="watch-row">
        <div><b>${html(watch.keyword)}</b><span>${html(watch.vintage || "Any vintage")} / ${html(hits.length)} live hits in the current search</span></div>
        <span class="dash-pill${hits.length ? " live" : ""}">${hits.length ? "Found" : "Watching"}</span>
        <button class="dash-remove" type="button" data-dashboard-remove="${index}">Remove</button>
      </div>`;
    }).join("");

    const targetRows = state.guideTargets.slice(0, 12).map((target) => {
      let sources = [];
      try { sources = JSON.parse(target.sources_json || "[]"); } catch (_error) {}
      return `<tr>
        <td><b>${html(target.name)}</b><br><span>${html([target.city, target.country].filter(Boolean).join(", "))}</span></td>
        <td>${sources.map((source) => `<span class="dash-pill">${html(source)}</span>`).join(" ") || "-"}</td>
        <td><span class="dash-pill${target.status === "found" ? " live" : target.status === "review" || target.status === "error" ? " review" : ""}">${html(target.status || "not_checked")}</span></td>
        <td>${target.website_url ? `<a href="${html(target.website_url)}" target="_blank" rel="noreferrer">Website</a>` : "<span class=\"dash-pill review\">Missing</span>"}</td>
      </tr>`;
    }).join("");
    const hitRows = state.guideHits.slice(0, 10).map((hit) => `<tr>
      <td>${html(hit.raw_text)}</td>
      <td>${html(hit.vintage || "")}</td>
      <td>${html([hit.currency, hit.price_text || hit.price_value || ""].filter(Boolean).join(" "))}</td>
      <td>${html([hit.name, hit.city, hit.country].filter(Boolean).join(", "))}</td>
    </tr>`).join("");

    root.innerHTML = `<div class="dashboard-grid">
      <div class="dashboard-card"><span>Guide collection</span><b>${html(guideStatus)}</b><small>${guideDetail}</small></div>
      <div class="dashboard-card"><span>Places tracked</span><b>${html(guideCounts.targets || progress.targetsCollected || 0)}</b><small>Restaurants and wine-list places from Michelin, La Liste, and World's 50 Best.</small></div>
      <div class="dashboard-card"><span>Wine lists found</span><b>${html(guideCounts.sources || 0)}</b><small>${html(guideCounts.wineLines || 0)} collected wine lines.</small></div>
      <div class="dashboard-card"><span>Watchlist hits</span><b>${html(guideHitCount + watchHitCount)}</b><small>${watchDetail}</small></div>
    </div>
    <div class="dashboard-main">
      <section class="dash-panel">
        <p class="dash-kicker">Watchlist</p>
        <h2>Watched wines</h2>
        <form class="watch-form" id="dashboardWatchForm">
          <input id="dashboardWatchKeyword" type="search" placeholder="Romanee-Conti, Coche-Dury, Raveneau..." autocomplete="off">
          <input id="dashboardWatchVintage" type="search" placeholder="Vintage" maxlength="4">
          <button type="submit">Add</button>
        </form>
        <div class="watch-items">${watchRows || `<div class="watch-row"><div><b>No keywords yet</b><span>Add one here.</span></div></div>`}</div>
      </section>
      <section class="dash-panel">
        <p class="dash-kicker">Live progress</p>
        <h2>Collection progress</h2>
        <table class="dash-table">
          <tbody>${progressRows}</tbody>
        </table>
      </section>
      <section class="dash-panel">
        <p class="dash-kicker">Guide collection</p>
        <h2>Place targets</h2>
        <table class="dash-table">
          <thead><tr><th>Place</th><th>Sources</th><th>Status</th><th>Website</th></tr></thead>
          <tbody>${targetRows || `<tr><td colspan="4">No guide targets collected yet.</td></tr>`}</tbody>
        </table>
      </section>
      <section class="dash-panel">
        <p class="dash-kicker">Alerts</p>
        <h2>Collected watch hits</h2>
        <table class="dash-table">
          <thead><tr><th>Wine line</th><th>Vintage</th><th>Price</th><th>Restaurant</th></tr></thead>
          <tbody>${hitRows || `<tr><td colspan="4">${alertDetail}</td></tr>`}</tbody>
        </table>
      </section>
    </div>`;
  }

  function boot() {
    loadWatchlist();
    const nav = cleanTabs();
    ensureDashboardView();
    nav.addEventListener("click", (event) => {
      const button = event.target.closest("[data-view]");
      if (!button) return;
      window.setTimeout(() => activate(button.dataset.view), 0);
    }, true);
    document.body.addEventListener("submit", (event) => {
      if (event.target?.id !== "dashboardWatchForm") return;
      event.preventDefault();
      const keyword = document.querySelector("#dashboardWatchKeyword")?.value?.trim();
      const vintage = document.querySelector("#dashboardWatchVintage")?.value?.trim() || "";
      if (!keyword) return;
      state.watchlist.push({ keyword, vintage });
      saveWatchlist();
      renderDashboard();
    });
    document.body.addEventListener("click", (event) => {
      const remove = event.target.closest("[data-dashboard-remove]");
      if (!remove) return;
      state.watchlist.splice(Number(remove.dataset.dashboardRemove), 1);
      saveWatchlist();
      renderDashboard();
    });
    const cleanup = new MutationObserver(() => {
      document.querySelectorAll(".source-strip").forEach((node) => node.remove());
      document.querySelector("#watchlistView")?.remove();
      renderDashboard();
    });
    const results = document.querySelector("#results");
    if (results) cleanup.observe(results, { childList: true, subtree: true });
    activate("search");
    loadGuideStats();
    window.setInterval(loadGuideStats, 5000);
  }

  if (document.readyState === "loading") {
    document.addEventListener("DOMContentLoaded", boot);
  } else {
    boot();
  }
})();
