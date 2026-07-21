from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session
from sqlalchemy import desc

from backend.data.database import get_db, ETFMetadata, SentimentRecord
from backend.analytics.sentiment import get_ticker_sentiment

router = APIRouter(prefix="/sentiment", tags=["Sentiment Analysis"])


@router.get("/{ticker}")
def get_sentiment(
    ticker: str,
    days_back: int = Query(default=7, ge=1, le=30),
    db: Session = Depends(get_db)
):
    """
    Fetch and analyze recent news sentiment for a specific ETF.
    - **days_back**: How many days of news to look back (1-30, default 7)
    """
    ticker = ticker.upper()

    etf = db.query(ETFMetadata).filter_by(ticker=ticker).first()
    if not etf:
        raise HTTPException(status_code=404, detail=f"ETF '{ticker}' not found.")

    try:
        result = get_ticker_sentiment(ticker, db, days_back=days_back)
        return result
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/{ticker}/history")
def get_sentiment_history(
    ticker: str,
    limit: int = Query(default=50, ge=1, le=200),
    db: Session = Depends(get_db)
):
    """Get historical sentiment records stored in the database for a ticker."""
    ticker = ticker.upper()

    records = (
        db.query(SentimentRecord)
        .filter(SentimentRecord.ticker == ticker)
        .order_by(desc(SentimentRecord.published_at))
        .limit(limit)
        .all()
    )

    return {
        "ticker": ticker,
        "count": len(records),
        "records": [
            {
                "headline": r.headline,
                "source": r.source,
                "published_at": str(r.published_at),
                "sentiment": r.sentiment,
                "positive_score": r.positive_score,
                "negative_score": r.negative_score,
                "neutral_score": r.neutral_score,
            }
            for r in records
        ]
    }


@router.get("/")
def get_all_sentiment(
    days_back: int = Query(default=7, ge=1, le=30),
    db: Session = Depends(get_db)
):
    """
    Get sentiment summary for all ETFs.
    Note: This calls NewsAPI for each ETF — use sparingly on the free tier.
    """
    etfs = db.query(ETFMetadata).all()
    results = []

    for etf in etfs:
        try:
            result = get_ticker_sentiment(etf.ticker, db, days_back=days_back)
            results.append({
                "ticker": result["ticker"],
                "name": result["name"],
                "overall_sentiment": result["overall_sentiment"],
                "scores": result["scores"],
                "articles_analyzed": result["articles_analyzed"],
            })
        except Exception as e:
            results.append({
                "ticker": etf.ticker,
                "name": etf.name,
                "error": str(e)
            })

    return results