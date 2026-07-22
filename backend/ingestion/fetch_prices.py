import yfinance as yf
import pandas as pd
import json
import os
from datetime import datetime, timedelta
from sqlalchemy.orm import Session
from backend.data.database import ETFPrice, ETFMetadata, SessionLocal, init_db

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


def fetch_and_store(ticker: str, start: str, end: str, db: Session):
    """Fetch historical OHLCV data for a single ETF and store in SQLite."""
    try:
        # timeout=15 — without it, a rate-limited/hung request to Yahoo
        # Finance (common from datacenter IPs) can block indefinitely,
        # stalling every ticker queued behind it.
        df = yf.download(ticker, start=start, end=end, auto_adjust=True, progress=False, timeout=15)

        if df.empty:
            print(f"  [WARN] No data returned for {ticker}")
            return

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

        records_added = 0
        for _, row in df.iterrows():
            record_id = f"{ticker}_{row['date'].date()}"
            existing = db.query(ETFPrice).filter_by(id=record_id).first()
            if not existing:
                db.add(ETFPrice(
                    id=record_id,
                    ticker=ticker,
                    date=row["date"].date(),
                    open=row.get("open"),
                    high=row.get("high"),
                    low=row.get("low"),
                    close=row.get("adj_close"),
                    adj_close=row.get("adj_close"),
                    volume=row.get("volume"),
                ))
                records_added += 1

        db.commit()
        print(f"  [OK] {ticker}: {records_added} new records added.")

    except Exception as e:
        db.rollback()
        print(f"  [ERROR] {ticker}: {e}")


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
    finally:
        db.close()
    _set_last_fetch_time()
    print("Latest fetch complete.")


if __name__ == "__main__":
    init_db()
    seed_historical(years=10)