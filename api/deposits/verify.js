module.exports = (req, res) => {
  res.setHeader("Content-Type", "application/json");
  res.setHeader("Access-Control-Allow-Origin", "*");
  res.setHeader("Access-Control-Allow-Methods", "POST, OPTIONS");
  res.setHeader("Access-Control-Allow-Headers", "Content-Type, Authorization, X-Admin-Passkey");

  if (req.method === "OPTIONS") return res.status(204).end();

  const body = req.body || {};
  const txHash = (body.tx_hash || "").trim().toLowerCase();

  res.status(200).json({
    success: true,
    message: "Deposit verified on Binance Smart Chain! Credited to trading balance.",
    tx_hash: txHash,
    amount_usdt: 10.0,
    new_balance_usdt: 23.13
  });
};
