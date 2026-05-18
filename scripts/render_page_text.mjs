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

const url = process.argv[2];
if (!url) {
  console.error("Usage: node scripts/render_page_text.mjs <url>");
  process.exit(2);
}

const browserCandidates = [
  "C:\\Program Files\\Google\\Chrome\\Application\\chrome.exe",
  "C:\\Program Files (x86)\\Google\\Chrome\\Application\\chrome.exe",
  "C:\\Program Files\\Microsoft\\Edge\\Application\\msedge.exe",
  "C:\\Program Files (x86)\\Microsoft\\Edge\\Application\\msedge.exe"
];
const executablePath = browserCandidates.find((candidate) => fs.existsSync(candidate));
const browser = await chromium.launch({
  executablePath,
  headless: process.env.SWL_HEADED === "1" ? false : true
});
try {
  const page = await browser.newPage({
    userAgent:
      "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124 Safari/537.36"
  });
  await page.goto(url, { waitUntil: "domcontentloaded", timeout: 20000 });
  try {
    await page.waitForLoadState("networkidle", { timeout: 8000 });
  } catch {}
  await page.waitForTimeout(1200);
  const chunks = [];
  const firstText = await page.evaluate(() => document.body ? document.body.innerText : "");
  chunks.push(firstText);
  const labels = await page.evaluate(() =>
    Array.from(document.querySelectorAll("a,button,[role='button'],[tabindex]"))
      .map((element, index) => ({ index, text: (element.innerText || element.textContent || "").trim() }))
      .filter((item) => /wine|wines|champagne|sparkling|cellar|red|white|rose|ros[eé]|vin|vins|wein|vino|vini|wijn|vinkort|drink/i.test(item.text))
      .slice(0, 18)
  );
  for (const item of labels) {
    try {
      await page.evaluate((index) => {
        const elements = Array.from(document.querySelectorAll("a,button,[role='button'],[tabindex]"));
        const element = elements[index];
        if (element) element.click();
      }, item.index);
      await page.waitForTimeout(900);
      const text = await page.evaluate(() => document.body ? document.body.innerText : "");
      chunks.push(text);
    } catch {}
  }
  const text = Array.from(new Set(chunks.filter(Boolean))).join("\n");
  process.stdout.write(JSON.stringify({ ok: true, url: page.url(), text }));
} catch (error) {
  process.stdout.write(JSON.stringify({ ok: false, error: error.message || String(error) }));
  process.exitCode = 1;
} finally {
  await browser.close();
}
