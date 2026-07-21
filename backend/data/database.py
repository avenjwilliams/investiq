from sqlalchemy import create_engine, Column, String, Float, Date, DateTime, Text, Integer
from sqlalchemy.orm import declarative_base, sessionmaker
from sqlalchemy.pool import NullPool
from datetime import datetime
import os

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
DB_PATH = os.path.join(BASE_DIR, "investment.db")

# Local dev defaults to a SQLite file. In production, set DATABASE_URL to a
# managed Postgres connection string (e.g. Neon) — most free-tier hosts
# (Render, Railway free/serverless tiers) wipe the local filesystem on every
# redeploy/restart, so SQLite doesn't survive there. Neon's free tier gives
# 0.5GB with scale-to-zero, which is plenty for this app's ~40-ticker dataset.
# `or` (not a plain .get default) so that an empty DATABASE_URL="" left over
# from a copied .env.example falls back to SQLite too, not just a missing key.
DATABASE_URL = os.environ.get("DATABASE_URL") or f"sqlite:///{DB_PATH}"
IS_SQLITE = DATABASE_URL.startswith("sqlite")

# NullPool: each request opens/closes its own connection directly, rather
# than holding a pool open. For SQLite this avoids QueuePool exhaustion
# during slow operations (e.g. Transformer inference). For Postgres on a
# free-tier host that can spin down between requests, it avoids handing out
# stale/dead connections from a pool after a cold start.
engine = create_engine(
    DATABASE_URL,
    connect_args={"check_same_thread": False} if IS_SQLITE else {},
    poolclass=NullPool,
)
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
Base = declarative_base()


class ETFPrice(Base):
    __tablename__ = "etf_prices"

    id = Column(String, primary_key=True)  # ticker + date
    ticker = Column(String, nullable=False, index=True)
    date = Column(Date, nullable=False, index=True)
    open = Column(Float)
    high = Column(Float)
    low = Column(Float)
    close = Column(Float)
    volume = Column(Float)
    adj_close = Column(Float)
    created_at = Column(DateTime, default=datetime.utcnow)


class ETFMetadata(Base):
    __tablename__ = "etf_metadata"

    ticker = Column(String, primary_key=True)
    name = Column(String)
    category = Column(String)  # Sector, Broad Market, Thematic
    last_updated = Column(DateTime, default=datetime.utcnow)


class SentimentRecord(Base):
    __tablename__ = "sentiment_records"

    id = Column(String, primary_key=True)  # ticker + published_at
    ticker = Column(String, nullable=False, index=True)
    headline = Column(Text)
    source = Column(String)
    published_at = Column(DateTime, index=True)
    sentiment = Column(String)   # positive / negative / neutral
    positive_score = Column(Float)
    negative_score = Column(Float)
    neutral_score = Column(Float)
    fetched_at = Column(DateTime, default=datetime.utcnow)



def init_db():
    """Create all tables if they don't exist."""
    Base.metadata.create_all(bind=engine)
    print("Database initialized successfully.")


def get_db():
    """Dependency for getting a DB session."""
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()