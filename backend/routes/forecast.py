import os
import json
import pandas as pd
from fastapi import APIRouter, Depends, HTTPException, BackgroundTasks
from sqlalchemy.orm import Session

from backend.data.database import get_db, ETFMetadata, SessionLocal
import backend.analytics.forecast_transformer as transformer_forecast

router = APIRouter(prefix="/forecast", tags=["Forecasting"])

# Training in-process (across all 40 tickers) OOMs Render's free-tier 512MB
# instance — confirmed via Render's Events log ("Ran out of memory (used over
# 512MB) while running your code") after trying it. Render's filesystem is
# also ephemeral, so even a successful in-container run wouldn't survive a
# restart anyway. The shipped model is trained locally and committed to the
# repo instead (see backend/models/). ALLOW_TRAINING defaults on for local
# dev; render.yaml sets it to "0" in production so neither the API nor the
# weekly scheduler job can trigger the same crash again.
ALLOW_TRAINING = (os.environ.get("ALLOW_TRAINING") or "1") == "1"


# ── Transformer endpoints ─────────────────────────────────────────────────────
# The Transformer (direction head + richer features + walk-forward CV) is the
# only forecasting model in the app — the original LSTM was removed after the
# Transformer replaced it everywhere (Forecast Dashboard, ETF Explorer, Model
# Metrics, Black-Litterman views).

def _train_transformer_background():
    db = SessionLocal()
    try:
        result = transformer_forecast.train_all(db)
        print(f"[Transformer Train-All] Complete — {result['n_tickers']} tickers, {result['samples']} samples.")
    except Exception as e:
        print(f"[Transformer Train-All] Failed: {e}")
    finally:
        db.close()


@router.post("/transformer/train-all")
def train_transformer(background_tasks: BackgroundTasks):
    """
    Train (or retrain) the Transformer model on all ETFs.
    Returns immediately — training runs in the background.
    """
    if not ALLOW_TRAINING:
        raise HTTPException(
            status_code=503,
            detail=(
                "Model training is disabled on this host — Render's free tier "
                "doesn't have enough RAM to train the Transformer in-process "
                "(this previously crashed the instance with an OOM). The "
                "shipped model is trained locally and committed to the repo; "
                "retrain locally and redeploy to update it."
            ),
        )
    background_tasks.add_task(_train_transformer_background)
    return {
        "status": "training_started",
        "model": "transformer",
        "message": (
            "Training the multivariate Transformer in the background. "
            "Check GET /forecast/transformer/metrics once complete."
        ),
    }


@router.get("/transformer/metrics")
def get_transformer_metrics():
    """Return per-ticker and overall Transformer evaluation metrics from the last training run."""
    if not os.path.exists(transformer_forecast.METRICS_PATH):
        raise HTTPException(
            status_code=404,
            detail="No Transformer metrics available. Train first via POST /forecast/transformer/train-all.",
        )
    with open(transformer_forecast.METRICS_PATH) as f:
        return json.load(f)


def _cross_validate_transformer_background(n_folds: int):
    db = SessionLocal()
    try:
        result = transformer_forecast.train_cv(db, n_folds=n_folds)
        print(f"[Transformer CV] Complete — {result['n_folds']} folds, "
              f"mean dir acc {result['cv_mean_directional_accuracy']}.")
    except Exception as e:
        print(f"[Transformer CV] Failed: {e}")
    finally:
        db.close()


@router.post("/transformer/cross-validate")
def cross_validate_transformer(background_tasks: BackgroundTasks, n_folds: int = 5):
    """
    Run walk-forward (expanding window) cross-validation for the Transformer model.
    Trains n_folds independent models on progressively larger training windows and
    evaluates each on the block that follows. Does not affect the production model —
    check GET /forecast/transformer/cv-metrics once complete.
    """
    if not ALLOW_TRAINING:
        raise HTTPException(
            status_code=503,
            detail=(
                "Model training is disabled on this host — cross-validation trains "
                "n_folds separate models, which is even more memory-hungry than a "
                "single train-all run and isn't safe on Render's free tier."
            ),
        )
    background_tasks.add_task(_cross_validate_transformer_background, n_folds)
    return {
        "status": "cross_validation_started",
        "model": "transformer",
        "n_folds": n_folds,
        "message": (
            "Running walk-forward cross-validation in the background. "
            "Check GET /forecast/transformer/cv-metrics once complete."
        ),
    }


@router.get("/transformer/cv-metrics")
def get_transformer_cv_metrics():
    """Return the results of the last walk-forward cross-validation run."""
    if not os.path.exists(transformer_forecast.CV_METRICS_PATH):
        raise HTTPException(
            status_code=404,
            detail="No CV metrics available. Run POST /forecast/transformer/cross-validate first.",
        )
    with open(transformer_forecast.CV_METRICS_PATH) as f:
        return json.load(f)


@router.get("/transformer/")
def list_trained_transformer_models(db: Session = Depends(get_db)):
    """
    List all ETFs and whether the Transformer model is ready.
    All tickers share one model — they're all ready or none are.
    Includes last_trained timestamp (ISO 8601) when the model exists.
    """
    ready = transformer_forecast.model_exists()
    last_trained = None
    if ready:
        mtime = os.path.getmtime(transformer_forecast.MODEL_PATH)
        last_trained = pd.Timestamp(mtime, unit="s", tz="UTC").isoformat()
    etfs = db.query(ETFMetadata).all()
    return {
        "model_ready": ready,
        "last_trained": last_trained,
        "training_enabled": ALLOW_TRAINING,
        "etfs": [
            {
                "ticker": e.ticker,
                "name": e.name,
                "category": e.category,
                "model_ready": ready,
            }
            for e in etfs
        ],
    }


@router.get("/transformer/{ticker}")
def get_transformer_forecast(ticker: str, db: Session = Depends(get_db)):
    """Get a 90-day price forecast for a specific ETF using the Transformer model."""
    ticker = ticker.upper()

    etf = db.query(ETFMetadata).filter_by(ticker=ticker).first()
    if not etf:
        raise HTTPException(status_code=404, detail=f"ETF '{ticker}' not found.")

    if not transformer_forecast.model_exists():
        raise HTTPException(
            status_code=400,
            detail="Transformer model not trained yet. Run POST /forecast/transformer/train-all first.",
        )

    try:
        result = transformer_forecast.predict(ticker, db)
        return result
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Transformer forecast failed: {str(e)}")
