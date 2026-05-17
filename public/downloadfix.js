(function () {
  pdfFallbackUrls = function pdfFallbackUrls(list = {}) {
    if (list.downloadUrl) return [];
    return [list.fileViewUrl, list.fileUrl, list.externalUrl, list.localFileUrl]
      .filter((url) => url && url !== pdfUrl(list));
  };
})();
