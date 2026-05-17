(function () {
  pdfUrl = function pdfUrl(list = {}) {
    return list.fileViewUrl || list.fileUrl || list.localFileUrl || list.externalUrl || list.downloadUrl || "";
  };

  function proxiedPdfUrl(list = {}, filename = "") {
    const url = pdfUrl(list);
    if (!url) return "";
    const params = new URLSearchParams({
      url,
      fallbackUrls: pdfFallbackUrls(list).join("|"),
      filename: filename || `wine-list-${list.id || "download"}.pdf`
    });
    return `/api/pdf_file?${params.toString()}`;
  }

  pdfFallbackUrls = function pdfFallbackUrls(list = {}) {
    return [list.fileViewUrl, list.fileUrl, list.localFileUrl, list.externalUrl, list.downloadUrl]
      .filter((url) => url && url !== pdfUrl(list));
  };

  pdfMarkup = function pdfMarkup(list = {}) {
    const url = proxiedPdfUrl(list);
    if (!url) return `<span class="pdf-pill muted">No PDF</span>`;
    return `<a class="pdf-pill pdf-link" href="${escapeHtml(url)}">PDF</a>`;
  };

  pdfLinksMarkup = function pdfLinksMarkup(lists = []) {
    const validLists = lists.filter((list) => pdfUrl(list));
    return validLists
      .slice(0, 3)
      .map((list, index) => {
        const label = validLists.length === 1 ? "PDF" : `PDF ${index + 1}`;
        const url = proxiedPdfUrl(list);
        return `<a href="${escapeHtml(url)}">${escapeHtml(label)}</a>`;
      })
      .join("");
  };
})();
