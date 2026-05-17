(function () {
  const originalFetch = window.fetch.bind(window);
  let manifestPromise = null;
  let linesPromise = null;

  function normalize(value) {
    return String(value || "")
      .normalize("NFD")
      .replace(/[\u0300-\u036f]/g, "")
      .toLowerCase()
      .replace(/[^a-z0-9]+/g, " ")
      .trim();
  }

  async function fetchJson(path) {
    const response = await originalFetch(path, { cache: "no-store" });
    if (!response.ok) return null;
    return response.json();
  }

  async function fetchChunk(chunk) {
    const response = await originalFetch(`/data/${chunk.file}`, { cache: "no-store" });
    if (!response.ok) return [];
    if (chunk.encoding !== "gzip-base64-json") return response.json();
    if (!("DecompressionStream" in window)) return [];
    const encoded = (await response.text()).trim();
    const bytes = Uint8Array.from(atob(encoded), (char) => char.charCodeAt(0));
    const stream = new Blob([bytes]).stream().pipeThrough(new DecompressionStream("gzip"));
    return JSON.parse(await new Response(stream).text());
  }

  async function loadManifest() {
    if (!manifestPromise) manifestPromise = fetchJson(`/data/search-manifest.json?ts=${Date.now()}`);
    return manifestPromise;
  }

  async function loadLines() {
    if (!linesPromise) {
      linesPromise = loadManifest().then(async (manifest) => {
        const chunks = Array.isArray(manifest?.chunks) ? manifest.chunks : [];
        const loaded = await Promise.all(chunks.map(fetchChunk));
        return loaded.flatMap((chunk) => Array.isArray(chunk) ? chunk : []);
      });
    }
    return linesPromise;
  }

  function searchText(result) {
    return normalize([
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

  function matches(result, params) {
    const query = normalize(params.get("q") || "");
    const tokens = query.split(/\s+/).filter(Boolean);
    const text = searchText(result);
    if (tokens.length && !tokens.every((token) => text.includes(token))) return false;
    const country = normalize(params.get("country") || "");
    if (country && normalize(result.venue?.country) !== country) return false;
    const city = normalize(params.get("city") || "");
    if (city && !normalize(result.venue?.city).includes(city)) return false;
    const vintage = String(params.get("vintage") || "");
    if (vintage && String(result.vintage || "") !== vintage && !String(result.text || "").includes(vintage)) return false;
    return true;
  }

  function keyFor(result) {
    return [
      String(result.text || "").trim().toLowerCase(),
      result.vintage || "",
      result.currency || "",
      result.priceValue ?? "",
      result.wineList?.id || ""
    ].join("|");
  }

  function tagType(result, source) {
    const venue = { ...(result.venue || {}) };
    const originalType = String(venue.type || "Restaurant / wine bar").replace(/^\[[^\]]+\]\s*/, "");
    venue.type = `[${source}] ${originalType}`;
    return { ...result, venue, source };
  }

  function mergeResults(dbResults, liveResults) {
    const byKey = new Map();
    for (const result of dbResults) byKey.set(keyFor(result), tagType(result, "DB"));
    for (const result of liveResults) {
      const key = keyFor(result);
      byKey.set(key, tagType(result, byKey.has(key) ? "DB + Live" : "Live"));
    }
    return [...byKey.values()];
  }

  async function mergedSearchResponse(input, init) {
    const response = await originalFetch(input, init);
    const url = new URL(typeof input === "string" ? input : input.url, window.location.href);
    if (url.pathname !== "/api/search" || !url.searchParams.get("q")) return response;
    const payload = await response.clone().json();
    const limit = Number(url.searchParams.get("limit") || 5000);
    const lines = await loadLines();
    const dbResults = lines
      .filter((result) => matches(result, url.searchParams))
      .slice(0, limit);
    const liveResults = Array.isArray(payload.results) ? payload.results : [];
    const merged = mergeResults(dbResults, liveResults);
    payload.results = merged;
    payload.count = merged.length;
    payload.liveRefresh = {
      ...(payload.liveRefresh || {}),
      sourceSummary: "DB snapshot + live API",
      snapshotLines: lines.length,
      snapshotMatches: dbResults.length,
      liveMatches: liveResults.length
    };
    return new Response(JSON.stringify(payload), {
      status: response.status,
      statusText: response.statusText,
      headers: response.headers
    });
  }

  function injectStyles() {
    const style = document.createElement("style");
    style.textContent = `
      .source-badge{display:inline-flex;align-items:center;min-height:20px;margin-right:6px;padding:0 7px;border-radius:999px;font-size:11px;font-weight:900;line-height:1}
      .source-badge.db{background:#eef2ff;color:#3730a3}
      .source-badge.live{background:#ecfdf3;color:#047857}
      .source-badge.both{background:#fff1f2;color:#9f1239}
    `;
    document.head.appendChild(style);
  }

  function renderSourceBadges() {
    document.querySelectorAll(".place-cell span").forEach((node) => {
      if (node.dataset.sourceRendered) return;
      const match = node.textContent.match(/^\[(DB \+ Live|DB|Live)\]\s*(.*)$/);
      if (!match) return;
      const source = match[1];
      const type = match[2] || "";
      const cls = source === "DB + Live" ? "both" : source.toLowerCase();
      node.innerHTML = `<span class="source-badge ${cls}">${source}</span>${type}`;
      node.dataset.sourceRendered = "1";
    });
  }

  window.fetch = mergedSearchResponse;
  injectStyles();
  new MutationObserver(renderSourceBadges).observe(document.documentElement, { childList: true, subtree: true });
})();
