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

  const email = (body.email || "newuser@apextrade.ai").trim().toLowerCase();
  const bep20 = (body.bep20_address || "0x66A06fA03BE98383fe4F73a5f1783332CAC0F5A0").trim().toLowerCase();

  res.statusCode = 201;
  res.end(JSON.stringify({
    success: true,
    message: "Account created successfully! Welcome to ApexTrade AI.",
    token: "jwt_token_" + Date.now(),
    user: {
      id: 1,
      email: email,
      bep20_address: bep20,
      balance_usdt: 0.0,
      account_status: "PENDING_DEPOSIT",
      bot_trading_enabled: false
    }
  }, null, 2));
};
