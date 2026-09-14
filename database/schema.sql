-- SQLite Schema for Emerging Stock Board (ESB) Market Making Analytics

CREATE TABLE IF NOT EXISTS broker_master (
    broker_code TEXT PRIMARY KEY,
    broker_name TEXT NOT NULL,
    branch_name TEXT,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS stock_master (
    stock_id TEXT PRIMARY KEY,
    stock_name TEXT NOT NULL,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS daily_broker_trades (
    trade_date TEXT NOT NULL,
    stock_id TEXT NOT NULL,
    broker_code TEXT NOT NULL,
    broker_name TEXT,
    is_t INTEGER NOT NULL DEFAULT 0,
    buy_qty INTEGER NOT NULL DEFAULT 0,
    buy_amount REAL NOT NULL DEFAULT 0.0,
    buy_avg_price REAL,
    buy_ratio REAL NOT NULL DEFAULT 0.0,
    sell_qty INTEGER NOT NULL DEFAULT 0,
    sell_amount REAL NOT NULL DEFAULT 0.0,
    sell_avg_price REAL,
    sell_ratio REAL NOT NULL DEFAULT 0.0,
    net_qty INTEGER NOT NULL DEFAULT 0,
    PRIMARY KEY (trade_date, stock_id, broker_code)
);

CREATE TABLE IF NOT EXISTS daily_stock_pnl (
    trade_date TEXT NOT NULL,
    stock_id TEXT NOT NULL,
    stock_name TEXT,
    buy_qty INTEGER NOT NULL DEFAULT 0,
    buy_amount REAL NOT NULL DEFAULT 0.0,
    buy_vwap REAL NOT NULL DEFAULT 0.0,
    sell_qty INTEGER NOT NULL DEFAULT 0,
    sell_amount REAL NOT NULL DEFAULT 0.0,
    sell_vwap REAL NOT NULL DEFAULT 0.0,
    matched_qty INTEGER NOT NULL DEFAULT 0,
    gross_spread_pnl REAL NOT NULL DEFAULT 0.0,
    transaction_cost REAL NOT NULL DEFAULT 0.0,
    total_estimated_mm_pnl REAL NOT NULL DEFAULT 0.0,
    PRIMARY KEY (trade_date, stock_id)
);

CREATE TABLE IF NOT EXISTS daily_mm_allocation (
    trade_date TEXT NOT NULL,
    stock_id TEXT NOT NULL,
    broker_code TEXT NOT NULL,
    broker_name TEXT,
    buy_qty INTEGER NOT NULL DEFAULT 0,
    sell_qty INTEGER NOT NULL DEFAULT 0,
    total_volume INTEGER NOT NULL DEFAULT 0,
    volume_share REAL NOT NULL DEFAULT 0.0,
    allocated_pnl REAL NOT NULL DEFAULT 0.0,
    PRIMARY KEY (trade_date, stock_id, broker_code)
);

CREATE INDEX IF NOT EXISTS idx_trades_date_stock ON daily_broker_trades(trade_date, stock_id);
CREATE INDEX IF NOT EXISTS idx_stock_pnl_date ON daily_stock_pnl(trade_date);
CREATE INDEX IF NOT EXISTS idx_allocation_date_broker ON daily_mm_allocation(trade_date, broker_code);
