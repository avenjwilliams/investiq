from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from sqlalchemy import func
from typing import Optional
from datetime import date

from backend.data.database import get_db, ETFPrice, ETFMetadata

router = APIRouter(prefix="/etfs", tags=["ETFs"])


@router.get("/")
def list_etfs(db: Session = Depends(get_db)):
    """List all ETFs in the universe with metadata."""
    etfs = db.query(ETFMetadata).all()
    return [
        {
            "ticker": e.ticker,
            "name": e.name,
            "category": e.category,
            "last_updated": e.last_updated,
        }
        for e in etfs
    ]


@router.get("/summary")
def database_summary(db: Session = Depends(get_db)):
    """High-level summary of what's in the database."""
    total_records = db.query(func.count(ETFPrice.id)).scalar()
    total_etfs = db.query(func.count(ETFMetadata.ticker)).scalar()
    earliest_date = db.query(func.min(ETFPrice.date)).scalar()
    latest_date = db.query(func.max(ETFPrice.date)).scalar()

    return {
        "total_etfs": total_etfs,
        "total_price_records": total_records,
        "date_range": {
            "from": str(earliest_date),
            "to": str(latest_date),
        }
    }


@router.get("/{ticker}/prices")
def get_prices(
    ticker: str,
    start: Optional[date] = None,
    end: Optional[date] = None,
    db: Session = Depends(get_db)
):
    """Get price history for a specific ETF. Optionally filter by date range."""
    ticker = ticker.upper()

    # Check ETF exists
    etf = db.query(ETFMetadata).filter_by(ticker=ticker).first()
    if not etf:
        raise HTTPException(status_code=404, detail=f"ETF '{ticker}' not found.")

    query = db.query(ETFPrice).filter(ETFPrice.ticker == ticker)
    if start:
        query = query.filter(ETFPrice.date >= start)
    if end:
        query = query.filter(ETFPrice.date <= end)

    prices = query.order_by(ETFPrice.date.asc()).all()

    return {
        "ticker": ticker,
        "name": etf.name,
        "category": etf.category,
        "count": len(prices),
        "prices": [
            {
                "date": str(p.date),
                "open": p.open,
                "high": p.high,
                "low": p.low,
                "close": p.close,
                "adj_close": p.adj_close,
                "volume": p.volume,
            }
            for p in prices
        ]
    }


@router.get("/{ticker}/latest")
def get_latest(ticker: str, db: Session = Depends(get_db)):
    """Get the most recent price record for a specific ETF."""
    ticker = ticker.upper()

    etf = db.query(ETFMetadata).filter_by(ticker=ticker).first()
    if not etf:
        raise HTTPException(status_code=404, detail=f"ETF '{ticker}' not found.")

    latest = (
        db.query(ETFPrice)
        .filter(ETFPrice.ticker == ticker)
        .order_by(ETFPrice.date.desc())
        .first()
    )

    if not latest:
        raise HTTPException(status_code=404, detail=f"No price data found for '{ticker}'.")

    return {
        "ticker": ticker,
        "name": etf.name,
        "date": str(latest.date),
        "open": latest.open,
        "high": latest.high,
        "low": latest.low,
        "close": latest.close,
        "adj_close": latest.adj_close,
        "volume": latest.volume,
    }