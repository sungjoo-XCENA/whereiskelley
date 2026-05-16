const form = document.querySelector("#searchForm");
const queryInput = document.querySelector("#query");
const countryInput = document.querySelector("#country");
const cityInput = document.querySelector("#city");
const vintageInput = document.querySelector("#vintage");
const liveInput = document.querySelector("#liveSearch");
const submitButton = form.querySelector("button[type='submit']");
const statsEl = document.querySelector("#stats");
const resultsEl = document.querySelector("#results");
const countEl = document.querySelector("#count");
const detailEl = document.querySelector("#detail");
const showSearchButton = document.querySelector("#showSearch");
const showUnparsedButton = document.querySelector("#showUnparsed");
const googleMapEl = document.querySelector("#googleMap");
const mapFallbackEl = document.querySelector("#mapFallback");
const mapKeyForm = document.querySelector("#mapKeyForm");
const mapKeyInput = document.querySelector("#mapKeyInput");
const mapSummaryEl = document.querySelector("#mapSummary");

let activeId = "";
let activeVenueKey = "";
let latestResults = [];
let latestLiveRefresh = null;
let latestMapVenues = [];
let googleMap = null;
let googleInfoWindow = null;
let googleMarkers = [];
let googleMapsPromise = null;
let mapRenderToken = 0;

function fallback(value) {
  return value || "Unknown";
}

function escapeHtml(value) {
  return String(value || "")
    .replace(/&/g, "&amp;")
    .replace(/</g, "&lt;")
    .replace(/>/g, "&gt;")
    .replace(/"/g, "&quot;");
}

async function getJson(path) {
  const response = await fetch(path);
  if (!response.ok) throw new Error(await response.text());
  return response.json();
}

function setMode(mode) {
  showSearchButton.classList.toggle("active", mode === "search");
  showUnparsedButton.classList.toggle("active", mode === "unparsed");
}

function renderStats(stats) {
  const lastSync = stats.lastRun?.finished_at
    ? new Date(stats.lastRun.finished_at).toLocaleDateString()
    : "Not synced";
  statsEl.innerHTML = [
    ["Countries", stats.countryCount],
    ["Venues", stats.venueCount],
    ["Lists", stats.wineListCount],
    ["Lines", stats.entryCount],
    ["Updated", lastSync]
  ].map(([label, value]) => `<span><b>${escapeHtml(value)}</b>${escapeHtml(label)}</span>`).join("");
}

function renderFilters(filters) {
  countryInput.innerHTML = `<option value="">All countries</option>${filters.countries
    .map((country) => `<option value="${escapeHtml(country)}">${escapeHtml(country)}</option>`)
    .join("")}`;
}

function resultPrice(result) {
  return result.prices?.length ? result.prices.join(", ") : "";
}

function hasValidPrice(result) {
  return Number.isFinite(Number(result.priceValue)) && Number(result.priceValue) > 0;
}

function resultLocation(result) {
  return [result.venue?.city, result.venue?.country].filter(Boolean).join(", ");
}

function numericPrice(result) {
  if (result.priceValue === null || result.priceValue === undefined || result.priceValue === "") {
    return Number.POSITIVE_INFINITY;
  }
  const price = Number(result.priceValue);
  return Number.isFinite(price) && price > 0 ? price : Number.POSITIVE_INFINITY;
}

function sortByCheapest(results) {
  return [...results].sort((a, b) => {
    const priceDiff = numericPrice(a) - numericPrice(b);
    if (priceDiff !== 0) return priceDiff;
    return String(a.venue?.name || "").localeCompare(String(b.venue?.name || ""));
  });
}

function liveRefreshLine(liveRefresh) {
  if (!liveRefresh) return "";
  const complete = liveRefresh.complete
    ? "Full pull complete"
    : `Loaded first ${liveRefresh.pages} pages`;
  const pageNote = liveRefresh.lastPage
    ? `page ${Math.min(liveRefresh.pages, liveRefresh.lastPage)} / ${liveRefresh.lastPage}`
    : `${liveRefresh.pages} pages`;
  return `<div class="sync-note">${escapeHtml(complete)}: ${escapeHtml(liveRefresh.entries)} lines, ${escapeHtml(liveRefresh.pdfs)} PDFs, ${escapeHtml(pageNote)}</div>`;
}

function renderResults(results, liveRefresh = null) {
  latestResults = sortByCheapest(results);
  latestLiveRefresh = liveRefresh;
  countEl.textContent = String(latestResults.length);
  if (!activeId && latestResults.length) {
    activeId = String(latestResults[0].id);
    activeVenueKey = venueKey(latestResults[0]);
  }
  renderMap(latestResults);
  renderResultList();
}

function renderResultList() {
  const liveLine = liveRefreshLine(latestLiveRefresh);
  const results = latestResults;
  if (!results.length) {
    resultsEl.innerHTML = `${liveLine}<div class="empty-list"><h3>No results</h3><p>Try another spelling or turn Live on.</p></div>`;
    return;
  }
  const rows = results.map((result) => {
    const prices = hasValidPrice(result) ? resultPrice(result) : "Price review";
    const location = resultLocation(result);
    const key = venueKey(result);
    const pdfState = result.wineList?.localFileUrl ? "PDF saved" : result.wineList?.fileUrl ? "PDF source" : "No PDF";
    const list = result.wineList || {};
    return `<tr class="result-row${String(result.id) === String(activeId) ? " active" : ""}${key && key === activeVenueKey ? " venue-active" : ""}" data-id="${escapeHtml(result.id)}" data-venue-key="${escapeHtml(key)}">
      <td class="price-cell">${escapeHtml(prices)}</td>
      <td class="wine-cell">${escapeHtml(result.text)}</td>
      <td>${escapeHtml(result.venue?.name || "")}</td>
      <td>${escapeHtml(location)}</td>
      <td>${escapeHtml(result.vintage || "")}</td>
      <td>${escapeHtml(list.updatedDate || list.updatedText || "")}</td>
      <td><span class="pdf-pill">${escapeHtml(pdfState)}</span></td>
    </tr>`;
  }).join("");
  resultsEl.innerHTML = `${liveLine}<div class="table-wrap">
    <table class="result-table">
      <thead>
        <tr>
          <th>Price</th>
          <th>Wine</th>
          <th>Venue</th>
          <th>Location</th>
          <th>Vintage</th>
          <th>Updated</th>
          <th>PDF</th>
        </tr>
      </thead>
      <tbody>${rows}</tbody>
    </table>
  </div>`;
}

function venueKey(result) {
  return String(result.venue?.id || result.venue?.url || result.venue?.name || "");
}

function groupedVenues(results) {
  const groups = new Map();
  for (const result of results) {
    const venue = result.venue || {};
    const key = venueKey(result);
    if (!key) continue;
    if (!groups.has(key)) {
      groups.set(key, { key, venue, results: [], lat: Number(venue.lat), lng: Number(venue.lng) });
    }
    groups.get(key).results.push(result);
  }
  return [...groups.values()].sort((a, b) => numericPrice(a.results[0]) - numericPrice(b.results[0]));
}

function renderMap(results) {
  const venues = groupedVenues(results).filter((group) => Number.isFinite(group.lat) && Number.isFinite(group.lng));
  latestMapVenues = venues;
  const totalLines = venues.reduce((sum, group) => sum + group.results.length, 0);
  mapSummaryEl.textContent = venues.length
    ? `${venues.length} mapped venues / ${totalLines} matching lines`
    : "No coordinates for these results yet";
  drawGoogleMap(venues);
}

function getGoogleMapsKey() {
  return localStorage.getItem("googleMapsApiKey") || window.STARWINE_CONFIG?.googleMapsApiKey || "";
}

function showMapFallback(message = "") {
  googleMapEl.classList.add("hidden");
  mapFallbackEl.classList.remove("hidden");
  const note = message || "Enter a Google Maps JavaScript API key to display venue pins.";
  mapFallbackEl.querySelector("p:last-child").textContent = note;
}

function loadGoogleMaps() {
  if (window.google?.maps) return Promise.resolve(window.google.maps);
  const key = getGoogleMapsKey();
  if (!key) return Promise.resolve(null);
  if (googleMapsPromise) return googleMapsPromise;
  googleMapsPromise = new Promise((resolve, reject) => {
    const callbackName = `initStarWineMap${Date.now()}`;
    window[callbackName] = () => {
      delete window[callbackName];
      resolve(window.google.maps);
    };
    const script = document.createElement("script");
    script.src = `https://maps.googleapis.com/maps/api/js?key=${encodeURIComponent(key)}&callback=${callbackName}&v=weekly`;
    script.async = true;
    script.defer = true;
    script.onerror = () => reject(new Error("Google Maps failed to load. Check the API key, billing, and allowed referrers."));
    document.head.appendChild(script);
  });
  return googleMapsPromise;
}

async function drawGoogleMap(venues) {
  const token = ++mapRenderToken;
  if (!venues.length) {
    clearGoogleMarkers();
    showMapFallback("No coordinates are available for this result set yet.");
    return;
  }
  try {
    const maps = await loadGoogleMaps();
    if (token !== mapRenderToken) return;
    if (!maps) {
      showMapFallback("Enter a Google Maps JavaScript API key to display venue pins.");
      return;
    }
    mapFallbackEl.classList.add("hidden");
    googleMapEl.classList.remove("hidden");
    if (!googleMap) {
      googleMap = new maps.Map(googleMapEl, {
        center: { lat: 25, lng: 8 },
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
      googleInfoWindow = new maps.InfoWindow();
    }
    clearGoogleMarkers();
    const bounds = new maps.LatLngBounds();
    for (const group of venues) {
      const position = { lat: group.lat, lng: group.lng };
      bounds.extend(position);
      const marker = new maps.Marker({
        map: googleMap,
        position,
        label: String(group.results.length),
        title: group.venue.name || "Wine venue",
      });
      marker.starWineKey = group.key;
      marker.addListener("click", () => selectVenueGroup(group));
      googleMarkers.push(marker);
    }
    googleMap.fitBounds(bounds, 56);
    if (venues.length === 1) {
      googleMap.setZoom(12);
    }
    setActiveMapMarker(activeVenueKey);
  } catch (error) {
    showMapFallback(error.message);
  }
}

function clearGoogleMarkers() {
  for (const marker of googleMarkers) {
    marker.setMap(null);
  }
  googleMarkers = [];
}

function selectVenueGroup(group) {
  const first = group.results[0];
  activeId = first ? String(first.id) : "";
  activeVenueKey = group.key;
  renderResultList();
  setActiveMapMarker(group.key);
  renderVenueDetail(group);
  scrollToVenue(group.key);
}

function setActiveMapMarker(key) {
  if (!googleMarkers.length) return;
  for (const marker of googleMarkers) {
    const active = marker.starWineKey === key;
    marker.setAnimation(active ? google.maps.Animation.BOUNCE : null);
    window.setTimeout(() => marker.setAnimation(null), 900);
    if (active && googleInfoWindow) {
      const group = latestMapVenues.find((item) => item.key === key);
      if (group) {
        googleInfoWindow.setContent(`<strong>${escapeHtml(group.venue.name)}</strong><br>${escapeHtml([group.venue.city, group.venue.country].filter(Boolean).join(", "))}<br>${group.results.length} matching lines`);
        googleInfoWindow.open({ map: googleMap, anchor: marker });
      }
    }
  }
}

function scrollToVenue(key) {
  const target = [...resultsEl.querySelectorAll("[data-venue-key]")]
    .find((item) => item.dataset.venueKey === key);
  if (target) {
    target.scrollIntoView({ behavior: "smooth", block: "center" });
  }
}

function renderDetail(result) {
  if (!result) {
    detailEl.innerHTML = `<div class="empty">
      <p class="panel-kicker">Selection</p>
      <h2>No result selected</h2>
      <p>Country, city, price, update date, venue link, and PDF links appear here.</p>
    </div>`;
    return;
  }
  const venue = result.venue || {};
  const list = result.wineList || {};
  const location = resultLocation(result);
  const prices = hasValidPrice(result) ? resultPrice(result) : "Needs price review";
  detailEl.innerHTML = `<div class="detail-grid">
    <div class="detail-title">
      <p class="eyebrow">${escapeHtml(fallback(venue.name))}</p>
      <h2>${escapeHtml(result.text)}</h2>
      <div class="detail-meta">
        <span>${escapeHtml(fallback(location))}</span>
        ${result.vintage ? `<span>${escapeHtml(result.vintage)}</span>` : ""}
        <span class="price">${escapeHtml(prices)}</span>
      </div>
    </div>
    <div class="fact-grid">
      <div class="fact"><span>Country</span><b>${escapeHtml(fallback(venue.country))}</b></div>
      <div class="fact"><span>City</span><b>${escapeHtml(fallback(venue.city))}</b></div>
      <div class="fact wide"><span>Address</span><b>${escapeHtml(fallback(venue.address))}</b></div>
      <div class="fact"><span>List updated</span><b>${escapeHtml(fallback(list.updatedDate || list.updatedText))}</b></div>
      <div class="fact"><span>Price</span><b>${escapeHtml(prices)}</b></div>
    </div>
    <div class="actions">
      ${list.localFileUrl ? `<a href="${escapeHtml(list.localFileUrl)}" target="_blank" rel="noreferrer">Local PDF</a>` : ""}
      ${list.fileUrl ? `<a class="secondary" href="${escapeHtml(list.fileUrl)}" target="_blank" rel="noreferrer">Source PDF</a>` : ""}
      ${list.fileViewUrl ? `<a class="secondary" href="${escapeHtml(list.fileViewUrl)}" target="_blank" rel="noreferrer">External PDF</a>` : ""}
      ${venue.googleMapsUrl ? `<a class="secondary" href="${escapeHtml(venue.googleMapsUrl)}" target="_blank" rel="noreferrer">Map</a>` : ""}
      ${venue.url ? `<a class="secondary" href="${escapeHtml(venue.url)}" target="_blank" rel="noreferrer">Venue</a>` : ""}
      ${list.downloadUrl ? `<a class="ghost" href="${escapeHtml(list.downloadUrl)}" target="_blank" rel="noreferrer">Download page</a>` : ""}
    </div>
  </div>`;
}

function renderVenueDetail(group) {
  const venue = group.venue || {};
  const first = group.results[0] || {};
  const firstList = first.wineList || {};
  const lines = group.results
    .slice(0, 80)
    .map((result) => {
      const prices = hasValidPrice(result) ? resultPrice(result) : "Price review";
      return `<li>
        <span>${escapeHtml(result.text)}</span>
        <b>${escapeHtml(prices)}</b>
      </li>`;
    })
    .join("");
  detailEl.innerHTML = `<div class="detail-grid">
    <div class="detail-title">
      <p class="eyebrow">${escapeHtml([venue.city, venue.country].filter(Boolean).join(", "))}</p>
      <h2>${escapeHtml(venue.name)}</h2>
      <div class="detail-meta">
        <span>${escapeHtml(venue.type || "Wine venue")}</span>
        <span>${escapeHtml(group.results.length)} matching lines</span>
        ${Number.isFinite(group.lat) && Number.isFinite(group.lng) ? `<span>${group.lat.toFixed(3)}, ${group.lng.toFixed(3)}</span>` : ""}
      </div>
    </div>
    <div class="fact-grid">
      <div class="fact"><span>Country</span><b>${escapeHtml(fallback(venue.country))}</b></div>
      <div class="fact"><span>City</span><b>${escapeHtml(fallback(venue.city))}</b></div>
      <div class="fact wide"><span>Address</span><b>${escapeHtml(fallback(venue.address))}</b></div>
      <div class="fact"><span>Latest list update</span><b>${escapeHtml(fallback(firstList.updatedDate || firstList.updatedText))}</b></div>
      <div class="fact"><span>PDF status</span><b>${escapeHtml(firstList.localFileUrl ? "Saved locally" : firstList.fileUrl ? "Source available" : "No source")}</b></div>
    </div>
    <div class="actions">
      ${firstList.localFileUrl ? `<a href="${escapeHtml(firstList.localFileUrl)}" target="_blank" rel="noreferrer">Local PDF</a>` : ""}
      ${firstList.fileUrl ? `<a class="secondary" href="${escapeHtml(firstList.fileUrl)}" target="_blank" rel="noreferrer">Source PDF</a>` : ""}
      ${firstList.fileViewUrl ? `<a class="secondary" href="${escapeHtml(firstList.fileViewUrl)}" target="_blank" rel="noreferrer">External PDF</a>` : ""}
      ${venue.starWineMapUrl ? `<a class="secondary" href="${escapeHtml(venue.starWineMapUrl)}" target="_blank" rel="noreferrer">Star Map</a>` : ""}
      ${venue.url ? `<a class="secondary" href="${escapeHtml(venue.url)}" target="_blank" rel="noreferrer">Venue</a>` : ""}
    </div>
    <div class="venue-lines">
      <h3>Matching wines at this venue</h3>
      <ul>${lines}</ul>
    </div>
  </div>`;
}

async function runSearch() {
  setMode("search");
  activeId = "";
  activeVenueKey = "";
  latestResults = [];
  latestLiveRefresh = null;
  resultsEl.innerHTML = `<div class="loading">Collecting every matching page...</div>`;
  detailEl.innerHTML = `<div class="empty"><p class="panel-kicker">Search</p><h2>Searching...</h2><p>Results will appear after the full pull finishes.</p></div>`;
  mapSummaryEl.textContent = "Waiting for search to finish";
  clearGoogleMarkers();
  submitButton.disabled = true;
  const params = new URLSearchParams();
  if (queryInput.value.trim()) params.set("q", queryInput.value.trim());
  if (countryInput.value) params.set("country", countryInput.value);
  if (cityInput.value.trim()) params.set("city", cityInput.value.trim());
  if (vintageInput.value.trim()) params.set("vintage", vintageInput.value.trim());
  if (liveInput.checked && queryInput.value.trim()) {
    params.set("live", "1");
    params.set("livePages", "all");
    params.set("livePageCap", "10");
    params.set("liveMaxPdfs", "10");
  }
  params.set("limit", "2000");
  try {
    const payload = await getJson(`/api/search?${params.toString()}`);
    renderResults(payload.results, payload.liveRefresh);
    const selected = latestResults.find((result) => String(result.id) === String(activeId)) || latestResults[0];
    if (selected) {
      activeId = String(selected.id);
      activeVenueKey = venueKey(selected);
      renderResultList();
      setActiveMapMarker(activeVenueKey);
    }
    renderDetail(selected);
    refreshStats();
  } finally {
    submitButton.disabled = false;
  }
}

async function refreshStats() {
  const stats = await getJson("/api/stats");
  renderStats(stats);
}

async function showUnparsed() {
  setMode("unparsed");
  const payload = await getJson("/api/unparsed?limit=300");
  countEl.textContent = String(payload.count);
  latestResults = [];
  resultsEl.innerHTML = payload.items.length
    ? payload.items.map((item, index) => `<button class="result-item" data-unparsed="${index}">
      <span class="result-topline">
        <span>${escapeHtml(item.venueName)}</span>
        <span>${escapeHtml(item.kind === "price" ? "Price review" : item.localFileUrl ? "PDF saved" : "Needs PDF")}</span>
      </span>
      <span class="wine-line">${escapeHtml(item.rawText || item.label || item.venueName)}</span>
      <span class="result-meta">
        <span>${escapeHtml([item.city, item.country].filter(Boolean).join(", "))}</span>
        <span>${escapeHtml(item.updatedDate || "No date")}</span>
        ${item.priceText ? `<span class="price">${escapeHtml(item.priceText)}</span>` : ""}
      </span>
    </button>`).join("")
    : `<div class="empty-list"><h3>No items need review</h3></div>`;
  renderReviewDetail();
  resultsEl.querySelectorAll("[data-unparsed]").forEach((button) => {
    button.addEventListener("click", () => {
      const item = payload.items[Number(button.dataset.unparsed)];
      renderReviewDetail(item);
    });
  });
}

function renderReviewDetail(item = null) {
  if (!item) {
    detailEl.innerHTML = `<div class="empty">
      <p class="panel-kicker">Review</p>
      <h2>PDF review queue</h2>
      <p>Items without parsed lines, local PDFs, or reliable prices are collected here.</p>
    </div>`;
    return;
  }
  detailEl.innerHTML = `<div class="detail-grid">
    <div class="detail-title">
      <p class="eyebrow">${escapeHtml([item.city, item.country].filter(Boolean).join(", "))}</p>
      <h2>${escapeHtml(item.kind === "price" ? item.rawText : item.venueName)}</h2>
      <div class="detail-meta"><span>${escapeHtml(item.kind === "price" ? item.venueName : item.label || "")}</span></div>
    </div>
    <div class="fact-grid">
      <div class="fact"><span>List updated</span><b>${escapeHtml(item.updatedDate || "Unknown")}</b></div>
      <div class="fact"><span>Status</span><b>${escapeHtml(item.lastError || "No parsed entries")}</b></div>
      ${item.kind === "price" ? `<div class="fact"><span>Parsed price</span><b>${escapeHtml(item.priceText || "Missing")}</b></div>` : ""}
    </div>
    <div class="actions">
      ${item.localFileUrl ? `<a href="${escapeHtml(item.localFileUrl)}" target="_blank" rel="noreferrer">Local PDF</a>` : ""}
      ${item.fileUrl ? `<a class="secondary" href="${escapeHtml(item.fileUrl)}" target="_blank" rel="noreferrer">Source PDF</a>` : ""}
      ${item.fileViewUrl ? `<a class="secondary" href="${escapeHtml(item.fileViewUrl)}" target="_blank" rel="noreferrer">External PDF</a>` : ""}
      ${item.venueUrl ? `<a class="secondary" href="${escapeHtml(item.venueUrl)}" target="_blank" rel="noreferrer">Venue</a>` : ""}
      ${item.downloadUrl ? `<a class="ghost" href="${escapeHtml(item.downloadUrl)}" target="_blank" rel="noreferrer">Download page</a>` : ""}
    </div>
  </div>`;
}

form.addEventListener("submit", (event) => {
  event.preventDefault();
  runSearch().catch((error) => {
    resultsEl.innerHTML = `<div class="empty-list"><h3>Search error</h3><p>${escapeHtml(error.message)}</p></div>`;
  });
});

showSearchButton.addEventListener("click", () => runSearch());
showUnparsedButton.addEventListener("click", () => showUnparsed());

mapKeyForm.addEventListener("submit", (event) => {
  event.preventDefault();
  const key = mapKeyInput.value.trim();
  if (!key) return;
  localStorage.setItem("googleMapsApiKey", key);
  googleMapsPromise = null;
  drawGoogleMap(latestMapVenues);
});

resultsEl.addEventListener("click", (event) => {
  const row = event.target.closest("[data-id]");
  if (!row) return;
  activeId = row.dataset.id;
  const selected = latestResults.find((result) => String(result.id) === String(activeId));
  activeVenueKey = selected ? venueKey(selected) : "";
  renderResultList();
  setActiveMapMarker(activeVenueKey);
  renderDetail(selected);
});

Promise.all([getJson("/api/stats"), getJson("/api/filters")])
  .then(([stats, filters]) => {
    renderStats(stats);
    renderFilters(filters);
    queryInput.value = "William Kelley";
    return runSearch();
  })
  .catch((error) => {
    statsEl.innerHTML = `<span><b>Error</b>${escapeHtml(error.message)}</span>`;
  });
