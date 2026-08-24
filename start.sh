#!/bin/bash
# 24/7 Cloud Multi-Service Cluster Launcher
echo "=================================================="
echo "  🚀 STARTING APEX TRADE AI 24/7 CLOUD CLUSTER"
echo "=================================================="

# 1. Start Platform API Server in background
echo "[Cluster] Starting Web Platform API Server..."
python server.py &

# 2. Start Telegram Bot Daemon in background
echo "[Cluster] Starting Telegram Bot Daemon..."
python telegram_bot.py &

# 3. Start Binance Futures Trading Bot (Foreground Process)
echo "[Cluster] Starting Live Trading Engine Daemon..."
exec python bot.py
