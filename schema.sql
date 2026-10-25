CREATE SEQUENCE IF NOT EXISTS seq_commit_id START 1;

CREATE TABLE IF NOT EXISTS funding_rates (
    symbol VARCHAR,
    exchange VARCHAR,
    funding_rate_8h DOUBLE,
    annualized_funding_pct DOUBLE,
    mark_price DOUBLE,
    index_price DOUBLE,
    basis_spread_pct DOUBLE,
    arbitrage_direction VARCHAR,
    content_hash VARCHAR,
    last_updated_utc VARCHAR,
    PRIMARY KEY (symbol, exchange)
);

CREATE TABLE IF NOT EXISTS ledger (
    commit_id BIGINT PRIMARY KEY,
    timestamp_utc VARCHAR,
    operation VARCHAR,
    symbol VARCHAR,
    exchange VARCHAR,
    annualized_funding_pct DOUBLE,
    detail VARCHAR
);
