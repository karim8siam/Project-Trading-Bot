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
    user: {
      id: 1,
      email: "trader@apextrade.ai",
      bep20_address: "0x66A06fA03BE98383fe4F73a5f1783332CAC0F5A0",
      balance_usdt: 13.13,
      account_status: "ACTIVE",
      bot_trading_enabled: true,
      auto_compound: true
    }
  }, null, 2));
};
