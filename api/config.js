module.exports = function handler(_req, res) {
  const payload = {
    googleMapsApiKey: process.env.GOOGLE_PLACES_API_KEY || "",
  };
  res.setHeader("content-type", "application/javascript; charset=utf-8");
  res.setHeader("cache-control", "no-store");
  res.status(200).send(`window.STARWINE_CONFIG = ${JSON.stringify(payload)};`);
};
