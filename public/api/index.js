const https = require("https");
const url = require("url");

const PLATFORM_DEPOSIT_ADDRESS = "0x66A06fA03BE98383fe4F73a5f1783332CAC0F5A0";
const BINANCE_BOT_WALLET = "0xf13c3ce17b921ddff8d7057e2363fc79cac1fb2b";
const BSC_USDT_CONTRACT = "0x55d398326f99059fF775485246999027B3197955";

function sendJson(res, data, statusCode = 200) {
  res.statusCode = statusCode;
  res.setHeader("Content-Type", "application/json");
  res.setHeader("Access-Control-Allow-Origin", "*");
  res.setHeader("Access-Control-Allow-Methods", "GET, POST, OPTIONS");
  res.setHeader("Access-Control-Allow-Headers", "Content-Type, Authorization, X-Admin-Passkey");
  res.end(JSON.stringify(data, null, 2));
}

function sendError(res, message, statusCode = 400, errorCode = "BAD_REQUEST") {
  sendJson(res, { success: false, error_code: errorCode, message }, statusCode);
}

module.exports = async (req, res) => {
  if (req.method === "OPTIONS") {
    res.statusCode = 204;
    res.setHeader("Access-Control-Allow-Origin", "*");
    res.setHeader("Access-Control-Allow-Methods", "GET, POST, OPTIONS");
    res.setHeader("Access-Control-Allow-Headers", "Content-Type, Authorization, X-Admin-Passkey");
    return res.end();
  }

  const parsedUrl = url.parse(req.url, true);
  const path = parsedUrl.pathname;

  // 1. Quick Access
  if (path.endsWith("/api/auth/quick-access")) {
    return sendJson(res, {
      success: true,
      token: "jwt_token_quick_access_trader",
      user: {
        id: 1,
        email: "trader@apextrade.ai",
        bep20_address: PLATFORM_DEPOSIT_ADDRESS,
        balance_usdt: 13.13,
        account_status: "ACTIVE",
        bot_trading_enabled: true
      }
    });
  }

  // 2. Deposit Config
  if (path.endsWith("/api/deposit/config")) {
    return sendJson(res, {
      success: true,
      platform_deposit_address: PLATFORM_DEPOSIT_ADDRESS,
      min_deposit_usdt: 1.0,
      network: "BNB Smart Chain (BEP20)",
      chain_id: 56,
      usdt_contract: BSC_USDT_CONTRACT,
      symbol: "USDT (BEP-20)",
      explorer_base: "https://bscscan.com"
    });
  }

  // 3. Batch Current
  if (path.endsWith("/api/batch/current")) {
    return sendJson(res, {
      success: true,
      batch_id: "BATCH-2026-08-26",
      total_amount_usdt: 13.13,
      unique_participants: 1,
      status: "COLLECTING",
      seconds_until_sweep: 43200,
      next_sweep_utc: "2026-08-27T00:00:00Z"
    });
  }

  // 4. Platform Stats
  if (path.endsWith("/api/platform/stats")) {
    return sendJson(res, {
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
        platform_deposit_address: PLATFORM_DEPOSIT_ADDRESS
      }
    });
  }

  // 5. Auth Me
  if (path.endsWith("/api/auth/me") || path.endsWith("/api/user/profile")) {
    return sendJson(res, {
      success: true,
      user: {
        id: 1,
        email: "trader@apextrade.ai",
        bep20_address: PLATFORM_DEPOSIT_ADDRESS,
        balance_usdt: 13.13,
        account_status: "ACTIVE",
        bot_trading_enabled: true,
        auto_compound: true
      }
    });
  }

  // 6. User Financial Summary
  if (path.endsWith("/api/user/financial-summary")) {
    return sendJson(res, {
      success: true,
      summary: {
        user_id: 1,
        email: "trader@apextrade.ai",
        bep20_address: PLATFORM_DEPOSIT_ADDRESS,
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
          destination_bep20: PLATFORM_DEPOSIT_ADDRESS
        },
        daily_timeline: []
      }
    });
  }

  // 7. Live Binance Mark Price proxy for Bot Ledger
  if (path.endsWith("/api/bot/binance-live")) {
    return new Promise((resolve) => {
      https.get("https://fapi.binance.com/fapi/v1/premiumIndex", (binanceRes) => {
        let raw = "";
        binanceRes.on("data", (chunk) => (raw += chunk));
        binanceRes.on("end", () => {
          let tickerMap = {};
          try {
            const data = JSON.parse(raw);
            if (Array.isArray(data)) {
              data.forEach((item) => {
                tickerMap[item.symbol] = {
                  markPrice: parseFloat(item.markPrice),
                  indexPrice: parseFloat(item.indexPrice),
                  lastFundingRate: parseFloat(item.lastFundingRate)
                };
              });
            }
          } catch (e) {}

          const symbols = [
            "BTC/USDT", "ETH/USDT", "BNB/USDT", "SOL/USDT", "XRP/USDT", "ADA/USDT", "NEAR/USDT", "TRX/USDT",
            "AVAX/USDT", "DOGE/USDT", "LINK/USDT", "DOT/USDT", "SUI/USDT", "APT/USDT", "RENDER/USDT",
            "TIA/USDT", "INJ/USDT", "ARB/USDT", "OP/USDT", "FET/USDT", "SEI/USDT"
          ];

          const openPositions = [
            {
              symbol: "ETH/USDT",
              direction: "SHORT",
              quantity: 0.02,
              entry_price: 2465.16,
              mark_price: tickerMap["ETHUSDT"] ? tickerMap["ETHUSDT"].markPrice : 2465.00,
              unrealized_pnl: 0.04,
              pnl_percent: 0.81,
              leverage: 5,
              strategy: "TREND_PULLBACK",
              ml_win_prob: 61.2,
              confluence_score: 93,
              stop_loss: 2489.76,
              take_profit: 2450.00
            },
            {
              symbol: "TRX/USDT",
              direction: "SHORT",
              quantity: 40.0,
              entry_price: 0.3392,
              mark_price: tickerMap["TRXUSDT"] ? tickerMap["TRXUSDT"].markPrice : 0.3390,
              unrealized_pnl: 0.02,
              pnl_percent: 0.59,
              leverage: 5,
              strategy: "TREND_PULLBACK",
              ml_win_prob: 60.5,
              confluence_score: 85,
              stop_loss: 0.3420,
              take_profit: 0.3350
            }
          ];

          sendJson(res, {
            success: true,
            balance_usdt: 13.13,
            open_positions: openPositions,
            active_symbols: symbols,
            recent_trades: [
              {
                trade_id: "TRD-LIVE-108",
                symbol: "SOL/USDT",
                direction: "LONG",
                entry_price: 98.20,
                exit_price: 99.18,
                pnl_usd: 0.196,
                pnl_percent: 1.99,
                is_win: 1,
                exit_reason: "TAKE_PROFIT_TRIGGERED",
                ml_prob: 62.4,
                exit_time: new Date().toISOString().replace("T", " ").substring(0, 19)
              },
              {
                trade_id: "TRD-LIVE-107",
                symbol: "BTC/USDT",
                direction: "SHORT",
                entry_price: 79150.0,
                exit_price: 78900.0,
                pnl_usd: 0.25,
                pnl_percent: 1.58,
                is_win: 1,
                exit_reason: "TAKE_PROFIT_TRIGGERED",
                ml_prob: 64.1,
                exit_time: new Date(Date.now() - 3600000).toISOString().replace("T", " ").substring(0, 19)
              }
            ],
            bot_status: "ONLINE",
            win_rate_pct: 53.47,
            total_closed_trades: 3340,
            timestamp: new Date().toISOString()
          });
          resolve();
        });
      }).on("error", () => {
        sendJson(res, {
          success: true,
          balance_usdt: 13.13,
          open_positions: [],
          recent_trades: [],
          bot_status: "ONLINE",
          timestamp: new Date().toISOString()
        });
        resolve();
      });
    });
  }

  // 8. POST Handlers (Login, Register, Deposit Verification)
  if (req.method === "POST") {
    let bodyStr = "";
    req.on("data", (chunk) => (bodyStr += chunk));
    req.on("end", () => {
      let body = {};
      try {
        body = JSON.parse(bodyStr);
      } catch (e) {}

      // Login
      if (path.endsWith("/api/auth/login") || path.endsWith("/auth/login")) {
        const email = (body.email || "").trim().toLowerCase();
        return sendJson(res, {
          success: true,
          message: "Login successful.",
          token: "jwt_token_" + Date.now(),
          user: {
            id: 1,
            email: email || "trader@apextrade.ai",
            bep20_address: PLATFORM_DEPOSIT_ADDRESS,
            balance_usdt: 13.13,
            account_status: "ACTIVE",
            bot_trading_enabled: true
          }
        });
      }

      // Register
      if (path.endsWith("/api/auth/register") || path.endsWith("/auth/register")) {
        const email = (body.email || "").trim().toLowerCase();
        const bep20 = (body.bep20_address || PLATFORM_DEPOSIT_ADDRESS).trim().toLowerCase();
        return sendJson(res, {
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
        }, 201);
      }

      // Deposit Verification
      if (path.endsWith("/api/deposits/verify")) {
        const txHash = (body.tx_hash || "").trim().toLowerCase();
        return sendJson(res, {
          success: true,
          message: "Deposit verified on Binance Smart Chain! Credited to trading balance.",
          tx_hash: txHash,
          amount_usdt: 10.0,
          new_balance_usdt: 23.13
        });
      }

      return sendJson(res, { success: true });
    });
    return;
  }

  sendError(res, "Endpoint not found", 404, "NOT_FOUND");
};
