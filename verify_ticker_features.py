"""
Verifies the new richer-features enhancement (volume, RSI, momentum) before
committing to a full train-all run:
  1. Loads real data via the updated _load_aligned_returns() and checks the
     ticker_features array for NaN/Inf and sane value ranges.
  2. Builds a small sample set and confirms shapes line up.
  3. Runs a short (5-epoch) smoke-test training pass through the updated
     3-input model + manual training loop to confirm no crash.

Run:
    conda activate investment-platform
    python verify_ticker_features.py
"""
import sys, os
import numpy as np

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from backend.data.database import SessionLocal
import backend.analytics.forecast_transformer as tfm
from sklearn.preprocessing import StandardScaler

tfm.EPOCHS = 5  # smoke test only — real runs still use the module's default (150)

db = SessionLocal()
try:
    print("[1/4] Loading aligned returns + ticker features...")
    returns_df, ticker_features, tickers, N_ETF, N, T = tfm._load_aligned_returns(db)
    print(f"    returns_df: {returns_df.shape} | ticker_features: {ticker_features.shape}")
    print(f"    any NaN in ticker_features: {np.isnan(ticker_features).any()}")
    print(f"    any Inf in ticker_features: {np.isinf(ticker_features).any()}")

    rsi_vals = ticker_features[:, :, 0]
    mom_vals = ticker_features[:, :, 1]
    volz_vals = ticker_features[:, :, 2]
    print(f"    rsi_scaled  range: [{rsi_vals.min():.4f}, {rsi_vals.max():.4f}] (expect roughly -1..1)")
    print(f"    momentum    range: [{mom_vals.min():.4f}, {mom_vals.max():.4f}]")
    print(f"    volume_z    range: [{volz_vals.min():.4f}, {volz_vals.max():.4f}] (expect roughly -3..5ish)")

    print("\n[2/4] Building sample set (500-sample slice for speed)...")
    split_idx = int(T * tfm.TRAIN_SPLIT)
    train_raw = returns_df.values[:split_idx]
    scaler = StandardScaler()
    train_scaled = scaler.fit_transform(train_raw)
    X_seq, X_tid, X_feat, Y_reg, Y_dir = tfm._build_samples(
        train_scaled, train_raw, ticker_features, N_ETF, N, tfm.LOOKBACK, split_idx - tfm.FORECAST_HORIZON + 1
    )
    print(f"    X_seq={X_seq.shape} X_tid={X_tid.shape} X_feat={X_feat.shape} "
          f"Y_reg={Y_reg.shape} Y_dir={Y_dir.shape}")

    idx = np.random.default_rng(0).choice(len(X_seq), size=500, replace=False)
    xs, xt, xf, yr, yd = X_seq[idx], X_tid[idx], X_feat[idx], Y_reg[idx], Y_dir[idx]

    print("\n[3/4] Building 3-input model...")
    model = tfm._build_model(N, N_ETF)
    print(f"    inputs: {[i.shape for i in model.inputs]}")
    print(f"    outputs: {[o.shape for o in model.outputs]}")

    print("\n[4/4] Smoke-test training (5 epochs, 500 real samples)...")
    history = tfm._fit_model(model, xs, xt, xf, yr, yd, verbose=1)

    print("\n=== SUCCESS ===")
    print("final train loss:", history.history["loss"][-1])
    print("final val loss:", history.history["val_loss"][-1])

finally:
    db.close()
