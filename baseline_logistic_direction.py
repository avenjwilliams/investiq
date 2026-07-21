"""
Simple baseline check: does a plain logistic regression on cheap features
(lagged returns + RSI/momentum/volume-z + macro) predict next-day direction
better than the Transformer's ~50% CV result? And critically — does either
beat just always predicting the majority class (the "do nothing clever"
floor)?

Predicts single-day-ahead direction (not the full 90-day path) since that's
the horizon where any real signal is most plausible, and it's the most
direct point of comparison.

Reuses the real data-loading helpers from forecast_transformer.py so this is
apples-to-apples with the same dataset the Transformer trains on. No
TensorFlow involved — this only needs sklearn/pandas/numpy.

Run:
    conda activate investment-platform
    python baseline_logistic_direction.py
"""
import sys, os
import numpy as np
import pandas as pd

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from backend.data.database import SessionLocal
import backend.analytics.forecast_transformer as tfm
from sklearn.linear_model import LogisticRegression
from sklearn.preprocessing import StandardScaler
from sklearn.metrics import accuracy_score

LAGS = [1, 2, 3, 5, 10]

db = SessionLocal()
try:
    print("[1/3] Loading aligned returns + ticker features...")
    returns_df, ticker_features, tickers, N_ETF, N, T = tfm._load_aligned_returns(db)
    raw = returns_df.values
    macro_cols = returns_df.columns[N_ETF:]  # VIX, TNX
    print(f"    T={T} days | {N_ETF} ETFs | macro cols: {list(macro_cols)}")

    print("[2/3] Building lag/technical feature matrix (single-day-ahead target)...")
    max_lag = max(LAGS)
    start_t = max(max_lag, tfm.LOOKBACK)  # keep consistent with what the Transformer has available
    rows = []
    for t in range(start_t, T - 1):  # predict return at t+1 using info as of t
        for i in range(N_ETF):
            feat = {}
            for lag in LAGS:
                feat[f"lag_{lag}"] = raw[t - lag + 1, i]  # ticker i's own return, lag days back
            feat["rsi"] = ticker_features[t, i, 0]
            feat["momentum"] = ticker_features[t, i, 1]
            feat["volume_z"] = ticker_features[t, i, 2]
            feat["vix_ret"] = raw[t, N_ETF]      # VIX log return that day
            feat["tnx_ret"] = raw[t, N_ETF + 1]  # TNX log return that day
            feat["ticker_idx"] = i
            feat["y"] = 1 if raw[t + 1, i] > 0 else 0
            feat["t"] = t
            rows.append(feat)

    df = pd.DataFrame(rows)
    print(f"    {len(df)} samples, {df.shape[1] - 2} features")

    # Same chronological 80/20 split logic as the Transformer, on the `t` timeline
    split_t = start_t + int((T - 1 - start_t) * tfm.TRAIN_SPLIT)
    train_df = df[df["t"] < split_t]
    test_df  = df[df["t"] >= split_t]
    print(f"    train: {len(train_df)} samples | test: {len(test_df)} samples "
          f"(split at t={split_t}, matches TRAIN_SPLIT={tfm.TRAIN_SPLIT})")

    feature_cols = [c for c in df.columns if c not in ("y", "t")]
    X_train, y_train = train_df[feature_cols], train_df["y"]
    X_test, y_test = test_df[feature_cols], test_df["y"]

    print("\n[3/3] Fitting baselines...")

    # Floor: always predict the majority class seen in training
    majority_class = y_train.mode()[0]
    majority_pred = np.full(len(y_test), majority_class)
    majority_acc = accuracy_score(y_test, majority_pred)
    print(f"    Majority-class floor (train up-day frac={y_train.mean():.4f}): "
          f"{majority_acc:.4%} test accuracy")

    # Logistic regression on standardized features
    scaler = StandardScaler()
    X_train_scaled = scaler.fit_transform(X_train)
    X_test_scaled = scaler.transform(X_test)

    clf = LogisticRegression(max_iter=1000, C=1.0)
    clf.fit(X_train_scaled, y_train)
    pred = clf.predict(X_test_scaled)
    lr_acc = accuracy_score(y_test, pred)
    print(f"    Logistic regression: {lr_acc:.4%} test accuracy")

    # Per-ticker breakdown for the logistic regression
    test_df = test_df.copy()
    test_df["pred"] = pred
    test_df["correct"] = (test_df["pred"] == test_df["y"]).astype(int)
    per_ticker = test_df.groupby("ticker_idx")["correct"].mean().sort_values(ascending=False)
    idx_to_ticker = {i: t for i, t in enumerate(tickers[:N_ETF])}
    print("\n    Per-ticker logistic regression accuracy (top 5 / bottom 5):")
    for idx, acc in per_ticker.head(5).items():
        print(f"      {idx_to_ticker[idx]:>6}: {acc:.4%}")
    print("      ...")
    for idx, acc in per_ticker.tail(5).items():
        print(f"      {idx_to_ticker[idx]:>6}: {acc:.4%}")

    # Feature importance (coefficients) — which features the logistic model leaned on
    coefs = pd.Series(clf.coef_[0], index=feature_cols).sort_values(key=abs, ascending=False)
    print("\n    Logistic regression coefficients (by |magnitude|):")
    for name, val in coefs.items():
        print(f"      {name:>12}: {val:+.4f}")

    print("\n=== SUMMARY ===")
    print(f"Majority-class floor: {majority_acc:.4%}")
    print(f"Logistic regression:  {lr_acc:.4%}")
    print(f"(Transformer 5-fold CV, for reference: ~50.16-50.39%)")

finally:
    db.close()
