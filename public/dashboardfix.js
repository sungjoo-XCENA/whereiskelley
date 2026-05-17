(function () {
  const state = {
    db: null,
    dbStatus: "checking",
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

  async function loadDbStats() {
    state.dbStatus = "checking";
    renderDashboard();
    try {
      const response = await fetch("/api/stats", { cache: "no-store" });
      if (!response.ok) throw new Error(await response.text());
      state.db = await response.json();
      state.dbStatus = "connected";
    } catch (_error) {
      state.db = null;
      state.dbStatus = "missing";
    }
    renderDashboard();
  }

  function dashboardStats() {
    const groups = getGroups();
    const reviewGroups = groups.filter((group) => !priceIsValid(lowestResult(group)) || reviewReason(group));
    const countries = new Set(groups.map((group) => group.venue?.country).filter(Boolean));
    return {
      places: groups.length,
      lines: getResults().length,
      countries: countries.size,
      reviews: reviewGroups.length
    };
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
    const stats = dashboardStats();
    const db = state.db || {};
    const dbConnected = state.dbStatus === "connected";
    const watchHitCount = state.watchlist.reduce((sum, watch) => sum + watchHits(watch.keyword).length, 0);
    const lastRun = db.lastRun || null;
    const lastRunText = lastRun?.finished_at || lastRun?.started_at || "";
    const running = Boolean(lastRun?.started_at && !lastRun?.finished_at);
    const collectionStatus = running ? "Running" : lastRun ? "Completed" : dbConnected ? "Ready" : "Waiting";
    const collectionDetail = running
      ? "A background collection is running now."
      : lastRun
        ? `Last checked ${html(lastRunText || "unknown time")}. Saved ${html(lastRun.parsed_entries || 0)} wine lines with ${html(lastRun.errors || 0)} issues.`
        : "No background collection has run yet.";
    const savedDetail = dbConnected
      ? `${html(db.venueCount || 0)} places / ${html(db.wineListCount || 0)} wine lists / ${html(db.entryCount || 0)} wine lines`
      : "No saved collection is available yet.";
    const watchDetail = `${html(state.watchlist.length)} watched keywords. ${html(watchHitCount)} matches are visible in the current search.`;
    const alertDetail = watchHitCount
      ? `${html(watchHitCount)} current matches can be reviewed from this dashboard.`
      : "New matches will appear here after a search or after a scheduled collection runs.";
    const watchRows = state.watchlist.map((watch, index) => {
      const hits = watchHits(watch.keyword);
      return `<div class="watch-row">
        <div><b>${html(watch.keyword)}</b><span>${html(watch.vintage || "Any vintage")} / ${html(hits.length)} live hits in the current search</span></div>
        <span class="dash-pill${hits.length ? " live" : ""}">${hits.length ? "Found" : "Watching"}</span>
        <button class="dash-remove" type="button" data-dashboard-remove="${index}">Remove</button>
      </div>`;
    }).join("");

    root.innerHTML = `<div class="dashboard-grid">
      <div class="dashboard-card"><span>Collection</span><b>${html(collectionStatus)}</b><small>${collectionDetail}</small></div>
      <div class="dashboard-card"><span>Saved wines</span><b>${dbConnected ? html(db.entryCount || 0) : "--"}</b><small>${savedDetail}</small></div>
      <div class="dashboard-card"><span>Watchlist hits</span><b>${html(watchHitCount)}</b><small>${watchDetail}</small></div>
      <div class="dashboard-card"><span>Needs review</span><b>${html(stats.reviews)}</b><small>Places needing price, PDF, or manual checks from the current search.</small></div>
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
        <p class="dash-kicker">Collection status</p>
        <h2>Background collection</h2>
        <table class="dash-table">
          <tbody>
            <tr><th>Item</th><th>Status</th><th>Detail</th></tr>
            <tr><td>Collector</td><td><span class="dash-pill${running || lastRun ? " live" : ""}">${html(collectionStatus)}</span></td><td>${collectionDetail}</td></tr>
            <tr><td>Saved results</td><td><span class="dash-pill${dbConnected ? " live" : ""}">${dbConnected ? "Available" : "Waiting"}</span></td><td>${savedDetail}</td></tr>
            <tr><td>Watchlist scan</td><td><span class="dash-pill${watchHitCount ? " live" : ""}">${watchHitCount ? "Matches found" : "Watching"}</span></td><td>${watchDetail}</td></tr>
            <tr><td>Alerts</td><td><span class="dash-pill${watchHitCount ? " review" : ""}">${watchHitCount ? "Review" : "Waiting"}</span></td><td>${alertDetail}</td></tr>
            <tr><td>Guide lists</td><td><span class="dash-pill">Planned</span></td><td>Michelin, World's 50 Best, and La Liste collection will feed this same dashboard once the scheduled collector is connected.</td></tr>
          </tbody>
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
    loadDbStats();
  }

  if (document.readyState === "loading") {
    document.addEventListener("DOMContentLoaded", boot);
  } else {
    boot();
  }
})();
