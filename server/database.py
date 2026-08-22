"""
Database Manager for Orbital Trading Platform.
Universal database adapter supporting both:
1. Neon Serverless PostgreSQL (Production for 1,000+ users)
2. SQLite (Local development fallback)
"""

import os
import sqlite3
from typing import Dict, Any, List, Optional
import psycopg2
import psycopg2.extras
from config import DB_PATH, DATABASE_URL, USE_POSTGRES


class DictRow(dict):
    """Dictionary that also allows integer indexing (e.g. row[0] or row['col'])."""
    def __getitem__(self, item):
        if isinstance(item, int):
            vals = list(self.values())
            if 0 <= item < len(vals):
                return vals[item]
            return None
        return super().get(item)


class UniversalCursor:
    """Universal cursor that translates queries and handles dictionary mapping."""
    def __init__(self, cursor, is_postgres: bool = False):
        self.cursor = cursor
        self.is_postgres = is_postgres

    def execute(self, query: str, params=None):
        if self.is_postgres:
            pg_query = query.replace("?", "%s")
            if params is not None:
                return self.cursor.execute(pg_query, params)
            return self.cursor.execute(pg_query)
        else:
            if params is not None:
                return self.cursor.execute(query, params)
            return self.cursor.execute(query)

    def fetchone(self):
        row = self.cursor.fetchone()
        if row is None:
            return None
        return DictRow(dict(row))

    def fetchall(self):
        rows = self.cursor.fetchall()
        return [DictRow(dict(r)) for r in rows]

    def close(self):
        return self.cursor.close()


class UniversalConnection:
    """Universal database connection wrapping PostgreSQL or SQLite."""
    def __init__(self, conn, is_postgres: bool = False):
        self.conn = conn
        self.is_postgres = is_postgres

    def cursor(self):
        if self.is_postgres:
            c = self.conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)
        else:
            c = self.conn.cursor()
        return UniversalCursor(c, self.is_postgres)

    def commit(self):
        return self.conn.commit()

    def rollback(self):
        return self.conn.rollback()

    def close(self):
        return self.conn.close()


def get_db() -> UniversalConnection:
    """Returns a Universal database connection."""
    if USE_POSTGRES and DATABASE_URL:
        try:
            raw_conn = psycopg2.connect(DATABASE_URL)
            return UniversalConnection(raw_conn, is_postgres=True)
        except Exception as e:
            print(f"[Database] ⚠️ Neon Postgres connection failed ({e}), falling back to SQLite.")

    raw_conn = sqlite3.connect(DB_PATH)
    raw_conn.row_factory = sqlite3.Row
    return UniversalConnection(raw_conn, is_postgres=False)


def init_platform_db():
    """Creates all required tables and indexes across PostgreSQL or SQLite."""
    conn = get_db()
    cursor = conn.cursor()
    is_pg = conn.is_postgres

    pk_def = "SERIAL PRIMARY KEY" if is_pg else "INTEGER PRIMARY KEY AUTOINCREMENT"

    # 1. Users Table
    cursor.execute(f"""
    CREATE TABLE IF NOT EXISTS users (
        id {pk_def},
        user_uuid TEXT UNIQUE NOT NULL,
        email TEXT UNIQUE NOT NULL,
        password_hash TEXT NOT NULL,
        bep20_address TEXT UNIQUE NOT NULL,
        telegram_handle TEXT,
        balance_usdt REAL DEFAULT 0.0,
        active_vault_balance REAL DEFAULT 0.0,
        pending_rollover_balance REAL DEFAULT 0.0,
        total_deposited REAL DEFAULT 0.0,
        total_withdrawn REAL DEFAULT 0.0,
        total_profit_earned REAL DEFAULT 0.0,
        device_token TEXT,
        is_admin INTEGER DEFAULT 0,
        is_compounding INTEGER DEFAULT 1,
        compounding_status TEXT DEFAULT 'ACTIVE',
        created_at TEXT NOT NULL,
        last_login_at TEXT
    )
    """)
    conn.commit()

    if not is_pg:
        # Try adding columns if existing SQLite DB
        for col_def in [
            "pending_rollover_balance REAL DEFAULT 0.0",
            "is_compounding INTEGER DEFAULT 1",
            "compounding_status TEXT DEFAULT 'ACTIVE'"
        ]:
            try:
                cursor.execute(f"ALTER TABLE users ADD COLUMN {col_def}")
                conn.commit()
            except Exception:
                pass

    # 2. Deposits Table
    cursor.execute(f"""
    CREATE TABLE IF NOT EXISTS deposits (
        id {pk_def},
        deposit_id TEXT UNIQUE NOT NULL,
        user_uuid TEXT NOT NULL,
        bep20_sender TEXT NOT NULL,
        destination_address TEXT NOT NULL,
        amount_usdt REAL NOT NULL,
        tx_hash TEXT UNIQUE NOT NULL,
        block_number INTEGER,
        status TEXT NOT NULL,
        created_at TEXT NOT NULL,
        verified_at TEXT
    )
    """)

    # 3. Withdrawals Table
    cursor.execute(f"""
    CREATE TABLE IF NOT EXISTS withdrawals (
        id {pk_def},
        withdrawal_id TEXT UNIQUE NOT NULL,
        user_uuid TEXT NOT NULL,
        bep20_recipient TEXT NOT NULL,
        amount_usdt REAL NOT NULL,
        status TEXT NOT NULL,
        tx_hash TEXT,
        created_at TEXT NOT NULL,
        completed_at TEXT
    )
    """)

    # 4. Vault Epochs Table
    cursor.execute(f"""
    CREATE TABLE IF NOT EXISTS vault_epochs (
        id {pk_def},
        epoch_id INTEGER UNIQUE NOT NULL,
        start_time TEXT NOT NULL,
        end_time TEXT,
        starting_pool_usdt REAL NOT NULL,
        ending_pool_usdt REAL,
        daily_pnl_usd REAL DEFAULT 0.0,
        daily_roi_pct REAL DEFAULT 0.0,
        platform_fee_collected REAL DEFAULT 0.0,
        status TEXT NOT NULL,
        settled_at TEXT
    )
    """)

    # 5. Epoch Shares Table
    cursor.execute(f"""
    CREATE TABLE IF NOT EXISTS epoch_shares (
        id {pk_def},
        epoch_id INTEGER NOT NULL,
        user_uuid TEXT NOT NULL,
        deposited_amount REAL NOT NULL,
        pool_share_pct REAL NOT NULL,
        profit_loss_earned REAL DEFAULT 0.0,
        created_at TEXT NOT NULL
    )
    """)

    # 6. Sweeps Table
    cursor.execute(f"""
    CREATE TABLE IF NOT EXISTS sweeps (
        id {pk_def},
        sweep_id TEXT UNIQUE NOT NULL,
        epoch_id INTEGER,
        amount_usdt REAL NOT NULL,
        from_address TEXT NOT NULL,
        to_address TEXT NOT NULL,
        method TEXT NOT NULL,
        tx_hash TEXT,
        created_at TEXT NOT NULL
    )
    """)

    # Create Indexes
    cursor.execute("CREATE INDEX IF NOT EXISTS idx_users_email ON users(email)")
    cursor.execute("CREATE INDEX IF NOT EXISTS idx_users_bep20 ON users(bep20_address)")
    cursor.execute("CREATE INDEX IF NOT EXISTS idx_deposits_tx ON deposits(tx_hash)")
    cursor.execute("CREATE INDEX IF NOT EXISTS idx_deposits_user ON deposits(user_uuid)")
    cursor.execute("CREATE INDEX IF NOT EXISTS idx_sweeps_epoch ON sweeps(epoch_id)")

    conn.commit()
    conn.close()
    db_type = "Neon PostgreSQL Cloud" if is_pg else "SQLite"
    print(f"[Database] ✅ Orbital Platform {db_type} initialized successfully!")


if __name__ == "__main__":
    init_platform_db()
