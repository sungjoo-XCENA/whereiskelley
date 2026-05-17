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
  return result.source || result.sourceLabel || "Live";
}

function sourceBadge(source) {
  const value = String(source || "Live");
  const normalized = value.toLowerCase();
  const key = normalized.includes("db") && normalized.includes("live")
    ? "both"
    : normalized.includes("db")
      ? "db"
      : "live";
  const label = key === "both" ? "Saved DB + Live API" : key === "db" ? "Saved DB" : "Live API";
  return `<span class="source-badge ${key}">${escapeHtml(label)}</span>`;
}

function mergeResultSources(results = []) {
  const byKey = new Map();
  for (const raw of results) {
    const result = { ...raw };
    const key = resultDedupKey(result);
    if (!byKey.has(key)) {
      byKey.set(key, result);
      continue;
    }
    const existing = byKey.get(key);
    const sources = new Set(
      [resultSource(existing), resultSource(result)]
        .join("+")
        .split("+")
        .map((item) => item.trim())
        .filter(Boolean)
    );
    if (sources.has("DB") && sources.has("Live")) {
      existing.source = "DB + Live";
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

function groupUpdatedValue(group) {
  return group.results
    .map((result) => result.wineList?.updatedDate || result.wineList?.updatedText || "")
    .filter(Boolean)
    .sort()
    .at(-1) || "";
}

function groupLowestPriceResult(group) {
  const candidates = reconciledGroupLines(group);
  return [...candidates].sort((a, b) => numericPrice(a) - numericPrice(b))[0] || {};
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
  if (!hasValidPrice(result)) return Number.POSITIVE_INFINITY;
  const rate = KRW_RATES[currencyCode(result)];
  return rate ? Number(result.priceValue) * rate : Number.POSITIVE_INFINITY;
}

function groupPdfList(group) {
  return groupPdfLists(group)[0] || {};
}

function groupPdfLists(group) {
  const seen = new Set();
  const lists = [];
  for (const result of group.results) {
    const list = result.wineList || {};
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
      left = groupUpdatedValue(a);
      right = groupUpdatedValue(b);
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
    const pdfLists = groupPdfLists(group);
    const lines = reconciledGroupLines(group);
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
      source: line.source || "Search index",
      pdfUrls,
      starWineListUrl: venue.url || "",
      mapUrl: venue.starWineMapUrl || ""
    }));
  });
}

function downloadSearchResults() {
  const headers = ["Place", "Type", "City", "Country", "Updated", "Matched line", "Vintage", "Original price", "KRW", "Source", "PDF URLs", "Star Wine List URL", "Map URL"];
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
    row.pdfUrls,
    row.starWineListUrl,
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
  groups.forEach((group) => {
    if (groupPdfLists(group).length) window.setTimeout(() => loadPdfLines(group), 0);
  });
  const rows = groups.map((group) => renderPlaceRow(group)).join("");
  resultsEl.innerHTML = `${liveLine}<div class="table-wrap">
    <table class="result-table">
      <thead>
        <tr>
          <th>${sortHeader("Place", "place")}</th>
          <th>${sortHeader("City", "city")}</th>
          <th>${sortHeader("Country", "country")}</th>
          <th>${sortHeader("Updated", "updated")}</th>
          <th>${sortHeader("Matches", "matches")}</th>
          <th>${sortHeader("Lowest KRW", "krw")}</th>
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
  const lowest = groupLowestPriceResult(group);
  const expanded = key && key === activeVenueKey;
  const sources = [...new Set(group.results.map(resultSource))].sort();
  return `<tr class="place-row${expanded ? " active" : ""}" data-venue-key="${escapeHtml(key)}">
      <td class="place-cell"><b>${escapeHtml(fallback(venue.name))}</b><span>${escapeHtml(venue.type || "Restaurant / wine bar")}</span><span class="source-badges">${sources.map(sourceBadge).join("")}</span></td>
      <td>${escapeHtml(fallback(venue.city))}</td>
      <td>${escapeHtml(fallback(venue.country))}</td>
      <td>${escapeHtml(fallback(groupUpdatedValue(group) || firstList.updatedDate || firstList.updatedText))}</td>
      <td>${escapeHtml(placeLineLabel(group))}</td>
      <td class="krw-cell">${krwPriceMarkup(lowest)}</td>
    </tr>${expanded ? renderExpandedPlace(group) : ""}`;
}

function placeLineLabel(group) {
  const indexedLines = fallbackWineLines(group.results);
  const verified = reconciledGroupLines(group).filter((line) => line.pdfVerified).length;
  if (indexedLines.length && verified) return `${indexedLines.length} indexed / ${verified} verified`;
  if (indexedLines.length) return `${indexedLines.length} indexed lines`;
  const pdfLines = groupPdfLines(group);
  if (pdfLines.length) return `${pdfLines.length} PDF-only lines`;
  return "Review";
}

function renderExpandedPlace(group) {
  const venue = group.venue || {};
  const pdfLists = groupPdfLists(group);
  const pdfLines = groupPdfLines(group);
  if (groupPdfPending(group)) {
    window.setTimeout(() => loadPdfLines(group), 0);
  }
  const sourceLines = reconciledGroupLines(group);
  const reviewReason = groupPdfReviewReason(group);
  const indexedLines = fallbackWineLines(group.results);
  const verifiedCount = sourceLines.filter((line) => line.pdfVerified).length;
  const heldPdfExtras = indexedLines.length ? Math.max(0, pdfLines.length - verifiedCount) : 0;
  const reviewNote = heldPdfExtras
    ? `<div class="review-note">Showing Star Wine List indexed rows first. ${escapeHtml(String(heldPdfExtras))} PDF-only rows were held for review instead of being added automatically.</div>`
    : pdfLines.length
      ? ""
    : groupPdfPending(group)
      ? `<div class="review-note">Reading the current PDF download...</div>`
      : reviewReason
        ? `<div class="review-note">${escapeHtml(reviewReason)} ${sourceLines.length ? "The rows below are from the Star Wine List search index." : "No priced wine line was found in the downloaded PDF or search index."}</div>`
        : "";
  const lines = sourceLines
    .slice()
    .sort((a, b) => numericPrice(a) - numericPrice(b))
    .map((result) => `<tr>
      <td class="wine-cell">${escapeHtml(result.text)}</td>
      <td>${escapeHtml(result.vintage || "")}</td>
      <td class="price-cell">${originalPriceMarkup(result)}</td>
      <td class="krw-cell">${krwPriceMarkup(result)}</td>
      <td>${escapeHtml(result.pageNumber || "")}</td>
      <td>${sourceBadge(resultSource(result))}</td>
    </tr>`)
    .join("") || `<tr><td colspan="6" class="muted">Review needed. The search index matched text for this place, but no priced wine line was verified from the PDF.</td></tr>`;
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
            ${venue.starWineMapUrl ? `<a class="secondary" href="${escapeHtml(venue.starWineMapUrl)}" target="_blank" rel="noreferrer">Map</a>` : ""}
            ${venue.url ? `<a class="secondary" href="${escapeHtml(venue.url)}" target="_blank" rel="noreferrer">Star Wine List page</a>` : ""}
          </div>
        </div>
        ${reviewNote}
        <table class="line-table">
          <thead>
            <tr><th>Matched PDF/search line</th><th>Vintage</th><th>Price</th><th>KRW</th><th>Page</th><th>Source</th></tr>
          </thead>
          <tbody>${lines}</tbody>
        </table>
      </div>
    </td>
  </tr>`;
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
  submitButton.disabled = true;
  const params = new URLSearchParams();
  if (queryInput.value.trim()) params.set("q", queryInput.value.trim());
  if (countryInput.value) params.set("country", countryInput.value);
  if (cityInput.value.trim()) params.set("city", cityInput.value.trim());
  if (vintageInput.value.trim()) params.set("vintage", vintageInput.value.trim());
  if (queryInput.value.trim()) {
    params.set("live", "1");
    params.set("livePages", "all");
    params.set("livePageCap", "200");
    params.set("liveMaxPdfs", "50");
  }
  params.set("limit", "5000");
  try {
    const [snapshotResult, liveResult] = await Promise.allSettled([
      searchSnapshot(params),
      getJson(`/api/search?${params.toString()}`)
    ]);
    const snapshotPayload = snapshotResult.status === "fulfilled" ? snapshotResult.value : { results: [], liveRefresh: null };
    const livePayload = liveResult.status === "fulfilled" ? liveResult.value : { results: [], liveRefresh: null };
    const dbResults = (snapshotPayload.results || []).map((result) => ({ ...result, source: result.source || "DB" }));
    const liveResults = (livePayload.results || []).map((result) => ({ ...result, source: "Live" }));
    renderResults([...dbResults, ...liveResults], {
      sourceSummary: "DB snapshot + live API",
      snapshotLines: snapshotPayload.liveRefresh?.snapshotLines || 0,
      snapshotMatches: dbResults.length,
      liveMatches: liveResults.length
    });
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

resultsEl.addEventListener("click", (event) => {
  const sortButton = event.target.closest("[data-sort]");
  if (sortButton) {
    const key = sortButton.dataset.sort;
    if (sortState.key === key) {
      sortState.direction = sortState.direction === "asc" ? "desc" : "asc";
    } else {
      sortState = { key, direction: key === "krw" || key === "matches" ? "desc" : "asc" };
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
    return runSearch();
  })
  .catch((error) => {
    resultsEl.innerHTML = `<div class="empty-list"><h3>Load error</h3><p>${escapeHtml(error.message)}</p></div>`;
  });
