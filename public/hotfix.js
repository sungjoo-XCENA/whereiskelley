const hotfixStyle = document.createElement("style");
hotfixStyle.textContent = `
  .sort-badge {
    display: inline-flex;
    align-items: center;
    justify-content: center;
    margin-left: 6px;
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
  .line-table .muted {
    color: var(--muted);
    font-weight: 750;
  }
  .download-results {
    min-height: 34px;
    border-color: var(--line);
    background: #fff;
    color: var(--ink);
    font-size: 13px;
    white-space: nowrap;
  }
  .download-results:hover {
    border-color: rgba(159, 18, 57, 0.35);
    background: #fff5f7;
    color: var(--accent);
  }
  .panel-tools {
    display: inline-flex;
    align-items: center;
    gap: 10px;
  }
  @media (max-width: 720px) {
    .app-shell {
      width: min(100vw - 14px, 720px);
      padding: 10px 0 18px;
    }
    .app-header {
      padding: 14px 2px 12px;
    }
    h1 {
      font-size: clamp(38px, 14vw, 54px);
    }
    .world-map {
      height: 300px;
      margin: 0 8px 8px;
    }
    .panel-heading {
      align-items: flex-start;
      flex-wrap: wrap;
      padding: 14px;
    }
    .panel-tools {
      width: 100%;
      justify-content: space-between;
    }
    .download-results {
      flex: 1;
    }
    .result-stack {
      max-height: none;
    }
    .table-wrap {
      overflow: visible;
    }
    .result-table {
      min-width: 0;
      border-spacing: 0;
    }
    .result-table > thead {
      display: none;
    }
    .result-table,
    .result-table > tbody,
    .result-table > tbody > tr,
    .result-table > tbody > tr > td {
      display: block;
      width: 100%;
    }
    .result-table > tbody > tr.place-row {
      margin: 10px;
      border: 1px solid var(--line);
      border-radius: 8px;
      overflow: hidden;
      background: #fff;
    }
    .result-table > tbody > tr.place-row.active {
      box-shadow: inset 4px 0 0 var(--accent);
    }
    .result-table > tbody > tr.place-row > td {
      display: grid;
      grid-template-columns: 96px minmax(0, 1fr);
      gap: 10px;
      padding: 10px 12px;
      border-bottom: 1px solid var(--line);
    }
    .result-table > tbody > tr.place-row > td:last-child {
      border-bottom: 0;
    }
    .result-table > tbody > tr.place-row > td::before {
      color: var(--muted);
      font-size: 11px;
      font-weight: 900;
      text-transform: uppercase;
    }
    .result-table > tbody > tr.place-row > td:nth-child(1)::before { content: "Place"; }
    .result-table > tbody > tr.place-row > td:nth-child(2)::before { content: "City"; }
    .result-table > tbody > tr.place-row > td:nth-child(3)::before { content: "Country"; }
    .result-table > tbody > tr.place-row > td:nth-child(4)::before { content: "Updated"; }
    .result-table > tbody > tr.place-row > td:nth-child(5)::before { content: "Matches"; }
    .result-table > tbody > tr.place-row > td:nth-child(6)::before { content: "KRW"; }
    .result-table > tbody > tr.place-row > td:nth-child(7)::before { content: "PDF"; }
    .place-cell {
      min-width: 0;
    }
    .krw-cell,
    .price-cell {
      width: auto;
    }
    .expanded-row {
      margin: 0 10px 12px;
    }
    .expanded-place {
      padding: 14px;
      border: 1px solid var(--line);
      border-left: 4px solid var(--accent);
      border-radius: 8px;
    }
    .expanded-head {
      display: grid;
    }
    .actions.compact {
      display: grid;
      grid-template-columns: repeat(3, minmax(0, 1fr));
    }
    .actions.compact a {
      justify-content: center;
      padding: 0 8px;
      text-align: center;
    }
    .line-table,
    .line-table tbody,
    .line-table tr,
    .line-table td {
      display: block;
      width: 100%;
    }
    .line-table thead {
      display: none;
    }
    .line-table tr {
      padding: 10px 0;
      border-top: 1px solid var(--line);
    }
    .line-table td {
      display: grid;
      grid-template-columns: 88px minmax(0, 1fr);
      gap: 10px;
      padding: 5px 0;
      border-top: 0;
    }
    .line-table td::before {
      color: var(--muted);
      font-size: 11px;
      font-weight: 900;
      text-transform: uppercase;
    }
    .line-table td:nth-child(1)::before { content: "Line"; }
    .line-table td:nth-child(2)::before { content: "Vintage"; }
    .line-table td:nth-child(3)::before { content: "Price"; }
    .line-table td:nth-child(4)::before { content: "KRW"; }
    .line-table td:nth-child(5)::before { content: "Page"; }
    .wine-cell {
      min-width: 0;
      width: auto;
    }
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
  ensureDownloadButton();
  latestResults = sortByCheapest(uniqueResults(results));
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

function exportRows(pdfStatusByUrl = new Map()) {
  return groupedVenues(latestResults).flatMap((group) => {
    const venue = group.venue || {};
    const pdfLists = groupPdfLists(group);
    const lines = reconciledGroupLines(group);
    const pdfUrlsArray = pdfLists.map((list) => pdfUrl(list)).filter(Boolean);
    const pdfUrls = pdfUrlsArray.join(" | ");
    const pdfZipPaths = pdfUrlsArray.map((url) => pdfStatusByUrl.get(url)?.path || "").filter(Boolean).join(" | ");
    const pdfDownloadStatus = pdfUrlsArray.map((url) => pdfStatusByUrl.get(url)?.status || (pdfStatusByUrl.size ? "Not attempted" : "")).filter(Boolean).join(" | ");
    const pdfDownloadError = pdfUrlsArray.map((url) => pdfStatusByUrl.get(url)?.error || "").filter(Boolean).join(" | ");
    return (lines.length ? lines : [{ text: "", vintage: "", priceValue: "", currency: "", review: true }]).map((line) => ({
      place: displayVenueName(venue),
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
      pdfZipPaths,
      pdfDownloadStatus,
      pdfDownloadError,
      starWineListUrl: venue.url || "",
      mapUrl: venue.starWineMapUrl || ""
    }));
  });
}

function safeZipName(value, fallback = "item") {
  const cleaned = String(value || fallback)
    .normalize("NFKD")
    .replace(/[\u0300-\u036f]/g, "")
    .replace(/[^A-Za-z0-9._-]+/g, "-")
    .replace(/^-+|-+$/g, "");
  return cleaned || fallback;
}

function csvForRows(headers, rows) {
  return [headers, ...rows].map((row) => row.map(csvCell).join(",")).join("\r\n");
}

function resultsCsv(pdfStatusByUrl = new Map()) {
  const headers = ["Place", "Type", "City", "Country", "Updated", "Matched line", "Vintage", "Original price", "KRW", "Source", "PDF URLs", "PDF ZIP paths", "PDF download status", "PDF download error", "Star Wine List URL", "Map URL"];
  const rows = exportRows(pdfStatusByUrl);
  return csvForRows(headers, rows.map((row) => [
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
    row.pdfZipPaths,
    row.pdfDownloadStatus,
    row.pdfDownloadError,
    row.starWineListUrl,
    row.mapUrl
  ]));
}

function downloadBlob(blob, filename) {
  const url = URL.createObjectURL(blob);
  const a = document.createElement("a");
  a.href = url;
  a.download = filename;
  document.body.appendChild(a);
  a.click();
  a.remove();
  URL.revokeObjectURL(url);
}

function uniquePdfDownloads() {
  const seen = new Set();
  const downloads = [];
  for (const group of groupedVenues(latestResults)) {
    const venue = group.venue || {};
    groupPdfLists(group).forEach((list, index) => {
      const url = pdfUrl(list);
      if (!url) return;
      const key = String(list.id || url);
      if (seen.has(key)) return;
      seen.add(key);
      const place = displayVenueName(venue);
      const filename = `${safeZipName(place, "place")}-${safeZipName(list.id || index + 1, "list")}.pdf`;
      const path = [
        "pdfs",
        safeZipName(venue.country || "unknown-country", "unknown-country"),
        safeZipName(venue.city || "unknown-city", "unknown-city"),
        filename
      ].join("/");
      downloads.push({
        place,
        city: venue.city || "",
        country: venue.country || "",
        url,
        fallbackUrls: pdfFallbackUrls(list),
        filename,
        path
      });
    });
  }
  return downloads;
}

async function fetchPdfForZip(item) {
  const params = new URLSearchParams({
    url: item.url,
    fallbackUrls: item.fallbackUrls.join("|"),
    filename: item.filename
  });
  const response = await fetch(`/api/pdf_file?${params.toString()}`);
  if (!response.ok) {
    throw new Error((await response.text()) || `HTTP ${response.status}`);
  }
  const blob = await response.blob();
  if (!blob.size) throw new Error("Empty PDF response");
  return blob;
}

async function downloadSearchResults() {
  const stamp = new Date().toISOString().slice(0, 10);
  const button = document.querySelector("#downloadResults");
  const originalLabel = button?.textContent || "Download results";
  const csv = resultsCsv();
  if (!window.JSZip) {
    downloadBlob(new Blob([`\uFEFF${csv}`], { type: "text/csv;charset=utf-8" }), `whereiskelley-results-${stamp}.csv`);
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
    zip.file("whereiskelley-results.csv", `\uFEFF${resultsCsv(pdfStatusByUrl)}`);
    if (button) button.textContent = "Creating ZIP";
    const blob = await zip.generateAsync({ type: "blob" });
    downloadBlob(blob, `whereiskelley-results-${stamp}.zip`);
  } finally {
    if (button) {
      button.disabled = false;
      button.textContent = originalLabel;
    }
  }
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
      <td>${escapeHtml(placeLineLabel(group))}</td>
      <td class="krw-cell">${krwPriceMarkup(lowest)}</td>
      <td>${pdfMarkup(groupPdfList(group))}</td>
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
    </tr>`)
    .join("") || `<tr><td colspan="5" class="muted">Review needed. The search index matched text for this place, but no priced wine line was verified from the PDF.</td></tr>`;
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
