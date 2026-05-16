const form = document.querySelector("#searchForm");
const queryInput = document.querySelector("#query");
const countryInput = document.querySelector("#country");
const cityInput = document.querySelector("#city");
const vintageInput = document.querySelector("#vintage");
const submitButton = form.querySelector("button[type='submit']");
const resultsEl = document.querySelector("#results");
const countEl = document.querySelector("#count");
const detailEl = document.querySelector("#detail");
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

const COUNTRY_CURRENCY = {
  Argentina: "ARS",
  Australia: "AUD",
  Austria: "EUR",
  Belgium: "EUR",
  Canada: "CAD",
  "Czech Republic": "CZK",
  Denmark: "DKK",
  France: "EUR",
  Germany: "EUR",
  "Greater China": "CNY",
  "Hong Kong": "HKD",
  Italy: "EUR",
  Netherlands: "EUR",
  Norway: "NOK",
  Singapore: "SGD",
  Spain: "EUR",
  Sweden: "SEK",
  Switzerland: "CHF",
  UK: "GBP",
  USA: "USD"
};

const KRW_RATES = {
  KRW: 1,
  EUR: 1705,
  USD: 1465,
  GBP: 1945,
  CHF: 1815,
  DKK: 229,
  SEK: 154,
  NOK: 145,
  CAD: 1065,
  AUD: 960,
  SGD: 1135,
  HKD: 188,
  AED: 399,
  CNY: 203,
  CZK: 69,
  ARS: 1.4,
  JPY: 9.8
};

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

function renderFilters(filters) {
  countryInput.innerHTML = `<option value="">All countries</option>${filters.countries
    .map((country) => `<option value="${escapeHtml(country)}">${escapeHtml(country)}</option>`)
    .join("")}`;
}

function hasValidPrice(result) {
  return Number.isFinite(Number(result.priceValue)) && Number(result.priceValue) > 0;
}

function currencyCode(result) {
  const raw = String(result.currency || "").trim().toUpperCase();
  return raw || COUNTRY_CURRENCY[result.venue?.country] || "";
}

function formatAmount(value, currency) {
  const digits = Number.isInteger(value) ? 0 : 2;
  if (currency) {
    try {
      return new Intl.NumberFormat("en-US", {
        style: "currency",
        currency,
        maximumFractionDigits: digits
      }).format(value);
    } catch (_error) {
      return `${new Intl.NumberFormat("en-US", { maximumFractionDigits: digits }).format(value)} ${currency}`;
    }
  }
  return new Intl.NumberFormat("en-US", { maximumFractionDigits: digits }).format(value);
}

function reviewBadge(label = "Review") {
  return `<span class="review-pill">${escapeHtml(label)}</span>`;
}

function originalPriceMarkup(result) {
  if (!hasValidPrice(result)) return reviewBadge("Review");
  return `<span class="price-main">${escapeHtml(formatAmount(Number(result.priceValue), currencyCode(result)))}</span>`;
}

function krwPriceMarkup(result) {
  if (!hasValidPrice(result)) return `<span class="review-pill muted">N/A</span>`;
  const currency = currencyCode(result);
  const rate = KRW_RATES[currency];
  if (!rate) return `<span class="review-pill muted">N/A</span>`;
  const krw = Math.round(Number(result.priceValue) * rate);
  return `<span class="krw-price">${escapeHtml(new Intl.NumberFormat("ko-KR", {
    style: "currency",
    currency: "KRW",
    maximumFractionDigits: 0
  }).format(krw))}</span>`;
}

function originalPriceText(result) {
  return hasValidPrice(result) ? formatAmount(Number(result.priceValue), currencyCode(result)) : "Review";
}

function krwPriceText(result) {
  if (!hasValidPrice(result)) return "N/A";
  const rate = KRW_RATES[currencyCode(result)];
  if (!rate) return "N/A";
  return new Intl.NumberFormat("ko-KR", {
    style: "currency",
    currency: "KRW",
    maximumFractionDigits: 0
  }).format(Math.round(Number(result.priceValue) * rate));
}

function pdfUrl(list = {}) {
  return list.localFileUrl || list.fileUrl || list.fileViewUrl || list.downloadUrl || "";
}

function pdfMarkup(list = {}) {
  const url = pdfUrl(list);
  if (!url) return `<span class="pdf-pill muted">No PDF</span>`;
  return `<a class="pdf-pill pdf-link" href="${escapeHtml(url)}" target="_blank" rel="noreferrer">PDF</a>`;
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
    resultsEl.innerHTML = `${liveLine}<div class="empty-list"><h3>No results</h3><p>Try another spelling or a broader query.</p></div>`;
    return;
  }
  const rows = results.map((result) => {
    const location = resultLocation(result);
    const key = venueKey(result);
    const list = result.wineList || {};
    return `<tr class="result-row${String(result.id) === String(activeId) ? " active" : ""}${key && key === activeVenueKey ? " venue-active" : ""}" data-id="${escapeHtml(result.id)}" data-venue-key="${escapeHtml(key)}">
      <td class="price-cell">${originalPriceMarkup(result)}</td>
      <td class="krw-cell">${krwPriceMarkup(result)}</td>
      <td class="wine-cell">${escapeHtml(result.text)}</td>
      <td>${escapeHtml(result.venue?.name || "")}</td>
      <td>${escapeHtml(location)}</td>
      <td>${escapeHtml(result.vintage || "")}</td>
      <td>${escapeHtml(list.updatedDate || list.updatedText || "")}</td>
      <td>${pdfMarkup(list)}</td>
    </tr>`;
  }).join("");
  resultsEl.innerHTML = `${liveLine}<div class="table-wrap">
    <table class="result-table">
      <thead>
        <tr>
          <th>Original price</th>
          <th>KRW</th>
          <th>Wine</th>
          <th>Restaurant / bar</th>
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
    ? `${venues.length} restaurants/bars on map / ${totalLines} matching wines`
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
        googleInfoWindow.setContent(`<strong>${escapeHtml(group.venue.name)}</strong><br>${escapeHtml([group.venue.city, group.venue.country].filter(Boolean).join(", "))}<br>${group.results.length} matching wines`);
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
  const originalPrice = originalPriceText(result);
  const krwPrice = krwPriceText(result);
  detailEl.innerHTML = `<div class="detail-grid">
    <div class="detail-title">
      <p class="eyebrow">${escapeHtml(fallback(venue.name))}</p>
      <h2>${escapeHtml(result.text)}</h2>
      <div class="detail-meta">
        <span>${escapeHtml(fallback(location))}</span>
        ${result.vintage ? `<span>${escapeHtml(result.vintage)}</span>` : ""}
        <span class="price">${escapeHtml(originalPrice)}</span>
        <span class="price">${escapeHtml(krwPrice)}</span>
      </div>
    </div>
    <div class="fact-grid">
      <div class="fact"><span>Country</span><b>${escapeHtml(fallback(venue.country))}</b></div>
      <div class="fact"><span>City</span><b>${escapeHtml(fallback(venue.city))}</b></div>
      <div class="fact wide"><span>Address</span><b>${escapeHtml(fallback(venue.address))}</b></div>
      <div class="fact"><span>List updated</span><b>${escapeHtml(fallback(list.updatedDate || list.updatedText))}</b></div>
      <div class="fact"><span>Original price</span><b>${escapeHtml(originalPrice)}</b></div>
      <div class="fact"><span>KRW estimate</span><b>${escapeHtml(krwPrice)}</b></div>
    </div>
    <div class="actions">
      ${pdfUrl(list) ? `<a href="${escapeHtml(pdfUrl(list))}" target="_blank" rel="noreferrer">PDF</a>` : ""}
      ${venue.googleMapsUrl ? `<a class="secondary" href="${escapeHtml(venue.googleMapsUrl)}" target="_blank" rel="noreferrer">Map</a>` : ""}
      ${venue.url ? `<a class="secondary" href="${escapeHtml(venue.url)}" target="_blank" rel="noreferrer">Star Wine List page</a>` : ""}
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
      return `<li>
        <span>${escapeHtml(result.text)}</span>
        <b>${escapeHtml(originalPriceText(result))}<small>${escapeHtml(krwPriceText(result))}</small></b>
      </li>`;
    })
    .join("");
  detailEl.innerHTML = `<div class="detail-grid">
    <div class="detail-title">
      <p class="eyebrow">${escapeHtml([venue.city, venue.country].filter(Boolean).join(", "))}</p>
      <h2>${escapeHtml(venue.name)}</h2>
      <div class="detail-meta">
        <span>${escapeHtml(venue.type || "Wine venue")}</span>
        <span>${escapeHtml(group.results.length)} matching wines</span>
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
      ${pdfUrl(firstList) ? `<a href="${escapeHtml(pdfUrl(firstList))}" target="_blank" rel="noreferrer">PDF</a>` : ""}
      ${venue.starWineMapUrl ? `<a class="secondary" href="${escapeHtml(venue.starWineMapUrl)}" target="_blank" rel="noreferrer">Star Map</a>` : ""}
      ${venue.url ? `<a class="secondary" href="${escapeHtml(venue.url)}" target="_blank" rel="noreferrer">Star Wine List page</a>` : ""}
    </div>
    <div class="venue-lines">
      <h3>Matching wines at this venue</h3>
      <ul>${lines}</ul>
    </div>
  </div>`;
}

async function runSearch() {
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
  if (queryInput.value.trim()) {
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
  } finally {
    submitButton.disabled = false;
  }
}

form.addEventListener("submit", (event) => {
  event.preventDefault();
  runSearch().catch((error) => {
    resultsEl.innerHTML = `<div class="empty-list"><h3>Search error</h3><p>${escapeHtml(error.message)}</p></div>`;
  });
});

mapKeyForm.addEventListener("submit", (event) => {
  event.preventDefault();
  const key = mapKeyInput.value.trim();
  if (!key) return;
  localStorage.setItem("googleMapsApiKey", key);
  googleMapsPromise = null;
  drawGoogleMap(latestMapVenues);
});

resultsEl.addEventListener("click", (event) => {
  if (event.target.closest("a")) return;
  const row = event.target.closest("[data-id]");
  if (!row) return;
  activeId = row.dataset.id;
  const selected = latestResults.find((result) => String(result.id) === String(activeId));
  activeVenueKey = selected ? venueKey(selected) : "";
  renderResultList();
  setActiveMapMarker(activeVenueKey);
  renderDetail(selected);
});

getJson("/api/filters")
  .then((filters) => {
    renderFilters(filters);
    queryInput.value = "William Kelley";
    return runSearch();
  })
  .catch((error) => {
    resultsEl.innerHTML = `<div class="empty-list"><h3>Load error</h3><p>${escapeHtml(error.message)}</p></div>`;
  });
