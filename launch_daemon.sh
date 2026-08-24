#!/bin/bash
# 24/7 Persistent Background Daemon for Apex / Orbital Trading Platform Cluster
export PYTHONPATH="/Users/karimsiam/.gemini/antigravity/scratch/crypto_futures_trading_bot"
export PYTHONUNBUFFERED=1

cd /Users/karimsiam/.gemini/antigravity/scratch/crypto_futures_trading_bot || exit 1
mkdir -p logs

# Prevent macOS system and network sleep while trading daemon is running
caffeinate -s -i -m &

# 1. Start Platform Web API Server in background
./venv/bin/python server.py >> logs/server.log 2>&1 &

# 2. Start Telegram Platform Bot Daemon in background
./venv/bin/python telegram_bot.py >> logs/telegram.log 2>&1 &

# 3. Start Binance Futures Trading Engine in Foreground (Watched by launchd)
exec ./venv/bin/python bot.py >> logs/trading_bot.log 2>&1
