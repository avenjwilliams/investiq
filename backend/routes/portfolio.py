from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from typing import Literal

from backend.data.database import get_db
from backend.analytics.optimize import run_optimization, run_black_litterman

router = APIRouter(prefix="/portfolio", tags=["Portfolio Optimization"])


@router.get("/optimize")
def optimize_portfolio(
    strategy: Literal["max_sharpe", "min_volatility"] = "max_sharpe",
    db: Session = Depends(get_db)
):
    """
    Run portfolio optimization across all ETFs in the database.

    - **max_sharpe**: Maximize risk-adjusted return (Sharpe ratio)
    - **min_volatility**: Minimize portfolio risk
    """
    try:
        result = run_optimization(db, strategy=strategy)
        return result
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Optimization failed: {str(e)}")


@router.get("/optimize/black-litterman")
def optimize_black_litterman(db: Session = Depends(get_db)):
    """
    Black-Litterman portfolio optimization.

    Blends Transformer 90-day forecasts (as views) with market equilibrium returns
    derived from ETF market cap weights. View confidence is weighted by each
    ETF's per-ticker directional accuracy from the last training run.

    Requires the Transformer model to be trained first (POST /forecast/transformer/train-all).
    """
    try:
        result = run_black_litterman(db)
        return result
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Black-Litterman optimization failed: {str(e)}")