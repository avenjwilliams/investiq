"""
Follow-up to baseline_logistic_direction.py. That run showed the majority-
class floor (53.52%, i.e. "always guess up") beating both a logistic
regression (51.39%) and the Transformer's CV result (~50.2-50.4%) — meaning
none of the tested features beat just riding the market's upward drift.

This script tests whether removing that drift reveals any real idiosyncratic
signal, by predicting CROSS-SECTIONAL (relative) direction instead of raw
direction: did ticker i outperform the equal-weighted universe average that
day, rather than did it go up in absolute terms. If there's real
stock-picking-style signal in these features, it should show up here even
if it's invisible under raw returns (which are dominated by common market
moves). If the majority-class floor collapses toward ~50% here (as expected,
since "who beats the average" has no inherent upward bias) and nothing beats
it, that's strong evidence there's no idiosyncratic signal either — not just
no directional signal, but no relative-performance signal.

Runs three variants for comparison:
  A) Raw target, raw features       (reproduces the original baseline)
  B) Demeaned target, raw features  (does removing drift from the LABEL help?)
  C) Demeaned target, demeaned features (does removing drift from BOTH help?)

Run:
    conda activate investment-platform
    python baseline_cross_sectional.py
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


def run_experiment(label, train_df, test_df, feature_cols):
    X_train, y_train = train_df[feature_cols], train_df["y"]
    X_test, y_test = test_df[feature_cols], test_df["y"]

    majority_class = y_train.mode()[0]
    majority_pred = np.full(len(y_test), majority_class)
    majority_acc = accuracy_score(y_test, majority_pred)

    scaler = StandardScaler()
    X_train_scaled = scaler.fit_transform(X_train)
    X_test_scaled = scaler.transform(X_test)

    clf = LogisticRegression(max_iter=1000, C=1.0)
    clf.fit(X_train_scaled, y_train)
    pred = clf.predict(X_test_scaled)
    lr_acc = accuracy_score(y_test, pred)

    print(f"\n--- {label} ---")
    print(f"    train positive-class frac: {y_train.mean():.4f}")
    print(f"    majority-class floor:      {majority_acc:.4%}")
    print(f"    logistic regression:       {lr_acc:.4%}")

    coefs = pd.Series(clf.coef_[0], index=feature_cols).sort_values(key=abs, ascending=False)
    print("    top coefficients:")
    for name, val in coefs.head(5).items():
        print(f"      {name:>12}: {val:+.4f}")

    return {"label": label, "majority_acc": majority_acc, "lr_acc": lr_acc}


db = SessionLocal()
try:
    print("[1/3] Loading aligned returns + ticker features...")
    returns_df, ticker_features, tickers, N_ETF, N, T = tfm._load_aligned_returns(db)
    raw = returns_df.values
    print(f"    T={T} days | {N_ETF} ETFs")

    # Daily equal-weighted cross-sectional mean return across the ETF universe
    # (macro columns excluded — only the 40 ETFs count toward "the market").
    cs_mean = raw[:, :N_ETF].mean(axis=1)  # shape (T,)

    print("[2/3] Building feature matrix (raw AND demeaned versions)...")
    max_lag = max(LAGS)
    start_t = max(max_lag, tfm.LOOKBACK)
    rows = []
    for t in range(start_t, T - 1):
        for i in range(N_ETF):
            feat = {}
            for lag in LAGS:
                lag_t = t - lag + 1
                feat[f"lag_{lag}"] = raw[lag_t, i]
                feat[f"lag_{lag}_excess"] = raw[lag_t, i] - cs_mean[lag_t]
            feat["rsi"] = ticker_features[t, i, 0]
            feat["momentum"] = ticker_features[t, i, 1]
            feat["volume_z"] = ticker_features[t, i, 2]
            feat["vix_ret"] = raw[t, N_ETF]
            feat["tnx_ret"] = raw[t, N_ETF + 1]
            feat["ticker_idx"] = i
            feat["y_raw"] = 1 if raw[t + 1, i] > 0 else 0
            feat["y_excess"] = 1 if (raw[t + 1, i] - cs_mean[t + 1]) > 0 else 0
            feat["t"] = t
            rows.append(feat)

    df = pd.DataFrame(rows)
    print(f"    {len(df)} samples")

    split_t = start_t + int((T - 1 - start_t) * tfm.TRAIN_SPLIT)
    train_df = df[df["t"] < split_t]
    test_df = df[df["t"] >= split_t]
    print(f"    train: {len(train_df)} | test: {len(test_df)} (split at t={split_t})")

    raw_feature_cols = ["lag_1", "lag_2", "lag_3", "lag_5", "lag_10",
                         "rsi", "momentum", "volume_z", "vix_ret", "tnx_ret", "ticker_idx"]
    excess_feature_cols = ["lag_1_excess", "lag_2_excess", "lag_3_excess", "lag_5_excess", "lag_10_excess",
                            "rsi", "momentum", "volume_z", "vix_ret", "tnx_ret", "ticker_idx"]

    print("\n[3/3] Running the three variants...")

    train_a = train_df.rename(columns={"y_raw": "y"})
    test_a = test_df.rename(columns={"y_raw": "y"})
    result_a = run_experiment("A) Raw target, raw features (reproduces original baseline)",
                               train_a, test_a, raw_feature_cols)

    train_b = train_df.rename(columns={"y_excess": "y"})
    test_b = test_df.rename(columns={"y_excess": "y"})
    result_b = run_experiment("B) Demeaned (excess) target, raw features",
                               train_b, test_b, raw_feature_cols)

    result_c = run_experiment("C) Demeaned (excess) target, demeaned (excess) features",
                               train_b, test_b, excess_feature_cols)

    print("\n\n=== SUMMARY ===")
    print(f"{'Variant':<55} {'Floor':>10} {'LogReg':>10}")
    for r in (result_a, result_b, result_c):
        print(f"{r['label']:<55} {r['majority_acc']:>9.4%} {r['lr_acc']:>9.4%}")

finally:
    db.close()
