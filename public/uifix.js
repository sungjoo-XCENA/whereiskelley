(function () {
  const style = document.createElement("style");
  style.textContent = `
    .result-table > thead > tr > th:nth-child(7),
    .result-table > tbody > tr.place-row > td:nth-child(7) {
      display: none !important;
    }
    .map-link,
    .actions.compact a.map-link {
      border-color: rgba(23, 92, 80, 0.28);
      background: #eefaf6;
      color: #0f766e;
    }
    .map-link:hover,
    .actions.compact a.map-link:hover {
      border-color: rgba(23, 92, 80, 0.45);
      background: #dff5ef;
      color: #0f5f58;
    }
    .view-tabs {
      display: flex;
      gap: 8px;
      align-items: center;
      margin: 0 0 14px;
      padding: 6px;
      border: 1px solid var(--line);
      border-radius: 10px;
      background: rgba(255, 255, 255, 0.8);
      box-shadow: 0 10px 30px rgba(16, 24, 40, 0.05);
      overflow-x: auto;
    }
    .view-tab {
      min-height: 38px;
      border: 0;
      border-radius: 8px;
      background: transparent;
      color: var(--muted);
      white-space: nowrap;
      font-size: 13px;
    }
    .view-tab:hover,
    .view-tab.active {
      background: var(--ink);
      color: #fff;
    }
    .app-view {
      display: none;
      margin-top: 16px;
    }
    .app-view.active {
      display: block;
    }
    .dashboard-grid {
      display: grid;
      grid-template-columns: repeat(4, minmax(0, 1fr));
      gap: 12px;
    }
    .dashboard-card,
    .watch-panel,
    .guide-panel,
    .review-panel {
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
    .guide-table th,
    .mini-label {
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
      grid-template-columns: minmax(0, 1.1fr) minmax(320px, 0.9fr);
      gap: 14px;
      margin-top: 14px;
    }
    .panel-pad {
      padding: 16px;
    }
    .panel-pad h2 {
      margin-bottom: 12px;
    }
    .watch-form {
      display: grid;
      grid-template-columns: minmax(220px, 1fr) 110px 100px;
      gap: 10px;
      margin-bottom: 12px;
    }
    .watch-list,
    .mini-list {
      display: grid;
      gap: 8px;
    }
    .watch-item,
    .mini-item {
      display: grid;
      grid-template-columns: minmax(0, 1fr) auto;
      gap: 10px;
      align-items: center;
      padding: 11px 12px;
      border: 1px solid var(--line);
      border-radius: 8px;
      background: #fff;
    }
    .watch-item b,
    .mini-item b {
      display: block;
      font-weight: 950;
    }
    .watch-item span,
    .mini-item span {
      display: block;
      margin-top: 3px;
      color: var(--muted);
      font-size: 12px;
      font-weight: 750;
    }
    .ghost-button {
      min-height: 30px;
      border-color: var(--line);
      background: #fff;
      color: var(--muted);
      font-size: 12px;
    }
    .ghost-button:hover {
      border-color: rgba(159, 18, 57, 0.3);
      background: #fff5f7;
      color: var(--accent);
    }
    .guide-table {
      width: 100%;
      border-collapse: collapse;
      font-size: 13px;
    }
    .guide-table th,
    .guide-table td {
      padding: 10px 9px;
      border-top: 1px solid var(--line);
      text-align: left;
      vertical-align: middle;
    }
    .status-pill {
      display: inline-flex;
      align-items: center;
      min-height: 24px;
      padding: 0 8px;
      border-radius: 999px;
      background: #f1f5f9;
      color: var(--muted);
      font-size: 12px;
      font-weight: 850;
    }
    .status-pill.live {
      background: #ecfdf5;
      color: #047857;
    }
    .status-pill.review {
      background: #fff7ed;
      color: #b45309;
    }
    .source-strip {
      display: flex;
      flex-wrap: wrap;
      gap: 8px;
      padding: 12px 16px;
      border-bottom: 1px solid var(--line);
      background: #fbfcfe;
    }
    @media (max-width: 980px) {
      .dashboard-grid,
      .dashboard-main {
        grid-template-columns: 1fr;
      }
      .watch-form {
        grid-template-columns: 1fr;
      }
    }
  `;
  document.head.appendChild(style);

  function googleMapsSearchUrl(name, place) {
    const query = [name, place].filter(Boolean).join(", ");
    return `https://www.google.com/maps/search/?api=1&query=${encodeURIComponent(query)}`;
  }

  function expandedPlaceParts(link) {
    const expanded = link.closest(".expanded-place");
    const name = expanded?.querySelector(".expanded-head b")?.textContent.trim() || "";
    const place = expanded?.querySelector(".expanded-head span")?.textContent.trim() || "";
    return { name, place };
  }

  function tagMapLinks(root = document) {
    root.querySelectorAll(".actions.compact a").forEach((link) => {
      const label = link.textContent.trim().toLowerCase();
      if (label === "map") {
        const { name, place } = expandedPlaceParts(link);
        if (name || place) link.href = googleMapsSearchUrl(name, place);
        link.classList.add("map-link");
      }
      if (label === "star wine list page") {
        link.textContent = "Star Wine";
      }
    });
  }

  const observer = new MutationObserver((mutations) => {
    for (const mutation of mutations) {
      mutation.addedNodes.forEach((node) => {
        if (node.nodeType === Node.ELEMENT_NODE) tagMapLinks(node);
      });
    }
  });
  observer.observe(document.body, { childList: true, subtree: true });
  tagMapLinks();

  function downloadSafeName(value, fallback = "search") {
    const safeName = typeof safeZipName === "function"
      ? safeZipName(value, fallback)
      : String(value || fallback)
        .normalize("NFKD")
        .replace(/[\u0300-\u036f]/g, "")
        .replace(/[^A-Za-z0-9._-]+/g, "-")
        .replace(/^-+|-+$/g, "");
    return safeName || fallback;
  }

  function currentSearchSnapshot() {
    const query = queryInput?.value?.trim() || "";
    const country = countryInput?.value?.trim() || "";
    const city = cityInput?.value?.trim() || "";
    const vintage = vintageInput?.value?.trim() || "";
    const parts = [query, country, city, vintage].filter(Boolean);
    return {
      query,
      country,
      city,
      vintage,
      filenamePart: downloadSafeName(parts.join("-") || "all-results", "all-results"),
      text: [
        `Query: ${query || "All"}`,
        `Country: ${country || "All"}`,
        `City: ${city || "All"}`,
        `Vintage: ${vintage || "All"}`,
        `Downloaded at: ${new Date().toISOString()}`,
        `Visible result lines: ${latestResults?.length || 0}`
      ].join("\r\n")
    };
  }

  downloadSearchResults = async function patchedDownloadSearchResults() {
    const stamp = new Date().toISOString().slice(0, 10);
    const search = currentSearchSnapshot();
    const basename = `whereiskelley-${search.filenamePart}-${stamp}`;
    const button = document.querySelector("#downloadResults");
    const originalLabel = button?.textContent || "Download results";
    const csv = resultsCsv();
    if (!window.JSZip) {
      downloadBlob(new Blob([`\uFEFF${csv}`], { type: "text/csv;charset=utf-8" }), `${basename}.csv`);
      return;
    }

    const zip = new JSZip();
    const pdfs = uniquePdfDownloads();
    const pdfStatusByUrl = new Map();
    if (button) {
      button.disabled = true;
      button.textContent = pdfs.length ? `Packing PDFs 0/${pdfs.length}` : "Packing results";
    }
    try {
      for (let index = 0; index < pdfs.length; index += 1) {
        const item = pdfs[index];
        if (button) button.textContent = `Packing PDFs ${index + 1}/${pdfs.length}`;
        try {
          zip.file(item.path, await fetchPdfForZip(item));
          pdfStatusByUrl.set(item.url, { status: "Downloaded", path: item.path, error: "" });
        } catch (error) {
          pdfStatusByUrl.set(item.url, { status: "Failed", path: "", error: error.message });
        }
      }
      zip.file(`${basename}.csv`, `\uFEFF${resultsCsv(pdfStatusByUrl)}`);
      zip.file("search-query.txt", search.text);
      if (button) button.textContent = "Creating ZIP";
      const blob = await zip.generateAsync({ type: "blob" });
      downloadBlob(blob, `${basename}.zip`);
    } finally {
      if (button) {
        button.disabled = false;
        button.textContent = originalLabel;
      }
    }
  };

  const viewState = {
    current: localStorage.getItem("whereiskelley.activeView") || "dashboard",
    watchlist: []
  };

  function loadWatchlist() {
    try {
      viewState.watchlist = JSON.parse(localStorage.getItem("whereiskelley.watchlist") || "[]");
    } catch (_error) {
      viewState.watchlist = [];
    }
    if (!viewState.watchlist.length) {
      viewState.watchlist = [
        { keyword: "Romanee-Conti", vintage: "" },
        { keyword: "William Kelley", vintage: "" }
      ];
    }
  }

  function saveWatchlist() {
    localStorage.setItem("whereiskelley.watchlist", JSON.stringify(viewState.watchlist));
  }

  function dashboardStats() {
    const groups = typeof groupedVenues === "function" ? groupedVenues(latestResults || []) : [];
    const reviewGroups = groups.filter((group) => {
      const lowest = groupLowestPriceResult(group);
      return !hasValidPrice(lowest) || groupPdfReviewReason(group);
    });
    const countries = new Set(groups.map((group) => group.venue?.country).filter(Boolean));
    const prices = groups
      .map((group) => groupLowestPriceResult(group))
      .filter(hasValidPrice)
      .map((result) => krwPriceText(result))
      .filter((value) => value !== "N/A");
    return {
      places: groups.length,
      lines: latestResults?.length || 0,
      countries: countries.size,
      reviews: reviewGroups.length,
      lowestKrw: prices[0] || "N/A"
    };
  }

  function watchedHitsFor(keyword) {
    const needle = String(keyword || "").toLowerCase();
    if (!needle) return [];
    return (latestResults || []).filter((result) => String(result.text || "").toLowerCase().includes(needle));
  }

  function renderDashboardPanel() {
    const root = document.querySelector("#dashboardView");
    if (!root) return;
    const stats = dashboardStats();
    const watchItems = viewState.watchlist.map((watch) => {
      const hits = watchedHitsFor(watch.keyword);
      return `<div class="mini-item">
        <div><b>${escapeHtml(watch.keyword)}</b><span>${escapeHtml(watch.vintage || "Any vintage")} / ${escapeHtml(String(hits.length))} live hits in current search</span></div>
        <span class="status-pill${hits.length ? " live" : ""}">${hits.length ? "Found" : "Watching"}</span>
      </div>`;
    }).join("");
    root.innerHTML = `<div class="dashboard-grid">
      <div class="dashboard-card"><span>Live places</span><b>${escapeHtml(String(stats.places))}</b><small>From the current Star Wine search result set.</small></div>
      <div class="dashboard-card"><span>Wine lines</span><b>${escapeHtml(String(stats.lines))}</b><small>Search-index and verified PDF lines.</small></div>
      <div class="dashboard-card"><span>Countries</span><b>${escapeHtml(String(stats.countries))}</b><small>Mapped from city/country metadata.</small></div>
      <div class="dashboard-card"><span>Review</span><b>${escapeHtml(String(stats.reviews))}</b><small>Places needing price/PDF/manual checks.</small></div>
    </div>
    <div class="dashboard-main">
      <section class="watch-panel panel-pad">
        <p class="panel-kicker">Watchlist</p>
        <h2>Watched wines</h2>
        <div class="mini-list">${watchItems || `<div class="mini-item"><div><b>No keywords yet</b><span>Add one from the Watchlist tab.</span></div></div>`}</div>
      </section>
      <section class="guide-panel panel-pad">
        <p class="panel-kicker">Database plan</p>
        <h2>Guide collection</h2>
        <table class="guide-table">
          <tbody>
            <tr><th>Source</th><th>Status</th><th>Role</th></tr>
            <tr><td>La Liste</td><td><span class="status-pill">Schema ready</span></td><td>Top 1000 restaurant candidates</td></tr>
            <tr><td>World's 50 Best</td><td><span class="status-pill">Schema ready</span></td><td>Annual rank and place candidates</td></tr>
            <tr><td>Michelin</td><td><span class="status-pill">Schema ready</span></td><td>Stars, Bib, selected, Green Star</td></tr>
          </tbody>
        </table>
      </section>
    </div>`;
  }

  function renderWatchlistPanel() {
    const root = document.querySelector("#watchlistView");
    if (!root) return;
    const rows = viewState.watchlist.map((watch, index) => {
      const hits = watchedHitsFor(watch.keyword);
      return `<div class="watch-item">
        <div><b>${escapeHtml(watch.keyword)}</b><span>${escapeHtml(watch.vintage || "Any vintage")} / ${escapeHtml(String(hits.length))} current live hits</span></div>
        <button class="ghost-button" type="button" data-remove-watch="${index}">Remove</button>
      </div>`;
    }).join("");
    root.innerHTML = `<section class="watch-panel panel-pad">
      <p class="panel-kicker">Watchlist</p>
      <h2>Wine keywords</h2>
      <form class="watch-form" id="watchForm">
        <input id="watchKeyword" type="search" placeholder="Romanee-Conti, Coche-Dury, Raveneau..." autocomplete="off">
        <input id="watchVintage" type="search" placeholder="Vintage" maxlength="4">
        <button type="submit">Add</button>
      </form>
      <div class="watch-list">${rows || `<div class="watch-item"><div><b>No keywords yet</b><span>Add the wines you want to monitor weekly.</span></div></div>`}</div>
    </section>`;
  }

  function guideBadgeForVenue(venue = {}) {
    const name = String(venue.name || "").toLowerCase();
    if (/noma|geranium|maido|disfrutar|central|alchemist|asador|piazza duomo|mirazur|odette/.test(name)) {
      return "Guide candidate";
    }
    return "Live only";
  }

  function renderPlacesPanel() {
    const root = document.querySelector("#placesView");
    if (!root) return;
    const groups = groupedVenues(latestResults || []);
    const rows = groups.slice(0, 80).map((group) => {
      const venue = group.venue || {};
      return `<tr>
        <td><b>${escapeHtml(displayVenueName(venue))}</b><br><span class="mini-label">${escapeHtml(venue.type || "Place")}</span></td>
        <td>${escapeHtml(venue.city || "")}</td>
        <td>${escapeHtml(venue.country || "")}</td>
        <td><span class="status-pill">${escapeHtml(guideBadgeForVenue(venue))}</span></td>
        <td>${escapeHtml(placeLineLabel(group))}</td>
        <td>${krwPriceMarkup(groupLowestPriceResult(group))}</td>
      </tr>`;
    }).join("");
    root.innerHTML = `<section class="guide-panel panel-pad">
      <p class="panel-kicker">Places</p>
      <h2>Guide and live places</h2>
      <table class="guide-table">
        <thead><tr><th>Place</th><th>City</th><th>Country</th><th>Guide</th><th>Wine list</th><th>Lowest KRW</th></tr></thead>
        <tbody>${rows || `<tr><td colspan="6">Run a search to see live places here. Persistent guide DB rows will appear here after collection is connected.</td></tr>`}</tbody>
      </table>
    </section>`;
  }

  function renderReviewPanel() {
    const root = document.querySelector("#reviewView");
    if (!root) return;
    const groups = groupedVenues(latestResults || []).filter((group) => {
      const lowest = groupLowestPriceResult(group);
      return !hasValidPrice(lowest) || groupPdfReviewReason(group);
    });
    const rows = groups.map((group) => {
      const venue = group.venue || {};
      const reason = groupPdfReviewReason(group) || "Price or source needs review";
      return `<tr>
        <td><b>${escapeHtml(displayVenueName(venue))}</b></td>
        <td>${escapeHtml([venue.city, venue.country].filter(Boolean).join(", "))}</td>
        <td><span class="status-pill review">${escapeHtml(reason)}</span></td>
        <td>${escapeHtml(placeLineLabel(group))}</td>
      </tr>`;
    }).join("");
    root.innerHTML = `<section class="review-panel panel-pad">
      <p class="panel-kicker">Review</p>
      <h2>Needs review</h2>
      <table class="guide-table">
        <thead><tr><th>Place</th><th>Location</th><th>Reason</th><th>Lines</th></tr></thead>
        <tbody>${rows || `<tr><td colspan="4">No review items in the current live search.</td></tr>`}</tbody>
      </table>
    </section>`;
  }

  function refreshAppViews() {
    ensureSearchSourceStrip();
    renderDashboardPanel();
    renderWatchlistPanel();
    renderPlacesPanel();
    renderReviewPanel();
  }

  function ensureSearchSourceStrip() {
    const resultList = document.querySelector(".result-list");
    const heading = resultList?.querySelector(".panel-heading");
    if (!resultList || !heading) return;
    let strip = resultList.querySelector("#sourceStrip");
    if (!strip) {
      strip = document.createElement("div");
      strip.id = "sourceStrip";
      strip.className = "source-strip";
      heading.insertAdjacentElement("afterend", strip);
    }
    const liveCount = latestResults?.length || 0;
    strip.innerHTML = `
      <span class="status-pill">DB ready / not connected</span>
      <span class="status-pill live">Star Wine live ${escapeHtml(String(liveCount))} lines</span>
      <span class="status-pill">Guide DB schema ready</span>
    `;
  }

  function setActiveView(view) {
    viewState.current = view;
    localStorage.setItem("whereiskelley.activeView", view);
    document.querySelectorAll(".view-tab").forEach((tab) => {
      tab.classList.toggle("active", tab.dataset.view === view);
    });
    document.querySelectorAll(".app-view").forEach((panel) => {
      panel.classList.toggle("active", panel.dataset.viewPanel === view);
    });
    const showSearch = view === "search";
    const showMap = view === "map";
    document.querySelector(".command-bar")?.classList.toggle("hidden", !(showSearch || showMap));
    document.querySelector(".workspace")?.classList.toggle("hidden", !(showSearch || showMap));
    document.querySelector(".map-panel")?.classList.toggle("hidden", !showMap);
    if (showMap) renderMap(latestResults || []);
  }

  function setupAppShellViews() {
    if (document.querySelector(".view-tabs")) return;
    loadWatchlist();
    const header = document.querySelector(".app-header");
    const nav = document.createElement("nav");
    nav.className = "view-tabs";
    nav.innerHTML = [
      ["dashboard", "Dashboard"],
      ["search", "Search"],
      ["watchlist", "Watchlist"],
      ["places", "Places"],
      ["review", "Review"],
      ["map", "Map"]
    ].map(([key, label]) => `<button class="view-tab" type="button" data-view="${key}">${label}</button>`).join("");
    header.insertAdjacentElement("afterend", nav);
    const commandBar = document.querySelector(".command-bar");
    commandBar.insertAdjacentHTML("beforebegin", `
      <section id="dashboardView" class="app-view" data-view-panel="dashboard"></section>
      <section id="watchlistView" class="app-view" data-view-panel="watchlist"></section>
      <section id="placesView" class="app-view" data-view-panel="places"></section>
      <section id="reviewView" class="app-view" data-view-panel="review"></section>
    `);
    nav.addEventListener("click", (event) => {
      const button = event.target.closest("[data-view]");
      if (!button) return;
      setActiveView(button.dataset.view);
    });
    document.body.addEventListener("submit", (event) => {
      if (event.target?.id !== "watchForm") return;
      event.preventDefault();
      const keyword = document.querySelector("#watchKeyword")?.value?.trim();
      const vintage = document.querySelector("#watchVintage")?.value?.trim() || "";
      if (!keyword) return;
      viewState.watchlist.push({ keyword, vintage });
      saveWatchlist();
      refreshAppViews();
    });
    document.body.addEventListener("click", (event) => {
      const remove = event.target.closest("[data-remove-watch]");
      if (!remove) return;
      viewState.watchlist.splice(Number(remove.dataset.removeWatch), 1);
      saveWatchlist();
      refreshAppViews();
    });
    const previousRenderResults = renderResults;
    renderResults = function patchedRenderResults(results, liveRefresh = null) {
      previousRenderResults(results, liveRefresh);
      refreshAppViews();
    };
    refreshAppViews();
    setActiveView(viewState.current);
  }

  setupAppShellViews();

  function cleanMapVenueName(venue = {}) {
    if (typeof displayVenueName === "function") return displayVenueName(venue);
    return String(venue.name || "Unknown")
      .replace(/^[\s\u00d7\u2715\u2716\u2717\u2718\u274c]+/, "")
      .trim();
  }

  function markerStyleForVenue(venue = {}) {
    const type = String(venue.type || "").toLowerCase();
    const isWineBar = type.includes("wine bar");
    const isRestaurant = type.includes("restaurant");
    if (isWineBar && isRestaurant) {
      return { color: "#7c3aed", label: "B/R" };
    }
    if (isWineBar) {
      return { color: "#0f766e", label: "B" };
    }
    if (isRestaurant) {
      return { color: "#a30f3d", label: "R" };
    }
    return { color: "#4b5563", label: "P" };
  }

  function winePinIcon(maps, venue = {}) {
    const { color, label } = markerStyleForVenue(venue);
    const svg = `<svg xmlns="http://www.w3.org/2000/svg" width="36" height="44" viewBox="0 0 36 44">
      <path fill="${color}" stroke="#ffffff" stroke-width="2.5" d="M18 2.5c-8.1 0-14.7 6.6-14.7 14.7 0 11 14.7 24.3 14.7 24.3s14.7-13.3 14.7-24.3C32.7 9.1 26.1 2.5 18 2.5Z"/>
      <circle cx="18" cy="17.2" r="5.2" fill="#ffffff"/>
      <text x="18" y="20.8" text-anchor="middle" font-family="Arial, sans-serif" font-size="${label.length > 1 ? 7 : 10}" font-weight="800" fill="${color}">${label}</text>
    </svg>`;
    return {
      url: `data:image/svg+xml;charset=UTF-8,${encodeURIComponent(svg)}`,
      scaledSize: new maps.Size(32, 39),
      anchor: new maps.Point(16, 39)
    };
  }

  function refreshMarkerIcons() {
    if (!googleMarkers?.length || typeof google === "undefined" || !google.maps) return;
    for (const marker of googleMarkers) {
      const group = latestMapVenues.find((item) => item.key === marker.starWineKey);
      if (group) {
        marker.setIcon(winePinIcon(google.maps, group.venue));
        marker.setTitle(cleanMapVenueName(group.venue) || "Wine place");
      }
    }
  }

  const previousDrawGoogleMap = drawGoogleMap;
  drawGoogleMap = async function patchedDrawGoogleMap(groups) {
    const result = await previousDrawGoogleMap(groups);
    refreshMarkerIcons();
    return result;
  };

  setActiveMapMarker = function patchedSetActiveMapMarker(key) {
    if (!googleMarkers?.length) return;
    refreshMarkerIcons();
    for (const marker of googleMarkers) {
      const active = marker.starWineKey === key;
      marker.setAnimation(active ? google.maps.Animation.BOUNCE : null);
      window.setTimeout(() => marker.setAnimation(null), 900);
      if (active && googleInfoWindow) {
        const group = latestMapVenues.find((item) => item.key === key);
        if (group) {
          const venueName = cleanMapVenueName(group.venue);
          const place = [group.venue.city, group.venue.country].filter(Boolean).join(", ");
          googleInfoWindow.setContent(`<strong>${escapeHtml(venueName)}</strong><br>${escapeHtml(place)}<br>${group.results.length} matching wines`);
          googleInfoWindow.open({ map: googleMap, anchor: marker });
        }
      }
    }
  };
})();
