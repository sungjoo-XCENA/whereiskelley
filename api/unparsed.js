module.exports = function handler(_req, res) {
  res.setHeader("cache-control", "no-store");
  res.status(200).json({
    count: 0,
    items: [],
    listReviewCount: 0,
    priceReviewCount: 0,
  });
};
