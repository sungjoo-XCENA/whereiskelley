(function () {
  let cachedStats = null;
  let loaded = false;
  let refreshScheduled = false;

  async function readJson(path) {
    try {
      const response = await fetch(path, { cache: "no-store" });
      if (!response.ok) throw new Error(await response.text());
      return await response.json();
    } catch (error) {
      return { error: error.message || "Unavailable" };
    }
  }

  function ensureDbSourceStrip(stats) {
    const heading = document.querySelector(".result-list .panel-heading");
    if (!heading) return;
    let strip = document.querySelector("#sourceStrip");
    if (!strip) {
      strip = document.createElement("div");
      strip.id = "sourceStrip";
      strip.className = "source-strip";
      heading.insertAdjacentElement("afterend", strip);
    }
    const liveCount = Array.isArray(window.latestResults) ? window.latestResults.length : "";
    const dbText = stats && !stats.error
      ? `DB stored ${stats.entryCount || 0} lines / ${stats.venueCount || 0} places`
      : "DB storage ready / cloud DB not connected";
    const liveText = liveCount === "" ? "Star Wine live" : `Star Wine live ${liveCount} lines`;
    const next = `
      <span class="status-pill">${dbText}</span>
      <span class="status-pill live">${liveText}</span>
      <span class="status-pill">Guide DB schema ready</span>
    `;
    if (strip.innerHTML.trim() !== next.trim()) strip.innerHTML = next;
  }

  function patchDashboardDatabaseCard(stats) {
    const firstCard = document.querySelector("#dashboardView .dashboard-card");
    if (!firstCard) return;
    let next = "";
    if (stats && !stats.error) {
      next = `
        <span>Database</span>
        <b>${stats.entryCount || 0}</b>
        <small>SQLite connected. ${stats.venueCount || 0} places / ${stats.wineListCount || 0} lists stored locally.</small>
      `;
    } else {
      next = `
        <span>Database</span>
        <b>--</b>
        <small>Cloud DB not connected. Live search works now; persistent Supabase/Firebase storage is next.</small>
      `;
    }
    if (firstCard.innerHTML.trim() !== next.trim()) firstCard.innerHTML = next;
  }

  async function refreshDbStatus() {
    if (!loaded) {
      cachedStats = await readJson("/api/stats");
      loaded = true;
    }
    const stats = cachedStats;
    ensureDbSourceStrip(stats);
    patchDashboardDatabaseCard(stats);
  }

  function scheduleRefresh() {
    if (refreshScheduled) return;
    refreshScheduled = true;
    window.setTimeout(() => {
      refreshScheduled = false;
      refreshDbStatus();
    }, 150);
  }

  const observer = new MutationObserver(() => {
    const strip = document.querySelector("#sourceStrip");
    const dashboard = document.querySelector("#dashboardView .dashboard-card");
    if (strip || dashboard) scheduleRefresh();
  });

  window.addEventListener("load", refreshDbStatus);
  observer.observe(document.body, { childList: true, subtree: true });
})();
