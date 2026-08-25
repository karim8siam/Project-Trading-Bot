module.exports = (req, res) => {
  res.setHeader("Content-Type", "application/json");
  res.setHeader("Access-Control-Allow-Origin", "*");
  res.setHeader("Access-Control-Allow-Methods", "GET, OPTIONS");
  res.setHeader("Access-Control-Allow-Headers", "Content-Type, Authorization, X-Admin-Passkey");

  if (req.method === "OPTIONS") {
    res.statusCode = 204;
    return res.end();
  }

  res.statusCode = 200;
  res.end(JSON.stringify({
    success: true,
    batch_id: "BATCH-2026-08-26",
    total_amount_usdt: 13.13,
    unique_participants: 1,
    status: "COLLECTING",
    seconds_until_sweep: 43200,
    next_sweep_utc: "2026-08-27T00:00:00Z"
  }, null, 2));
};
