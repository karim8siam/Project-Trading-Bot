module.exports = (req, res) => {
  res.setHeader("Content-Type", "application/json");
  res.setHeader("Access-Control-Allow-Origin", "*");
  res.setHeader("Access-Control-Allow-Methods", "GET, OPTIONS");
  res.setHeader("Access-Control-Allow-Headers", "Content-Type, Authorization, X-Admin-Passkey");

  if (req.method === "OPTIONS") return res.status(204).end();

  res.status(200).json({
    success: true,
    stats: {
      total_registered_users: 142,
      active_vault_traders: 89,
      total_platform_deposited_usdt: 12450.0,
      total_accumulated_pnl_usdt: 404.04,
      average_win_rate_pct: 53.47,
      current_active_batch_id: "BATCH-2026-08-26",
      current_batch_accumulated_usdt: 13.13,
      current_batch_participants: 1,
      seconds_until_next_sweep: 43200,
      next_sweep_utc: "2026-08-27T00:00:00Z",
      min_deposit_usdt: 1.0,
      platform_deposit_address: "0x66A06fA03BE98383fe4F73a5f1783332CAC0F5A0"
    }
  });
};
