import os
from apscheduler.schedulers.background import BackgroundScheduler
from apscheduler.triggers.cron import CronTrigger

ETF_UNIVERSE = [
    # Sector
    "XLK", "XLF", "XLE", "XLV", "XLI", "XLB", "XLY", "XLP", "XLU", "XLRE", "XLC",
    # Broad Market
    "SPY", "QQQ", "IWM", "VTI", "EFA", "EEM", "BND", "GLD",
    # Thematic
    "ARKK", "ICLN", "CIBR", "ROBO", "HERO", "AWAY", "BOTZ", "FINX", "BITO",
    # International
    "VEU", "EWJ", "INDA", "FXI", "VWO",
    # Commodity
    "USO", "DBA", "PDBC",
    # Factor
    "VTV", "VUG", "MTUM", "QUAL",
]

scheduler = BackgroundScheduler(timezone="America/New_York")


def _run_fetch():
    from backend.ingestion.fetch_prices import fetch_latest
    # fetch_latest() manages its own DB session internally — it doesn't take
    # one as an argument. (Previously called as fetch_latest(db), which threw
    # a TypeError every time this job ran, silently swallowed below.)
    try:
        fetch_latest()
        print("[Scheduler] Daily price fetch complete.")
    except Exception as e:
        print(f"[Scheduler] Price fetch failed: {e}")


def _retrain_all_models():
    from backend.data.database import SessionLocal
    from backend.analytics.forecast_transformer import train_all
    db = SessionLocal()
    try:
        result = train_all(db)
        print(f"[Scheduler] Weekly Transformer retrain complete — {result['n_tickers']} tickers, {result['samples']} samples.")
    except Exception as e:
        print(f"[Scheduler] Weekly Transformer retrain failed: {e}")
    finally:
        db.close()


def stop_scheduler(sched=None):
    s = sched or scheduler
    if s.running:
        s.shutdown()
        print("[Scheduler] Stopped.")


def start_scheduler():
    # Daily price fetch — weekdays at 6 PM ET
    scheduler.add_job(
        _run_fetch,
        CronTrigger(day_of_week="mon-fri", hour=18, minute=0, timezone="America/New_York"),
        misfire_grace_time=3600,
        id="daily_price_fetch",
    )

    # Weekly model retrain — every Sunday at 2 AM ET
    scheduler.add_job(
        _retrain_all_models,
        CronTrigger(day_of_week="sun", hour=2, minute=0, timezone="America/New_York"),
        misfire_grace_time=3600,
        id="weekly_model_retrain",
    )

    scheduler.start()
    print("[Scheduler] Started — daily fetch (Mon–Fri 6 PM ET) | weekly retrain (Sun 2 AM ET)")
    return scheduler