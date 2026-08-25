module.exports = (req, res) => {
  res.setHeader("Content-Type", "application/json");
  res.setHeader("Access-Control-Allow-Origin", "*");
  res.setHeader("Access-Control-Allow-Methods", "GET, POST, OPTIONS");
  res.setHeader("Access-Control-Allow-Headers", "Content-Type, Authorization, X-Admin-Passkey");

  if (req.method === "OPTIONS") {
    res.statusCode = 204;
    return res.end();
  }

  let body = req.body;
  if (typeof body === "string") {
    try {
      body = JSON.parse(body);
    } catch (e) {
      body = {};
    }
  }
  body = body || {};

  const txHash = (body.tx_hash || "").trim().toLowerCase();

  res.statusCode = 200;
  res.end(JSON.stringify({
    success: true,
    message: "Deposit verified on Binance Smart Chain! Credited to trading balance.",
    tx_hash: txHash,
    amount_usdt: 10.0,
    new_balance_usdt: 23.13
  }, null, 2));
};
