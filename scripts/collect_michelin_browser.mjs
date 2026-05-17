import { createRequire } from "node:module";
import fs from "node:fs";
import path from "node:path";
import { fileURLToPath, pathToFileURL } from "node:url";

const __dirname = path.dirname(fileURLToPath(import.meta.url));
const root = path.dirname(__dirname);
const nodeModules =
  process.env.NODE_MODULES_DIR ||
  path.join(process.env.USERPROFILE || "", ".cache", "codex-runtimes", "codex-primary-runtime", "dependencies", "node", "node_modules");
let requireBase = path.join(nodeModules, "package.json");
try {
  const pnpmDir = path.join(nodeModules, ".pnpm");
  const playwrightDir = fs
    .readdirSync(pnpmDir)
    .find((name) => name.startsWith("playwright@") && !name.startsWith("playwright-core@"));
  if (playwrightDir) {
    requireBase = path.join(pnpmDir, playwrightDir, "node_modules", "playwright", "package.json");
  }
} catch {}
const require = createRequire(pathToFileURL(requireBase).href);
const { chromium } = require("playwright");

const args = new Map();
for (let index = 2; index < process.argv.length; index += 2) {
  args.set(process.argv[index], process.argv[index + 1]);
}

const outputPath = args.get("--output");
const progressPath = args.get("--progress");
const runId = args.get("--run-id") || null;
const maxPages = Number(args.get("--max-pages") || process.env.MICHELIN_MAX_PAGES || 100);
const startUrl = args.get("--start-url") || "https://guide.michelin.com/kr/ko/restaurants/all-starred/page/1";
if (!outputPath) {
  console.error("Usage: node scripts/collect_michelin_browser.mjs --output <path> [--max-pages 100]");
  process.exit(2);
}

const browserCandidates = [
  "C:\\Program Files\\Google\\Chrome\\Application\\chrome.exe",
  "C:\\Program Files (x86)\\Google\\Chrome\\Application\\chrome.exe",
  "C:\\Program Files\\Microsoft\\Edge\\Application\\msedge.exe",
  "C:\\Program Files (x86)\\Microsoft\\Edge\\Application\\msedge.exe"
];
const executablePath = browserCandidates.find((candidate) => fs.existsSync(candidate));
const profileDir = path.join(root, "data", "browser-profile-michelin");
const context = await chromium.launchPersistentContext(profileDir, {
  executablePath,
  headless: process.env.SWL_HEADED === "1" ? false : true,
  userAgent:
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124 Safari/537.36"
});
const page = await context.newPage();

function pageUrl(pageNumber) {
  return startUrl.replace(/\/page\/\d+\/?$/, `/page/${pageNumber}`);
}

async function writeProgress(payload) {
  if (!progressPath) return;
  await fs.promises.writeFile(
    progressPath,
    JSON.stringify({
      generatedAt: new Date().toISOString().replace(/\.\d{3}Z$/, "+00:00"),
      status: "running",
      phase: "reading_guides",
      message: "Reading MICHELIN starred restaurants in a browser.",
      runId: runId ? Number(runId) : null,
      source: "michelin",
      currentTarget: "",
      currentUrl: payload.url || "",
      targetsCollected: payload.targetsCollected || 0,
      websitesChecked: 0,
      totalWebsites: 0,
      wineListsFound: 0,
      wineLinesFound: 0,
      errors: 0,
    }) + "\n",
    "utf-8",
  );
}

try {
  const places = [];
  const pages = [];
  let reportedTotal = 0;
  for (let pageNumber = 1; pageNumber <= maxPages; pageNumber += 1) {
    const url = pageUrl(pageNumber);
    await writeProgress({ url, targetsCollected: places.length });
    await page.goto(url, { waitUntil: "domcontentloaded", timeout: 60000 });
    await page.waitForTimeout(1800);
    await page.getByText("?숈쓽 ?놁씠 怨꾩냽?섍린", { exact: false }).click({ timeout: 2000 }).catch(() => {});
    await page.waitForTimeout(500);
    const result = await page.evaluate(() => {
      const bodyText = document.body.innerText || "";
      const rangeMatch = bodyText.match(/([\d,]+)\s*-\s*([\d,]+)\s*媛?s*以?s*([\d,]+)\s*?덉뒪?좊옉/);
      const totalMatch = bodyText.match(/([\d,]+)\s*?덉뒪?좊옉/);
      const total = rangeMatch
        ? Number(rangeMatch[3].replace(/,/g, ""))
        : totalMatch
        ? Number(totalMatch[1].replace(/,/g, ""))
        : 0;
      const rangeCount = rangeMatch
        ? Number(rangeMatch[2].replace(/,/g, "")) - Number(rangeMatch[1].replace(/,/g, "")) + 1
        : 0;
      const nodes = Array.from(document.querySelectorAll(".card__menu.selection-card, .card__menu.js-restaurant__list_item"));
      const cards = [];
      const seen = new Set();
      for (const card of nodes) {
        const title = card.querySelector(".card__menu-content--title a, h3 a[href*='/restaurant/']");
        if (!title) continue;
        const href = new URL(title.getAttribute("href"), location.href).href;
        if (seen.has(href)) continue;
        const text = (card.innerText || "").split("\n").map((line) => line.trim()).filter(Boolean);
        const name = (title.textContent || text[0] || "").trim();
        if (!name || name.length > 120) continue;
        const locationLine = text.find((line) => line.includes(",")) || "";
        const priceCuisine = text.find((line) => /[??짜?㈑?+|쨌/.test(line)) || "";
        const [city = "", country = ""] = locationLine.split(",").map((value) => value.trim());
        const stars = card.querySelectorAll("img.michelin-award").length || null;
        cards.push({
          name,
          city,
          country,
          address: locationLine,
          place_url: href,
          price_cuisine: priceCuisine,
          stars,
        });
        seen.add(href);
      }
      const listedCards = rangeCount ? cards.slice(0, rangeCount) : cards;
      return { total, rangeCount, count: listedCards.length, cards: listedCards };
    });
    if (result.total) reportedTotal = result.total;
    pages.push({ page: pageNumber, url, count: result.count });
    if (!result.cards.length) break;
    for (const card of result.cards) {
      places.push({ ...card, rank: places.length + 1 });
    }
    if (reportedTotal && places.length >= reportedTotal) break;
  }
  await fs.promises.writeFile(
    outputPath,
    JSON.stringify({ reportedTotal, pages, places }, null, 2),
    "utf-8",
  );
  console.log(JSON.stringify({ ok: true, reportedTotal, pages: pages.length, places: places.length }));
} catch (error) {
  console.error(JSON.stringify({ ok: false, error: error.message }));
  process.exitCode = 1;
} finally {
  await context.close();
}
