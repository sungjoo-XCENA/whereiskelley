const STATE_KEY = "whereIsKelleyMerchantCollector";
const SECRET_KEY = "whereIsKelleyCollectorPassword";
let processing = false;
let navigationTimer = null;

const initialState = {
  running: false,
  waitingForVerification: false,
  status: "Ready",
  message: "Ready.",
  endpoint: "http://168.107.35.204",
  startId: 2,
  endId: 239995,
  currentId: 0,
  delayMs: 2000,
  checked: 0,
  saved: 0,
  missing: 0,
  errors: 0,
  tabId: null
};

async function getState() {
  const stored = await chrome.storage.local.get(STATE_KEY);
  return { ...initialState, ...(stored[STATE_KEY] || {}) };
}

async function setState(patch) {
  const next = { ...(await getState()), ...patch };
  await chrome.storage.local.set({ [STATE_KEY]: next });
  return next;
}

function merchantUrl(id) {
  return `https://www.wine-searcher.com/merchant/${id}`;
}

async function extractPage(tabId) {
  const results = await chrome.scripting.executeScript({
    target: { tabId },
    func: () => ({
      html: document.documentElement?.outerHTML || "",
      text: document.body?.innerText || "",
      title: document.title || "",
      finalUrl: location.href
    })
  });
  return results[0]?.result || {};
}

function visiblyBlocked(page) {
  const visible = `${page.title || ""}\n${page.text || ""}`.toLowerCase();
  const visibleChallenge = [
    "press and hold", "prove you are human", "verify you are human", "human verification",
    "로봇이 아니라 사람", "길게 눌러"
  ].some((marker) => visible.includes(marker));
  const challengeFrame = visible.trim().length < 800
    && ["px-captcha", "perimeterx"].some((marker) => (page.html || "").toLowerCase().includes(marker));
  return visibleChallenge || challengeFrame;
}

async function sign(password, timestamp, merchantId, html) {
  const encoder = new TextEncoder();
  const digest = await crypto.subtle.digest("SHA-256", encoder.encode(html));
  const digestHex = [...new Uint8Array(digest)].map((byte) => byte.toString(16).padStart(2, "0")).join("");
  const key = await crypto.subtle.importKey(
    "raw", encoder.encode(password), { name: "HMAC", hash: "SHA-256" }, false, ["sign"]
  );
  const signature = await crypto.subtle.sign(
    "HMAC", key, encoder.encode(`${timestamp}\n${merchantId}\n${digestHex}`)
  );
  return [...new Uint8Array(signature)].map((byte) => byte.toString(16).padStart(2, "0")).join("");
}

async function pauseForVerification(message) {
  return setState({
    running: true,
    waitingForVerification: true,
    status: "Waiting for verification",
    message: message || "Hold the verification button in the collector tab, then click Resume after verification."
  });
}

async function postPage(state, page) {
  const secret = await chrome.storage.session.get(SECRET_KEY);
  const password = secret[SECRET_KEY] || "";
  if (!password) throw new Error("The admin password session expired. Stop and start the collector again.");
  const timestamp = String(Math.floor(Date.now() / 1000));
  const signature = await sign(password, timestamp, state.currentId, page.html);
  const response = await fetch(`${state.endpoint}/api/shop-browser-import`, {
    method: "POST",
    headers: {
      "content-type": "application/json",
      "x-whereiskelley-timestamp": timestamp,
      "x-whereiskelley-signature": signature
    },
    body: JSON.stringify({
      merchantId: state.currentId,
      finalUrl: page.finalUrl,
      html: page.html,
      progress: {
        checked: state.checked + 1,
        total: state.endId - state.startId + 1,
        saved: state.saved,
        errors: state.errors,
        complete: state.currentId >= state.endId
      }
    })
  });
  let payload = {};
  try { payload = await response.json(); } catch (_error) { /* handled below */ }
  if (response.status === 409 && payload.status === "verification_required") {
    await pauseForVerification(payload.error);
    return null;
  }
  if (!response.ok) throw new Error(payload.error || `Server returned HTTP ${response.status}.`);
  return payload;
}

async function navigateNext(state) {
  const nextId = state.currentId + 1;
  if (nextId > state.endId) {
    await setState({
      running: false,
      waitingForVerification: false,
      status: "Complete",
      message: `Completed ${state.checked.toLocaleString()} merchant IDs.`
    });
    return;
  }
  const next = await setState({ currentId: nextId, status: "Collecting", message: `Loading merchant ${nextId}...` });
  clearTimeout(navigationTimer);
  navigationTimer = setTimeout(() => {
    chrome.tabs.update(next.tabId, { url: merchantUrl(nextId) }).catch(async (error) => {
      await setState({ running: false, status: "Paused", message: error.message });
    });
  }, next.delayMs);
}

async function processCurrentPage(tabId) {
  if (processing) return;
  const state = await getState();
  if (!state.running || state.waitingForVerification || tabId !== state.tabId) return;
  processing = true;
  try {
    const page = await extractPage(tabId);
    if (visiblyBlocked(page)) {
      await pauseForVerification();
      return;
    }
    const result = await postPage(state, page);
    if (!result) return;
    const next = await setState({
      checked: state.checked + 1,
      saved: state.saved + (result.saved ? 1 : 0),
      missing: state.missing + (result.status === "missing" ? 1 : 0),
      errors: state.errors + (result.status === "error" ? 1 : 0),
      status: "Collecting",
      message: result.saved
        ? `Saved ${result.name || `merchant ${state.currentId}`}.`
        : `Merchant ${state.currentId}: ${result.status}.`
    });
    await navigateNext(next);
  } catch (error) {
    await setState({
      running: false,
      waitingForVerification: false,
      status: "Paused",
      message: error.message
    });
  } finally {
    processing = false;
  }
}

chrome.tabs.onUpdated.addListener((tabId, changeInfo) => {
  if (changeInfo.status === "complete") setTimeout(() => processCurrentPage(tabId), 900);
});

chrome.tabs.onRemoved.addListener(async (tabId) => {
  const state = await getState();
  if (state.running && state.tabId === tabId) {
    await setState({ running: false, status: "Paused", message: "The collector tab was closed." });
  }
});

chrome.runtime.onMessage.addListener((message, _sender, sendResponse) => {
  (async () => {
    if (message.type === "state") return getState();
    if (message.type === "stop") {
      clearTimeout(navigationTimer);
      return setState({ running: false, waitingForVerification: false, status: "Stopped", message: "Collection stopped." });
    }
    if (message.type === "resume") {
      const state = await setState({ waitingForVerification: false, running: true, status: "Collecting", message: "Checking the verified page..." });
      setTimeout(() => processCurrentPage(state.tabId), 300);
      return state;
    }
    if (message.type === "start") {
      await chrome.storage.session.set({ [SECRET_KEY]: message.password });
      const tabs = await chrome.tabs.create({ url: merchantUrl(message.startId), active: true });
      return setState({
        ...initialState,
        running: true,
        status: "Collecting",
        message: `Loading merchant ${message.startId}...`,
        endpoint: message.endpoint,
        startId: message.startId,
        endId: message.endId,
        currentId: message.startId,
        delayMs: Math.max(1200, Number(message.delayMs) || 2000),
        tabId: tabs.id
      });
    }
    return getState();
  })().then(sendResponse).catch((error) => sendResponse({ status: "Paused", message: error.message }));
  return true;
});
