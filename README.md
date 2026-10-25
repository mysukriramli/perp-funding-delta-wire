# 📈 Perp Funding Delta Wire

An autonomous, zero-maintenance quantitative data infrastructure running entirely on GitHub Actions. It monitors live perpetual swap funding rates across centralized and decentralized venues (Binance, Hyperliquid), calculates annualized basis yields, and emits deterministic trade parameters for AI agents.

## Token Impact
- **Deterministic Math**: Eliminates LLM floating-point division and annualized compounding errors.
- **Input Overhead**: Replaces 10,000+ tokens of multi-exchange order-book and rate logs with an 80-token pre-computed matrix.

## Machine Feeds
- [`v1/top-arbitrage.json`](public/v1/top-arbitrage.json) (High-yield signals)
- [`v1/funding-spreads.json`](public/v1/funding-spreads.json) (Market matrix)
- [`llms.txt`](public/llms.txt) (Token-efficient LLM digest)
- `funding.parquet` (Columnar database snapshot)

## Architecture
- **Ingestion**: Public REST endpoints from Binance Futures and Hyperliquid DEX
- **Engine**: Python Quantitative Engine + DuckDB
- **Ledger**: Append-only Git-committed JSONL in `/data/history`
- **Edge CDN**: GitHub Pages (Fastly CDN)
