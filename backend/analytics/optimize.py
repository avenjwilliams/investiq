import json
import os
import numpy as np
import pandas as pd
import yfinance as yf
from pypfopt import expected_returns, risk_models, EfficientFrontier
from pypfopt.black_litterman import BlackLittermanModel, market_implied_prior_returns, market_implied_risk_aversion
from pypfopt.discrete_allocation import DiscreteAllocation, get_latest_prices
from sqlalchemy.orm import Session

from backend.data.database import ETFPrice, ETFMetadata, SessionLocal


def load_price_matrix(db: Session) -> pd.DataFrame:
    """
    Pull adjusted close prices from the database and return a
    DataFrame with dates as the index and tickers as columns.
    """
    records = db.query(ETFPrice.date, ETFPrice.ticker, ETFPrice.adj_close).all()

    if not records:
        raise ValueError("No price data found in the database.")

    df = pd.DataFrame(records, columns=["date", "ticker", "adj_close"])
    df["date"] = pd.to_datetime(df["date"])

    # Pivot to wide format: rows = dates, columns = tickers
    price_matrix = df.pivot(index="date", columns="ticker", values="adj_close")
    price_matrix.sort_index(inplace=True)

    # Drop any columns with too many missing values (>10%)
    threshold = 0.9 * len(price_matrix)
    price_matrix = price_matrix.dropna(axis=1, thresh=int(threshold))
    price_matrix.ffill(inplace=True)

    return price_matrix


def run_black_litterman(db: Session) -> dict:
    """
    Black-Litterman portfolio optimization.

    Pipeline:
      1. Market cap weights (ETF total assets via yfinance) → equilibrium prior returns
      2. Transformer 90-day forecasts → absolute views (annualized)
      3. Per-ticker directional accuracy → view confidences
      4. BL posterior returns → Max Sharpe allocation

    Falls back to equal weights for any ETF where market cap data is unavailable.
    Skips the view for any ETF whose forecast fails.
    """
    from backend.analytics.forecast_transformer import predict_all_pct_changes, model_exists, METRICS_PATH

    if not model_exists():
        raise ValueError(
            "Transformer model not trained yet. Run POST /forecast/transformer/train-all first — "
            "Black-Litterman uses the forecasts as views."
        )

    price_matrix = load_price_matrix(db)
    tickers = list(price_matrix.columns)

    S = risk_models.CovarianceShrinkage(price_matrix).ledoit_wolf()

    # ── 1. Market cap weights ─────────────────────────────────────────────────
    print("[BL] Fetching market cap weights...")
    market_caps = {}
    for ticker in tickers:
        try:
            info = yf.Ticker(ticker).info
            # totalAssets = AUM for ETFs; fall back to marketCap for stocks
            aum = info.get("totalAssets") or info.get("marketCap")
            if aum and aum > 0:
                market_caps[ticker] = float(aum)
        except Exception:
            pass

    if len(market_caps) < len(tickers) * 0.5:
        raise ValueError("Could not retrieve market cap data for enough ETFs.")

    # Fill any missing tickers with the median AUM to stay neutral
    median_aum = float(np.median(list(market_caps.values())))
    mcap_series = pd.Series(
        {t: market_caps.get(t, median_aum) for t in tickers}
    )
    mcap_weights = mcap_series / mcap_series.sum()

    # ── 2. Market equilibrium returns (reverse-optimised from mcap weights) ───
    delta = market_implied_risk_aversion(price_matrix.iloc[:, 0])  # uses SPY-like proxy
    # Use a fixed delta=2.5 (standard BL assumption) — more stable than data-derived
    delta = 2.5
    pi = market_implied_prior_returns(mcap_weights, delta, S)

    # ── 3. Transformer views: 90-day forecast → annualised return ─────────────
    # Load per-ticker directional accuracy for confidence weighting
    dir_acc_map = {}
    if os.path.exists(METRICS_PATH):
        with open(METRICS_PATH) as f:
            metrics = json.load(f)
        for t, m in metrics.get("per_ticker", {}).items():
            dir_acc_map[t] = m.get("directional_accuracy", 0.5)

    # Single-pass inference — model and prices loaded once across all tickers
    print("[BL] Generating Transformer views (single-pass)...")
    all_forecasts = predict_all_pct_changes(db)

    views = {}
    view_confidences = {}
    for ticker, r_annual in all_forecasts.items():
        if ticker not in tickers:
            continue
        views[ticker] = r_annual
        dir_acc = dir_acc_map.get(ticker, 0.5)
        # 0.20 floor so even weak forecasts suppress negative-view allocations
        view_confidences[ticker] = float(min(1.0, 0.20 + max(0.0, (dir_acc - 0.5) * 1.6)))

    if not views:
        raise ValueError("No Transformer forecasts available. Train the model first.")

    print(f"[BL] {len(views)} views generated across {len(tickers)} ETFs.")

    # ── 4. Black-Litterman posterior ──────────────────────────────────────────
    bl = BlackLittermanModel(
        S,
        pi=pi,
        absolute_views=views,
        omega="idzorek",               # Idzorek method: Ω derived from view confidences
        view_confidences=list(view_confidences[t] for t in views),
    )
    bl_returns = bl.bl_returns()
    bl_cov     = bl.bl_cov()

    # ── 5. Optimise on posterior ──────────────────────────────────────────────
    # If most Transformer views are negative, BL posterior returns may all sit
    # below the risk-free rate — max_sharpe becomes infeasible. Fall back to
    # min_volatility in that case, which always has a solution.
    ef = EfficientFrontier(bl_returns, bl_cov, weight_bounds=(0, 0.20))
    strategy_used = "max_sharpe"
    # Try max_sharpe at decreasing risk-free rates — BL posterior returns can be
    # low when Transformer views are broadly negative, pushing all assets below 5% rf.
    for rf in [0.05, 0.02, 0.0]:
        try:
            ef = EfficientFrontier(bl_returns, bl_cov, weight_bounds=(0, 0.20))
            ef.max_sharpe(risk_free_rate=rf)
            strategy_used = f"max_sharpe (rf={rf:.0%})"
            break
        except Exception:
            continue
    else:
        print("[BL] max_sharpe infeasible at all risk-free rates, falling back to min_volatility.")
        ef = EfficientFrontier(bl_returns, bl_cov, weight_bounds=(0, 0.20))
        ef.min_volatility()
        strategy_used = "min_volatility_fallback"
    weights = ef.clean_weights()
    expected_return, volatility, sharpe_ratio = ef.portfolio_performance(risk_free_rate=0.05)

    # ── 6. Build response (same shape as run_optimization) ───────────────────
    ticker_list = list(weights.keys())
    metadata = {
        e.ticker: {"name": e.name, "category": e.category}
        for e in db.query(ETFMetadata).filter(ETFMetadata.ticker.in_(ticker_list)).all()
    }

    allocations = []
    for ticker, weight in weights.items():
        if weight > 0.001:
            allocations.append({
                "ticker": ticker,
                "name": metadata.get(ticker, {}).get("name", ticker),
                "category": metadata.get(ticker, {}).get("category", "Unknown"),
                "weight": round(weight, 4),
                "weight_pct": f"{round(weight * 100, 2)}%",
                "view_return": f"{round(views.get(ticker, 0) * 100, 2)}%" if ticker in views else None,
                "view_confidence": round(view_confidences.get(ticker, 0), 3) if ticker in view_confidences else None,
            })

    allocations.sort(key=lambda x: x["weight"], reverse=True)

    category_breakdown = {}
    for alloc in allocations:
        cat = alloc["category"]
        category_breakdown[cat] = round(category_breakdown.get(cat, 0) + alloc["weight"], 4)

    return {
        "strategy": "black_litterman",
        "optimization": strategy_used,
        "n_views": len(views),
        "performance": {
            "expected_annual_return": round(expected_return, 4),
            "expected_annual_return_pct": f"{round(expected_return * 100, 2)}%",
            "annual_volatility": round(volatility, 4),
            "annual_volatility_pct": f"{round(volatility * 100, 2)}%",
            "sharpe_ratio": round(sharpe_ratio, 4),
        },
        "category_breakdown": {k: f"{round(v * 100, 2)}%" for k, v in category_breakdown.items()},
        "allocations": allocations,
    }


def run_optimization(db: Session, strategy: str = "max_sharpe") -> dict:
    """
    Run Mean-Variance Optimization on all ETFs in the database.

    Strategies:
      - max_sharpe: Maximize the Sharpe ratio (best risk-adjusted return)
      - min_volatility: Minimize portfolio volatility (most conservative)
    """
    price_matrix = load_price_matrix(db)

    # Calculate expected annual returns and covariance matrix
    mu = expected_returns.mean_historical_return(price_matrix)
    S = risk_models.CovarianceShrinkage(price_matrix).ledoit_wolf()

    # Build efficient frontier — cap any single ETF at 20% to prevent
    # corner solutions where max_sharpe piles into 1-2 assets
    ef = EfficientFrontier(mu, S, weight_bounds=(0, 0.20))

    if strategy == "max_sharpe":
        ef.max_sharpe(risk_free_rate=0.05)  # ~current risk-free rate
    elif strategy == "min_volatility":
        ef.min_volatility()
    else:
        raise ValueError(f"Unknown strategy: '{strategy}'. Use 'max_sharpe' or 'min_volatility'.")

    # Get cleaned weights (removes near-zero allocations)
    weights = ef.clean_weights()

    # Portfolio performance metrics
    expected_return, volatility, sharpe_ratio = ef.portfolio_performance(risk_free_rate=0.05)

    # Get ETF metadata for context
    tickers = list(weights.keys())
    metadata = {
        e.ticker: {"name": e.name, "category": e.category}
        for e in db.query(ETFMetadata).filter(ETFMetadata.ticker.in_(tickers)).all()
    }

    # Build allocation breakdown
    allocations = []
    for ticker, weight in weights.items():
        if weight > 0.001:  # filter out negligible weights
            allocations.append({
                "ticker": ticker,
                "name": metadata.get(ticker, {}).get("name", ticker),
                "category": metadata.get(ticker, {}).get("category", "Unknown"),
                "weight": round(weight, 4),
                "weight_pct": f"{round(weight * 100, 2)}%",
            })

    # Sort by weight descending
    allocations.sort(key=lambda x: x["weight"], reverse=True)

    # Group by category
    category_breakdown = {}
    for alloc in allocations:
        cat = alloc["category"]
        category_breakdown[cat] = round(
            category_breakdown.get(cat, 0) + alloc["weight"], 4
        )

    return {
        "strategy": strategy,
        "performance": {
            "expected_annual_return": round(expected_return, 4),
            "expected_annual_return_pct": f"{round(expected_return * 100, 2)}%",
            "annual_volatility": round(volatility, 4),
            "annual_volatility_pct": f"{round(volatility * 100, 2)}%",
            "sharpe_ratio": round(sharpe_ratio, 4),
        },
        "category_breakdown": {k: f"{round(v * 100, 2)}%" for k, v in category_breakdown.items()},
        "allocations": allocations,
    }