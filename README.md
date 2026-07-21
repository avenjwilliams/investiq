# InvestIQ

A full-stack investment intelligence platform featuring automated ETF data ingestion, mean-variance portfolio optimization, Transformer-based 90-day price forecasting, and FinBERT sentiment analysis on live news — surfaced through a React dashboard with a FastAPI backend and SQLite pipeline.

---

## Finish-Line Checklist (locked scope — this is what "done" means)

This project's goal is a polished, honestly-documented portfolio piece. The list
below is deliberately closed — anything not on it is explicitly deferred so
scope stops growing before the project ships.

### 1. Model validation — CLOSED
- [x] Richer-features Transformer run (volume, RSI-14, 10-day momentum added
      alongside returns + VIX/TNX) + 5-fold walk-forward CV
- [x] **Decision made — no further model iteration:**
  - Baseline (returns + VIX/TNX only): 50.16% ± 1.35pp across 5 folds.
  - With richer features (+ volume, RSI-14, 10-day momentum): **50.39% ± 0.83pp**
    across 5 folds (49.99%, 49.20%, 51.59%, 50.14%, 51.02%).
  - The richer features tightened consistency across folds (±1.35pp → ±0.83pp)
    but did not create a statistically real edge (+0.39pp over 50% against an
    SE of ~0.37pp — t ≈ 1.05, not significant).
  - **Conclusion:** returns + macro + volume/RSI/momentum on this 40-ETF
    universe, honestly validated with walk-forward CV, do not produce a
    reliable directional edge with this architecture. That's the shipped
    finding — documented with real numbers, benchmarked against the published
    Fischer & Krauss (2018) LSTM result of 51.4%, rather than an inflated
    accuracy claim.
- [x] **Follow-up: cross-sectional (demeaned) check to isolate market drift from real signal**
  - Ran a simpler logistic-regression baseline on the same features first: a
    plain "always predict up" majority-class rule hit 53.52% test accuracy —
    beating both the logistic regression (51.39%) and the Transformer's CV
    result. That's not model skill, it's market drift (more up days than down
    days in this window) — a floor any "smart" model needs to clear to mean
    anything.
  - To separate real signal from that drift, reran the comparison predicting
    **cross-sectional (relative-to-universe) direction** instead of raw
    direction — did a ticker beat the equal-weighted 40-ETF average that day,
    not just did it go up. Three variants:
    - Raw target, raw features (reproduces the baseline above): floor 53.52%,
      logistic regression 51.39%.
    - Demeaned target, raw features: floor collapsed to 50.40% as expected
      once drift is removed — logistic regression scored 50.31%, *below* the
      floor.
    - Demeaned target, demeaned features: floor 50.40%, logistic regression
      50.14%, still below the floor.
  - **Conclusion:** the apparent "edge" in the raw baseline was entirely
    market drift, not stock-picking signal — once removed, a linear model
    can't even match a naive floor. This rules out not just directional
    signal but relative-performance signal in these features (lagged
    returns, RSI-14, momentum, volume z-score, VIX/TNX), across both a
    linear model and the Transformer. Three independent methods converging
    on the same ~50% wall is stronger evidence than any one alone, and is
    consistent with how efficient daily-direction prediction is expected to
    be for liquid, diversified ETFs. Closing this out rather than continuing
    to iterate on the same feature family.

### 2. Ship
- [x] Visual polish pass across the site — shared button/select/card-hover styles,
      loading spinner, consistent focus states, Navbar rebuilt (fixed "IP" → "IQ"
      logo bug), fixed a factual error on the Universe page ("7 categories" → 6)
- [x] Research hosting and do the prep work (env vars, CORS, DB portability) — see **Hosting** section below. Actually deploying is still a manual step for you (needs real accounts/credentials).
- [ ] Rewrite this file as a public-facing project README: architecture,
      feature tour, screenshots, and the model validation story (numbers
      included, whichever way they land)
- [ ] Push to a public GitHub repo

### Explicitly cut from this release (not blocking ship)
- [ ] Learning mode (navbar tooltip toggle explaining Sharpe ratio, LSTM,
      FinBERT, etc.) — deferred indefinitely, pure UX polish with no bearing
      on what the project demonstrates
- [ ] Sub-sector ETF expansion (SOXX, IBB, KRE, XOP, JETS, ITB) — deferred
      indefinitely, adds surface area without adding differentiation

---

## Completed
- [x] Phase 1 — Data pipeline: 25 ETFs, yfinance ingestion, SQLite, APScheduler daily fetch
- [x] Phase 2 — Analytics: portfolio optimization (PyPortfolioOpt), LSTM forecasting, FinBERT sentiment
- [x] Phase 3 — React dashboard: Portfolio page, ETF Explorer, Sentiment Feed
- [x] Fix forecasting cliff — switched from raw price LSTM to log-returns LSTM with StandardScaler; added weekly auto-retrain to scheduler
- [x] Expand ETF universe to 40 ETFs — added International (VEU, EWJ, INDA, FXI, VWO), Commodity (USO, DBA, PDBC), Factor (VTV, VUG, MTUM, QUAL), and Thematic additions (BOTZ, FINX, BITO); new category colors and badges in UI
- [x] Forecast Dashboard (`/forecasts`) — grid of mini sparkline cards for all trained models with 90-day predicted price and % change; Train All button triggers background training for all 40 ETFs; sort by return or category; per-card Train button for untrained ETFs
- [x] ~~Political Trade Tracker (`/political`)~~ — signal dashboard scoring congressional trades per ETF using House/Senate Stock Watcher APIs (no key required); recency-weighted exponential decay (30-day half-life) × trade size × direction; normalized ±100 score; detail panel with party filter and per-trade disclosure dates. **Removed as of July 2026** — both the House and Senate Stock Watcher live sites and their S3 data endpoints went dark; the only surviving archive (a GitHub mirror) is frozen at 2020-era data, so every trade failed the recency filter. Free alternatives either require a paid API (Quiver Quantitative, ~$25/mo) or scraping with no public API (Capitol Trades) — not worth the added scope for this project. Backend routes, analytics module, DB table, and frontend page removed entirely rather than shipped broken.
- [x] Directional loss function — hybrid MSE + directional penalty loss, later replaced by a dedicated direction classification head (see below)
- [x] Transformer forecasting model — replaced the stacked LSTM with a Transformer + positional encoding for the shared multivariate model
- [x] Macro input features (VIX + 10-year yield) — added as additional input channels alongside log returns
- [x] Black-Litterman optimization — added as a third portfolio strategy alongside Max Sharpe and Min Volatility, using model forecasts as views blended with market equilibrium returns
- [x] Direction-specific classification head — added a second model output trained directly on return sign (binary cross-entropy) instead of relying on a blended regression loss, with the direction/regression weighting (alpha) tuned up
- [x] Per-horizon directional accuracy logging — breaks out accuracy by day-ahead (day+1 through day+90) instead of a single blended average, to see whether signal decays with horizon
- [x] 5-fold walk-forward (expanding window) cross-validation — replaces trusting a single 80/20 chronological split, which wasn't enough test windows to distinguish real signal from noise
- [x] Fixed a TensorFlow/Keras multi-output `model.fit()` crash (`down_cast` assertion) via a manual `GradientTape` training loop, after isolating it to Keras' built-in multi-output training path on real (vs. synthetic) data
- [x] Richer per-ticker features (volume, RSI-14, 10-day momentum) fed alongside the ticker embedding, without expanding the shared sequence input's channel count
- [x] Logistic-regression and cross-sectional baseline scripts (`baseline_logistic_direction.py`, `baseline_cross_sectional.py`) — sanity checks proving the Transformer's ~50% result isn't an artifact of architecture complexity, and isolating market drift from real signal
- [x] Frontend + Black-Litterman fully repointed at the Transformer — Forecast Dashboard, ETF Explorer, Model Metrics, and BL view generation all call the Transformer's endpoints/functions instead of the legacy LSTM's
- [x] ~~Legacy LSTM model~~ — removed entirely (`backend/analytics/forecast.py`, its routes, its saved model/scaler/metrics artifacts) once the Transformer replaced it everywhere it was used; the weekly scheduler retrain job now retrains the Transformer instead
- [x] Hosting prep — `DATABASE_URL` env var support (SQLite dev / Postgres prod), configurable CORS origins, frontend API URL no longer hardcoded, `render.yaml` blueprint, `.env.example` files, and a populated `requirements.txt` (was empty — no host could have deployed this before). Also added a missing `.gitignore`, since a live NewsAPI key in `.env` had zero protection against being committed. See **Hosting** section below for the deploy path and what's still a manual step.

---

## Stack

| Layer | Tech |
|---|---|
| Backend | FastAPI, SQLAlchemy, SQLite (dev) / Postgres (prod, via `DATABASE_URL`) |
| Data | yfinance, NewsAPI |
| Analytics | PyPortfolioOpt, TensorFlow/Keras Transformer, HuggingFace FinBERT |
| Scheduler | APScheduler (daily fetch Mon–Fri 6PM ET, weekly retrain Sun 2AM ET) |
| Frontend | React, Recharts, Axios |
| Environment | conda (investment-platform env) |

## Running Locally

```bash
# Backend
conda activate investment-platform
cd investment-platform
python backend/main.py

# Frontend (separate terminal)
cd investment-platform/frontend
npm start
```

## Hosting

Chosen path: **Vercel (frontend) + Render free tier (backend) + Neon (Postgres,
replacing SQLite)** — all free. Researched in July 2026; alternatives considered
below.

**Why not just deploy SQLite as-is?** Render's free tier (and most free-tier
PaaS hosts) have an ephemeral filesystem — a local SQLite file gets wiped on
every redeploy or restart. Free Render Postgres also auto-expires after 30
days. Neon's free tier (0.5GB, scale-to-zero, no expiration) is a better fit
for a dataset this size and decouples the database from whichever backend
host you pick.

**What's already done** (this repo): `DATABASE_URL` env var support in
`backend/data/database.py` (falls back to local SQLite if unset), `psycopg2-binary`
added to `requirements.txt` (was previously empty — no host could have
installed dependencies before this), CORS origins now configurable via
`ALLOWED_ORIGINS`, the frontend's API base URL now reads `REACT_APP_API_URL`
instead of being hardcoded to `localhost:8000`, a `render.yaml` blueprint, and
`.env.example` files for both the backend and frontend.

**What's still a manual step for you** (credit cards aren't required for any
of these, but the actual account creation and secret values can't be done on
your behalf):
1. Create a free Neon project, copy its connection string into `DATABASE_URL`
   (Render dashboard → environment variables, not committed to the repo).
2. Deploy the backend to Render (New → Blueprint, point at this repo — it'll
   read `render.yaml`). Set `ALLOWED_ORIGINS` and `NEWS_API_KEY` there too.
3. Deploy the frontend to Vercel (New Project → this repo, root directory
   `frontend/`). Set `REACT_APP_API_URL` to the Render backend's URL.
4. Run `POST /forecast/transformer/train-all` once against the hosted backend
   to populate the model (Neon starts empty).

**Known limitations of this setup:**
- Render's free tier spins down after ~15 min idle; the next request eats a
  ~1 minute cold start. Fine for a portfolio demo, mildly annoying if showing
  it live. Railway's $5/mo Hobby plan avoids this if it matters.
- The weekly APScheduler retrain job (`backend/scheduler/scheduler.py`) only
  fires if the process is actually running at 2 AM Sunday ET — on a free tier
  that spins down when idle, this isn't reliable. The "⚡ Update Model" button
  in the Forecast Dashboard UI works regardless and is the practical way to
  retrain a hosted deployment.
- A fully free, zero-maintenance-fee alternative considered but not chosen:
  self-hosting everything (frontend + backend + SQLite, unchanged) on an
  Oracle Cloud Always Free ARM VM (2 OCPU/12GB, free forever as of mid-2026).
  No cold starts, no DB migration needed — but you own nginx, systemd, TLS
  certs, and OS security updates yourself. Worth it if you'd rather show
  "I deployed and manage a real server" than "I wired up managed services."
