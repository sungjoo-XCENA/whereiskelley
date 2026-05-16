import("/public/app.js").catch((error) => {
  const results = document.querySelector("#results");
  if (results) {
    results.innerHTML = `<div class="empty-list"><h3>Load error</h3><p>${String(error.message || error)}</p></div>`;
  }
});
