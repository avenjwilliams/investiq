import os
import uuid
import requests
from datetime import datetime, timedelta
from typing import Optional
from sqlalchemy.orm import Session
from sqlalchemy.dialects.sqlite import insert as sqlite_insert

from backend.data.database import ETFMetadata, SentimentRecord

# torch/transformers are NOT imported at module level on purpose — importing
# them eagerly means every app startup pays their load cost (noticeably slow,
# and memory-heavy) before the server can even bind to a port, which caused
# Render's free-tier deploy to time out during its port scan. Deferred into
# get_finbert() below so they only load on the first actual sentiment request.

# ── Config ────────────────────────────────────────────────────────────────────

NEWS_API_KEY = os.getenv("NEWS_API_KEY")
NEWS_API_URL = "https://newsapi.org/v2/everything"

# FinBERT — finance-specific sentiment model
# Downloaded automatically on first use (~400MB, one-time download)
_finbert = None

def get_finbert():
    """Lazy-load FinBERT (and torch/transformers themselves) so nothing in
    this module costs anything until the first actual sentiment request."""
    global _finbert
    if _finbert is None:
        import torch  # noqa: F401 — transformers needs torch importable, even if unused directly here
        from transformers import pipeline

        print("Loading FinBERT model (first-time download may take a minute)...")
        _finbert = pipeline(
            "text-classification",
            model="ProsusAI/finbert",
            tokenizer="ProsusAI/finbert",
            top_k=None,
            framework="pt"  # explicitly use PyTorch
        )
        print("FinBERT loaded.")
    return _finbert


# ── News Fetching ─────────────────────────────────────────────────────────────

def fetch_news(ticker: str, company_name: str, days_back: int = 7) -> list:
    """Fetch recent news headlines for an ETF from NewsAPI."""
    if not NEWS_API_KEY:
        raise ValueError("NEWS_API_KEY not set in environment variables.")

    from_date = (datetime.today() - timedelta(days=days_back)).strftime("%Y-%m-%d")

    # Use ticker + simplified company name for better results
    query = f"{ticker} ETF"

    params = {
        "q": query,
        "from": from_date,
        "sortBy": "relevancy",
        "language": "en",
        "pageSize": 20,
        "apiKey": NEWS_API_KEY,
    }

    response = requests.get(NEWS_API_URL, params=params, timeout=10)
    response.raise_for_status()

    articles = response.json().get("articles", [])
    return [
        {
            "headline": a.get("title", ""),
            "source": a.get("source", {}).get("name", "Unknown"),
            "published_at": a.get("publishedAt", ""),
        }
        for a in articles
        if a.get("title") and "[Removed]" not in a.get("title", "")
    ]


# ── Sentiment Analysis ────────────────────────────────────────────────────────

def analyze_headline(headline: str) -> dict:
    """Run a single headline through FinBERT and return scores."""
    finbert = get_finbert()

    # FinBERT max token length is 512 — truncate long headlines
    truncated = headline[:512]
    results = finbert(truncated)[0]

    scores = {r["label"].lower(): r["score"] for r in results}
    dominant = max(scores, key=scores.get)

    return {
        "sentiment": dominant,
        "positive_score": round(scores.get("positive", 0), 4),
        "negative_score": round(scores.get("negative", 0), 4),
        "neutral_score": round(scores.get("neutral", 0), 4),
    }


# ── Main Entry Point ──────────────────────────────────────────────────────────

def get_ticker_sentiment(ticker: str, db: Session, days_back: int = 7) -> dict:
    """
    Fetch news for a ticker, run through FinBERT, store results, return summary.
    """
    meta = db.query(ETFMetadata).filter_by(ticker=ticker).first()
    if not meta:
        raise ValueError(f"ETF '{ticker}' not found.")

    # Fetch headlines
    articles = fetch_news(ticker, meta.name, days_back=days_back)
    if not articles:
        return {
            "ticker": ticker,
            "name": meta.name,
            "articles_analyzed": 0,
            "message": "No recent news found for this ETF.",
            "overall_sentiment": "neutral",
            "scores": {"positive": 0, "negative": 0, "neutral": 1.0},
            "headlines": []
        }

    # Analyze each headline
    analyzed = []
    for article in articles:
        headline = article["headline"]
        scores = analyze_headline(headline)

        # Store in DB — use INSERT OR IGNORE to skip duplicates
        record_id = str(uuid.uuid5(uuid.NAMESPACE_DNS, f"{ticker}_{headline}"))
        pub = article.get("published_at", "")
        try:
            pub_dt = datetime.strptime(pub, "%Y-%m-%dT%H:%M:%SZ")
        except Exception:
            pub_dt = datetime.utcnow()

        stmt = sqlite_insert(SentimentRecord).values(
            id=record_id,
            ticker=ticker,
            headline=headline,
            source=article["source"],
            published_at=pub_dt,
            sentiment=scores["sentiment"],
            positive_score=scores["positive_score"],
            negative_score=scores["negative_score"],
            neutral_score=scores["neutral_score"],
            fetched_at=datetime.utcnow(),
        ).on_conflict_do_nothing(index_elements=["id"])
        db.execute(stmt)

        analyzed.append({
            "headline": headline,
            "source": article["source"],
            "published_at": article["published_at"],
            **scores
        })

    db.commit()

    # Aggregate scores
    n = len(analyzed)
    avg_positive = round(sum(a["positive_score"] for a in analyzed) / n, 4)
    avg_negative = round(sum(a["negative_score"] for a in analyzed) / n, 4)
    avg_neutral = round(sum(a["neutral_score"] for a in analyzed) / n, 4)

    overall = max(
        {"positive": avg_positive, "negative": avg_negative, "neutral": avg_neutral},
        key=lambda k: {"positive": avg_positive, "negative": avg_negative, "neutral": avg_neutral}[k]
    )

    sentiment_counts = {"positive": 0, "negative": 0, "neutral": 0}
    for a in analyzed:
        sentiment_counts[a["sentiment"]] += 1

    return {
        "ticker": ticker,
        "name": meta.name,
        "articles_analyzed": n,
        "overall_sentiment": overall,
        "scores": {
            "positive": avg_positive,
            "negative": avg_negative,
            "neutral": avg_neutral,
        },
        "sentiment_breakdown": {
            k: f"{round(v / n * 100, 1)}%" for k, v in sentiment_counts.items()
        },
        "headlines": analyzed,
    }