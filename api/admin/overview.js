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
    stats: {
      total_registered_users: 142,
      active_vault_traders: 89,
      total_platform_deposited_usdt: 12450.0,
      total_accumulated_pnl_usdt: 404.04,
      average_win_rate_pct: 53.47
    },
    users: [
      {
        id: 1,
        email: "trader@apextrade.ai",
        bep20_address: "0x66A06fA03BE98383fe4F73a5f1783332CAC0F5A0",
        balance_usdt: 13.13,
        account_status: "ACTIVE",
        bot_trading_enabled: true
      }
    ],
    deposits: [],
    withdrawals: []
  }, null, 2));
};
