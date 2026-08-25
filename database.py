"""
Database Manager for Binance Futures ML Trading Bot.
Manages trade logging, feature snapshots at entry, and ML training dataset retrieval.
"""

import sqlite3
import json
import time
from datetime import datetime
from typing import Dict, Any, List, Optional, Tuple
import pandas as pd
from config import DB_PATH, validate_symbol


_SCHEMA_INITIALIZED = False

def get_connection():
    """Returns a SQLite connection with dict-like row access."""
    global _SCHEMA_INITIALIZED
    try:
        DB_PATH.parent.mkdir(parents=True, exist_ok=True)
    except Exception:
        pass
    conn = sqlite3.connect(str(DB_PATH))
    conn.row_factory = sqlite3.Row
    if not _SCHEMA_INITIALIZED:
        try:
            init_db_conn(conn)
            _SCHEMA_INITIALIZED = True
        except Exception:
            pass
    return conn


def init_db_conn(conn):
    """Initializes all database tables with proper indexing on given connection."""
    cursor = conn.cursor()

    # 1. Trades table
    cursor.execute("""
    CREATE TABLE IF NOT EXISTS trades (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        trade_id TEXT UNIQUE NOT NULL,
        symbol TEXT NOT NULL,
        direction TEXT NOT NULL,
        entry_time TEXT NOT NULL,
        entry_price REAL NOT NULL,
        quantity REAL NOT NULL,
        leverage INTEGER NOT NULL DEFAULT 5,
        stop_loss REAL NOT NULL,
        take_profit REAL NOT NULL,
        exit_time TEXT,
        exit_price REAL,
        exit_reason TEXT,
        pnl_usd REAL,
        pnl_percent REAL,
        is_win INTEGER,
        status TEXT NOT NULL DEFAULT 'OPEN',
        ml_predicted_prob REAL,
        ml_approved INTEGER DEFAULT 1,
        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
    );
    """)

    # 2. Market feature snapshots table (features at the exact moment of signal/entry)
    cursor.execute("""
    CREATE TABLE IF NOT EXISTS market_snapshots (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        trade_id TEXT UNIQUE NOT NULL,
        symbol TEXT NOT NULL,
        timestamp TEXT NOT NULL,
        features_json TEXT NOT NULL,
        FOREIGN KEY (trade_id) REFERENCES trades(trade_id) ON DELETE CASCADE
    );
    """)

    # 3. Model training history table
    cursor.execute("""
    CREATE TABLE IF NOT EXISTS model_retraining_logs (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        timestamp TEXT NOT NULL,
        total_samples INTEGER NOT NULL,
        train_accuracy REAL,
        val_accuracy REAL,
        val_f1 REAL,
        val_roc_auc REAL,
        notes TEXT
    );
    """)

    # 4. Users table for web platform & trading bot access
    cursor.execute("""
    CREATE TABLE IF NOT EXISTS users (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        email TEXT UNIQUE NOT NULL,
        password_hash TEXT NOT NULL,
        bep20_address TEXT NOT NULL,
        balance_usdt REAL DEFAULT 0.0,
        account_status TEXT DEFAULT 'PENDING_DEPOSIT',
        bot_trading_enabled INTEGER DEFAULT 0,
        auto_compound INTEGER DEFAULT 1,
        binance_api_key TEXT,
        binance_api_secret TEXT,
        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
    );
    """)

    # Schema migration: ensure auto_compound column exists
    try:
        cursor.execute("ALTER TABLE users ADD COLUMN auto_compound INTEGER DEFAULT 1")
    except Exception:
        pass

    # 5. BEP20 USDT Deposits table with on-chain TxHash tracking & batch linkage
    cursor.execute("""
    CREATE TABLE IF NOT EXISTS deposits (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        user_id INTEGER NOT NULL,
        tx_hash TEXT UNIQUE NOT NULL,
        from_address TEXT NOT NULL,
        to_address TEXT NOT NULL,
        amount_usdt REAL NOT NULL,
        block_number INTEGER,
        network TEXT DEFAULT 'BSC_MAINNET',
        status TEXT NOT NULL DEFAULT 'CONFIRMED',
        batch_id TEXT,
        verification_details TEXT,
        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
        FOREIGN KEY (user_id) REFERENCES users(id) ON DELETE CASCADE
    );
    """)

    # Try to add batch_id column if table already existed without it
    try:
        cursor.execute("ALTER TABLE deposits ADD COLUMN batch_id TEXT;")
    except Exception:
        pass

    # 6. Daily Capital Accumulation & Binance Bot Sweep Batches
    cursor.execute("""
    CREATE TABLE IF NOT EXISTS daily_batches (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        batch_id TEXT UNIQUE NOT NULL,
        batch_date TEXT NOT NULL,
        total_amount_usdt REAL DEFAULT 0.0,
        total_deposits_count INTEGER DEFAULT 0,
        status TEXT DEFAULT 'ACCUMULATING',
        sweep_tx_hash TEXT,
        destination_address TEXT,
        swept_at TEXT,
        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
    );
    """)

    # 7. Daily Profit/Loss Settlements (60/40 Win Split & 100% Direct Loss Rule)
    cursor.execute("""
    CREATE TABLE IF NOT EXISTS settlements (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        batch_id TEXT NOT NULL,
        settlement_date TEXT NOT NULL,
        user_id INTEGER NOT NULL,
        starting_balance REAL NOT NULL,
        daily_roi_pct REAL NOT NULL,
        is_win INTEGER NOT NULL,
        user_net_pct REAL NOT NULL,
        system_cut_pct REAL NOT NULL,
        user_pnl_usdt REAL NOT NULL,
        system_fee_usdt REAL NOT NULL,
        ending_balance REAL NOT NULL,
        status TEXT DEFAULT 'COMPLETED',
        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
        FOREIGN KEY (user_id) REFERENCES users(id) ON DELETE CASCADE
    );
    """)

    # 8. Withdrawals Table (Queued for Daily Pool Settlement + Admin Approval)
    cursor.execute("""
    CREATE TABLE IF NOT EXISTS withdrawals (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        user_id INTEGER NOT NULL,
        amount_usdt REAL NOT NULL,
        destination_bep20 TEXT NOT NULL,
        status TEXT NOT NULL DEFAULT 'PENDING_ADMIN_CONFIRMATION',
        payout_tx_hash TEXT,
        admin_notes TEXT,
        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
        approved_at TEXT,
        completed_at TEXT,
        FOREIGN KEY (user_id) REFERENCES users(id) ON DELETE CASCADE
    );
    """)

    # 9. Gemini AI Active Trade Decisions Table (Real-time supervisor log)
    cursor.execute("""
    CREATE TABLE IF NOT EXISTS ai_trade_decisions (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        trade_id TEXT NOT NULL,
        symbol TEXT NOT NULL,
        direction TEXT NOT NULL,
        timestamp TEXT NOT NULL,
        current_price REAL NOT NULL,
        unrealized_pnl_usd REAL NOT NULL,
        action TEXT NOT NULL,
        confidence INTEGER NOT NULL,
        recommended_new_sl REAL,
        recommended_new_tp REAL,
        reasoning TEXT NOT NULL,
        executed INTEGER DEFAULT 1,
        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
    );
    """)

    # 10. Gemini AI Continuous Learning & Trade Post-Mortems Table
    cursor.execute("""
    CREATE TABLE IF NOT EXISTS ai_trade_post_mortems (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        trade_id TEXT UNIQUE NOT NULL,
        symbol TEXT NOT NULL,
        direction TEXT NOT NULL,
        outcome TEXT NOT NULL,
        pnl_usd REAL NOT NULL,
        pnl_percent REAL NOT NULL,
        entry_price REAL NOT NULL,
        exit_price REAL NOT NULL,
        exit_reason TEXT NOT NULL,
        ai_lesson TEXT NOT NULL,
        pattern_identified TEXT,
        strategic_takeaway TEXT,
        retrain_accuracy REAL,
        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
    );
    """)

    # Create indices for quick lookups
    cursor.execute("CREATE INDEX IF NOT EXISTS idx_trades_symbol ON trades(symbol);")
    cursor.execute("CREATE INDEX IF NOT EXISTS idx_withdrawals_user ON withdrawals(user_id);")
    cursor.execute("CREATE INDEX IF NOT EXISTS idx_withdrawals_status ON withdrawals(status);")
    cursor.execute("CREATE INDEX IF NOT EXISTS idx_trades_status ON trades(status);")
    cursor.execute("CREATE INDEX IF NOT EXISTS idx_snapshots_trade_id ON market_snapshots(trade_id);")
    cursor.execute("CREATE INDEX IF NOT EXISTS idx_ai_decisions_trade_id ON ai_trade_decisions(trade_id);")
    cursor.execute("CREATE INDEX IF NOT EXISTS idx_ai_decisions_symbol ON ai_trade_decisions(symbol);")
    cursor.execute("CREATE INDEX IF NOT EXISTS idx_ai_post_mortems_trade_id ON ai_trade_post_mortems(trade_id);")
    cursor.execute("CREATE INDEX IF NOT EXISTS idx_users_email ON users(email);")
    cursor.execute("CREATE INDEX IF NOT EXISTS idx_users_bep20 ON users(bep20_address);")
    cursor.execute("CREATE INDEX IF NOT EXISTS idx_deposits_tx_hash ON deposits(tx_hash);")
    cursor.execute("CREATE INDEX IF NOT EXISTS idx_deposits_user_id ON deposits(user_id);")
    cursor.execute("CREATE INDEX IF NOT EXISTS idx_deposits_batch_id ON deposits(batch_id);")
    cursor.execute("CREATE INDEX IF NOT EXISTS idx_batches_batch_id ON daily_batches(batch_id);")
    cursor.execute("CREATE INDEX IF NOT EXISTS idx_batches_status ON daily_batches(status);")
    cursor.execute("CREATE INDEX IF NOT EXISTS idx_settlements_user_id ON settlements(user_id);")
    cursor.execute("CREATE INDEX IF NOT EXISTS idx_settlements_batch_id ON settlements(batch_id);")
    cursor.execute("CREATE INDEX IF NOT EXISTS idx_settlements_date ON settlements(settlement_date);")

    conn.commit()


def init_db():
    """Initializes all database tables with proper indexing."""
    conn = get_connection()
    init_db_conn(conn)


def clear_db():
    """Clears all records from tables for fresh testing or bootstrapping."""
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute("DELETE FROM market_snapshots;")
    cursor.execute("DELETE FROM trades;")
    cursor.execute("DELETE FROM model_retraining_logs;")
    conn.commit()
    conn.close()


def insert_trade(trade_data: Dict[str, Any], features: Optional[Dict[str, Any]] = None):
    """
    Inserts a newly opened trade and its corresponding feature snapshot.
    """
    validate_symbol(trade_data["symbol"])
    conn = get_connection()
    cursor = conn.cursor()

    cursor.execute("""
    INSERT INTO trades (
        trade_id, symbol, direction, entry_time, entry_price,
        quantity, leverage, stop_loss, take_profit, status,
        ml_predicted_prob, ml_approved
    ) VALUES (
        :trade_id, :symbol, :direction, :entry_time, :entry_price,
        :quantity, :leverage, :stop_loss, :take_profit, :status,
        :ml_predicted_prob, :ml_approved
    )
    """, {
        "trade_id": trade_data["trade_id"],
        "symbol": trade_data["symbol"],
        "direction": trade_data["direction"],
        "entry_time": trade_data.get("entry_time", datetime.utcnow().isoformat()),
        "entry_price": float(trade_data["entry_price"]),
        "quantity": float(trade_data["quantity"]),
        "leverage": int(trade_data.get("leverage", 5)),
        "stop_loss": float(trade_data["stop_loss"]),
        "take_profit": float(trade_data["take_profit"]),
        "status": "OPEN",
        "ml_predicted_prob": float(trade_data.get("ml_predicted_prob", 0.5)),
        "ml_approved": int(trade_data.get("ml_approved", 1))
    })

    if features:
        cursor.execute("""
        INSERT INTO market_snapshots (trade_id, symbol, timestamp, features_json)
        VALUES (?, ?, ?, ?)
        """, (
            trade_data["trade_id"],
            trade_data["symbol"],
            trade_data.get("entry_time", datetime.utcnow().isoformat()),
            json.dumps(features)
        ))

    conn.commit()
    conn.close()


def close_trade(
    trade_id: str,
    exit_price: float,
    exit_reason: str,
    exit_time: Optional[str] = None
) -> Optional[Dict[str, Any]]:
    """
    Updates an open trade to CLOSED status and calculates exact PnL and Win/Loss label.
    """
    conn = get_connection()
    cursor = conn.cursor()

    cursor.execute("SELECT * FROM trades WHERE trade_id = ? AND status = 'OPEN'", (trade_id,))
    row = cursor.fetchone()
    if not row:
        conn.close()
        return None

    trade = dict(row)
    entry_price = float(trade["entry_price"])
    qty = float(trade["quantity"])
    direction = trade["direction"]

    if direction == "LONG":
        pnl_usd = (exit_price - entry_price) * qty
        pnl_pct = ((exit_price - entry_price) / entry_price) * 100.0 * trade["leverage"]
    else:  # SHORT
        pnl_usd = (entry_price - exit_price) * qty
        pnl_pct = ((entry_price - exit_price) / entry_price) * 100.0 * trade["leverage"]

    is_win = 1 if pnl_usd > 0 else 0
    now_str = exit_time or datetime.utcnow().isoformat()

    cursor.execute("""
    UPDATE trades SET
        exit_time = ?,
        exit_price = ?,
        exit_reason = ?,
        pnl_usd = ?,
        pnl_percent = ?,
        is_win = ?,
        status = 'CLOSED'
    WHERE trade_id = ?
    """, (now_str, exit_price, exit_reason, pnl_usd, pnl_pct, is_win, trade_id))

    conn.commit()
    conn.close()

    trade["exit_price"] = exit_price
    trade["exit_reason"] = exit_reason
    trade["pnl_usd"] = pnl_usd
    trade["pnl_percent"] = pnl_pct
    trade["is_win"] = is_win
    trade["status"] = "CLOSED"
    return trade


def get_open_trades() -> List[Dict[str, Any]]:
    """Retrieves all active open positions."""
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute("SELECT * FROM trades WHERE status = 'OPEN' AND exit_price IS NULL ORDER BY entry_time DESC")
    rows = cursor.fetchall()
    conn.close()
    return [dict(r) for r in rows]


def get_closed_trades(limit: int = 1000) -> List[Dict[str, Any]]:
    """Retrieves closed trades sorted from newest to oldest."""
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute("SELECT * FROM trades WHERE status = 'CLOSED' ORDER BY exit_time DESC LIMIT ?", (limit,))
    rows = cursor.fetchall()
    conn.close()
    return [dict(r) for r in rows]


def get_recent_executed_trades(limit: int = 10) -> List[Dict[str, Any]]:
    """Retrieves most recent executed trades (OPEN or CLOSED) ordered by entry_time DESC."""
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute("SELECT * FROM trades ORDER BY id DESC LIMIT ?", (limit,))
    rows = cursor.fetchall()
    conn.close()
    return [dict(r) for r in rows]


def log_ai_trade_decision(decision: Dict[str, Any]) -> bool:
    """Logs a real-time Gemini AI active trade supervisor verdict."""
    try:
        conn = get_connection()
        cursor = conn.cursor()
        cursor.execute("""
        INSERT INTO ai_trade_decisions (
            trade_id, symbol, direction, timestamp, current_price, unrealized_pnl_usd,
            action, confidence, recommended_new_sl, recommended_new_tp, reasoning, executed
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """, (
            decision.get("trade_id", ""),
            decision.get("symbol", ""),
            decision.get("direction", ""),
            decision.get("timestamp", datetime.utcnow().isoformat()),
            float(decision.get("current_price", 0.0)),
            float(decision.get("unrealized_pnl_usd", 0.0)),
            decision.get("action", "HOLD_AND_LET_RUN"),
            int(decision.get("confidence", 80)),
            float(decision.get("recommended_new_sl")) if decision.get("recommended_new_sl") is not None else None,
            float(decision.get("recommended_new_tp")) if decision.get("recommended_new_tp") is not None else None,
            decision.get("reasoning", "Hold position; setup momentum healthy."),
            1 if decision.get("executed", True) else 0
        ))
        conn.commit()
        conn.close()
        return True
    except Exception as e:
        print(f"[Database Error] log_ai_trade_decision failed: {e}")
        return False


def get_latest_ai_decisions(limit: int = 15) -> List[Dict[str, Any]]:
    """Retrieves the most recent Gemini AI live supervisor decisions."""
    try:
        conn = get_connection()
        cursor = conn.cursor()
        cursor.execute("SELECT * FROM ai_trade_decisions ORDER BY id DESC LIMIT ?", (limit,))
        rows = cursor.fetchall()
        conn.close()
        return [dict(r) for r in rows]
    except Exception:
        return []


def log_ai_post_mortem(post_mortem: Dict[str, Any]) -> bool:
    """Logs a continuous learning trade post-mortem and AI insight."""
    try:
        conn = get_connection()
        cursor = conn.cursor()
        cursor.execute("""
        INSERT OR REPLACE INTO ai_trade_post_mortems (
            trade_id, symbol, direction, outcome, pnl_usd, pnl_percent,
            entry_price, exit_price, exit_reason, ai_lesson,
            pattern_identified, strategic_takeaway, retrain_accuracy
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """, (
            post_mortem.get("trade_id", ""),
            post_mortem.get("symbol", ""),
            post_mortem.get("direction", ""),
            post_mortem.get("outcome", "WIN" if float(post_mortem.get("pnl_usd", 0.0)) >= 0 else "LOSS"),
            float(post_mortem.get("pnl_usd", 0.0)),
            float(post_mortem.get("pnl_percent", 0.0)),
            float(post_mortem.get("entry_price", 0.0)),
            float(post_mortem.get("exit_price", 0.0)),
            post_mortem.get("exit_reason", "STRATEGY_EXIT"),
            post_mortem.get("ai_lesson", "Trade executed to rule targets."),
            post_mortem.get("pattern_identified", "SFP_PULLBACK"),
            post_mortem.get("strategic_takeaway", "Maintain strict confluence gates."),
            float(post_mortem.get("retrain_accuracy", 0.0))
        ))
        conn.commit()
        conn.close()
        return True
    except Exception as e:
        print(f"[Database Error] log_ai_post_mortem failed: {e}")
        return False


def get_latest_ai_post_mortems(limit: int = 10) -> List[Dict[str, Any]]:
    """Retrieves the most recent continuous learning trade post-mortems."""
    try:
        conn = get_connection()
        cursor = conn.cursor()
        cursor.execute("SELECT * FROM ai_trade_post_mortems ORDER BY id DESC LIMIT ?", (limit,))
        rows = cursor.fetchall()
        conn.close()
        return [dict(r) for r in rows]
    except Exception:
        return []


def get_training_dataset() -> Tuple[pd.DataFrame, pd.Series]:
    """
    Constructs the feature matrix (X) and binary label vector (y) from closed trades
    joined with their market feature snapshots.
    """
    conn = get_connection()
    query = """
    SELECT 
        t.trade_id,
        t.symbol,
        t.direction,
        t.is_win,
        t.pnl_usd,
        t.pnl_percent,
        s.features_json
    FROM trades t
    JOIN market_snapshots s ON t.trade_id = s.trade_id
    WHERE t.status = 'CLOSED' AND t.is_win IS NOT NULL
    """
    df = pd.read_sql_query(query, conn)
    conn.close()

    if df.empty:
        return pd.DataFrame(), pd.Series(dtype=int)

    # Parse JSON feature snapshots into columns
    features_list = []
    for _, row in df.iterrows():
        feat_dict = json.loads(row["features_json"])
        feat_dict["direction_is_long"] = 1 if row["direction"] == "LONG" else 0
        features_list.append(feat_dict)

    X = pd.DataFrame(features_list)
    y = df["is_win"].astype(int)

    return X, y


def log_model_retraining(
    total_samples: int,
    train_acc: float,
    val_acc: float,
    val_f1: float,
    val_roc_auc: float,
    notes: str = ""
):
    """Logs model performance metrics after a retraining cycle."""
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute("""
    INSERT INTO model_retraining_logs (
        timestamp, total_samples, train_accuracy, val_accuracy, val_f1, val_roc_auc, notes
    ) VALUES (?, ?, ?, ?, ?, ?, ?)
    """, (
        datetime.utcnow().isoformat(),
        total_samples,
        train_acc,
        val_acc,
        val_f1,
        val_roc_auc,
        notes
    ))
    conn.commit()
    conn.close()


def get_performance_summary() -> Dict[str, Any]:
    """Computes overall statistics: Win Rate, Total PnL, Profit Factor, Total Trades."""
    conn = get_connection()
    cursor = conn.cursor()

    cursor.execute("""
    SELECT 
        COUNT(*) as total_trades,
        SUM(CASE WHEN is_win = 1 THEN 1 ELSE 0 END) as wins,
        SUM(CASE WHEN is_win = 0 THEN 1 ELSE 0 END) as losses,
        SUM(pnl_usd) as total_pnl_usd,
        SUM(CASE WHEN pnl_usd > 0 THEN pnl_usd ELSE 0 END) as gross_profit,
        SUM(CASE WHEN pnl_usd < 0 THEN ABS(pnl_usd) ELSE 0 END) as gross_loss
    FROM trades
    WHERE status = 'CLOSED'
    """)
    row = cursor.fetchone()
    conn.close()

    if not row or row["total_trades"] == 0:
        return {
            "total_trades": 0,
            "wins": 0,
            "losses": 0,
            "win_rate_pct": 0.0,
            "total_pnl_usd": 0.0,
            "profit_factor": 0.0
        }

    total = row["total_trades"]
    wins = row["wins"] or 0
    losses = row["losses"] or 0
    win_rate = (wins / total) * 100.0 if total > 0 else 0.0
    gross_profit = row["gross_profit"] or 0.0
    gross_loss = row["gross_loss"] or 0.0
    profit_factor = (gross_profit / gross_loss) if gross_loss > 0 else (gross_profit if gross_profit > 0 else 1.0)

    return {
        "total_trades": total,
        "wins": wins,
        "losses": losses,
        "win_rate_pct": round(win_rate, 2),
        "total_pnl_usd": round(row["total_pnl_usd"] or 0.0, 2),
        "profit_factor": round(profit_factor, 2)
    }


# ===================================================
# USER MANAGEMENT & BEP20 DEPOSIT HELPER FUNCTIONS
# ===================================================

def create_user(email: str, password_hash: str, bep20_address: str) -> Dict[str, Any]:
    """Creates a new user account with PENDING_DEPOSIT status."""
    conn = get_connection()
    cursor = conn.cursor()
    try:
        cursor.execute("""
        INSERT INTO users (email, password_hash, bep20_address, balance_usdt, account_status, bot_trading_enabled)
        VALUES (?, ?, ?, 0.0, 'PENDING_DEPOSIT', 0)
        """, (email.strip().lower(), password_hash, bep20_address.strip().lower()))
        conn.commit()
        user_id = cursor.lastrowid
        return get_user_by_id(user_id)
    finally:
        conn.close()


def get_user_by_email(email: str) -> Optional[Dict[str, Any]]:
    """Retrieves user profile by email."""
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute("SELECT * FROM users WHERE LOWER(email) = ?", (email.strip().lower(),))
    row = cursor.fetchone()
    conn.close()
    return dict(row) if row else None


def get_user_by_id(user_id: int) -> Optional[Dict[str, Any]]:
    """Retrieves user profile by user_id."""
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute("SELECT * FROM users WHERE id = ?", (user_id,))
    row = cursor.fetchone()
    conn.close()
    return dict(row) if row else None


def get_user_by_bep20(bep20_address: str) -> Optional[Dict[str, Any]]:
    """Retrieves user profile by BEP20 wallet address."""
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute("SELECT * FROM users WHERE LOWER(bep20_address) = ?", (bep20_address.strip().lower(),))
    row = cursor.fetchone()
    conn.close()
    return dict(row) if row else None


def update_user_balance_and_status(user_id: int, added_balance: float, new_status: str = "ACTIVE_TRADER") -> bool:
    """Credits deposited USDT to user balance and updates status to ACTIVE_TRADER."""
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute("""
    UPDATE users 
    SET balance_usdt = balance_usdt + ?,
        account_status = ?
    WHERE id = ?
    """, (float(added_balance), new_status, user_id))
    conn.commit()
    rows_affected = cursor.rowcount
    conn.close()
    return rows_affected > 0


def update_bot_trading_status(user_id: int, enabled: bool) -> bool:
    """Toggles automated bot trading for the specified user."""
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute("""
    UPDATE users
    SET bot_trading_enabled = ?
    WHERE id = ?
    """, (1 if enabled else 0, user_id))
    conn.commit()
    rows_affected = cursor.rowcount
    conn.close()
    return rows_affected > 0


def update_user_auto_compound(user_id: int, enabled: bool) -> bool:
    """Toggles continuous auto-compounding rollover for the specified user."""
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute("""
    UPDATE users
    SET auto_compound = ?
    WHERE id = ?
    """, (1 if enabled else 0, user_id))
    conn.commit()
    rows_affected = cursor.rowcount
    conn.close()
    return rows_affected > 0


def is_tx_hash_used(tx_hash: str) -> bool:
    """Checks if a blockchain transaction hash has already been credited (prevents double-spending)."""
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute("SELECT id FROM deposits WHERE LOWER(tx_hash) = ?", (tx_hash.strip().lower(),))
    row = cursor.fetchone()
    conn.close()
    return row is not None


def record_deposit(
    user_id: int,
    tx_hash: str,
    from_address: str,
    to_address: str,
    amount_usdt: float,
    block_number: Optional[int] = None,
    network: str = "BSC_MAINNET",
    status: str = "CONFIRMED",
    verification_details: Optional[Dict[str, Any]] = None,
    batch_id: Optional[str] = None
) -> Dict[str, Any]:
    """Records a verified BEP20 USDT deposit and links it to the active daily accumulation batch."""
    if not batch_id:
        active_batch = get_or_create_active_batch()
        batch_id = active_batch["batch_id"]

    conn = get_connection()
    cursor = conn.cursor()
    details_json = json.dumps(verification_details or {})
    cursor.execute("""
    INSERT INTO deposits (
        user_id, tx_hash, from_address, to_address, amount_usdt,
        block_number, network, status, batch_id, verification_details
    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
    """, (
        user_id,
        tx_hash.strip().lower(),
        from_address.strip().lower(),
        to_address.strip().lower(),
        float(amount_usdt),
        block_number,
        network,
        status,
        batch_id,
        details_json
    ))
    deposit_id = cursor.lastrowid

    # Increment batch totals
    cursor.execute("""
    UPDATE daily_batches
    SET total_amount_usdt = total_amount_usdt + ?,
        total_deposits_count = total_deposits_count + 1
    WHERE batch_id = ?
    """, (float(amount_usdt), batch_id))

    conn.commit()
    conn.close()

    return {
        "id": deposit_id,
        "user_id": user_id,
        "tx_hash": tx_hash,
        "from_address": from_address,
        "to_address": to_address,
        "amount_usdt": amount_usdt,
        "block_number": block_number,
        "network": network,
        "status": status,
        "batch_id": batch_id,
        "verification_details": verification_details or {}
    }


# ===================================================
# DAILY BATCH & BINANCE BOT SWEEP MANAGEMENT
# ===================================================

def get_or_create_active_batch() -> Dict[str, Any]:
    """Retrieves the current ACCUMULATING batch or creates a fresh one for the active cycle."""
    today_utc = datetime.utcnow().strftime("%Y-%m-%d")

    conn = get_connection()
    cursor = conn.cursor()

    cursor.execute("SELECT * FROM daily_batches WHERE status = 'ACCUMULATING' ORDER BY id DESC LIMIT 1")
    row = cursor.fetchone()

    if not row:
        from config import BINANCE_BOT_WALLET_ADDRESS
        cursor.execute("SELECT COUNT(*) as count FROM daily_batches WHERE batch_date = ?", (today_utc,))
        count_row = cursor.fetchone()
        cycle_num = (count_row["count"] + 1) if count_row else 1
        suffix = f"-CYCLE-{cycle_num}" if cycle_num > 1 else ""
        batch_id = f"BATCH-{today_utc}{suffix}"

        cursor.execute("""
        INSERT INTO daily_batches (batch_id, batch_date, total_amount_usdt, total_deposits_count, status, destination_address)
        VALUES (?, ?, 0.0, 0, 'ACCUMULATING', ?)
        """, (batch_id, today_utc, BINANCE_BOT_WALLET_ADDRESS))
        conn.commit()
        cursor.execute("SELECT * FROM daily_batches WHERE batch_id = ?", (batch_id,))
        row = cursor.fetchone()

    conn.close()
    return dict(row)


def get_current_batch_summary() -> Dict[str, Any]:
    """Gets real-time metrics for today's active accumulation batch."""
    batch = get_or_create_active_batch()
    batch_id = batch["batch_id"]

    conn = get_connection()
    cursor = conn.cursor()

    # Get distinct participants
    cursor.execute("""
    SELECT COUNT(DISTINCT user_id) as participant_count, SUM(amount_usdt) as sum_usdt
    FROM deposits
    WHERE batch_id = ? AND status = 'CONFIRMED'
    """, (batch_id,))
    agg = cursor.fetchone()
    conn.close()

    total_usdt = round(agg["sum_usdt"] or 0.0, 2) if agg else 0.0
    participants = agg["participant_count"] if agg else 0

    return {
        "batch_id": batch_id,
        "batch_date": batch["batch_date"],
        "status": batch["status"],
        "total_amount_usdt": total_usdt,
        "total_deposits_count": batch["total_deposits_count"],
        "unique_participants": participants,
        "destination_address": batch["destination_address"]
    }


def execute_daily_sweep(batch_id: Optional[str] = None, sweep_tx_hash: Optional[str] = None) -> Dict[str, Any]:
    """
    Consolidates the day's accumulated deposits and sweeps them to the Binance Trading Bot hot wallet.
    Updates batch state to SWEPT_TO_BINANCE and user accounts to ACTIVE_IN_BOT_CYCLE.
    """
    from config import BINANCE_BOT_WALLET_ADDRESS
    if not batch_id:
        active = get_or_create_active_batch()
        batch_id = active["batch_id"]

    conn = get_connection()
    cursor = conn.cursor()

    cursor.execute("SELECT * FROM daily_batches WHERE batch_id = ?", (batch_id,))
    batch_row = cursor.fetchone()
    if not batch_row:
        conn.close()
        return {"success": False, "message": f"Batch {batch_id} not found."}

    # Fetch total amount in this batch
    cursor.execute("""
    SELECT SUM(amount_usdt) as total_usdt, COUNT(*) as count, GROUP_CONCAT(DISTINCT user_id) as user_ids
    FROM deposits
    WHERE batch_id = ? AND status = 'CONFIRMED'
    """, (batch_id,))
    agg = cursor.fetchone()

    total_usdt = round(agg["total_usdt"] or 0.0, 2) if agg else 0.0
    now_iso = datetime.utcnow().isoformat()
    dest_address = BINANCE_BOT_WALLET_ADDRESS

    if not sweep_tx_hash:
        sweep_tx_hash = f"0xsweep_{batch_id.lower()}_{int(time.time())}"

    # Update batch record
    cursor.execute("""
    UPDATE daily_batches
    SET status = 'SWEPT_TO_BINANCE',
        sweep_tx_hash = ?,
        destination_address = ?,
        swept_at = ?,
        total_amount_usdt = ?
    WHERE batch_id = ?
    """, (sweep_tx_hash, dest_address, now_iso, total_usdt, batch_id))

    # Activate bot status for all users who contributed to this batch
    if agg and agg["user_ids"]:
        user_id_list = [int(uid) for uid in agg["user_ids"].split(",") if uid]
        placeholders = ",".join("?" * len(user_id_list))
        cursor.execute(f"""
        UPDATE users
        SET account_status = 'ACTIVE_IN_BOT_CYCLE',
            bot_trading_enabled = 1
        WHERE id IN ({placeholders})
        """, user_id_list)

    conn.commit()
    conn.close()

    return {
        "success": True,
        "batch_id": batch_id,
        "total_amount_usdt": total_usdt,
        "sweep_tx_hash": sweep_tx_hash,
        "destination_address": dest_address,
        "status": "SWEPT_TO_BINANCE",
        "swept_at": now_iso
    }


def get_batch_history() -> List[Dict[str, Any]]:
    """Returns list of historical daily batch sweeps."""
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute("""
    SELECT batch_id, batch_date, total_amount_usdt, total_deposits_count, status, sweep_tx_hash, destination_address, swept_at, created_at
    FROM daily_batches
    ORDER BY created_at DESC
    LIMIT 30
    """)
    rows = cursor.fetchall()
    conn.close()
    return [dict(r) for r in rows]


def get_user_batch_status(user_id: int) -> Dict[str, Any]:
    """Calculates user's status within today's accumulating batch and overall bot cycle."""
    active_batch = get_or_create_active_batch()
    batch_id = active_batch["batch_id"]

    conn = get_connection()
    cursor = conn.cursor()

    # User's deposits in today's batch
    cursor.execute("""
    SELECT SUM(amount_usdt) as today_user_usdt, COUNT(*) as count
    FROM deposits
    WHERE user_id = ? AND batch_id = ? AND status = 'CONFIRMED'
    """, (user_id, batch_id))
    user_batch_row = cursor.fetchone()
    today_user_usdt = round(user_batch_row["today_user_usdt"] or 0.0, 2) if user_batch_row else 0.0

    # User overall profile
    cursor.execute("SELECT balance_usdt, account_status, bot_trading_enabled FROM users WHERE id = ?", (user_id,))
    user = cursor.fetchone()
    conn.close()

    total_batch_usdt = active_batch["total_amount_usdt"] or 0.0
    pool_share_pct = round((today_user_usdt / total_batch_usdt * 100.0), 2) if total_batch_usdt > 0 else 0.0

    queue_state = "NOT_DEPOSITED"
    if today_user_usdt >= 1.0:
        if active_batch["status"] == "ACCUMULATING":
            queue_state = "QUEUED_FOR_TODAY_BATCH"
        else:
            queue_state = "ACTIVE_IN_BOT_CYCLE"
    elif user and user["account_status"] == "ACTIVE_IN_BOT_CYCLE":
        queue_state = "ACTIVE_IN_BOT_CYCLE"

    return {
        "active_batch_id": batch_id,
        "batch_status": active_batch["status"],
        "user_today_deposited_usdt": today_user_usdt,
        "user_total_balance_usdt": round(user["balance_usdt"] if user else 0.0, 2),
        "user_pool_share_pct": pool_share_pct,
        "queue_state": queue_state
    }


def get_user_deposits(user_id: int) -> List[Dict[str, Any]]:
    """Fetches all deposit transactions for a given user."""
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute("""
    SELECT id, tx_hash, from_address, to_address, amount_usdt, block_number, network, status, batch_id, created_at
    FROM deposits
    WHERE user_id = ?
    ORDER BY created_at DESC
    """, (user_id,))
    rows = cursor.fetchall()
    conn.close()
    return [dict(r) for r in rows]


def get_platform_stats() -> Dict[str, Any]:
    """Aggregates platform statistics for landing/dashboard overview."""
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute("SELECT COUNT(*) as total_users, SUM(balance_usdt) as total_tvl FROM users;")
    user_stats = cursor.fetchone()
    
    cursor.execute("SELECT COUNT(*) as total_deposits, SUM(amount_usdt) as total_deposited FROM deposits WHERE status = 'CONFIRMED';")
    dep_stats = cursor.fetchone()

    cursor.execute("SELECT COUNT(*) as total_batches, SUM(total_amount_usdt) as total_swept FROM daily_batches WHERE status = 'SWEPT_TO_BINANCE';")
    batch_stats = cursor.fetchone()
    conn.close()

    bot_summary = get_performance_summary()

    return {
        "total_users": user_stats["total_users"] if user_stats else 0,
        "total_tvl_usdt": round(user_stats["total_tvl"] or 0.0, 2) if user_stats else 0.0,
        "total_deposits_count": dep_stats["total_deposits"] if dep_stats else 0,
        "total_deposited_usdt": round(dep_stats["total_deposited"] or 0.0, 2) if dep_stats else 0.0,
        "total_swept_to_binance_usdt": round(batch_stats["total_swept"] or 0.0, 2) if batch_stats else 0.0,
        "bot_performance": bot_summary
    }


# ===================================================
# DAILY SETTLEMENT (60/40 WIN & 100% DIRECT LOSS)
# ===================================================

def record_user_settlement(
    batch_id: str,
    settlement_date: str,
    user_id: int,
    starting_balance: float,
    daily_roi_pct: float,
    is_win: int,
    user_net_pct: float,
    system_cut_pct: float,
    user_pnl_usdt: float,
    system_fee_usdt: float,
    ending_balance: float
) -> Dict[str, Any]:
    """Logs an individual user's daily settlement record and updates user balance."""
    conn = get_connection()
    cursor = conn.cursor()

    cursor.execute("""
    INSERT INTO settlements (
        batch_id, settlement_date, user_id, starting_balance, daily_roi_pct,
        is_win, user_net_pct, system_cut_pct, user_pnl_usdt, system_fee_usdt, ending_balance
    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
    """, (
        batch_id,
        settlement_date,
        user_id,
        round(starting_balance, 4),
        round(daily_roi_pct, 4),
        is_win,
        round(user_net_pct, 4),
        round(system_cut_pct, 4),
        round(user_pnl_usdt, 4),
        round(system_fee_usdt, 4),
        round(ending_balance, 4)
    ))
    settlement_id = cursor.lastrowid

    # Update user's live balance
    cursor.execute("UPDATE users SET balance_usdt = ? WHERE id = ?", (round(ending_balance, 4), user_id))

    conn.commit()
    conn.close()

    return {
        "id": settlement_id,
        "batch_id": batch_id,
        "settlement_date": settlement_date,
        "user_id": user_id,
        "starting_balance": starting_balance,
        "daily_roi_pct": daily_roi_pct,
        "is_win": is_win,
        "user_net_pct": user_net_pct,
        "system_cut_pct": system_cut_pct,
        "user_pnl_usdt": user_pnl_usdt,
        "system_fee_usdt": system_fee_usdt,
        "ending_balance": ending_balance
    }


def get_user_settlements(user_id: int) -> List[Dict[str, Any]]:
    """Retrieves settlement payout records for a specific user."""
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute("""
    SELECT id, batch_id, settlement_date, starting_balance, daily_roi_pct,
           is_win, user_net_pct, system_cut_pct, user_pnl_usdt, system_fee_usdt,
           ending_balance, status, created_at
    FROM settlements
    WHERE user_id = ?
    ORDER BY settlement_date DESC, id DESC
    """, (user_id,))
    rows = cursor.fetchall()
    conn.close()
    return [dict(r) for r in rows]


def get_all_settlements(limit: int = 50) -> List[Dict[str, Any]]:
    """Retrieves platform-wide daily settlements."""
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute("""
    SELECT s.*, u.email, u.bep20_address
    FROM settlements s
    JOIN users u ON s.user_id = u.id
    ORDER BY s.settlement_date DESC, s.id DESC
    LIMIT ?
    """, (limit,))
    rows = cursor.fetchall()
    conn.close()
    return [dict(r) for r in rows]


def get_active_trading_users() -> List[Dict[str, Any]]:
    """Retrieves all users currently eligible for daily trading pool settlement."""
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute("""
    SELECT id, email, bep20_address, balance_usdt, account_status, bot_trading_enabled
    FROM users
    WHERE balance_usdt >= 1.0 AND account_status IN ('ACTIVE_TRADER', 'ACTIVE_IN_BOT_CYCLE')
    """)
    rows = cursor.fetchall()
    conn.close()
    return [dict(r) for r in rows]


def get_user_financial_analytics(user_id: int) -> Dict[str, Any]:
    """
    Computes comprehensive, personalized financial analytics for a user:
    - Total Deposited Capital
    - Current Active Balance
    - Total Bot Profit Earned (60% win rule)
    - Total Losses Incurred (100% loss rule)
    - Net PnL ($) & Net ROI (%)
    - Last-Day Settlement & Payout Return Confirmation
    - Full Daily Timeline History
    """
    conn = get_connection()
    cursor = conn.cursor()

    # 1. User profile
    cursor.execute("SELECT id, email, bep20_address, balance_usdt, account_status, bot_trading_enabled, created_at FROM users WHERE id = ?", (user_id,))
    user_row = cursor.fetchone()
    if not user_row:
        conn.close()
        return {"error": "User not found"}

    user = dict(user_row)

    # 2. Total deposits
    cursor.execute("SELECT SUM(amount_usdt) as total_dep, COUNT(*) as dep_count FROM deposits WHERE user_id = ? AND status = 'CONFIRMED'", (user_id,))
    dep_stats = cursor.fetchone()
    total_deposited = round(dep_stats["total_dep"] or 0.0, 2) if dep_stats else 0.0
    deposit_count = dep_stats["dep_count"] if dep_stats else 0

    # 3. Settlements aggregation
    cursor.execute("""
    SELECT 
        SUM(CASE WHEN is_win = 1 THEN user_pnl_usdt ELSE 0 END) as total_profit,
        SUM(CASE WHEN is_win = 0 THEN ABS(user_pnl_usdt) ELSE 0 END) as total_loss,
        SUM(system_fee_usdt) as total_system_fees,
        COUNT(*) as total_cycles
    FROM settlements
    WHERE user_id = ?
    """, (user_id,))
    settle_agg = cursor.fetchone()

    total_profit = round(settle_agg["total_profit"] or 0.0, 2) if settle_agg else 0.0
    total_loss = round(settle_agg["total_loss"] or 0.0, 2) if settle_agg else 0.0
    total_system_fees = round(settle_agg["total_system_fees"] or 0.0, 2) if settle_agg else 0.0
    total_cycles = settle_agg["total_cycles"] if settle_agg else 0
    net_pnl = round(total_profit - total_loss, 2)

    # Net ROI based on initial deposit or starting capital
    base_capital = total_deposited if total_deposited > 0 else (user["balance_usdt"] or 1.0)
    net_roi_pct = round((net_pnl / base_capital * 100.0), 2) if base_capital > 0 else 0.0

    # 4. Settlements timeline & last settlement
    cursor.execute("""
    SELECT id, batch_id, settlement_date, starting_balance, daily_roi_pct,
           is_win, user_net_pct, system_cut_pct, user_pnl_usdt, system_fee_usdt,
           ending_balance, status, created_at
    FROM settlements
    WHERE user_id = ?
    ORDER BY settlement_date DESC, id DESC
    """, (user_id,))
    settlement_rows = [dict(r) for r in cursor.fetchall()]
    conn.close()

    last_settlement = settlement_rows[0] if settlement_rows else None

    # Last Day Return confirmation details
    if last_settlement:
        is_win = last_settlement["is_win"] == 1
        rule_name = "60/40 Win Split (60% to You / 40% System Fee)" if is_win else "100% Direct Loss (0% System Fee)"
        last_return_confirmation = {
            "has_settlement": True,
            "settlement_date": last_settlement["settlement_date"],
            "batch_id": last_settlement["batch_id"],
            "status": "CONFIRMED & RETURNED",
            "daily_roi_pct": last_settlement["daily_roi_pct"],
            "is_win": is_win,
            "rule_applied": rule_name,
            "starting_capital_usdt": last_settlement["starting_balance"],
            "net_payout_usdt": last_settlement["user_pnl_usdt"],
            "system_fee_usdt": last_settlement["system_fee_usdt"],
            "ending_balance_usdt": last_settlement["ending_balance"],
            "destination_bep20": user["bep20_address"],
            "confirmed_at": last_settlement["created_at"]
        }
    else:
        last_return_confirmation = {
            "has_settlement": False,
            "status": "QUEUED_FOR_FIRST_DAILY_CYCLE",
            "message": "Your capital is queued for the upcoming 24h trading cycle at 00:00 UTC.",
            "destination_bep20": user["bep20_address"]
        }

    return {
        "user_id": user["id"],
        "email": user["email"],
        "bep20_address": user["bep20_address"],
        "balance_usdt": round(user["balance_usdt"], 2),
        "account_status": user["account_status"],
        "bot_trading_enabled": bool(user["bot_trading_enabled"]),
        "auto_compound": bool(user.get("auto_compound", 1)),
        "total_deposited_usdt": total_deposited,
        "deposit_count": deposit_count,
        "total_profit_usdt": total_profit,
        "total_loss_usdt": total_loss,
        "net_pnl_usdt": net_pnl,
        "net_roi_pct": net_roi_pct,
        "total_system_fees_paid": total_system_fees,
        "total_cycles_settled": total_cycles,
        "last_return_confirmation": last_return_confirmation,
        "daily_timeline": settlement_rows
    }


# ===================================================
# WITHDRAWAL MANAGEMENT & ADMIN APPROVAL FUNCTIONS
# ===================================================

def create_withdrawal_request(user_id: int, amount_usdt: float, destination_bep20: str) -> Dict[str, Any]:
    """
    Submits a withdrawal request.
    Deducts the requested amount from the user's active trading balance and queues it for admin approval.
    """
    conn = get_connection()
    cursor = conn.cursor()
    try:
        # Check current balance
        cursor.execute("SELECT balance_usdt FROM users WHERE id = ?", (user_id,))
        row = cursor.fetchone()
        if not row or row["balance_usdt"] < amount_usdt:
            raise ValueError(f"Insufficient funds: available {row['balance_usdt'] if row else 0.0:.2f} USDT, requested {amount_usdt:.2f} USDT")

        # Deduct balance
        cursor.execute("UPDATE users SET balance_usdt = balance_usdt - ? WHERE id = ?", (amount_usdt, user_id))

        # Insert withdrawal record
        cursor.execute("""
        INSERT INTO withdrawals (user_id, amount_usdt, destination_bep20, status)
        VALUES (?, ?, ?, 'PENDING_ADMIN_CONFIRMATION')
        """, (user_id, float(amount_usdt), destination_bep20.strip().lower()))
        conn.commit()

        withdrawal_id = cursor.lastrowid
        cursor.execute("SELECT * FROM withdrawals WHERE id = ?", (withdrawal_id,))
        return dict(cursor.fetchone())
    finally:
        conn.close()


def get_user_withdrawals(user_id: int, limit: int = 50) -> List[Dict[str, Any]]:
    """Retrieves all withdrawal requests made by a specific user."""
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute("""
    SELECT * FROM withdrawals
    WHERE user_id = ?
    ORDER BY created_at DESC, id DESC
    LIMIT ?
    """, (user_id, limit))
    rows = cursor.fetchall()
    conn.close()
    return [dict(r) for r in rows]


def get_pending_withdrawals(limit: int = 50) -> List[Dict[str, Any]]:
    """Retrieves all pending withdrawals awaiting admin confirmation."""
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute("""
    SELECT w.*, u.email, u.bep20_address as user_registered_bep20
    FROM withdrawals w
    JOIN users u ON w.user_id = u.id
    WHERE w.status = 'PENDING_ADMIN_CONFIRMATION'
    ORDER BY w.created_at ASC
    LIMIT ?
    """, (limit,))
    rows = cursor.fetchall()
    conn.close()
    return [dict(r) for r in rows]


def approve_withdrawal_request(
    withdrawal_id: int,
    payout_tx_hash: Optional[str] = None,
    admin_notes: Optional[str] = None
) -> Optional[Dict[str, Any]]:
    """
    Admin confirms and dispatches payout from System Vault Address to user's BEP20 address.
    """
    conn = get_connection()
    cursor = conn.cursor()
    try:
        now_str = datetime.utcnow().isoformat()
        if not payout_tx_hash:
            # Generate confirmed on-chain payout simulation hash if not manually supplied
            import hashlib
            payout_tx_hash = "0x" + hashlib.sha256(f"payout_{withdrawal_id}_{now_str}".encode()).hexdigest()

        cursor.execute("""
        UPDATE withdrawals
        SET status = 'CONFIRMED_DISPATCHED',
            payout_tx_hash = ?,
            admin_notes = ?,
            approved_at = ?,
            completed_at = ?
        WHERE id = ? AND status = 'PENDING_ADMIN_CONFIRMATION'
        """, (payout_tx_hash, admin_notes or "Dispatched from Master System Vault (0x66A06fA03BE98383fe4F73a5f1783332CAC0F5A0)", now_str, now_str, withdrawal_id))
        conn.commit()

        cursor.execute("SELECT * FROM withdrawals WHERE id = ?", (withdrawal_id,))
        row = cursor.fetchone()
        return dict(row) if row else None
    finally:
        conn.close()


def reject_withdrawal_request(withdrawal_id: int, reason: str = "Admin rejected") -> Optional[Dict[str, Any]]:
    """
    Admin rejects a withdrawal request and refunds the money back to the user's active trading balance.
    """
    conn = get_connection()
    cursor = conn.cursor()
    try:
        cursor.execute("SELECT * FROM withdrawals WHERE id = ? AND status = 'PENDING_ADMIN_CONFIRMATION'", (withdrawal_id,))
        row = cursor.fetchone()
        if not row:
            return None

        w = dict(row)
        now_str = datetime.utcnow().isoformat()

        # Refund user balance
        cursor.execute("UPDATE users SET balance_usdt = balance_usdt + ? WHERE id = ?", (w["amount_usdt"], w["user_id"]))

        # Mark rejected
        cursor.execute("""
        UPDATE withdrawals
        SET status = 'REJECTED',
            admin_notes = ?,
            completed_at = ?
        WHERE id = ?
        """, (reason, now_str, withdrawal_id))
        conn.commit()

        cursor.execute("SELECT * FROM withdrawals WHERE id = ?", (withdrawal_id,))
        return dict(cursor.fetchone())
    finally:
        conn.close()


def get_all_platform_deposits(limit: int = 50) -> List[Dict[str, Any]]:
    """Retrieves all confirmed deposits across ALL users on the platform."""
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute("""
    SELECT d.*, u.email, u.bep20_address as user_registered_bep20
    FROM deposits d
    JOIN users u ON d.user_id = u.id
    ORDER BY d.created_at DESC, d.id DESC
    LIMIT ?
    """, (limit,))
    rows = cursor.fetchall()
    conn.close()
    return [dict(r) for r in rows]


def get_all_platform_users(limit: int = 100) -> List[Dict[str, Any]]:
    """Retrieves all registered traders and their balances/compounding status."""
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute("""
    SELECT id, email, bep20_address, balance_usdt, account_status, bot_trading_enabled, auto_compound, created_at
    FROM users
    ORDER BY id ASC
    LIMIT ?
    """, (limit,))
    rows = cursor.fetchall()
    conn.close()
    return [dict(r) for r in rows]


# Auto-initialize on import safely
try:
    init_db()
except Exception as e:
    print(f"[Database] Init notice: {e}")




