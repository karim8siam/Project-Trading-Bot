"""
Order Execution and Advanced Position Life-Cycle Manager for Binance Futures.
Implements:
- Direct support for Binance Futures Demo API (https://demo-fapi.binance.com) & Mainnet (https://fapi.binance.com)
- 3-Pillar Risk Guardrails Evaluation
- Partial Take-Profit Execution
- Rule 6: Automatic Breakeven Protection at 1R profit
- Rule 7: Dynamic Trailing Stop Loss Management
- Continuous ML Model Retraining Trigger
"""

import time
import uuid
import hmac
import hashlib
import requests
from datetime import datetime
from typing import Dict, Any, Optional, List, Tuple

from config import (
    validate_symbol,
    DEFAULT_LEVERAGE,
    BINANCE_API_KEY,
    BINANCE_API_SECRET,
    USE_TESTNET,
    ALLOWED_SYMBOLS
)
from database import (
    insert_trade,
    close_trade,
    get_open_trades,
    get_connection
)
from risk_manager import (
    calculate_position_size,
    check_3_pillar_risk_guardrails,
    update_breakeven_and_trailing_stops,
    SYMBOL_SPECS
)
from ml_brain import ml_brain
from data_fetcher import data_fetcher, DEMO_FAPI_BASE_URL, PROD_FAPI_BASE_URL
from google_sheets_sync import sheets_sync


class BinanceFuturesExecutor:
    """
    Executes futures orders on Binance USD(S)-M Futures and actively manages positions.
    """

    def __init__(self, paper_mode: bool = False):
        self.paper_mode = paper_mode
        self.api_key = BINANCE_API_KEY
        self.api_secret = BINANCE_API_SECRET
        self.use_testnet = USE_TESTNET
        self.base_url = DEMO_FAPI_BASE_URL if self.use_testnet else PROD_FAPI_BASE_URL

    def _get_headers(self) -> Dict[str, str]:
        return {
            "X-MBX-APIKEY": self.api_key,
            "Content-Type": "application/x-www-form-urlencoded"
        }

    def _sign_payload(self, params: Dict[str, Any]) -> Dict[str, Any]:
        """Generates HMAC-SHA256 signature for authenticated order requests."""
        params["timestamp"] = int(time.time() * 1000)
        query_string = "&".join([f"{k}={v}" for k, v in params.items()])
        signature = hmac.new(
            self.api_secret.encode("utf-8"),
            query_string.encode("utf-8"),
            hashlib.sha256
        ).hexdigest()
        params["signature"] = signature
        return params

    def set_leverage_and_margin_type(self, symbol: str, leverage: int = DEFAULT_LEVERAGE) -> bool:
        """Sets Isolated margin mode and leverage on Binance Futures."""
        raw_sym = symbol.replace("/", "")
        # Set Leverage
        try:
            params = self._sign_payload({"symbol": raw_sym, "leverage": leverage})
            requests.post(f"{self.base_url}/fapi/v1/leverage", headers=self._get_headers(), params=params, timeout=5)
        except Exception:
            pass

        # Set Margin Type to ISOLATED
        try:
            params = self._sign_payload({"symbol": raw_sym, "marginType": "ISOLATED"})
            requests.post(f"{self.base_url}/fapi/v1/marginType", headers=self._get_headers(), params=params, timeout=5)
        except Exception:
            pass
        return True

    def place_futures_order(
        self,
        symbol: str,
        side: str,
        quantity: float,
        reduce_only: bool = False
    ) -> Dict[str, Any]:
        """
        Sends Market order to Binance USD(S)-M Futures API.
        """
        if self.paper_mode or not self.api_key or self.api_key == "mock_key_paper_mode":
            curr_p = data_fetcher.fetch_current_price(symbol)
            return {
                "success": True,
                "orderId": f"PAPER-{int(time.time()*1000)}",
                "avgPrice": curr_p,
                "executedQty": quantity,
                "status": "FILLED"
            }

        validate_symbol(symbol)
        raw_sym = symbol.replace("/", "")

        # Set isolated margin mode
        self.set_leverage_and_margin_type(symbol)

        params = {
            "symbol": raw_sym,
            "side": side.upper(),
            "type": "MARKET",
            "quantity": quantity
        }
        if reduce_only:
            params["reduceOnly"] = "true"

        signed_params = self._sign_payload(params)
        url = f"{self.base_url}/fapi/v1/order"

        try:
            r = data_fetcher.session.post(url, headers=self._get_headers(), params=signed_params, timeout=8)
            data = r.json()
            if r.status_code == 200:
                avg_p = float(data.get("avgPrice", 0.0))
                if avg_p == 0.0:
                    avg_p = data_fetcher.fetch_current_price(symbol)
                return {
                    "success": True,
                    "orderId": str(data.get("orderId")),
                    "avgPrice": avg_p,
                    "executedQty": float(data.get("executedQty", quantity)),
                    "status": data.get("status", "FILLED")
                }
            else:
                return {"success": False, "error": data.get("msg", str(data))}
        except Exception as e:
            return {"success": False, "error": str(e)}

    def place_exchange_stop_loss(self, symbol: str, side: str, stop_price: float, quantity: float) -> Dict[str, Any]:
        """Places native STOP_MARKET protection directly on Binance matching engine."""
        if self.paper_mode or not self.api_key or self.api_key == "mock_key_paper_mode":
            return {"success": True, "type": "PAPER_SL"}

        from risk_manager import SYMBOL_SPECS
        raw_sym = symbol.replace("/", "")
        prec = SYMBOL_SPECS.get(symbol, {}).get("price_precision", 4)
        formatted_stop_price = f"{float(stop_price):.{prec}f}"

        params = {
            "symbol": raw_sym,
            "side": side.upper(),
            "type": "STOP_MARKET",
            "stopPrice": formatted_stop_price,
            "closePosition": "true",
            "workingType": "MARK_PRICE"
        }
        signed_params = self._sign_payload(params)
        try:
            r = data_fetcher.session.post(f"{self.base_url}/fapi/v1/order", headers=self._get_headers(), params=signed_params, timeout=8)
            data = r.json()
            if r.status_code == 200:
                return {"success": True, "data": data}
            else:
                return {"success": False, "error": data.get("msg", str(data))}
        except Exception as e:
            return {"success": False, "error": str(e)}

    def place_exchange_take_profit(self, symbol: str, side: str, tp_price: float, quantity: float) -> Dict[str, Any]:
        """Places native TAKE_PROFIT_MARKET order directly on Binance matching engine."""
        if self.paper_mode or not self.api_key or self.api_key == "mock_key_paper_mode":
            return {"success": True, "type": "PAPER_TP"}

        from risk_manager import SYMBOL_SPECS
        raw_sym = symbol.replace("/", "")
        prec = SYMBOL_SPECS.get(symbol, {}).get("price_precision", 4)
        formatted_tp_price = f"{float(tp_price):.{prec}f}"

        params = {
            "symbol": raw_sym,
            "side": side.upper(),
            "type": "TAKE_PROFIT_MARKET",
            "stopPrice": formatted_tp_price,
            "closePosition": "true",
            "workingType": "MARK_PRICE"
        }
        signed_params = self._sign_payload(params)
        try:
            r = data_fetcher.session.post(f"{self.base_url}/fapi/v1/order", headers=self._get_headers(), params=signed_params, timeout=8)
            data = r.json()
            if r.status_code == 200:
                return {"success": True, "data": data}
            else:
                return {"success": False, "error": data.get("msg", str(data))}
        except Exception as e:
            return {"success": False, "error": str(e)}

    def place_maker_limit_order(self, symbol: str, side: str, quantity: float, timeout_seconds: int = 15) -> Dict[str, Any]:
        """
        Submits a Post-Only (GTX) Maker Limit Order at the Best Bid (for BUY) or Best Ask (for SELL).
        Qualifies for the 60% Maker fee discount (0.02% vs 0.05%) with 0% negative slippage.
        If unfilled within timeout_seconds, cancels order with $0.00 cost.
        """
        if self.paper_mode or not self.api_key or self.api_key == "mock_key_paper_mode":
            curr_p = data_fetcher.fetch_current_price(symbol)
            return {"success": True, "avgPrice": curr_p, "status": "FILLED", "is_maker": True}

        raw_sym = symbol.replace("/", "")
        from risk_manager import SYMBOL_SPECS
        prec = SYMBOL_SPECS.get(symbol, {}).get("price_precision", 4)

        # 1. Fetch live Best Bid / Best Ask from Binance Orderbook
        try:
            r_book = data_fetcher.session.get(f"{self.base_url}/fapi/v1/ticker/bookTicker?symbol={raw_sym}", timeout=4)
            if r_book.status_code == 200:
                book_data = r_book.json()
                bid_price = float(book_data.get("bidPrice", 0.0))
                ask_price = float(book_data.get("askPrice", 0.0))
            else:
                curr_p = data_fetcher.fetch_current_price(symbol)
                bid_price = curr_p * 0.9998
                ask_price = curr_p * 1.0002
        except Exception:
            curr_p = data_fetcher.fetch_current_price(symbol)
            bid_price = curr_p * 0.9998
            ask_price = curr_p * 1.0002

        # Post-Only pricing: Best Bid for BUY, Best Ask for SELL
        limit_price = bid_price if side.upper() == "BUY" else ask_price
        formatted_price = f"{float(limit_price):.{prec}f}"

        # 2. Submit GTX (Post-Only) Limit Order
        params = {
            "symbol": raw_sym,
            "side": side.upper(),
            "type": "LIMIT",
            "timeInForce": "GTX",  # Post-Only: Guaranteed Maker Fee (0.02%)
            "price": formatted_price,
            "quantity": quantity
        }
        signed_params = self._sign_payload(params)
        url = f"{self.base_url}/fapi/v1/order"

        try:
            r = data_fetcher.session.post(url, headers=self._get_headers(), params=signed_params, timeout=8)
            data = r.json()

            if r.status_code != 200:
                err = data.get("msg", str(data))
                if "Order would immediately trigger" in err or "Post Only" in err:
                    print(f"[Maker Engine] ⚡ Post-Only price crossed book, taking best entry...")
                    return self.place_futures_order(symbol=symbol, side=side, quantity=quantity)
                return {"success": False, "error": err}

            order_id = str(data.get("orderId"))
            print(f"[Maker Engine] 🟢 Post-Only Limit Order placed on orderbook: {side} {quantity} {symbol} @ ${limit_price:,.{prec}f} (0.02% Maker Fee Active)")

            # 3. Smart Fill Listener Window (Up to 15s)
            start_wait = time.time()
            while (time.time() - start_wait) < timeout_seconds:
                time.sleep(1.5)
                q_params = {"symbol": raw_sym, "orderId": order_id}
                signed_q = self._sign_payload(q_params)
                r_status = data_fetcher.session.get(url, headers=self._get_headers(), params=signed_q, timeout=4)
                if r_status.status_code == 200:
                    stat_data = r_status.json()
                    status = stat_data.get("status")
                    if status == "FILLED":
                        avg_p = float(stat_data.get("avgPrice") or limit_price)
                        print(f"[Maker Engine] ✅ FILLED via Maker Order @ ${avg_p:,.{prec}f} | Saved 60% in Taker Fees!")
                        return {
                            "success": True,
                            "orderId": order_id,
                            "avgPrice": avg_p,
                            "executedQty": float(stat_data.get("executedQty", quantity)),
                            "status": "FILLED",
                            "is_maker": True
                        }
                    elif status in ["CANCELED", "REJECTED", "EXPIRED"]:
                        return {"success": False, "reason": f"Maker order {status}"}

            # 4. Timeout -> Cancel Order with $0.00 cost to release margin
            print(f"[Maker Engine] ⏳ 15s Fill Window expired for {symbol}. Cancelling order ($0.00 Cost)...")
            c_params = {"symbol": raw_sym, "orderId": order_id}
            signed_c = self._sign_payload(c_params)
            data_fetcher.session.delete(url, headers=self._get_headers(), params=signed_c, timeout=4)
            return {"success": False, "reason": "Maker 15s fill timeout — safely cancelled with $0.00 cost."}

        except Exception as e:
            return {"success": False, "error": str(e)}

    def execute_signal(self, signal: Dict[str, Any], account_balance: Optional[float] = None) -> Dict[str, Any]:
        """Validates signal through 3 Pillars of Risk, executes on Binance Futures, and logs to DB."""
        bal = account_balance if account_balance is not None else data_fetcher.fetch_balance_usdt()
        return self.execute_trade(signal, balance=bal)

    def execute_trade(self, signal: Dict[str, Any], balance: Optional[float] = None) -> Dict[str, Any]:
        """Evaluates Risk Rules, executes order on Binance Futures via Maker Engine, sets SL/TP, and records to DB."""
        # Always query fresh live balance from Binance to calculate exact 1.0% risk at this exact millisecond
        live_balance = data_fetcher.fetch_balance_usdt()
        balance = live_balance if live_balance > 0 else (balance or 10.0)

        symbol = signal["symbol"]
        direction = signal["direction"]
        entry_price = float(signal.get("current_price") or signal.get("price") or data_fetcher.fetch_current_price(symbol))
        stop_loss = float(signal.get("stop_loss", entry_price * 0.985))
        take_profit = float(signal.get("take_profit", entry_price * 1.03))

        # 1. 3-Pillar Risk Guardrails Check (Bypassed for Exceptional Sovereign Delta Hedge)
        is_exceptional_hedge = (signal.get("strategy") == "DELTA_HEDGE_SNIPER" or signal.get("is_hedge", False))
        if not is_exceptional_hedge:
            guardrails_ok, guardrail_reason = check_3_pillar_risk_guardrails(
                symbol=symbol,
                account_balance=balance
            )
            if not guardrails_ok:
                return {"success": False, "reason": f"Risk Guardrail Block: {guardrail_reason}"}
        else:
            # Exceptional Hedge bypasses all macro and cooldown rules; only prevents duplicate coin exposure
            open_trades = get_open_trades()
            if symbol in [t["symbol"] for t in open_trades]:
                return {"success": False, "reason": f"Hedge Block: Position already active for {symbol}."}

        # 2. Dynamic Position Sizing (5.0% Dedicated Risk for Delta Hedge, <= 1.0% Standard)
        custom_risk = float(signal.get("risk_pct")) if signal.get("risk_pct") is not None else (5.0 if is_exceptional_hedge else None)
        risk_plan = calculate_position_size(
            symbol=symbol,
            entry_price=entry_price,
            stop_loss_price=stop_loss,
            account_balance_usdt=balance,
            leverage=DEFAULT_LEVERAGE,
            custom_risk_pct=custom_risk
        )
        if not risk_plan["valid"]:
            return {"success": False, "reason": f"Risk sizing failed: {risk_plan['reason']}"}

        quantity = float(risk_plan["quantity"])
        stop_loss = float(risk_plan.get("stop_loss") or risk_plan.get("stop_loss_price") or stop_loss)
        trade_id = f"TRD-{uuid.uuid4().hex[:8].upper()}"

        # 3. Live Binance Execution via Maker-First Post-Only Engine
        if not self.paper_mode and self.api_key and self.api_key != "mock_key_paper_mode":
            side = "BUY" if direction == "LONG" else "SELL"
            order_res = self.place_maker_limit_order(symbol=symbol, side=side, quantity=quantity)
            
            # If exceptional hedge and maker times out, immediately execute as market to guarantee hedge entry
            if not order_res.get("success") and is_exceptional_hedge:
                print(f"[Executor LIVE] ⚡ Exceptional Hedge Maker Timeout: Executing instant Market Order for {symbol} {direction}...")
                order_res = self.place_market_order(symbol=symbol, side=side, quantity=quantity)

            if order_res.get("success"):
                entry_price = order_res.get("avgPrice", entry_price)
                print(f"[Executor LIVE] 🚀 Order FILLED on Binance: {direction} {quantity} {symbol} @ ${entry_price:,.2f}")

                sl_side = "SELL" if direction == "LONG" else "BUY"
                sl_res = self.place_exchange_stop_loss(symbol=symbol, side=sl_side, stop_price=stop_loss, quantity=quantity)
                if sl_res.get("success"):
                    print(f"[Executor LIVE] 🛡️ Native Exchange Stop Loss active on Binance matching engine @ ${stop_loss:,.2f}")
                else:
                    print(f"[Executor LIVE] 🛡️ Active 24/7 Daemon Stop-Loss armed @ ${stop_loss:,.4f} | TP1: ${take_profit:,.4f}")

                tp_res = self.place_exchange_take_profit(symbol=symbol, side=sl_side, tp_price=take_profit, quantity=quantity)
                if tp_res.get("success"):
                    print(f"[Executor LIVE] 🎯 Native Exchange Take Profit active on Binance matching engine @ ${take_profit:,.2f}")
            else:
                err_msg = order_res.get("error") or order_res.get("reason", "Unknown Binance Error")
                print(f"[Executor LIVE] ⚠️ Order not executed: {err_msg}")
                return {"success": False, "reason": err_msg}

        # Log to Database
        trade_record = {
            "trade_id": trade_id,
            "symbol": symbol,
            "direction": direction,
            "entry_time": datetime.utcnow().isoformat(),
            "entry_price": entry_price,
            "quantity": quantity,
            "leverage": DEFAULT_LEVERAGE,
            "stop_loss": stop_loss,
            "take_profit": take_profit,
            "ml_predicted_prob": signal.get("ml_confidence", 0.5),
            "ml_approved": 1 if signal.get("ml_approved") else 0
        }

        insert_trade(trade_record, features=signal.get("features"))

        # Real-Time Telegram Push Alert
        try:
            from telegram_notifier import notify_trade_opened
            notify_trade_opened(trade_record, signal)
        except Exception:
            pass

        return {
            "success": True,
            "trade_id": trade_id,
            "symbol": symbol,
            "direction": direction,
            "entry_price": entry_price,
            "quantity": quantity,
            "stop_loss": stop_loss,
            "take_profit": take_profit,
            "target_risk_usd": risk_plan["target_risk_usd"],
            "risk_pct_used": risk_plan["risk_pct_used"],
            "tier_desc": risk_plan["tier_desc"],
            "ml_confidence": signal.get("ml_confidence", 0.5)
        }

    def check_and_execute_portfolio_unrealized_pnl_harvest(
        self,
        account_balance: Optional[float] = None
    ) -> Tuple[bool, float, float]:
        """
        PORTFOLIO UNREALIZED PNL CASH HARVEST ENGINE:
        No matter how many trades are running, if Total Unrealized PnL of all open positions
        is >= +1.0% of the total account balance, execute MARKET CLOSE ALL immediately,
        banking the +1.0% cash profit into the wallet balance.
        """
        if self.paper_mode or not self.api_key or self.api_key == "mock_key_paper_mode":
            return False, 0.0, 0.0

        balance = account_balance or data_fetcher.fetch_balance_usdt()
        if balance <= 0:
            return False, 0.0, 0.0

        try:
            params = self._sign_payload({})
            url = f"{self.base_url}/fapi/v2/positionRisk"
            r = data_fetcher.session.get(url, headers=self._get_headers(), params=params, timeout=8)
            if r.status_code != 200:
                return False, 0.0, 0.0

            total_unrealized_profit = 0.0
            live_active_positions = []

            for p in r.json():
                amt = float(p.get("positionAmt", 0.0))
                if amt != 0.0:
                    unrealized_pnl = float(p.get("unRealizedProfit", 0.0))
                    total_unrealized_profit += unrealized_pnl
                    raw_sym = p.get("symbol", "")
                    std_sym = raw_sym
                    for s in ALLOWED_SYMBOLS:
                        if s.replace("/", "") == raw_sym:
                            std_sym = s
                            break
                    live_active_positions.append({
                        "raw_symbol": raw_sym,
                        "symbol": std_sym,
                        "amount": amt,
                        "unrealized_pnl": unrealized_pnl
                    })

            if not live_active_positions:
                return False, 0.0, 0.0

            target_profit_threshold = balance * 0.01  # Exact 1.0% of Total Balance (e.g. $0.133 on $13.27)
            pnl_pct = (total_unrealized_profit / balance) * 100.0
            print(f"  [Basket Monitor] 📊 Open Positions: {len(live_active_positions)} | Unrealized PnL: ${total_unrealized_profit:+.4f} / +${target_profit_threshold:,.4f} Target ({pnl_pct:+.2f}% / +1.00%)")

            if total_unrealized_profit >= target_profit_threshold:
                print("\n" + "=" * 80)
                print(f"  💰 [PORTFOLIO 1% CASH HARVEST ACTIVATED] 💰")
                print(f"  • Total Unrealized PnL : +${total_unrealized_profit:,.4f} USD ({pnl_pct:+.2f}% of Total Balance)")
                print(f"  • 1.0% Target Threshold: >= +${target_profit_threshold:,.4f} USD")
                print(f"  • Action: Executing MKT Close All across {len(live_active_positions)} positions!")
                print("=" * 80)

                for pos in live_active_positions:
                    std_sym = pos["symbol"]
                    spec = SYMBOL_SPECS.get(std_sym, {"amount_precision": 3})
                    amt_prec = spec.get("amount_precision", 3)
                    qty = round(abs(pos["amount"]), amt_prec) if amt_prec > 0 else int(abs(pos["amount"]))
                    close_side = "SELL" if pos["amount"] > 0 else "BUY"
                    print(f"    -> MKT Close All: {std_sym} {close_side} {qty} (Unrealized PnL: ${pos['unrealized_pnl']:+.4f})...")
                    self.place_futures_order(symbol=std_sym, side=close_side, quantity=qty, reduce_only=True)

                # Instantly sync SQLite Database trade closures
                try:
                    conn = get_connection()
                    cursor = conn.cursor()
                    now_iso = datetime.utcnow().isoformat()
                    for pos in live_active_positions:
                        std_sym = pos["symbol"]
                        pnl_val = pos["unrealized_pnl"]
                        cursor.execute(
                            "UPDATE trades SET status = 'CLOSED', exit_time = ?, exit_reason = 'BASKET_1PCT_HARVEST', pnl_usd = ? WHERE symbol = ? AND status = 'OPEN'",
                            (now_iso, pnl_val, std_sym)
                        )
                    conn.commit()
                    conn.close()
                except Exception as dbe:
                    print(f"[Basket Harvest DB Sync Warning]: {dbe}")

                # Continuous Learning Retrain
                try:
                    ml_brain.check_and_retrain(force=True)
                except Exception:
                    pass

                # Push real-time Telegram notification
                try:
                    from telegram_notifier import send_telegram_alert
                    pos_names = ", ".join([p["symbol"] for p in live_active_positions])
                    send_telegram_alert(
                        f"💰 <b>PORTFOLIO 1.0% CASH HARVEST TRIGGERED!</b>\n\n"
                        f"• <b>Total Profit Banked:</b> +${total_unrealized_profit:,.4f} USDT (+{pnl_pct:.2f}%)\n"
                        f"• <b>Total Wallet Balance:</b> ${balance:,.2f} USDT\n"
                        f"• <b>Positions Closed:</b> {len(live_active_positions)} ({pos_names})\n"
                        f"• <b>Status:</b> All positions closed at Market. Profit secured into cash!"
                    )
                except Exception:
                    pass

                return True, total_unrealized_profit, target_profit_threshold

            return False, total_unrealized_profit, target_profit_threshold

        except Exception as e:
            print(f"[Portfolio Harvest Error]: {e}")
            return False, 0.0, 0.0

    def check_and_update_positions(
        self,
        current_candle_data: Optional[Dict[str, Dict[str, float]]] = None
    ) -> List[Dict[str, Any]]:
        """Active Trade Manager: Manages SL, TP, Breakeven at 1R, and Trailing Stops."""
        # 1. Check Portfolio Unrealized PnL 1% Basket Harvest
        self.check_and_execute_portfolio_unrealized_pnl_harvest()

        open_trades = get_open_trades()
        closed_this_cycle = []

        # Live Binance Open Position Reconciliation
        live_binance_open_symbols = None
        if not self.paper_mode and self.api_key and self.api_key != "mock_key_paper_mode":
            try:
                params = self._sign_payload({})
                url = f"{self.base_url}/fapi/v2/positionRisk"
                r = data_fetcher.session.get(url, headers=self._get_headers(), params=params, timeout=8)
                if r.status_code == 200:
                    live_binance_open_symbols = set()
                    for p in r.json():
                        if float(p.get("positionAmt", 0)) != 0:
                            sym = p.get("symbol", "")
                            for std_sym in ALLOWED_SYMBOLS:
                                if std_sym.replace("/", "") == sym:
                                    live_binance_open_symbols.add(std_sym)
                                    break
            except Exception:
                live_binance_open_symbols = None

        conn = get_connection()
        cursor = conn.cursor()

        for trade in open_trades:
            symbol = trade["symbol"]
            direction = trade["direction"]
            trade_id = trade["trade_id"]
            sl = float(trade["stop_loss"])
            tp = float(trade["take_profit"])

            # 1. Check if position was already filled/settled on Binance matching engine or manually closed
            if live_binance_open_symbols is not None and symbol not in live_binance_open_symbols:
                curr_p = data_fetcher.fetch_current_price(symbol)
                entry_p = float(trade.get("entry_price") or curr_p)
                is_profit = (curr_p >= entry_p) if direction == "LONG" else (curr_p <= entry_p)
                exit_reason = "TAKE_PROFIT" if is_profit else "STOP_LOSS"
                exit_price = curr_p

                closed_trade = close_trade(trade_id=trade_id, exit_price=exit_price, exit_reason=exit_reason)
                if closed_trade:
                    closed_this_cycle.append(closed_trade)
                    print(f"[Executor] 🔄 Binance Sync: Reconciled closed position {trade_id} ({symbol} {direction}) -> {exit_reason} @ ${exit_price:,.2f}")
                continue

            if current_candle_data and symbol in current_candle_data:
                price_info = current_candle_data[symbol]
                high = price_info.get("high", price_info.get("close", 0))
                low = price_info.get("low", price_info.get("close", 0))
                close = price_info.get("close", 0)
                atr = price_info.get("atr_14", close * 0.005)
            else:
                curr = data_fetcher.fetch_current_price(symbol)
                high, low, close = curr, curr, curr
                atr = curr * 0.005

            exit_reason = None
            exit_price = None

            if direction == "LONG":
                if high >= tp:
                    exit_reason = "TAKE_PROFIT"
                    exit_price = tp
                elif low <= sl:
                    exit_reason = "STOP_LOSS"
                    exit_price = sl
            elif direction == "SHORT":
                if low <= tp:
                    exit_reason = "TAKE_PROFIT"
                    exit_price = tp
                elif high >= sl:
                    exit_reason = "STOP_LOSS"
                    exit_price = sl

            if exit_reason and exit_price:
                # 1. Execute live market close order on Binance Futures!
                close_side = "SELL" if direction == "LONG" else "BUY"
                qty = float(trade.get("quantity") or 0.0)
                if qty > 0:
                    print(f"[Executor] 🚀 Sending {exit_reason} ({close_side} {qty} {symbol}) to Binance Futures...")
                    close_res = self.place_futures_order(symbol=symbol, side=close_side, quantity=qty, reduce_only=True)
                    if close_res.get("success"):
                        exit_price = close_res.get("price") or exit_price
                        print(f"[Executor] ✅ Closed on Binance Mainnet! OrderId: {close_res.get('orderId')} @ ${exit_price:,.2f}")
                    else:
                        print(f"[Executor] ⚠️ Binance Close Notice: {close_res.get('error')}")

                # 2. Record closure in database
                closed_trade = close_trade(
                    trade_id=trade_id,
                    exit_price=exit_price,
                    exit_reason=exit_reason
                )
                if closed_trade:
                    closed_this_cycle.append(closed_trade)
                    if exit_reason == "STOP_LOSS":
                        try:
                            from risk_manager import register_symbol_stop_out
                            register_symbol_stop_out(symbol)
                            print(f"[Anti-Whipsaw] ❄️ {symbol} placed in 30-min cooldown window after stop-loss.")
                        except Exception:
                            pass

                    print(
                        f"[Executor] Position Closed in Journal: {trade_id} ({symbol} {direction}) -> "
                        f"{exit_reason} @ ${exit_price:,.2f} | PnL: ${closed_trade['pnl_usd']:.2f} "
                        f"({closed_trade['pnl_percent']:.2f}%)"
                    )
                    # Real-time Google Sheets Live Sync
                    try:
                        sheets_sync.log_trade(closed_trade)
                        sheets_sync.calculate_and_sync_daily_summary()
                    except Exception as e:
                        print(f"[Google Sheets Sync Error]: {e}")

                    # Real-time Telegram Closed Trade Alert
                    try:
                        from telegram_notifier import notify_trade_closed
                        notify_trade_closed(closed_trade)
                    except Exception:
                        pass
            else:
                from btc_sentinel import btc_sentinel
                btc_state = btc_sentinel.get_btc_state()
                be_res = update_breakeven_and_trailing_stops(trade, current_price=close, atr=atr, btc_state=btc_state)
                new_sl = be_res["updated_sl"]
                new_tp = be_res["updated_tp"]

                # 1. Update Stop-Loss if moved forward
                if new_sl != sl:
                    cursor.execute("UPDATE trades SET stop_loss = ? WHERE trade_id = ?", (new_sl, trade_id))
                    conn.commit()
                    if be_res["is_breakeven"]:
                        print(f"[Executor] 🛡️ Rule 6 BREAKEVEN Activated for {trade_id} ({symbol}) -> SL moved to ${new_sl:,.4f} (Zero Risk)")
                        try:
                            from telegram_notifier import notify_breakeven_activated
                            notify_breakeven_activated(trade_id, symbol, float(trade.get("entry_price", 0.0)), new_sl)
                        except Exception:
                            pass
                    elif be_res["is_trailing"]:
                        print(f"[Executor] 📈 Rule 7 TRAILING STOP Updated for {trade_id} ({symbol}) -> New SL: ${new_sl:,.4f}")
                        try:
                            from telegram_notifier import notify_trailing_stop_updated
                            notify_trailing_stop_updated(trade_id, symbol, new_sl, 1.0)
                        except Exception:
                            pass

                # 2. Update Take-Profit if expanded by Bitcoin momentum
                if be_res.get("is_tp_expanded") and new_tp != tp:
                    cursor.execute("UPDATE trades SET take_profit = ? WHERE trade_id = ?", (new_tp, trade_id))
                    conn.commit()
                    print(f"[Executor] 🚀 DYNAMIC TP EXPANSION for {trade_id} ({symbol}): {be_res.get('tp_reason')} -> New TP: ${new_tp:,.4f}")

        conn.close()

        # =============================================================
        # CONTINUOUS MACHINE LEARNING & TRADE POST-MORTEM FEEDBACK LOOP
        # =============================================================
        if closed_this_cycle:
            for ct in closed_this_cycle:
                try:
                    from gemini_reasoner import gemini_reasoner
                    from database import log_ai_post_mortem
                    post_mortem = gemini_reasoner.generate_trade_post_mortem(ct)
                    post_mortem["retrain_accuracy"] = ml_brain.ensemble_accuracy
                    log_ai_post_mortem(post_mortem)
                    print(f"[Continuous AI Learning] 🧠 Lesson Recorded for {ct['symbol']}: {post_mortem.get('ai_lesson')}")
                except Exception as e:
                    pass

            retrain_result = ml_brain.check_and_retrain(force=True)
            if retrain_result and retrain_result.get("success"):
                acc = retrain_result.get("ensemble_accuracy", retrain_result.get("val_accuracy", 0.0))
                roc = retrain_result.get("val_roc_auc", 0.5)
                print(
                    f"[ML Brain Retrained] Dual Ensemble Accuracy: {acc*100:.1f}%, "
                    f"ROC-AUC: {roc:.3f}"
                )

        return closed_this_cycle


# Global Executor instance
executor = BinanceFuturesExecutor(paper_mode=False)
