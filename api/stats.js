module.exports = function handler(_req, res) {
  res.setHeader("cache-control", "no-store");
  res.status(200).json({
    countryCount: "Live",
    cityCount: "-",
    venueCount: "API",
    wineListCount: "-",
    entryCount: "-",
    lastRun: null,
  });
};
