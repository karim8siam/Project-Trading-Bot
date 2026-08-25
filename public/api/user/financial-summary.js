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
    summary: {
      user_id: 1,
      email: "trader@apextrade.ai",
      bep20_address: "0x66A06fA03BE98383fe4F73a5f1783332CAC0F5A0",
      balance_usdt: 13.13,
      account_status: "ACTIVE",
      bot_trading_enabled: true,
      auto_compound: true,
      total_deposited_usdt: 13.13,
      deposit_count: 1,
      total_profit_usdt: 4.82,
      total_loss_usdt: 1.20,
      net_pnl_usdt: 3.62,
      net_roi_pct: 27.5,
      total_system_fees_paid: 1.93,
      total_cycles_settled: 8,
      last_return_confirmation: {
        has_settlement: true,
        status: "SETTLED_24H_CYCLE",
        message: "Your capital settled the 24h trading cycle at 00:00 UTC with net profit +2.4%.",
        destination_bep20: "0x66A06fA03BE98383fe4F73a5f1783332CAC0F5A0"
      },
      daily_timeline: []
    }
  }, null, 2));
};
