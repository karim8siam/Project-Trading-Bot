# 🚀 Binance Futures ML-Powered Adaptive Trading Bot

An algorithmic trading bot engineered for **Binance USD(S)-M Futures** using a **Dual Decision Gate**: rule-based multi-indicator candidate signal generation (LONG & SHORT) coupled with an **Adaptive Machine Learning Meta-Classifier** (`HistGradientBoosting` / `LightGBM`) that continuously learns from past trade outcomes.

---

## 🌟 Key Architecture & Highlights

1. **Strict 4-Pair Whitelist (Hard Security Rule)**:
   - Only processes and trades: **`BTC/USDT`**, **`ETH/USDT`**, **`BNB/USDT`**, and **`SOL/USDT`**.
   - Any other symbol is rejected at both the data ingestion and execution layers.

2. **Strict 1.0% Portfolio Risk Management**:
   - Every single trade dynamically sizes position quantity based on current wallet equity:
     $$\text{Position Size} = \frac{\text{Account Balance} \times 0.01}{|\text{Entry Price} - \text{Stop Loss Price}|}$$
   - Respects contract minimums, step sizes, and notional values.

3. **Dual Decision Gate (Technical + ML)**:
   - **Step 1 (Candidate Trigger):** Evaluates multi-timeframe EMA trend (50/200), RSI momentum pullbacks, MACD histogram accelerations, and ATR volatility.
   - **Step 2 (ML Meta-Filter):** Extracts a 25+ dimension market snapshot at the entry candle. Evaluates historical pattern win probability. If $P(\text{Win}) < 58\%$, the trade is filtered out as a low-quality false breakout.

4. **Continuous Learning & Auto-Retraining Feedback Loop**:
   - Every trade logs full market context into SQLite (`data/trading_journal.db`).
   - Upon position exit (Take-Profit or Stop-Loss), the outcome is logged.
   - The ML brain automatically retrains on updated real-world data every 20 completed trades.

---

## 📁 Project Structure

```
crypto_futures_trading_bot/
├── config.py             # Settings, Whitelist, 1% Risk Parameters, API keys
├── .env.example          # Environment variables template
├── database.py           # SQLite trade journal, market snapshots, training dataset exporter
├── indicators.py         # Quantitative indicators (EMA, RSI, MACD, ATR, Bollinger Bands, Stoch)
├── feature_extractor.py  # 25+ dimension normalized market snapshot vector extractor
├── risk_manager.py       # Strict 1% risk position sizer, leverage & circuit breakers
├── ml_brain.py           # ML Meta-Classifier with continuous retraining & feature importance
├── strategy.py           # Dual Decision Gate: Indicator candidate + ML confidence filter
├── data_fetcher.py       # CCXT Binance Futures connector + offline market data generator
├── execution.py          # Futures order execution (Long/Short, SL/TP brackets)
├── backtester.py         # Historical simulator & ML seed bootstrapper
├── bot.py                # Main real-time async trading orchestrator
├── dashboard.py          # Terminal dashboard with performance & ML metrics
├── test_trading_bot.py   # Complete unit test suite
└── requirements.txt      # Python dependencies
```

---

## ⚡ Quickstart Guide

### 1. Activate the Virtual Environment
```bash
cd /Users/karimsiam/.gemini/antigravity/scratch/crypto_futures_trading_bot
source venv/bin/activate
```

### 2. Configure Credentials (`.env`)
Copy `.env.example` to `.env` and add your Binance Testnet API keys:
```bash
cp .env.example .env
```
Inside `.env`:
```env
BINANCE_API_KEY=your_testnet_api_key_here
BINANCE_API_SECRET=your_testnet_api_secret_here
USE_TESTNET=true
```

### 3. Run Historical Bootstrap & Train ML Model
Populate the database with historical simulations across the 4 whitelisted pairs and train the initial ML classifier:
```bash
python backtester.py
```

### 4. Run the Trading Bot
* **Run a single market scan cycle:**
  ```bash
  python bot.py --once
  ```
* **Run continuous real-time trading loop (e.g. checks every 30s):**
  ```bash
  python bot.py --interval 30
  ```

### 5. View Real-Time Dashboard & ML Intelligence
```bash
python dashboard.py
```

### 6. Run Unit Tests
```bash
python -m unittest test_trading_bot.py -v
```
