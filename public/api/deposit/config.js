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
    platform_deposit_address: "0x66A06fA03BE98383fe4F73a5f1783332CAC0F5A0",
    min_deposit_usdt: 1.0,
    network: "BNB Smart Chain (BEP20)",
    chain_id: 56,
    usdt_contract: "0x55d398326f99059fF775485246999027B3197955",
    symbol: "USDT (BEP-20)",
    explorer_base: "https://bscscan.com"
  }, null, 2));
};
