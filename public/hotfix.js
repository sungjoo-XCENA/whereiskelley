const hotfixStyle = document.createElement("style");
hotfixStyle.textContent = `
  .sort-badge {
    display: inline-flex;
    align-items: center;
    justify-content: center;
    min-width: 22px;
    height: 20px;
    border: 1px solid rgba(159, 18, 57, 0.18);
    border-radius: 999px;
    background: #fff5f7;
    color: var(--accent);
    font-size: 12px;
    font-weight: 950;
    line-height: 1;
  }
`;
document.head.appendChild(hotfixStyle);

function pdfUrl(list = {}) {
  return list.downloadUrl || list.fileViewUrl || list.fileUrl || list.externalUrl || list.localFileUrl || "";
}

function pdfFallbackUrls(list = {}) {
  return [list.fileViewUrl, list.fileUrl, list.externalUrl, list.localFileUrl]
    .filter((url) => url && url !== pdfUrl(list));
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

function cleanVenueName(value) {
  return String(value || "").replace(/^[\s\u00d7\u2715\u2716\u2717\u2718\u274c]+/, "").trim();
}

function displayVenueName(venue = {}) {
  return cleanVenueName(fallback(venue.name));
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

function groupPdfList(group) {
  return groupPdfLists(group)[0] || {};
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
    .map((payload) => payload.reason);
  return [...new Set(reasons)].join(" ");
}

function groupLowestPriceResult(group) {
  const pdfLines = groupPdfLines(group);
  const candidates = pdfLines.length ? pdfLines : group.results;
  return [...candidates].sort((a, b) => numericPrice(a) - numericPrice(b))[0] || {};
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

function renderResults(results, liveRefresh = null) {
  latestResults = sortByCheapest(uniqueResults(results));
  latestLiveRefresh = liveRefresh;
  countEl.textContent = String(groupedVenues(latestResults).length);
  renderMap(latestResults);
  renderResultList();
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
      let payload;
      try {
        payload = await getJson(`/api/pdf_lines_v2?${params.toString()}`);
      } catch (_error) {
        payload = await getJson(`/api/pdf-lines?${params.toString()}`);
      }
      pdfLineCache.set(key, payload);
    } catch (error) {
      pdfLineCache.set(key, { status: "review", reason: error.message, lines: [] });
    } finally {
      pdfLineLoading.delete(key);
    }
  }));
  if (activeVenueKey === group.key) renderResultList();
}

function sortHeader(label, key) {
  const active = sortState.key === key;
  const directionLabel = sortState.direction === "asc" ? "ascending" : "descending";
  const badge = active
    ? `<span class="sort-badge" aria-hidden="true">${sortState.direction === "asc" ? "&#8593;" : "&#8595;"}</span>`
    : "";
  return `<button class="sort-button${active ? " active" : ""}" type="button" data-sort="${escapeHtml(key)}" aria-label="Sort ${escapeHtml(label)}${active ? `, currently ${directionLabel}` : ""}"><span>${escapeHtml(label)}</span>${badge}</button>`;
}

function renderPlaceRow(group) {
  const key = group.key;
  const venue = group.venue || {};
  const firstList = group.results[0]?.wineList || {};
  const lowest = groupLowestPriceResult(group);
  const expanded = key && key === activeVenueKey;
  return `<tr class="place-row${expanded ? " active" : ""}" data-venue-key="${escapeHtml(key)}">
      <td class="place-cell"><b>${escapeHtml(displayVenueName(venue))}</b><span>${escapeHtml(venue.type || "Restaurant / wine bar")}</span></td>
      <td>${escapeHtml(fallback(venue.city))}</td>
      <td>${escapeHtml(fallback(venue.country))}</td>
      <td>${escapeHtml(fallback(groupUpdatedValue(group) || firstList.updatedDate || firstList.updatedText))}</td>
      <td>${escapeHtml(group.results.length)} lines</td>
      <td class="krw-cell">${krwPriceMarkup(lowest)}</td>
      <td>${pdfMarkup(groupPdfList(group))}</td>
    </tr>${expanded ? renderExpandedPlace(group) : ""}`;
}

function renderExpandedPlace(group) {
  const venue = group.venue || {};
  const pdfLists = groupPdfLists(group);
  const pdfLines = groupPdfLines(group);
  if (groupPdfPending(group)) {
    window.setTimeout(() => loadPdfLines(group), 0);
  }
  const sourceLines = uniqueResults(pdfLines.length ? pdfLines : group.results);
  const reviewReason = groupPdfReviewReason(group);
  const reviewNote = pdfLines.length
    ? ""
    : groupPdfPending(group)
      ? `<div class="review-note">Reading the current PDF download...</div>`
      : reviewReason
        ? `<div class="review-note">${escapeHtml(reviewReason)} Showing Star Wine List search-index lines until this PDF is reviewed.</div>`
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
    </tr>`)
    .join("");
  return `<tr class="expanded-row">
    <td colspan="7">
      <div class="expanded-place">
        <div class="expanded-head">
          <div>
            <b>${escapeHtml(displayVenueName(venue))}</b>
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
            <tr><th>Matched PDF/search line</th><th>Vintage</th><th>Price</th><th>KRW</th><th>Page</th></tr>
          </thead>
          <tbody>${lines}</tbody>
        </table>
      </div>
    </td>
  </tr>`;
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
    let payload;
    try {
      payload = await getJson(`/api/search_v2?${params.toString()}`);
    } catch (_error) {
      payload = await getJson(`/api/search?${params.toString()}`);
    }
    renderResults(uniqueResults(payload.results), payload.liveRefresh);
  } finally {
    submitButton.disabled = false;
  }
}
