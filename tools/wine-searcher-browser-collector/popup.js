const fields = {
  endpoint: document.querySelector("#endpoint"),
  password: document.querySelector("#password"),
  start: document.querySelector("#start"),
  end: document.querySelector("#end"),
  delay: document.querySelector("#delay"),
  startButton: document.querySelector("#startButton"),
  resumeButton: document.querySelector("#resumeButton"),
  stopButton: document.querySelector("#stopButton"),
  status: document.querySelector("#status"),
  current: document.querySelector("#current"),
  checked: document.querySelector("#checked"),
  saved: document.querySelector("#saved"),
  missing: document.querySelector("#missing"),
  errors: document.querySelector("#errors"),
  message: document.querySelector("#message")
};

function endpointOrigin(value) {
  const parsed = new URL(value);
  return `${parsed.protocol}//${parsed.host}/*`;
}

async function state() {
  return chrome.runtime.sendMessage({ type: "state" });
}

function render(value = {}) {
  fields.status.textContent = value.status || "Ready";
  fields.current.textContent = value.currentId || "-";
  fields.checked.textContent = Number(value.checked || 0).toLocaleString();
  fields.saved.textContent = Number(value.saved || 0).toLocaleString();
  fields.missing.textContent = Number(value.missing || 0).toLocaleString();
  fields.errors.textContent = Number(value.errors || 0).toLocaleString();
  fields.message.textContent = value.message || "Ready.";
  fields.message.classList.toggle("warn", value.status === "Waiting for verification" || value.status === "Paused");
  fields.startButton.disabled = Boolean(value.running);
  fields.stopButton.disabled = !value.running;
  fields.resumeButton.hidden = !value.waitingForVerification;
  if (value.endpoint) fields.endpoint.value = value.endpoint;
  if (value.startId) fields.start.value = value.startId;
  if (value.endId) fields.end.value = value.endId;
  if (value.delayMs) fields.delay.value = value.delayMs;
}

fields.startButton.addEventListener("click", async () => {
  try {
    const endpoint = fields.endpoint.value.trim().replace(/\/+$/, "");
    const password = fields.password.value;
    const startId = Number(fields.start.value);
    const endId = Number(fields.end.value);
    const delayMs = Number(fields.delay.value);
    if (!endpoint || !password) throw new Error("Server address and admin password are required.");
    if (!Number.isInteger(startId) || !Number.isInteger(endId) || startId < 2 || endId > 239995 || startId > endId) {
      throw new Error("Use a valid ID range between 2 and 239995.");
    }
    const granted = await chrome.permissions.request({ origins: [endpointOrigin(endpoint)] });
    if (!granted) throw new Error("Server access permission was not granted.");
    render(await chrome.runtime.sendMessage({
      type: "start", endpoint, password, startId, endId, delayMs
    }));
    fields.password.value = "";
  } catch (error) {
    render({ ...(await state()), status: "Paused", message: error.message });
  }
});

fields.stopButton.addEventListener("click", async () => render(await chrome.runtime.sendMessage({ type: "stop" })));
fields.resumeButton.addEventListener("click", async () => render(await chrome.runtime.sendMessage({ type: "resume" })));

state().then(render);
setInterval(() => state().then(render).catch(() => {}), 1000);
