module.exports = function handler(_req, res) {
  res.setHeader("cache-control", "no-store");
  res.status(200).json({
    countries: [
      "Argentina",
      "Australia",
      "Austria",
      "Belgium",
      "Czech Republic",
      "Denmark",
      "France",
      "Germany",
      "Greater China",
      "Hong Kong",
      "Italy",
      "Netherlands",
      "Norway",
      "Singapore",
      "Spain",
      "Sweden",
      "UK",
      "USA",
      "Unknown"
    ],
    cities: [],
  });
};
