module.exports = (req, res) => {
  res.setHeader("Content-Type", "application/json");
  res.setHeader("Access-Control-Allow-Origin", "*");
  res.setHeader("Access-Control-Allow-Methods", "POST, OPTIONS");
  res.setHeader("Access-Control-Allow-Headers", "Content-Type, Authorization, X-Admin-Passkey");

  if (req.method === "OPTIONS") return res.status(204).end();

  const body = req.body || {};
  const email = (body.email || "trader@apextrade.ai").trim().toLowerCase();

  res.status(200).json({
    success: true,
    message: "Login successful.",
    token: "jwt_token_" + Date.now(),
    user: {
      id: 1,
      email: email,
      bep20_address: "0x66A06fA03BE98383fe4F73a5f1783332CAC0F5A0",
      balance_usdt: 13.13,
      account_status: "ACTIVE",
      bot_trading_enabled: true
    }
  });
};
