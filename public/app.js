const form = document.querySelector("#searchForm");
const queryInput = document.querySelector("#query");
const countryInput = document.querySelector("#country");
const cityInput = document.querySelector("#city");
const vintageInput = document.querySelector("#vintage");
const submitButton = form.querySelector("button[type='submit']");
const resultsEl = document.querySelector("#results");
const countEl = document.querySelector("#count");
const googleMapEl = document.querySelector("#googleMap");
const mapFallbackEl = document.querySelector("#mapFallback");
const mapSummaryEl = document.querySelector("#mapSummary");

let activeId = "";
let activeVenueKey = "";
let sortState = { key: "place", direction: "asc" };
let latestResults = [];
let latestLiveRefresh = null;
let latestMapVenues = [];
const pdfLineCache = new Map();
const pdfLineLoading = new Set();
let googleMap = null;
let googleInfoWindow = null;
let googleMarkers = [];
let googleMapsPromise = null;
let mapRenderToken = 0;
let snapshotManifestCache = null;
let snapshotLineCache = null;
let activeSearchController = null;
let activeSearchRequestId = 0;

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
  China: "CNY",
  "Greater China": "CNY",
  "Hong Kong": "HKD",
  Macau: "MOP",
  Taiwan: "TWD",
  Italy: "EUR",
  Japan: "JPY",
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

async function getJson(path, options = {}) {
  const response = await fetch(path, options);
  const contentType = response.headers.get("content-type") || "";
  if (!response.ok) {
    let message = `Request failed (HTTP ${response.status}).`;
    if (contentType.includes("application/json")) {
      const payload = await response.json().catch(() => null);
      message = payload?.error || message;
    } else if (response.status === 502) {
      message = "The search server restarted before the scan finished. Please search again.";
    } else if (response.status === 504) {
      message = "The full search took too long to finish. Please search again.";
    } else if (response.status === 503) {
      message = "The search server is temporarily unavailable. Please try again shortly.";
    }
    throw new Error(message);
  }
  if (!contentType.includes("application/json") && !contentType.includes("javascript")) {
    throw new Error("The search server returned an invalid response. Please try again.");
  }
  return response.json();
}

function setSearchButtonState(searching) {
  submitButton.textContent = searching ? "Stop" : "Search";
  submitButton.classList.toggle("stop-search", searching);
  submitButton.setAttribute("aria-label", searching ? "Stop current search" : "Search");
  submitButton.setAttribute("aria-pressed", searching ? "true" : "false");
  form.setAttribute("aria-busy", searching ? "true" : "false");
}

function stopActiveSearch() {
  if (!activeSearchController) return false;
  const controller = activeSearchController;
  activeSearchController = null;
  activeSearchRequestId += 1;
  controller.abort();
  setSearchButtonState(false);
  countEl.textContent = "0";
  resultsEl.innerHTML = `<div class="empty-list"><h3>Search stopped</h3><p>Change the filters or press Search to start again.</p></div>`;
  mapSummaryEl.textContent = "Search stopped";
  showMapFallback("Ready for another search.", "Search stopped", false);
  return true;
}

async function getOptionalJson(path) {
  try {
    return await getJson(path);
  } catch (_error) {
    return null;
  }
}

async function getOptionalSnapshotChunk(chunk) {
  try {
    const url = `/data/${chunk.file}`;
    if (chunk.encoding !== "gzip-base64-json") return await getJson(url);
    const response = await fetch(url);
    if (!response.ok) throw new Error(await response.text());
    const encoded = (await response.text()).trim();
    const binary = atob(encoded);
    const bytes = Uint8Array.from(binary, (char) => char.charCodeAt(0));
    if (!("DecompressionStream" in window)) {
      throw new Error("This browser cannot read compressed DB snapshots.");
    }
    const stream = new Blob([bytes]).stream().pipeThrough(new DecompressionStream("gzip"));
    return JSON.parse(await new Response(stream).text());
  } catch (_error) {
    return null;
  }
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
  return list.downloadUrl || list.fileViewUrl || list.fileUrl || list.externalUrl || list.localFileUrl || "";
}

function pdfMarkup(list = {}) {
  const url = pdfUrl(list);
  if (!url) return `<span class="pdf-pill muted">No PDF</span>`;
  return `<a class="pdf-pill pdf-link" href="${escapeHtml(url)}" target="_blank" rel="noreferrer">PDF</a>`;
}

function pdfFallbackUrls(list = {}) {
  return [list.fileViewUrl, list.fileUrl, list.externalUrl, list.localFileUrl]
    .filter((url) => url && url !== pdfUrl(list));
}

function resultDedupKey(result = {}) {
  return [
    String(result.text || "").trim().toLowerCase(),
    result.vintage || "",
    result.currency || "",
    result.priceValue ?? "",
    result.wineList?.id || ""
  ].join("|");
}

function uniqueResults(results = []) {
  const seen = new Set();
  const unique = [];
  for (const result of results) {
    const key = resultDedupKey(result);
    if (seen.has(key)) continue;
    seen.add(key);
    unique.push(result);
  }
  return unique;
}

function resultSource(result = {}) {
  return result.source || result.sourceLabel || "Star Wine";
}

function resultSourceKind(result = {}) {
  const source = String(resultSource(result)).toLowerCase();
  if (source.includes("wine shop")) return "shop";
  if (source.includes("database") || source.includes("collected") || source === "db") return "db";
  return "live";
}

function resultSourceLabel(result = {}) {
  const kind = resultSourceKind(result);
  return kind === "shop" ? "Wine Shop DB" : kind === "db" ? "Restaurant DB" : "Star Wine";
}

const SOURCE_MARKS = {
  live: { short: "S", label: "Star Wine", className: "live" },
  db: { short: "R", label: "Restaurant DB", className: "db" },
  shop: { short: "W", label: "Wine Shop DB", className: "shop" }
};

function sourceMarkMarkup(kind, showLabel = false) {
  const meta = SOURCE_MARKS[kind];
  if (!meta) return "";
  return `<span class="source-key"><span class="source-mark ${meta.className}" title="${escapeHtml(meta.label)}" aria-label="${escapeHtml(meta.label)}">${meta.short}</span>${showLabel ? `<span class="source-key-label">${escapeHtml(meta.label)}</span>` : ""}</span>`;
}

function groupSourceMarks(group) {
  const kinds = new Set((group.results || []).map((result) => resultSourceKind(result)));
  return `<span class="source-marks" aria-label="Result sources">${["live", "db", "shop"].filter((kind) => kinds.has(kind)).map((kind) => sourceMarkMarkup(kind)).join("")}</span>`;
}

function sourceLegendMarkup() {
  return `<div class="source-legend" aria-label="Source legend"><span class="source-legend-title">Sources</span>${["live", "db", "shop"].map((kind) => sourceMarkMarkup(kind, true)).join("")}</div>`;
}

function stripVenueReviewPrefix(value) {
  return String(value || "").replace(/^[\s\u00d7\u2715\u2716\u2717\u2718\u274c]+/u, "").trim();
}

function hasVenueReviewPrefix(value) {
  return /^[\s\u00d7\u2715\u2716\u2717\u2718\u274c]+/u.test(String(value || ""));
}

function venueReviewBadge(group) {
  if (!group.nameNeedsReview && !groupPdfReviewReason(group)) return "";
  return `<span class="review-badge" title="Source list needs review">Review</span>`;
}

function sourceBadge(source) {
  const value = String(source || "Star Wine");
  const normalized = value.toLowerCase();
  if (normalized.includes("wine shop")) {
    return `<span class="source-badge shop">Wine Shop DB</span>`;
  }
  const hasDatabase = normalized.includes("database") || normalized.includes("collected") || normalized.includes("db");
  const hasStarWine = normalized.includes("star wine") || normalized.includes("live");
  const key = hasDatabase && hasStarWine ? "both" : hasDatabase ? "db" : "live";
  const label = key === "both" ? "Star Wine + Database" : key === "db" ? "Database" : "Star Wine";
  return `<span class="source-badge ${key}">${escapeHtml(label)}</span>`;
}

function mergeResultSources(results = []) {
  const byKey = new Map();
  for (const raw of results) {
    const result = { ...raw };
    const key = `${resultSourceKind(result)}|${resultDedupKey(result)}`;
    if (!byKey.has(key)) {
      byKey.set(key, result);
    }
  }
  return [...byKey.values()];
}

function pdfLinksMarkup(lists = []) {
  const validLists = lists.filter((list) => pdfUrl(list));
  return validLists
    .slice(0, 3)
    .map((list, index) => {
      const label = validLists.length === 1 ? "PDF" : `PDF ${index + 1}`;
      return `<a href="${escapeHtml(pdfUrl(list))}" target="_blank" rel="noreferrer">${escapeHtml(label)}</a>`;
    })
    .join("");
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

const UPDATED_MONTHS = {
  jan: 0,
  january: 0,
  feb: 1,
  february: 1,
  mar: 2,
  march: 2,
  apr: 3,
  april: 3,
  may: 4,
  jun: 5,
  june: 5,
  jul: 6,
  july: 6,
  aug: 7,
  august: 7,
  sep: 8,
  sept: 8,
  september: 8,
  oct: 9,
  october: 9,
  nov: 10,
  november: 10,
  dec: 11,
  december: 11
};

function parseUpdatedTime(value = "") {
  const text = String(value || "").trim().replace(/\s+/g, " ");
  if (!text) return 0;

  const isoMatch = text.match(/^(\d{4})-(\d{1,2})-(\d{1,2})/);
  if (isoMatch) {
    return Date.UTC(Number(isoMatch[1]), Number(isoMatch[2]) - 1, Number(isoMatch[3]));
  }

  const englishMatch = text.match(/^(\d{1,2})\s+([A-Za-z]+)\s+(\d{4})$/);
  if (englishMatch) {
    const month = UPDATED_MONTHS[englishMatch[2].toLowerCase()];
    if (month !== undefined) {
      return Date.UTC(Number(englishMatch[3]), month, Number(englishMatch[1]));
    }
  }

  const parsed = Date.parse(text);
  return Number.isNaN(parsed) ? 0 : parsed;
}

function groupUpdatedEntries(group) {
  return group.results
    .map((result) => result.wineList?.updatedDate || result.wineList?.updatedText || "")
    .filter(Boolean);
}

function groupUpdatedValue(group) {
  return groupUpdatedEntries(group)
    .sort((a, b) => {
      const timeDiff = parseUpdatedTime(a) - parseUpdatedTime(b);
      return timeDiff || String(a).localeCompare(String(b));
    })
    .at(-1) || "";
}

function groupUpdatedSortValue(group) {
  return parseUpdatedTime(groupUpdatedValue(group));
}

function groupLowestPriceResult(group) {
  const candidates = groupOfferLines(group);
  return [...candidates].sort((a, b) => groupResultKrwValue(a) - groupResultKrwValue(b))[0] || {};
}

function groupOfferLines(group) {
  const databaseLines = uniqueResults(
    group.results.filter((result) => resultSourceKind(result) !== "live")
  );
  const starWineGroup = {
    ...group,
    results: group.results.filter((result) => resultSourceKind(result) === "live")
  };
  return [...reconciledGroupLines(starWineGroup), ...databaseLines];
}

function sourcePriceOffers(group) {
  const offerLines = groupOfferLines(group);
  return [
    { key: "live", label: "Star Wine" },
    { key: "db", label: "Restaurant DB" },
    { key: "shop", label: "Wine Shop DB" }
  ].flatMap((source) => {
    const sourceLines = offerLines.filter((result) => resultSourceKind(result) === source.key);
    if (!sourceLines.length) return [];
    const candidates = sourceLines
      .filter(hasValidPrice)
      .sort((a, b) => groupResultKrwValue(a) - groupResultKrwValue(b));
    if (!candidates.length) return [];
    return [{ ...source, result: candidates[0] }];
  });
}

function groupResultKrwValue(result) {
  if (!hasValidPrice(result)) return Number.POSITIVE_INFINITY;
  const rate = KRW_RATES[currencyCode(result)];
  return rate ? Number(result.priceValue) * rate : Number.POSITIVE_INFINITY;
}

function priceOffersMarkup(group) {
  const offers = sourcePriceOffers(group);
  if (!offers.length) return `<span class="review-pill muted">N/A</span>`;
  return `<div class="price-offers">${offers.map((offer) => `
    <span class="price-offer ${escapeHtml(offer.key)}" title="${escapeHtml(offer.label)}">
      ${krwPriceMarkup(offer.result)}
    </span>`).join("")}</div>`;
}

function hasWineLineSignal(result = {}) {
  const price = Number(result.priceValue);
  return (Number.isFinite(price) && price > 0)
    || (Array.isArray(result.prices) && result.prices.some((priceText) => String(priceText || "").trim()))
    || /\b(?:NV|MV|N\/V|19\d{2}|20\d{2})\b/i.test(String(result.vintage || result.text || ""));
}

function fallbackWineLines(results = []) {
  return uniqueResults(results).filter(hasWineLineSignal);
}

function normalizedWineText(value = "") {
  return String(value || "")
    .normalize("NFKD")
    .replace(/[\u0300-\u036f]/g, "")
    .toLowerCase()
    .replace(/[^a-z0-9]+/g, " ")
    .trim();
}

async function loadSnapshotManifest() {
  if (snapshotManifestCache !== null) return snapshotManifestCache;
  snapshotManifestCache = await getOptionalJson(`/data/search-manifest.json?ts=${Date.now()}`);
  return snapshotManifestCache;
}

async function loadSnapshotLines() {
  if (snapshotLineCache !== null) return snapshotLineCache;
  const manifest = await loadSnapshotManifest();
  const chunks = Array.isArray(manifest?.chunks) ? manifest.chunks : [];
  if (!chunks.length) {
    snapshotLineCache = [];
    return snapshotLineCache;
  }
  const loaded = await Promise.all(chunks.map((chunk) => getOptionalSnapshotChunk(chunk)));
  snapshotLineCache = loaded.flatMap((chunk) => Array.isArray(chunk) ? chunk : []);
  return snapshotLineCache;
}

function snapshotSearchText(result = {}) {
  return normalizedWineText([
    result.text,
    result.producer,
    result.wineName,
    result.region,
    result.grape,
    result.venue?.name,
    result.venue?.city,
    result.venue?.country
  ].filter(Boolean).join(" "));
}

function snapshotMatches(result, query, country, city, vintage) {
  const text = snapshotSearchText(result);
  const tokens = normalizedWineText(query).split(/\s+/).filter(Boolean);
  if (tokens.length && !tokens.every((token) => text.includes(token))) return false;
  if (country && normalizedWineText(result.venue?.country) !== normalizedWineText(country)) return false;
  if (city && !normalizedWineText(result.venue?.city).includes(normalizedWineText(city))) return false;
  if (vintage && String(result.vintage || "") !== vintage && !String(result.text || "").includes(vintage)) return false;
  return true;
}

async function searchSnapshot(params) {
  const query = params.get("q") || "";
  if (!query.trim()) return { results: [], liveRefresh: null };
  const country = params.get("country") || "";
  const city = params.get("city") || "";
  const vintage = params.get("vintage") || "";
  const limit = Number(params.get("limit") || 5000);
  const lines = await loadSnapshotLines();
  const results = lines
    .filter((result) => snapshotMatches(result, query, country, city, vintage))
    .slice(0, limit)
    .map((result) => ({ ...result, source: result.source || "DB" }));
  return {
    results,
    liveRefresh: {
      sourceSummary: "DB snapshot + live API",
      snapshotLines: lines.length,
      snapshotMatches: results.length
    }
  };
}

function lineTokens(value = "") {
  return normalizedWineText(value)
    .split(/\s+/)
    .filter((token) => token.length >= 3 && !/^(?:the|and|aoc|aop|auc|doc|docg|cru|grand|wine|list)$/.test(token));
}

function lineMatchScore(indexLine = {}, pdfLine = {}) {
  const indexTokens = lineTokens(indexLine.text);
  const pdfText = ` ${normalizedWineText(pdfLine.text)} `;
  if (!indexTokens.length || !pdfText.trim()) return 0;
  const hits = indexTokens.filter((token) => pdfText.includes(` ${token} `)).length;
  let score = hits / indexTokens.length;
  if (indexLine.vintage && pdfLine.vintage && String(indexLine.vintage) === String(pdfLine.vintage)) score += 0.25;
  if (hasValidPrice(indexLine) && hasValidPrice(pdfLine) && Number(indexLine.priceValue) === Number(pdfLine.priceValue)) score += 0.2;
  return score;
}

function bestPdfMatch(indexLine, pdfLines, used) {
  let best = null;
  let bestScore = 0;
  pdfLines.forEach((pdfLine, index) => {
    if (used.has(index)) return;
    const score = lineMatchScore(indexLine, pdfLine);
    if (score > bestScore) {
      best = { index, line: pdfLine };
      bestScore = score;
    }
  });
  return bestScore >= 0.55 ? best : null;
}

function mergeIndexedWithPdf(indexLine, pdfLine) {
  if (!pdfLine) return { ...indexLine, source: "Search index" };
  return {
    ...indexLine,
    vintage: indexLine.vintage || pdfLine.vintage || "",
    priceValue: indexLine.priceValue,
    currency: indexLine.currency || "",
    prices: Array.isArray(indexLine.prices) ? indexLine.prices : [],
    pageNumber: pdfLine.pageNumber || indexLine.pageNumber || "",
    pdfVerified: true,
    source: "PDF verified"
  };
}

function reconciledGroupLines(group) {
  const indexedLines = fallbackWineLines(group.results);
  const pdfLines = uniqueResults(groupPdfLines(group));
  if (!indexedLines.length) {
    return pdfLines.map((line) => ({ ...line, source: "PDF only", pdfVerified: true }));
  }
  const used = new Set();
  return indexedLines.map((indexLine) => {
    const match = bestPdfMatch(indexLine, pdfLines, used);
    if (match) used.add(match.index);
    return mergeIndexedWithPdf(indexLine, match?.line);
  });
}

function groupKrwValue(group) {
  const result = groupLowestPriceResult(group);
  return groupResultKrwValue(result);
}

function groupPdfList(group) {
  return groupPdfLists(group)[0] || {};
}

function groupPdfLists(group) {
  const seen = new Set();
  const lists = [];
  for (const result of group.results) {
    const list = result.wineList || {};
    if (result.availabilityOnly || list.availabilityOnly) continue;
    const url = pdfUrl(list);
    if (!url) continue;
    const key = String(list.id || url);
    if (seen.has(key)) continue;
    seen.add(key);
    lists.push(list);
  }
  return lists;
}

function pdfLineCacheKeyForList(list = {}, group = {}) {
  return String(list.id || pdfUrl(list) || group.key || "");
}

function groupPdfPayloads(group) {
  return groupPdfLists(group)
    .map((list) => pdfLineCache.get(pdfLineCacheKeyForList(list, group)))
    .filter(Boolean);
}

function groupPdfLines(group) {
  return groupPdfPayloads(group).flatMap((payload) => payload.lines || []);
}

function groupPdfPending(group) {
  return groupPdfLists(group).some((list) => {
    const key = pdfLineCacheKeyForList(list, group);
    return key && !pdfLineCache.has(key);
  });
}

function groupPdfReviewReason(group) {
  const reasons = groupPdfPayloads(group)
    .filter((payload) => payload.status === "review" && payload.reason)
    .map((payload) => friendlyPdfReviewReason(payload.reason));
  return [...new Set(reasons)].join(" ");
}

function friendlyPdfReviewReason(reason = "") {
  const text = String(reason || "");
  if (/403|forbidden|not a pdf file|pdf response was not a pdf/i.test(text)) {
    return "PDF check unavailable. Showing indexed results until the PDF can be reviewed.";
  }
  if (/no matching text/i.test(text)) {
    return "No matching text was verified in the downloaded PDF.";
  }
  if (/ocr|extractable text/i.test(text)) {
    return "PDF text could not be extracted automatically. Manual review is needed.";
  }
  return "PDF check needs manual review.";
}

async function loadPdfLines(group) {
  const pendingLists = groupPdfLists(group).filter((list) => {
    const key = pdfLineCacheKeyForList(list, group);
    return key && !pdfLineCache.has(key) && !pdfLineLoading.has(key);
  });
  if (!pendingLists.length) return;
  pendingLists.forEach((list) => pdfLineLoading.add(pdfLineCacheKeyForList(list, group)));
  await Promise.all(pendingLists.map(async (list) => {
    const key = pdfLineCacheKeyForList(list, group);
    try {
      const params = new URLSearchParams({
        wineListId: String(list.id || key),
        q: queryInput.value.trim(),
        fileUrl: pdfUrl(list),
        fallbackUrls: pdfFallbackUrls(list).join("|"),
        country: group.venue?.country || ""
      });
      const payload = await getJson(`/api/pdf-lines?${params.toString()}`);
      pdfLineCache.set(key, payload);
    } catch (error) {
      pdfLineCache.set(key, { status: "review", reason: error.message, lines: [] });
    } finally {
      pdfLineLoading.delete(key);
    }
  }));
  if (activeVenueKey === group.key) renderResultList();
}

function sortGroups(groups) {
  const direction = sortState.direction === "asc" ? 1 : -1;
  return [...groups].sort((a, b) => {
    let left = "";
    let right = "";
    if (sortState.key === "place") {
      left = a.venue?.name || "";
      right = b.venue?.name || "";
    } else if (sortState.key === "city") {
      left = a.venue?.city || "";
      right = b.venue?.city || "";
    } else if (sortState.key === "country") {
      left = a.venue?.country || "";
      right = b.venue?.country || "";
    } else if (sortState.key === "updated") {
      left = groupUpdatedSortValue(a);
      right = groupUpdatedSortValue(b);
    } else if (sortState.key === "matches") {
      left = a.results.length;
      right = b.results.length;
    } else if (sortState.key === "krw") {
      left = groupKrwValue(a);
      right = groupKrwValue(b);
    }
    if (typeof left === "number" || typeof right === "number") {
      return ((left || 0) - (right || 0)) * direction;
    }
    return String(left).localeCompare(String(right)) * direction;
  });
}

function sortHeader(label, key) {
  const active = sortState.key === key;
  const directionLabel = sortState.direction === "asc" ? "ascending" : "descending";
  const badge = active
    ? `<span class="sort-badge" aria-hidden="true">${sortState.direction === "asc" ? "&#8593;" : "&#8595;"}</span>`
    : "";
  return `<button class="sort-button${active ? " active" : ""}" type="button" data-sort="${escapeHtml(key)}" aria-label="Sort ${escapeHtml(label)}${active ? `, currently ${directionLabel}` : ""}"><span>${escapeHtml(label)}</span>${badge}</button>`;
}

function liveRefreshLine(liveRefresh) {
  if (!liveRefresh) return "";
  if (liveRefresh.sourceSummary && "databaseMatches" in liveRefresh) {
    return `<div class="sync-note integrated-search-note"><b>${escapeHtml(liveRefresh.sourceSummary)}</b><span>${escapeHtml(String(liveRefresh.starWineMatches || 0))} Star Wine matches</span><span>${escapeHtml(String(liveRefresh.databaseMatches || 0))} Restaurant DB matches</span><span>${escapeHtml(String(liveRefresh.shopMatches || 0))} Wine Shop DB matches</span></div>`;
  }
  if (liveRefresh.sourceSummary) {
    return `<div class="sync-note">${escapeHtml(liveRefresh.sourceSummary)}: ${escapeHtml(String(liveRefresh.snapshotMatches || 0))} DB matches from ${escapeHtml(String(liveRefresh.snapshotLines || 0))} saved lines, ${escapeHtml(String(liveRefresh.liveMatches || 0))} live matches</div>`;
  }
  const complete = liveRefresh.complete
    ? "Full pull complete"
    : `Loaded first ${liveRefresh.pages} pages`;
  const pageNote = liveRefresh.lastPage
    ? `page ${Math.min(liveRefresh.pages, liveRefresh.lastPage)} / ${liveRefresh.lastPage}`
    : `${liveRefresh.pages} pages`;
  return `<div class="sync-note">${escapeHtml(complete)}: ${escapeHtml(liveRefresh.entries)} lines, ${escapeHtml(liveRefresh.pdfs)} PDFs, ${escapeHtml(pageNote)}</div>`;
}

function renderResults(results, liveRefresh = null) {
  ensureDownloadButton();
  latestResults = sortByCheapest(mergeResultSources(results));
  latestLiveRefresh = liveRefresh;
  countEl.textContent = String(groupedVenues(latestResults).length);
  renderMap(latestResults);
  renderResultList();
}

function ensureDownloadButton() {
  if (document.querySelector("#downloadResults")) return;
  const heading = document.querySelector(".result-list .panel-heading");
  if (!heading || !countEl) return;
  const tools = document.createElement("div");
  tools.className = "panel-tools";
  const button = document.createElement("button");
  button.id = "downloadResults";
  button.className = "download-results";
  button.type = "button";
  button.textContent = "Download results";
  button.addEventListener("click", downloadSearchResults);
  heading.insertBefore(tools, countEl);
  tools.appendChild(button);
  tools.appendChild(countEl);
}

function csvCell(value) {
  return `"${String(value ?? "").replace(/"/g, '""')}"`;
}

function exportRows() {
  return groupedVenues(latestResults).flatMap((group) => {
    const venue = group.venue || {};
    const starWineVenue = group.results.find((result) => resultSourceKind(result) === "live")?.venue || {};
    const databaseVenue = group.results.find((result) => resultSourceKind(result) !== "live")?.venue || {};
    const pdfLists = groupPdfLists(group);
    const lines = groupOfferLines(group);
    const pdfUrls = pdfLists.map((list) => pdfUrl(list)).filter(Boolean).join(" | ");
    return (lines.length ? lines : [{ text: "", vintage: "", priceValue: "", currency: "", review: true }]).map((line) => ({
      place: fallback(venue.name),
      type: venue.type || "Restaurant / wine bar",
      city: venue.city || "",
      country: venue.country || "",
      updated: groupUpdatedValue(group) || group.results[0]?.wineList?.updatedDate || group.results[0]?.wineList?.updatedText || "",
      matchedLine: line.text || "",
      vintage: line.vintage || "",
      originalPrice: originalPriceText(line),
      krw: krwPriceText(line),
      source: resultSourceLabel(line),
      sourceUrl: pdfUrl(line.wineList || {}),
      pdfUrls,
      starWineListUrl: starWineVenue.url || "",
      officialWebsiteUrl: databaseVenue.url || "",
      mapUrl: databaseVenue.googleMapsUrl || starWineVenue.googleMapsUrl || venue.googleMapsUrl || venue.starWineMapUrl || ""
    }));
  });
}

function downloadSearchResults() {
  const headers = ["Place", "Type", "City", "Country", "Updated", "Matched line", "Vintage", "Original price", "KRW", "Source", "Source URL", "PDF URLs", "Star Wine List URL", "Official website URL", "Map URL"];
  const rows = exportRows();
  const csv = [headers, ...rows.map((row) => [
    row.place,
    row.type,
    row.city,
    row.country,
    row.updated,
    row.matchedLine,
    row.vintage,
    row.originalPrice,
    row.krw,
    row.source,
    row.sourceUrl,
    row.pdfUrls,
    row.starWineListUrl,
    row.officialWebsiteUrl,
    row.mapUrl
  ])].map((row) => row.map(csvCell).join(",")).join("\r\n");
  const blob = new Blob([`\uFEFF${csv}`], { type: "text/csv;charset=utf-8" });
  const url = URL.createObjectURL(blob);
  const a = document.createElement("a");
  const stamp = new Date().toISOString().slice(0, 10);
  a.href = url;
  a.download = `whereiskelley-results-${stamp}.csv`;
  document.body.appendChild(a);
  a.click();
  a.remove();
  URL.revokeObjectURL(url);
}

function renderResultList() {
  const liveLine = liveRefreshLine(latestLiveRefresh);
  const results = latestResults;
  if (!results.length) {
    resultsEl.innerHTML = `${liveLine}<div class="empty-list"><h3>No results</h3><p>Try another spelling or a broader query.</p></div>`;
    return;
  }
  const groups = sortGroups(groupedVenues(results));
  const rows = groups.map((group) => renderPlaceRow(group)).join("");
  resultsEl.innerHTML = `${liveLine}${sourceLegendMarkup()}<div class="table-wrap">
    <table class="result-table">
      <thead>
        <tr>
          <th>${sortHeader("Place", "place")}</th>
          <th>${sortHeader("City", "city")}</th>
          <th>${sortHeader("Country", "country")}</th>
          <th>${sortHeader("Updated", "updated")}</th>
          <th>${sortHeader("Matches", "matches")}</th>
          <th>${sortHeader("Price", "krw")}</th>
        </tr>
      </thead>
      <tbody>${rows}</tbody>
    </table>
  </div>`;
}

function renderPlaceRow(group) {
  const key = group.key;
  const venue = group.venue || {};
  const firstList = group.results[0]?.wineList || {};
  const expanded = key && key === activeVenueKey;
  return `<tr class="place-row${expanded ? " active" : ""}" data-venue-key="${escapeHtml(key)}">
      <td class="place-cell"><div class="place-name-line"><b>${escapeHtml(fallback(venue.name))}</b>${groupSourceMarks(group)}${venueReviewBadge(group)}</div><span>${escapeHtml(venue.type || "Restaurant / wine bar")}</span></td>
      <td>${escapeHtml(fallback(venue.city))}</td>
      <td>${escapeHtml(fallback(venue.country))}</td>
      <td>${escapeHtml(fallback(groupUpdatedValue(group) || firstList.updatedDate || firstList.updatedText))}</td>
      <td>${escapeHtml(placeLineLabel(group))}</td>
      <td class="krw-cell">${priceOffersMarkup(group)}</td>
    </tr>${expanded ? renderExpandedPlace(group) : ""}`;
}

function placeLineLabel(group) {
  const collected = group.results.filter((result) => resultSourceKind(result) !== "live");
  const ordinaryGroup = { ...group, results: group.results.filter((result) => resultSourceKind(result) === "live") };
  const indexedLines = fallbackWineLines(ordinaryGroup.results);
  const verified = reconciledGroupLines(ordinaryGroup).filter((line) => line.pdfVerified).length;
  if (collected.length && !ordinaryGroup.results.length) return `${collected.length} database match${collected.length === 1 ? "" : "es"}`;
  if (collected.length) return `${indexedLines.length} Star Wine / ${collected.length} Database`;
  if (indexedLines.length && verified) return `${indexedLines.length} indexed / ${verified} verified`;
  if (indexedLines.length) return `${indexedLines.length} indexed lines`;
  const pdfLines = groupPdfLines(group);
  if (pdfLines.length) return `${pdfLines.length} PDF-only lines`;
  return "Review";
}

function renderExpandedPlace(group) {
  const venue = group.venue || {};
  const collectedResults = group.results.filter((result) => resultSourceKind(result) !== "live");
  const ordinaryGroup = { ...group, results: group.results.filter((result) => resultSourceKind(result) === "live") };
  const pdfLists = groupPdfLists(ordinaryGroup);
  const pdfLines = groupPdfLines(ordinaryGroup);
  if (ordinaryGroup.results.length && groupPdfPending(ordinaryGroup)) {
    window.setTimeout(() => loadPdfLines(ordinaryGroup), 0);
  }
  const sourceLines = reconciledGroupLines(ordinaryGroup);
  const reviewReason = groupPdfReviewReason(ordinaryGroup);
  const indexedLines = fallbackWineLines(ordinaryGroup.results);
  const verifiedCount = sourceLines.filter((line) => line.pdfVerified).length;
  const heldPdfExtras = indexedLines.length ? Math.max(0, pdfLines.length - verifiedCount) : 0;
  const reviewNote = heldPdfExtras
    ? `<div class="review-note">Showing Star Wine List indexed rows first. ${escapeHtml(String(heldPdfExtras))} PDF-only rows were held for review instead of being added automatically.</div>`
    : pdfLines.length
      ? ""
    : groupPdfPending(ordinaryGroup)
      ? `<div class="review-note">Reading the current PDF download...</div>`
      : reviewReason
        ? `<div class="review-note">${escapeHtml(reviewReason)} ${sourceLines.length ? "The rows below are from the Star Wine List search index." : "No priced wine line was found in the downloaded PDF or search index."}</div>`
        : "";
  const offerLines = [...sourceLines, ...uniqueResults(collectedResults)];
  const lines = offerLines
    .slice()
    .sort((a, b) => {
      const wineDiff = normalizedWineText(a.text).localeCompare(normalizedWineText(b.text));
      if (wineDiff) return wineDiff;
      const vintageDiff = String(a.vintage || "").localeCompare(String(b.vintage || ""));
      if (vintageDiff) return vintageDiff;
      return numericPrice(a) - numericPrice(b);
    })
    .map((result) => `<tr>
      <td class="wine-cell">${escapeHtml(result.text)}</td>
      <td>${escapeHtml(result.vintage || "")}</td>
      <td class="price-cell">${originalPriceMarkup(result)}</td>
      <td class="krw-cell">${krwPriceMarkup(result)}</td>
      <td>${escapeHtml(result.wineList?.updatedDate || result.wineList?.updatedText || "")}</td>
      <td>${escapeHtml(result.pageNumber || "")}</td>
      <td>${sourceBadge(resultSource(result))}</td>
    </tr>`)
    .join("");
  const offerNote = ordinaryGroup.results.length && collectedResults.length
    ? `<div class="offer-note">Prices are kept as separate offers by source. Nothing is overwritten when Star Wine and Database prices differ.</div>`
    : "";
  const ordinaryTable = offerLines.length || pdfLines.length
    ? `<table class="line-table">
        <thead>
          <tr><th>Matched wine</th><th>Vintage</th><th>Price</th><th>KRW</th><th>Updated</th><th>Page</th><th>Source</th></tr>
        </thead>
        <tbody>${lines || `<tr><td colspan="7" class="muted">Review needed. No priced wine line was verified from the PDF.</td></tr>`}</tbody>
      </table>`
    : "";
  const collectedListUrl = collectedResults
    .map((result) => result.venue?.inventoryUrl || pdfUrl(result.wineList || {}))
    .find(Boolean) || "";
  const starWineVenue = group.results.find((result) => resultSourceKind(result) === "live")?.venue || {};
  const databaseVenue = group.results.find((result) => resultSourceKind(result) !== "live")?.venue || {};
  const mapUrl = databaseVenue.googleMapsUrl || starWineVenue.googleMapsUrl || venue.googleMapsUrl || venue.starWineMapUrl;
  return `<tr class="expanded-row">
    <td colspan="6">
      <div class="expanded-place">
        <div class="expanded-head">
          <div>
            <b>${escapeHtml(fallback(venue.name))}</b>
            <span>${escapeHtml([venue.city, venue.country].filter(Boolean).join(", "))}</span>
          </div>
          <div class="actions compact">
            ${pdfLinksMarkup(pdfLists)}
            ${collectedListUrl ? `<a class="primary-link" href="${escapeHtml(collectedListUrl)}" target="_blank" rel="noreferrer">Wine list</a>` : ""}
            ${mapUrl ? `<a class="secondary" href="${escapeHtml(mapUrl)}" target="_blank" rel="noreferrer">Map</a>` : ""}
            ${starWineVenue.url ? `<a class="secondary" href="${escapeHtml(starWineVenue.url)}" target="_blank" rel="noreferrer">Star Wine</a>` : ""}
            ${databaseVenue.url ? `<a class="secondary" href="${escapeHtml(databaseVenue.url)}" target="_blank" rel="noreferrer">Official website</a>` : ""}
          </div>
        </div>
        ${offerNote}
        ${reviewNote}
        ${ordinaryTable}
      </div>
    </td>
  </tr>`;
}

function venueKey(result) {
  const venue = result.venue || {};
  const name = normalizedVenueText(stripVenueReviewPrefix(venue.name));
  const city = normalizedVenueText(venue.city);
  const country = normalizedVenueCountry(venue.country);
  if (name && city && country) return `${name}|${city}|${country}`;
  return String(venue.id || venue.url || venue.name || "");
}

function normalizedVenueText(value = "") {
  return String(value || "")
    .normalize("NFKC")
    .toLowerCase()
    .replace(/[^\p{L}\p{N}]+/gu, " ")
    .trim();
}

function normalizedVenueCountry(value = "") {
  const country = normalizedVenueText(value);
  const aliases = {
    "u k": "united kingdom",
    uk: "united kingdom",
    england: "united kingdom",
    "great britain": "united kingdom",
    usa: "united states",
    "u s a": "united states",
    "united states of america": "united states",
    "netherlands kingdom of the": "netherlands"
  };
  return aliases[country] || country;
}

function mergeVenueDetails(current = {}, incoming = {}) {
  const merged = { ...current };
  for (const field of [
    "name", "type", "city", "country", "lat", "lng", "address",
    "googleMapsUrl", "starWineMapUrl", "url", "needsReview"
  ]) {
    const value = incoming[field];
    if ((merged[field] === null || merged[field] === undefined || merged[field] === "")
      && value !== null && value !== undefined && value !== "") {
      merged[field] = value;
    }
  }
  return merged;
}

function coordinateValue(value) {
  if (value === null || value === undefined || value === "") return Number.NaN;
  const number = Number(value);
  return Number.isFinite(number) ? number : Number.NaN;
}

function groupedVenues(results) {
  const groups = new Map();
  for (const result of results) {
    const rawVenue = result.venue || {};
    const venue = { ...rawVenue, name: stripVenueReviewPrefix(rawVenue.name) };
    const key = venueKey(result);
    if (!key) continue;
    if (!groups.has(key)) {
      groups.set(key, {
        key,
        venue,
        results: [],
        lat: coordinateValue(venue.lat),
        lng: coordinateValue(venue.lng),
        nameNeedsReview: Boolean(rawVenue.needsReview) || hasVenueReviewPrefix(rawVenue.name)
      });
    } else {
      const group = groups.get(key);
      group.venue = mergeVenueDetails(group.venue, venue);
      group.nameNeedsReview = group.nameNeedsReview || Boolean(rawVenue.needsReview) || hasVenueReviewPrefix(rawVenue.name);
      const incomingLat = coordinateValue(venue.lat);
      const incomingLng = coordinateValue(venue.lng);
      if (!Number.isFinite(group.lat) && Number.isFinite(incomingLat)) group.lat = incomingLat;
      if (!Number.isFinite(group.lng) && Number.isFinite(incomingLng)) group.lng = incomingLng;
    }
    groups.get(key).results.push(result);
  }
  for (const group of groups.values()) {
    group.results = uniqueResults(group.results);
  }
  return [...groups.values()].sort((a, b) => String(a.venue?.name || "").localeCompare(String(b.venue?.name || "")));
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
  return window.STARWINE_CONFIG?.googleMapsApiKey || localStorage.getItem("googleMapsApiKey") || "";
}

function showMapFallback(message = "", title = "Map unavailable", loading = false) {
  googleMapEl.classList.add("hidden");
  mapFallbackEl.classList.remove("hidden");
  const heading = mapFallbackEl.querySelector("h3");
  const note = mapFallbackEl.querySelector(".map-state-message");
  const spinner = mapFallbackEl.querySelector(".spinner");
  if (heading) heading.textContent = title;
  if (note) note.textContent = message || "The map will appear when matching places have coordinates.";
  if (spinner) spinner.classList.toggle("hidden", !loading);
}

function loadGoogleMaps() {
  if (window.google?.maps) return Promise.resolve(window.google.maps);
  const key = getGoogleMapsKey();
  if (!key) return Promise.resolve(null);
  if (googleMapsPromise) return googleMapsPromise;
  googleMapsPromise = new Promise((resolve, reject) => {
    const callbackName = `initStarWineMap${Date.now()}`;
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
    script.src = `https://maps.googleapis.com/maps/api/js?key=${encodeURIComponent(key)}&callback=${callbackName}&v=weekly`;
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
  return googleMapsPromise;
}

async function drawGoogleMap(venues) {
  const token = ++mapRenderToken;
  if (!venues.length) {
    clearGoogleMarkers();
    showMapFallback("No matching places with coordinates were found for this search.", "No mapped places");
    return;
  }
  try {
    const maps = await loadGoogleMaps();
    if (token !== mapRenderToken) return;
    if (!maps) {
      showMapFallback("The map is hidden because the deployed Google Maps key is not configured.", "Map unavailable");
      return;
    }
    mapFallbackEl.classList.add("hidden");
    googleMapEl.classList.remove("hidden");
    if (!googleMap) {
      googleMap = new maps.Map(googleMapEl, {
        center: { lat: 25, lng: 8 },
        zoom: 2,
        zoomControl: true,
        zoomControlOptions: { position: maps.ControlPosition.RIGHT_BOTTOM },
        gestureHandling: "greedy",
        scrollwheel: true,
        draggable: true,
        keyboardShortcuts: true,
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
    showMapFallback(error.message, "Map unavailable");
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

async function runSearch() {
  const controller = new AbortController();
  const requestId = ++activeSearchRequestId;
  activeSearchController = controller;
  activeId = "";
  activeVenueKey = "";
  latestResults = [];
  latestLiveRefresh = null;
  pdfLineCache.clear();
  pdfLineLoading.clear();
  countEl.textContent = "0";
  resultsEl.innerHTML = `<div class="loading"><span class="spinner" aria-hidden="true"></span><div><b>Searching every page...</b><span>Results will appear after the full scan finishes.</span></div></div>`;
  mapSummaryEl.textContent = "Searching...";
  showMapFallback("Scanning all matching pages before drawing the map.", "Searching places", true);
  clearGoogleMarkers();
  setSearchButtonState(true);
  const params = new URLSearchParams();
  if (queryInput.value.trim()) params.set("q", queryInput.value.trim());
  if (countryInput.value) params.set("country", countryInput.value);
  if (cityInput.value.trim()) params.set("city", cityInput.value.trim());
  if (vintageInput.value.trim()) params.set("vintage", vintageInput.value.trim());
  if (queryInput.value.trim()) {
    params.set("live", "1");
    params.set("livePages", "all");
    params.set("livePageCap", "200");
    params.set("liveMaxPdfs", "0");
  }
  params.set("limit", "5000");
  try {
    const payload = await getJson(`/api/search_v2?${params.toString()}`, {
      signal: controller.signal
    });
    if (controller.signal.aborted || requestId !== activeSearchRequestId) return;
    const results = Array.isArray(payload.results) ? payload.results : [];
    const shopMatches = results.filter((result) => resultSourceKind(result) === "shop").length;
    const databaseMatches = results.filter((result) => resultSourceKind(result) === "db").length;
    const starWineMatches = results.filter((result) => resultSourceKind(result) === "live").length;
    renderResults(results, {
      sourceSummary: "Integrated search complete",
      databaseMatches,
      shopMatches,
      starWineMatches
    });
  } finally {
    if (activeSearchController === controller) {
      activeSearchController = null;
      setSearchButtonState(false);
    }
  }
}

form.addEventListener("submit", (event) => {
  event.preventDefault();
  if (stopActiveSearch()) return;
  runSearch().catch((error) => {
    if (error.name === "AbortError") return;
    resultsEl.innerHTML = `<div class="empty-list"><h3>Search error</h3><p>${escapeHtml(error.message)}</p></div>`;
  });
});

resultsEl.addEventListener("click", (event) => {
  const sortButton = event.target.closest("[data-sort]");
  if (sortButton) {
    const key = sortButton.dataset.sort;
    if (sortState.key === key) {
      sortState.direction = sortState.direction === "asc" ? "desc" : "asc";
    } else {
      sortState = { key, direction: key === "krw" || key === "matches" || key === "updated" ? "desc" : "asc" };
    }
    renderResultList();
    return;
  }
  if (event.target.closest("a")) return;
  const row = event.target.closest("[data-venue-key]");
  if (!row) return;
  activeVenueKey = activeVenueKey === row.dataset.venueKey ? "" : row.dataset.venueKey;
  renderResultList();
  setActiveMapMarker(activeVenueKey);
});

getJson("/api/filters")
  .then((filters) => {
    renderFilters(filters);
    queryInput.value = "William Kelley";
    resultsEl.innerHTML = `<div class="empty-list"><h3>Ready to search</h3><p>Enter a wine name and press Search.</p></div>`;
    mapSummaryEl.textContent = "Waiting for search";
    showMapFallback("Search results will draw the map.", "Ready", false);
  })
  .catch((error) => {
    resultsEl.innerHTML = `<div class="empty-list"><h3>Load error</h3><p>${escapeHtml(error.message)}</p></div>`;
  });
