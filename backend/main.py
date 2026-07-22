import sys
import os
from dotenv import load_dotenv

# Load environment variables from .env
load_dotenv()

# Ensure project root is on the path
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from contextlib import asynccontextmanager
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from backend.data.database import init_db
from backend.ingestion.fetch_prices import seed_historical, has_sufficient_historical_data
from backend.scheduler.scheduler import start_scheduler, stop_scheduler
from backend.routes.prices import router as prices_router
from backend.routes.portfolio import router as portfolio_router
from backend.routes.forecast import router as forecast_router
from backend.routes.sentiment import router as sentiment_router


def _seed_historical_in_background():
    """
    Runs the (slow, synchronous) historical price seed off the main startup
    path. yfinance/Yahoo Finance is known to rate-limit or silently hang on
    requests from datacenter IPs (Render, Railway, most cloud hosts included)
    - blocking startup on this meant one stuck ticker could hang the entire
    deploy past the host's port-scan timeout, since the server never got a
    chance to bind and start accepting connections until this finished.
    """
    import threading

    def _run():
        try:
            # Checked against the database itself, not a local timestamp
            # file — Render's filesystem is wiped on every deploy/restart,
            # so a file-based check would make every fresh deploy re-run the
            # full multi-year seed even after the database is already
            # populated. The daily scheduled job (backend/scheduler) handles
            # ongoing incremental updates once this initial seed is done.
            if has_sufficient_historical_data():
                print("Database already has historical data — skipping full seed.")
            else:
                print("Database looks empty/partial — running full historical seed...")
                seed_historical(years=10)
        except Exception as e:
            print(f"[Startup] Historical seed failed (non-fatal): {e}")

    threading.Thread(target=_run, daemon=True).start()


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Runs on startup and shutdown."""
    # Startup
    print("Initializing database...")
    init_db()

    print("Kicking off historical price seed in the background...")
    _seed_historical_in_background()

    print("Starting scheduler...")
    scheduler = start_scheduler()

    yield  # App is running

    # Shutdown
    print("Shutting down scheduler...")
    stop_scheduler(scheduler)


app = FastAPI(
    title="Investment Intelligence Platform",
    description="Automated ETF data pipeline with portfolio optimization and sentiment analysis.",
    version="0.1.0",
    lifespan=lifespan
)


# Comma-separated list of allowed frontend origins. Defaults to the local
# dev server; set ALLOWED_ORIGINS in production to the deployed frontend URL
# (e.g. "https://investiq.vercel.app") — without this, the hosted frontend's
# API calls will be blocked by the browser's CORS policy.
allowed_origins = (os.environ.get("ALLOWED_ORIGINS") or "http://localhost:3000").split(",")

app.add_middleware(
    CORSMiddleware,
    allow_origins=allowed_origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(prices_router)
app.include_router(portfolio_router)
app.include_router(forecast_router)
app.include_router(sentiment_router)


@app.get("/")
def root():
    return {"status": "running", "message": "Investment Intelligence Platform is live."}


@app.get("/health")
def health():
    return {"status": "healthy"}


if __name__ == "__main__":
    import uvicorn
    # Render (and most PaaS hosts) inject the port to bind via $PORT rather
    # than letting you choose it. reload=True is a dev-only convenience —
    # it's disabled by default in production and only enabled locally via
    # DEV_MODE=1, since autoreload has no purpose (and some overhead) once deployed.
    port = int(os.environ.get("PORT") or 8000)
    dev_mode = (os.environ.get("DEV_MODE") or "1") == "1"
    uvicorn.run("main:app", host="0.0.0.0", port=port, reload=dev_mode)