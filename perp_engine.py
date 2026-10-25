import os
import json
import hashlib
import duckdb
import requests
from datetime import datetime, timezone

DB_FILE = "data/perp_funding.db"
HISTORY_DIR = "data/history"
EXPORT_DIR = "public"
API_DIR = os.path.join(EXPORT_DIR, "v1")

BINANCE_FUTURES_URL = "https://fapi.binance.com/fapi/v1/premiumIndex"
HYPERLIQUID_INFO_URL = "https://api.hyperliquid.xyz/info"

WATCHED_SYMBOLS = ["BTC", "ETH", "SOL", "AVAX", "BNB", "DOGE", "SUI", "NEAR", "APT", "ARB"]

def compute_hash(payload: dict) -> str:
    canonical = json.dumps(payload, sort_keys=True, separators=(",", ":")).encode("utf-8")
    return hashlib.sha256(canonical).hexdigest()

def fetch_binance_funding():
    results = []
    headers = {"User-Agent": "PerpFundingDeltaWire/1.0"}
    try:
        r = requests.get(BINANCE_FUTURES_URL, headers=headers, timeout=15)
        if r.status_code == 200:
            for item in r.json():
                symbol = item.get("symbol", "")
                base = symbol.replace("USDT", "")
                if symbol.endswith("USDT") and base in WATCHED_SYMBOLS:
                    rate_8h = float(item.get("lastFundingRate", 0.0))
                    mark = float(item.get("markPrice", 0.0))
                    index = float(item.get("indexPrice", 0.0))
                    annualized = rate_8h * 3 * 365 * 100.0
                    basis_spread = ((mark - index) / index * 100.0) if index > 0 else 0.0

                    direction = "SHORT_PERP_LONG_SPOT" if rate_8h > 0 else "LONG_PERP_SHORT_SPOT"

                    results.append({
                        "symbol": f"{base}-PERP",
                        "exchange": "Binance",
                        "funding_rate_8h": rate_8h,
                        "annualized_funding_pct": round(annualized, 2),
                        "mark_price": mark,
                        "index_price": index,
                        "basis_spread_pct": round(basis_spread, 4),
                        "arbitrage_direction": direction
                    })
    except Exception as e:
        print(f"Binance fetch error: {e}")
    return results

def fetch_hyperliquid_funding():
    results = []
    headers = {"User-Agent": "PerpFundingDeltaWire/1.0", "Content-Type": "application/json"}
    try:
        payload = {"type": "metaAndAssetCtxs"}
        r = requests.post(HYPERLIQUID_INFO_URL, headers=headers, json=payload, timeout=15)
        if r.status_code == 200:
            data = r.json()
            universe = data[0].get("universe", [])
            contexts = data[1] if len(data) > 1 else []
            for meta, ctx in zip(universe, contexts):
                name = meta.get("name", "")
                if name in WATCHED_SYMBOLS:
                    rate_1h = float(ctx.get("funding", 0.0))
                    rate_8h = rate_1h * 8
                    mark = float(ctx.get("markPx", 0.0))
                    oracle = float(ctx.get("oraclePx", 0.0))
                    annualized = rate_1h * 24 * 365 * 100.0
                    basis_spread = ((mark - oracle) / oracle * 100.0) if oracle > 0 else 0.0

                    direction = "SHORT_PERP_LONG_SPOT" if rate_1h > 0 else "LONG_PERP_SHORT_SPOT"

                    results.append({
                        "symbol": f"{name}-PERP",
                        "exchange": "Hyperliquid",
                        "funding_rate_8h": round(rate_8h, 6),
                        "annualized_funding_pct": round(annualized, 2),
                        "mark_price": mark,
                        "index_price": oracle,
                        "basis_spread_pct": round(basis_spread, 4),
                        "arbitrage_direction": direction
                    })
    except Exception as e:
        print(f"Hyperliquid fetch error: {e}")
    return results

def harvest_funding_data():
    all_rates = []
    all_rates.extend(fetch_binance_funding())
    all_rates.extend(fetch_hyperliquid_funding())

    normalized = []
    for r in all_rates:
        hash_payload = {
            "symbol": r["symbol"],
            "exchange": r["exchange"],
            "rate_8h": r["funding_rate_8h"],
            "direction": r["arbitrage_direction"]
        }
        r["content_hash"] = compute_hash(hash_payload)
        normalized.append(r)

    normalized.sort(key=lambda x: abs(x["annualized_funding_pct"]), reverse=True)
    return normalized

def build_static_api(conn):
    os.makedirs(API_DIR, exist_ok=True)
    now_iso = datetime.now(timezone.utc).isoformat()

    cur = conn.execute("SELECT * FROM funding_rates ORDER BY ABS(annualized_funding_pct) DESC")
    cols = [desc[0] for desc in cur.description]
    all_rates = [dict(zip(cols, row)) for row in cur.fetchall()]

    with open(os.path.join(API_DIR, "funding-spreads.json"), "w", encoding="utf-8") as f:
        json.dump({"metadata": {"updated_at": now_iso, "count": len(all_rates)}, "rates": all_rates}, f, indent=2)

    top_opportunities = [r for r in all_rates if abs(r["annualized_funding_pct"]) >= 10.0]
    with open(os.path.join(API_DIR, "top-arbitrage.json"), "w", encoding="utf-8") as f:
        json.dump({"metadata": {"updated_at": now_iso, "count": len(top_opportunities)}, "opportunities": top_opportunities}, f, indent=2)

    lines = [
        "# Perp Funding Delta Wire",
        f"> Last Sync: {now_iso} UTC",
        "> Optimization: Pre-calculated annualized basis yields and cash-and-carry arbitrage directions.",
        "",
        "## Top Funding Rate Opportunities (Annualized Yield >= 10%)"
    ]
    for r in top_opportunities[:15]:
        lines.append(
            f"- **{r['symbol']}** ({r['exchange']}): **{r['annualized_funding_pct']:+.2f}% APR** "
            f"(8h: {r['funding_rate_8h']:+.4%}) | Strategy: `{r['arbitrage_direction']}` | Basis: {r['basis_spread_pct']:+.3f}%"
        )

    with open(os.path.join(EXPORT_DIR, "llms.txt"), "w", encoding="utf-8") as f:
        f.write("\n".join(lines) + "\n")

    html = f"""<!DOCTYPE html><html><head><title>Perp Funding Delta Wire</title></head>
    <body style='font-family:system-ui,sans-serif;max-width:900px;margin:2rem auto;line-height:1.6;padding:0 1rem;'>
    <h1>📈 Perp Funding Delta Wire</h1>
    <p>Real-time perpetual swap funding rate spreads and cash-and-carry yields for quantitative agents.</p>
    <h3>Machine Feeds</h3>
    <ul>
      <li><a href='v1/top-arbitrage.json'>/v1/top-arbitrage.json</a> (High-Yield Arbitrage Opportunities)</li>
      <li><a href='v1/funding-spreads.json'>/v1/funding-spreads.json</a> (Full Multi-Exchange Market Matrix)</li>
      <li><a href='llms.txt'>llms.txt</a> (Token-Efficient LLM Digest)</li>
      <li><a href='funding.parquet'>funding.parquet</a> (Columnar Parquet Snapshot)</li>
    </ul>
    <h3>Top Funding Spreads</h3>
    <table border="1" cellpadding="6" style="border-collapse:collapse;width:100%;text-align:left;">
      <tr><th>Symbol</th><th>Exchange</th><th>8h Rate</th><th>Annualized APR</th><th>Basis Spread</th><th>Action</th></tr>
      {"".join([f"<tr><td><strong>{r['symbol']}</strong></td><td>{r['exchange']}</td><td>{r['funding_rate_8h']:+.4%}</td><td><strong>{r['annualized_funding_pct']:+.2f}%</strong></td><td>{r['basis_spread_pct']:+.3f}%</td><td><code>{r['arbitrage_direction']}</code></td></tr>" for r in all_rates[:12]])}
    </table>
    </body></html>"""
    with open(os.path.join(EXPORT_DIR, "index.html"), "w", encoding="utf-8") as f:
        f.write(html)

def run():
    os.makedirs("data", exist_ok=True)
    os.makedirs(HISTORY_DIR, exist_ok=True)
    os.makedirs(EXPORT_DIR, exist_ok=True)

    conn = duckdb.connect(DB_FILE)
    with open("schema.sql", "r", encoding="utf-8") as f:
        conn.execute(f.read())

    now = datetime.now(timezone.utc)
    now_iso = now.isoformat()
    date_str = now.strftime("%Y-%m-%d")
    year_str = now.strftime("%Y")
    month_str = now.strftime("%m")

    month_dir = os.path.join(HISTORY_DIR, year_str, month_str)
    os.makedirs(month_dir, exist_ok=True)
    daily_history_file = os.path.join(month_dir, f"{date_str}.jsonl")

    records = harvest_funding_data()

    conn.execute("BEGIN TRANSACTION")

    for r in records:
        sym = r["symbol"].replace("'", "''")
        exch = r["exchange"].replace("'", "''")
        rate_8h = r["funding_rate_8h"]
        apr = r["annualized_funding_pct"]
        mark = r["mark_price"]
        idx = r["index_price"]
        basis = r["basis_spread_pct"]
        direction = r["arbitrage_direction"].replace("'", "''")
        h = r["content_hash"]

        existing = conn.execute(f"""
            SELECT content_hash, annualized_funding_pct 
            FROM funding_rates 
            WHERE symbol = '{sym}' AND exchange = '{exch}'
        """).fetchone()

        if not existing:
            conn.execute(f"""
                INSERT INTO funding_rates (
                    symbol, exchange, funding_rate_8h, annualized_funding_pct,
                    mark_price, index_price, basis_spread_pct, arbitrage_direction,
                    content_hash, last_updated_utc
                ) VALUES (
                    '{sym}', '{exch}', {rate_8h}, {apr},
                    {mark}, {idx}, {basis}, '{direction}',
                    '{h}', '{now_iso}'
                )
            """)

            commit_id = conn.execute("SELECT nextval('seq_commit_id')").fetchone()[0]
            conn.execute(f"""
                INSERT INTO ledger (commit_id, timestamp_utc, operation, symbol, exchange, annualized_funding_pct, detail)
                VALUES ({commit_id}, '{now_iso}', 'INIT_RATE', '{sym}', '{exch}', {apr}, 'Initial funding observation')
            """)

            entry = {
                "commit_id": commit_id, "timestamp_utc": now_iso, "operation": "INIT_RATE",
                "symbol": sym, "exchange": exch, "apr": apr, "content_hash": h
            }
            with open(daily_history_file, "a", encoding="utf-8") as f:
                f.write(json.dumps(entry) + "\n")

        elif existing[0] != h:
            old_apr = existing[1]
            conn.execute(f"""
                UPDATE funding_rates SET
                    funding_rate_8h = {rate_8h},
                    annualized_funding_pct = {apr},
                    mark_price = {mark},
                    index_price = {idx},
                    basis_spread_pct = {basis},
                    arbitrage_direction = '{direction}',
                    content_hash = '{h}',
                    last_updated_utc = '{now_iso}'
                WHERE symbol = '{sym}' AND exchange = '{exch}'
            """)

            commit_id = conn.execute("SELECT nextval('seq_commit_id')").fetchone()[0]
            conn.execute(f"""
                INSERT INTO ledger (commit_id, timestamp_utc, operation, symbol, exchange, annualized_funding_pct, detail)
                VALUES ({commit_id}, '{now_iso}', 'RATE_DELTA', '{sym}', '{exch}', {apr}, 'APR delta: {apr - old_apr:+.2f}%')
            """)

            entry = {
                "commit_id": commit_id, "timestamp_utc": now_iso, "operation": "RATE_DELTA",
                "symbol": sym, "exchange": exch, "old_apr": old_apr, "new_apr": apr, "content_hash": h
            }
            with open(daily_history_file, "a", encoding="utf-8") as f:
                f.write(json.dumps(entry) + "\n")

    conn.execute("COMMIT")

    conn.execute(f"COPY (SELECT symbol, exchange, funding_rate_8h, annualized_funding_pct, mark_price, index_price, basis_spread_pct, arbitrage_direction, last_updated_utc FROM funding_rates) TO '{EXPORT_DIR}/funding.parquet' (FORMAT PARQUET)")
    build_static_api(conn)
    conn.close()

if __name__ == "__main__":
    run()
