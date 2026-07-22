import yfinance as yf
import pandas as pd
import json
import os
import time
from datetime import datetime, timedelta
from sqlalchemy.orm import Session
from sqlalchemy.dialects.sqlite import insert as sqlite_insert
from sqlalchemy.dialects.postgresql import insert as pg_insert
from backend.data.database import ETFPrice, ETFMetadata, SessionLocal, init_db, IS_SQLITE

_TIMESTAMP_FILE = os.path.join(os.path.dirname(__file__), ".last_fetch.json")


def _get_last_fetch_time() -> datetime | None:
    if not os.path.exists(_TIMESTAMP_FILE):
        return None
    with open(_TIMESTAMP_FILE) as f:
        data = json.load(f)
    return datetime.fromisoformat(data["last_fetch"])


def _set_last_fetch_time():
    with open(_TIMESTAMP_FILE, "w") as f:
        json.dump({"last_fetch": datetime.now().isoformat()}, f)


def was_fetched_recently(hours: int = 24) -> bool:
    last = _get_last_fetch_time()
    return last is not None and (datetime.now() - last) < timedelta(hours=hours)

# ── ETF Universe ──────────────────────────────────────────────────────────────

ETFS = {
    # Sector ETFs
    "XLK":  ("Technology Select Sector SPDR", "Sector"),
    "XLF":  ("Financial Select Sector SPDR", "Sector"),
    "XLE":  ("Energy Select Sector SPDR", "Sector"),
    "XLV":  ("Health Care Select Sector SPDR", "Sector"),
    "XLI":  ("Industrial Select Sector SPDR", "Sector"),
    "XLB":  ("Materials Select Sector SPDR", "Sector"),
    "XLY":  ("Consumer Discretionary Select Sector SPDR", "Sector"),
    "XLP":  ("Consumer Staples Select Sector SPDR", "Sector"),
    "XLU":  ("Utilities Select Sector SPDR", "Sector"),
    "XLRE": ("Real Estate Select Sector SPDR", "Sector"),
    "XLC":  ("Communication Services Select Sector SPDR", "Sector"),

    # Broad Market ETFs
    "SPY":  ("SPDR S&P 500 ETF", "Broad Market"),
    "QQQ":  ("Invesco QQQ Trust (Nasdaq 100)", "Broad Market"),
    "IWM":  ("iShares Russell 2000 ETF", "Broad Market"),
    "VTI":  ("Vanguard Total Stock Market ETF", "Broad Market"),
    "EFA":  ("iShares MSCI EAFE ETF", "Broad Market"),
    "EEM":  ("iShares MSCI Emerging Markets ETF", "Broad Market"),
    "BND":  ("Vanguard Total Bond Market ETF", "Broad Market"),
    "GLD":  ("SPDR Gold Shares", "Broad Market"),

    # Thematic ETFs
    "ARKK": ("ARK Innovation ETF", "Thematic"),
    "ICLN": ("iShares Global Clean Energy ETF", "Thematic"),
    "CIBR": ("First Trust Cybersecurity ETF", "Thematic"),
    "ROBO": ("Robo Global Robotics & Automation ETF", "Thematic"),
    "HERO": ("Global X Video Games & Esports ETF", "Thematic"),
    "AWAY": ("ETFMG Travel Tech ETF", "Thematic"),
    "BOTZ": ("Global X Robotics & Artificial Intelligence ETF", "Thematic"),
    "FINX": ("Global X FinTech ETF", "Thematic"),
    "BITO": ("ProShares Bitcoin Strategy ETF", "Thematic"),

    # International ETFs
    "VEU":  ("Vanguard FTSE All-World ex-US ETF", "International"),
    "EWJ":  ("iShares MSCI Japan ETF", "International"),
    "INDA": ("iShares MSCI India ETF", "International"),
    "FXI":  ("iShares China Large-Cap ETF", "International"),
    "VWO":  ("Vanguard FTSE Emerging Markets ETF", "International"),

    # Commodity ETFs
    "USO":  ("United States Oil Fund", "Commodity"),
    "DBA":  ("Invesco DB Agriculture Fund", "Commodity"),
    "PDBC": ("Invesco Optimum Yield Diversified Commodity ETF", "Commodity"),

    # Factor ETFs
    "VTV":  ("Vanguard Value ETF", "Factor"),
    "VUG":  ("Vanguard Growth ETF", "Factor"),
    "MTUM": ("iShares MSCI USA Momentum Factor ETF", "Factor"),
    "QUAL": ("iShares MSCI USA Quality Factor ETF", "Factor"),
}

# ── Helpers ───────────────────────────────────────────────────────────────────

def seed_metadata(db: Session):
    """Insert ETF metadata if not already present."""
    for ticker, (name, category) in ETFS.items():
        existing = db.query(ETFMetadata).filter_by(ticker=ticker).first()
        if not existing:
            db.add(ETFMetadata(ticker=ticker, name=name, category=category))
    db.commit()
    print("ETF metadata seeded.")


def fetch_and_store(ticker: str, start: str, end: str, db: Session, max_retries: int = 3):
    """
    Fetch historical OHLCV data for a single ETF and store in SQLite.

    Retries with backoff when Yahoo Finance returns no data, since that's
    almost always a rate limit rather than a real "no data" case for an ETF
    this liquid — yfinance swallows the actual YFRateLimitError internally
    and just returns an empty DataFrame, so an empty result is the only
    signal we get. Datacenter/cloud IPs (Render, Railway, etc.) get rate
    limited by Yahoo far more aggressively than residential ones.
    """
    for attempt in range(max_retries):
        try:
            # timeout=15 — without it, a hung request to Yahoo Finance can
            # block indefinitely, stalling every ticker queued behind it.
            df = yf.download(ticker, start=start, end=end, auto_adjust=True, progress=False, timeout=15)
        except Exception as e:
            db.rollback()
            print(f"  [ERROR] {ticker}: {e}")
            return

        if df.empty:
            if attempt < max_retries - 1:
                wait = 20 * (attempt + 1)
                print(f"  [WARN] No data for {ticker} (likely rate-limited) — retrying in {wait}s...")
                time.sleep(wait)
                continue
            print(f"  [WARN] No data returned for {ticker} after {max_retries} attempts, giving up.")
            return

        try:
            # Flatten multi-level columns if present
            if isinstance(df.columns, pd.MultiIndex):
                df.columns = df.columns.get_level_values(0)

            df.reset_index(inplace=True)
            df.rename(columns={
                "Date": "date",
                "Open": "open",
                "High": "high",
                "Low": "low",
                "Close": "adj_close",  # auto_adjust=True makes Close = Adj Close
                "Volume": "volume"
            }, inplace=True)

            # Bulk upsert instead of a per-row SELECT-then-INSERT loop. The old
            # loop ran one round-trip query per row to check for an existing
            # record before inserting — fine against local SQLite, but against
            # a remote host like Neon each round trip pays full network
            # latency, so a single ~2,500-row ticker could take minutes. A
            # single INSERT ... ON CONFLICT DO NOTHING lets the database
            # handle duplicate detection in one statement.
            records = [
                {
                    "id": f"{ticker}_{row['date'].date()}",
                    "ticker": ticker,
                    "date": row["date"].date(),
                    "open": row.get("open"),
                    "high": row.get("high"),
                    "low": row.get("low"),
                    "close": row.get("adj_close"),
                    "adj_close": row.get("adj_close"),
                    "volume": row.get("volume"),
                }
                for _, row in df.iterrows()
            ]

            insert_fn = sqlite_insert if IS_SQLITE else pg_insert
            stmt = insert_fn(ETFPrice).values(records).on_conflict_do_nothing(index_elements=["id"])
            result = db.execute(stmt)
            db.commit()
            records_added = result.rowcount if result.rowcount and result.rowcount > 0 else 0
            print(f"  [OK] {ticker}: {records_added} new records added.")
        except Exception as e:
            db.rollback()
            print(f"  [ERROR] {ticker}: {e}")

        return  # success (or a non-retryable processing error) — either way, don't retry


# ── Main Entry Points ─────────────────────────────────────────────────────────

def seed_historical(years: int = 10):
    """Pull full historical data for all ETFs on first run."""
    end = datetime.today().strftime("%Y-%m-%d")
    start = (datetime.today() - timedelta(days=365 * years)).strftime("%Y-%m-%d")

    print(f"Seeding historical data from {start} to {end}...")
    db = SessionLocal()
    try:
        seed_metadata(db)
        for ticker in ETFS:
            print(f"Fetching {ticker}...")
            fetch_and_store(ticker, start, end, db)
            time.sleep(1.5)  # space out requests — avoids tripping Yahoo Finance's rate limit in the first place
    finally:
        db.close()
    _set_last_fetch_time()
    print("Historical seed complete.")


def fetch_latest():
    """Pull only the latest 5 days of data — used by the scheduler."""
    end = datetime.today().strftime("%Y-%m-%d")
    start = (datetime.today() - timedelta(days=5)).strftime("%Y-%m-%d")

    print(f"Fetching latest data ({start} to {end})...")
    db = SessionLocal()
    try:
        for ticker in ETFS:
            fetch_and_store(ticker, start, end, db)
            time.sleep(1.5)
    finally:
        db.close()
    _set_last_fetch_time()
    print("Latest fetch complete.")


if __name__ == "__main__":
    init_db()
    seed_historical(years=10)