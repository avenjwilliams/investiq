import numpy as np
import pandas as pd
import os
import json
import joblib
from datetime import timedelta

from sqlalchemy.orm import Session
from backend.data.database import ETFPrice

LOOKBACK = 60
FORECAST_HORIZON = 90
EPOCHS = 150
BATCH_SIZE = 64
TRAIN_SPLIT = 0.8

# Transformer hyperparameters
D_MODEL = 32        # smaller projection — less capacity, less overfitting
NUM_HEADS = 4       # attention heads (D_MODEL must be divisible by NUM_HEADS)
FF_DIM = 64         # feed-forward hidden size inside each transformer block
NUM_BLOCKS = 1      # single block — dataset is too small for deeper stacking
DROPOUT_RATE = 0.3  # higher dropout to regularize aggressively
EMBEDDING_DIM = 16  # ticker embedding size

# Directional head
ALPHA = 0.4         # weight on the direction (classification) loss; forecast (regression) gets (1 - ALPHA)

# Cross-validation
N_FOLDS = 5          # walk-forward (expanding window) CV folds

# Ticker-specific technical features — fed in alongside the ticker embedding
# (not as extra channels in the shared return/macro sequence) so richer signal
# doesn't multiply the sequence input's channel count across 40 tickers, which
# would risk overfitting the already-small (~940 row) training set.
RSI_WINDOW = 14
MOMENTUM_WINDOW = 10
VOLUME_Z_WINDOW = 20
N_TICKER_FEATURES = 3  # [rsi_scaled, momentum, volume_z]

MODEL_DIR = os.path.join(os.path.dirname(__file__), "..", "models")
os.makedirs(MODEL_DIR, exist_ok=True)

MODEL_PATH        = os.path.join(MODEL_DIR, "multivariate_transformer.keras")
SCALER_PATH       = os.path.join(MODEL_DIR, "transformer_scaler.pkl")
TICKER_INDEX_PATH = os.path.join(MODEL_DIR, "transformer_ticker_index.json")
METRICS_PATH      = os.path.join(MODEL_DIR, "transformer_metrics.json")
CV_METRICS_PATH   = os.path.join(MODEL_DIR, "transformer_cv_metrics.json")


# ── Data helpers ──────────────────────────────────────────────────────────────

def _get_all_prices(tickers: list[str], db: Session) -> pd.DataFrame:
    series = {}
    for ticker in tickers:
        rows = (
            db.query(ETFPrice)
            .filter(ETFPrice.ticker == ticker)
            .order_by(ETFPrice.date)
            .all()
        )
        if rows:
            series[ticker] = pd.Series(
                [r.adj_close for r in rows],
                index=pd.to_datetime([r.date for r in rows]),
            )
    df = pd.DataFrame(series).dropna()
    return df


def _get_all_prices_and_volume(tickers: list[str], db: Session):
    """
    Like _get_all_prices, but also pulls volume, from the same DB rows so both
    series are guaranteed to share the exact same dates per ticker before the
    cross-ticker alignment/dropna() step.
    Returns (prices_df, volume_df), both [T_raw, N_ETF], identically aligned.
    """
    price_series, volume_series = {}, {}
    for ticker in tickers:
        rows = (
            db.query(ETFPrice)
            .filter(ETFPrice.ticker == ticker)
            .order_by(ETFPrice.date)
            .all()
        )
        if rows:
            idx = pd.to_datetime([r.date for r in rows])
            price_series[ticker] = pd.Series([r.adj_close for r in rows], index=idx)
            volume_series[ticker] = pd.Series([r.volume for r in rows], index=idx)

    prices_df = pd.DataFrame(price_series)
    volume_df = pd.DataFrame(volume_series)
    # Align both frames on dates that are fully populated in BOTH (not just each
    # independently) — a row missing volume for one ticker shouldn't silently
    # desync the two frames' indices from each other.
    combined = pd.concat([prices_df, volume_df], axis=1, keys=["price", "volume"]).dropna()
    return combined["price"], combined["volume"]


def _to_log_returns(prices: pd.DataFrame) -> pd.DataFrame:
    return np.log(prices / prices.shift(1)).dropna()


def _compute_ticker_features(prices_df: pd.DataFrame, volume_df: pd.DataFrame):
    """
    Per-ticker technical indicators, computed from raw price/volume levels
    (not returns), aligned to prices_df's full index (including the first row,
    which callers must drop/reindex to match a returns_df that lost it to diff()):

      rsi_scaled: 14-day RSI, rescaled from [0, 100] to roughly [-1, 1] via (RSI-50)/50
      momentum:   10-day log return, i.e. log(price_t / price_{t-10}) — same scale
                  as the other return channels
      volume_z:   (volume - 20d rolling mean) / 20d rolling std — flags unusual
                  trading activity relative to that ticker's own recent history

    Returns (rsi_scaled_df, momentum_df, volume_z_df), each [T_raw, N_ETF].
    """
    delta = prices_df.diff()
    gain = delta.clip(lower=0)
    loss = -delta.clip(upper=0)
    avg_gain = gain.rolling(RSI_WINDOW).mean()
    avg_loss = loss.rolling(RSI_WINDOW).mean()
    rs = avg_gain / avg_loss.replace(0, np.nan)
    rsi = 100 - (100 / (1 + rs))
    rsi_scaled = (rsi - 50) / 50

    momentum = np.log(prices_df / prices_df.shift(MOMENTUM_WINDOW))

    vol_mean = volume_df.rolling(VOLUME_Z_WINDOW).mean()
    vol_std = volume_df.rolling(VOLUME_Z_WINDOW).std()
    volume_z = (volume_df - vol_mean) / vol_std.replace(0, np.nan)

    return rsi_scaled, momentum, volume_z


def _get_macro_features(aligned_index: pd.DatetimeIndex) -> pd.DataFrame:
    """
    Fetch VIX (^VIX) and 10-year Treasury yield (^TNX) from yfinance.
    Aligns to aligned_index, forward-fills any missing trading days.
    Returns a DataFrame with columns ["VIX", "TNX"].
    """
    import yfinance as yf
    start = aligned_index[0].strftime("%Y-%m-%d")
    end   = (aligned_index[-1] + pd.Timedelta(days=5)).strftime("%Y-%m-%d")

    macro = {}
    for yf_ticker, col in [("^VIX", "VIX"), ("^TNX", "TNX")]:
        df = yf.download(yf_ticker, start=start, end=end, auto_adjust=True, progress=False)
        if isinstance(df.columns, pd.MultiIndex):
            df.columns = df.columns.get_level_values(0)
        macro[col] = df["Close"]

    macro_df = pd.DataFrame(macro)
    macro_df.index = pd.to_datetime(macro_df.index).tz_localize(None)
    # Align to ETF trading dates, fill any gaps
    macro_df = macro_df.reindex(aligned_index).ffill().bfill()
    return macro_df


def _load_aligned_returns(db: Session):
    """
    Shared data-prep pipeline used by both train_all() and train_cv().
    Returns (returns_df, ticker_features, tickers, N_ETF, N, T).

    ticker_features is a [T, N_ETF, N_TICKER_FEATURES] array (rsi_scaled,
    momentum, volume_z per ticker), aligned row-for-row to returns_df — i.e.
    ticker_features[k, i, :] is "as of" the same date as returns_df.iloc[k]
    for ticker i.
    """
    all_tickers_rows = db.query(ETFPrice.ticker).distinct().all()
    all_tickers = sorted([r.ticker for r in all_tickers_rows])

    prices_df, volume_df = _get_all_prices_and_volume(all_tickers, db)
    if prices_df.empty or len(prices_df) < LOOKBACK + FORECAST_HORIZON:
        raise ValueError("Not enough aligned price data to train the model.")

    tickers = list(prices_df.columns)
    N_ETF = len(tickers)

    etf_returns = _to_log_returns(prices_df)

    print("[Transformer] Fetching macro features (VIX, TNX)...")
    macro_df = _get_macro_features(prices_df.index)
    macro_returns = _to_log_returns(macro_df)

    common_idx = etf_returns.index.intersection(macro_returns.index)
    etf_returns = etf_returns.loc[common_idx]
    macro_returns = macro_returns.loc[common_idx]

    returns_df = pd.concat([etf_returns, macro_returns], axis=1)
    N = len(returns_df.columns)
    T = len(returns_df)

    # Technical features computed on raw price/volume levels (T_raw = T+1 rows,
    # since _to_log_returns' diff() drops the first date), then reindexed to
    # exactly match returns_df's dates.
    rsi_df, momentum_df, volume_z_df = _compute_ticker_features(prices_df, volume_df)
    rsi_df = rsi_df.reindex(common_idx)[tickers]
    momentum_df = momentum_df.reindex(common_idx)[tickers]
    volume_z_df = volume_z_df.reindex(common_idx)[tickers]

    # Defensive fill for rolling-window warmup NaN (first ~20 rows). Anchors
    # always start at t >= LOOKBACK (60), well past this warmup zone, so this
    # only guards rows that are never actually used as a sample's "current"
    # feature slice — but fail safe rather than propagate NaN into the model.
    rsi_df = rsi_df.bfill().fillna(0.0)
    momentum_df = momentum_df.bfill().fillna(0.0)
    volume_z_df = volume_z_df.bfill().fillna(0.0)

    ticker_features = np.stack(
        [rsi_df.values, momentum_df.values, volume_z_df.values], axis=-1
    ).astype(np.float32)  # [T, N_ETF, N_TICKER_FEATURES]

    return returns_df, ticker_features, tickers, N_ETF, N, T


# ── Model existence ───────────────────────────────────────────────────────────

def model_exists(ticker: str = None) -> bool:
    return (
        os.path.exists(MODEL_PATH)
        and os.path.exists(SCALER_PATH)
        and os.path.exists(TICKER_INDEX_PATH)
    )


def _load_ticker_index() -> dict:
    with open(TICKER_INDEX_PATH) as f:
        return json.load(f)


# ── Architecture helpers ──────────────────────────────────────────────────────

def _positional_encoding(seq_len: int, d_model: int):
    """
    Classic sinusoidal positional encoding (Vaswani et al. 2017).
    Returns a [1, seq_len, d_model] constant tensor.
    """
    import tensorflow as tf
    positions = np.arange(seq_len)[:, np.newaxis]        # [seq_len, 1]
    dims      = np.arange(d_model)[np.newaxis, :]        # [1, d_model]
    angles    = positions / np.power(10000, (2 * (dims // 2)) / d_model)
    angles[:, 0::2] = np.sin(angles[:, 0::2])
    angles[:, 1::2] = np.cos(angles[:, 1::2])
    return tf.cast(angles[np.newaxis, :, :], dtype=tf.float32)  # [1, seq_len, d_model]


def _transformer_block(x, d_model: int, num_heads: int, ff_dim: int, dropout: float):
    """
    Single Transformer encoder block:
      x → MultiHeadAttention → Add & LayerNorm → FFN → Add & LayerNorm
    """
    from tensorflow.keras.layers import (
        MultiHeadAttention, LayerNormalization, Dense, Dropout, Add
    )

    # Self-attention sublayer
    attn_output = MultiHeadAttention(num_heads=num_heads, key_dim=d_model // num_heads)(x, x)
    attn_output = Dropout(dropout)(attn_output)
    x = LayerNormalization(epsilon=1e-6)(Add()([x, attn_output]))

    # Feed-forward sublayer
    ff = Dense(ff_dim, activation="relu")(x)
    ff = Dense(d_model)(ff)
    ff = Dropout(dropout)(ff)
    x = LayerNormalization(epsilon=1e-6)(Add()([x, ff]))

    return x


def _force_cpu_if_requested():
    """
    Some tensorflow-metal builds on Apple Silicon crash with a low-level
    `down_cast` assertion (tsl/platform/default/casts.h) on certain graph
    configurations — the multi-output (forecast + direction) model added here
    is a plausible trigger, since the single-output LSTM model doesn't hit it.
    Set TRANSFORMER_FORCE_CPU=1 in the environment to route around the Metal
    plugin's device-placement path entirely and confirm/avoid this.
    """
    if os.environ.get("TRANSFORMER_FORCE_CPU") == "1":
        import tensorflow as tf
        tf.config.set_visible_devices([], "GPU")


def _build_model(N: int, n_etf: int, n_ticker_features: int = N_TICKER_FEATURES):
    """
    Builds the dual-head multivariate Transformer:
      - "forecast" head: Dense(FORECAST_HORIZON) regression on scaled log returns (MSE loss)
      - "direction" head: Dense(FORECAST_HORIZON, sigmoid) predicting P(return > 0) per
        forecast day (binary cross-entropy loss), trained directly against the sign of
        each future return so it optimizes the metric we actually care about instead of
        inheriting direction as a side effect of a regression loss.
    Total loss = (1 - ALPHA) * mse + ALPHA * binary_crossentropy.

    A third input, ticker_features (RSI, momentum, volume z-score for the specific
    ticker being predicted), is concatenated alongside the ticker embedding before
    the output heads — added as scalar side-features rather than extra channels in
    the shared [LOOKBACK, N] sequence, so richer signal doesn't multiply the
    sequence's channel count across all 40 tickers on an already-small dataset.
    """
    from tensorflow.keras.models import Model
    from tensorflow.keras.layers import (
        Input, Dense, Dropout, Embedding, Flatten,
        Concatenate, GlobalAveragePooling1D
    )

    pe = _positional_encoding(LOOKBACK, D_MODEL)

    seq_input          = Input(shape=(LOOKBACK, N),          name="returns_sequence")
    ticker_input        = Input(shape=(1,),                  name="ticker_id", dtype="int32")
    ticker_feat_input   = Input(shape=(n_ticker_features,),  name="ticker_features")

    x = Dense(D_MODEL)(seq_input)   # [batch, LOOKBACK, D_MODEL]
    x = x + pe                       # add positional encoding

    for _ in range(NUM_BLOCKS):
        x = _transformer_block(x, D_MODEL, NUM_HEADS, FF_DIM, DROPOUT_RATE)

    x = GlobalAveragePooling1D()(x)  # [batch, D_MODEL]
    x = Dropout(DROPOUT_RATE)(x)

    emb = Embedding(input_dim=n_etf, output_dim=EMBEDDING_DIM, name="ticker_embedding")(ticker_input)
    emb = Flatten()(emb)

    merged = Concatenate()([x, emb, ticker_feat_input])

    forecast_output  = Dense(FORECAST_HORIZON, name="forecast")(merged)
    direction_output = Dense(FORECAST_HORIZON, activation="sigmoid", name="direction")(merged)

    model = Model(
        inputs=[seq_input, ticker_input, ticker_feat_input],
        outputs=[forecast_output, direction_output],
    )
    # NOTE: deliberately NOT calling model.compile()/model.fit() here. On this project's
    # TensorFlow 2.18 / Keras 3.11 build, Keras' built-in multi-output fit()/train_step
    # reliably crashes with a low-level `down_cast` assertion (tsl/platform/default/casts.h)
    # whenever this two-head model is trained on real (non-synthetic) data — confirmed via
    # bisection: single-output real data trains fine, dual-output synthetic data trains fine,
    # dual-output real data crashes every time regardless of CPU/GPU, eager mode, batch size,
    # or how the loss/loss_weights are specified. A manual tf.GradientTape training step on
    # the identical failing data does NOT crash, so training is done by hand in _fit_model()
    # below instead of via model.fit(). See _fit_model() for the training loop.
    return model


def _fit_model(model, X_seq, X_tid, X_feat, Y_reg, Y_dir, verbose: int = 1):
    """
    Manual training loop replacing model.fit() — see the note in _build_model()
    for why. Reimplements what we actually need from Keras' fit(): a chronological
    validation_split, ReduceLROnPlateau-style LR decay, and EarlyStopping with
    restore_best_weights, all monitoring validation loss.

    Returns a lightweight object with a `.history` dict shaped like Keras'
    History.history, so callers (train_all/train_cv) don't need to change:
    keys "loss", "val_loss", "direction_accuracy", "val_direction_accuracy".
    """
    import tensorflow as tf

    class _History:
        def __init__(self):
            self.history = {
                "loss": [], "val_loss": [],
                "direction_accuracy": [], "val_direction_accuracy": [],
            }

    # Chronological validation split (last 10%), matching Keras' validation_split semantics.
    n = len(X_seq)
    val_start = int(n * 0.9)
    Xs_tr, Xt_tr, Xf_tr, Yr_tr, Yd_tr = (
        X_seq[:val_start], X_tid[:val_start], X_feat[:val_start], Y_reg[:val_start], Y_dir[:val_start]
    )
    Xs_val, Xt_val, Xf_val, Yr_val, Yd_val = (
        X_seq[val_start:], X_tid[val_start:], X_feat[val_start:], Y_reg[val_start:], Y_dir[val_start:]
    )
    n_train = len(Xs_tr)

    optimizer = tf.keras.optimizers.Adam()
    mse_loss_fn = tf.keras.losses.MeanSquaredError()
    bce_loss_fn = tf.keras.losses.BinaryCrossentropy()

    def _direction_accuracy(y_true, y_prob):
        return float(tf.reduce_mean(tf.cast(tf.equal(tf.round(y_prob), y_true), tf.float32)))

    @tf.function
    def train_step(xb_seq, xb_tid, xb_feat, yb_reg, yb_dir):
        with tf.GradientTape() as tape:
            forecast_pred, direction_pred = model([xb_seq, xb_tid, xb_feat], training=True)
            loss_reg = mse_loss_fn(yb_reg, forecast_pred)
            loss_dir = bce_loss_fn(yb_dir, direction_pred)
            total_loss = (1.0 - ALPHA) * loss_reg + ALPHA * loss_dir
        grads = tape.gradient(total_loss, model.trainable_variables)
        optimizer.apply_gradients(zip(grads, model.trainable_variables))
        return total_loss, direction_pred

    def _evaluate(xs, xt, xf, yr, yd):
        forecast_pred, direction_pred = model([xs, xt, xf], training=False)
        loss_reg = mse_loss_fn(yr, forecast_pred)
        loss_dir = bce_loss_fn(yd, direction_pred)
        total_loss = (1.0 - ALPHA) * loss_reg + ALPHA * loss_dir
        return float(total_loss), _direction_accuracy(yd, direction_pred)

    history = _History()
    best_val_loss = float("inf")
    best_weights = None
    epochs_since_improve = 0
    lr_patience_counter = 0
    lr_reduce_patience = 8
    early_stop_patience = 30
    lr_factor = 0.5
    min_lr = 1e-6

    rng = np.random.default_rng()

    for epoch in range(EPOCHS):
        perm = rng.permutation(n_train)
        epoch_losses = []
        epoch_dir_correct = 0
        epoch_dir_total = 0

        for start in range(0, n_train, BATCH_SIZE):
            batch_idx = perm[start: start + BATCH_SIZE]
            xb_seq = tf.constant(Xs_tr[batch_idx])
            xb_tid = tf.constant(Xt_tr[batch_idx])
            xb_feat = tf.constant(Xf_tr[batch_idx])
            yb_reg = tf.constant(Yr_tr[batch_idx])
            yb_dir = tf.constant(Yd_tr[batch_idx])

            total_loss, direction_pred = train_step(xb_seq, xb_tid, xb_feat, yb_reg, yb_dir)
            epoch_losses.append(float(total_loss))
            epoch_dir_correct += float(tf.reduce_sum(tf.cast(
                tf.equal(tf.round(direction_pred), yb_dir), tf.float32)))
            epoch_dir_total += yb_dir.shape[0] * yb_dir.shape[1]

        train_loss = float(np.mean(epoch_losses))
        train_dir_acc = epoch_dir_correct / epoch_dir_total if epoch_dir_total else 0.0
        val_loss, val_dir_acc = _evaluate(
            tf.constant(Xs_val), tf.constant(Xt_val), tf.constant(Xf_val),
            tf.constant(Yr_val), tf.constant(Yd_val)
        )

        history.history["loss"].append(train_loss)
        history.history["val_loss"].append(val_loss)
        history.history["direction_accuracy"].append(train_dir_acc)
        history.history["val_direction_accuracy"].append(val_dir_acc)

        if verbose:
            current_lr = float(optimizer.learning_rate.numpy())
            print(f"Epoch {epoch + 1}/{EPOCHS} - loss: {train_loss:.6f} - dir_acc: {train_dir_acc:.4f} "
                  f"- val_loss: {val_loss:.6f} - val_dir_acc: {val_dir_acc:.4f} - lr: {current_lr:.2e}")

        # ReduceLROnPlateau + EarlyStopping, both monitoring val_loss
        if val_loss < best_val_loss - 1e-6:
            best_val_loss = val_loss
            best_weights = model.get_weights()
            epochs_since_improve = 0
            lr_patience_counter = 0
        else:
            epochs_since_improve += 1
            lr_patience_counter += 1

            if lr_patience_counter > lr_reduce_patience:
                current_lr = float(optimizer.learning_rate.numpy())
                new_lr = max(current_lr * lr_factor, min_lr)
                optimizer.learning_rate.assign(new_lr)
                lr_patience_counter = 0
                if verbose:
                    print(f"    ReduceLROnPlateau: lr -> {new_lr:.2e}")

            if epochs_since_improve > early_stop_patience:
                if verbose:
                    print(f"    EarlyStopping: no improvement in {early_stop_patience} epochs, stopping.")
                break

    if best_weights is not None:
        model.set_weights(best_weights)

    return history


def _build_samples(scaled: np.ndarray, raw: np.ndarray, ticker_features: np.ndarray,
                    N_ETF: int, N: int, t_start: int, t_end: int):
    """
    Build training samples for anchor points t in [t_start, t_end).
    One sample per (anchor, ETF ticker) pair. `scaled` and `raw` must have at
    least LOOKBACK rows of history available before t_start, and FORECAST_HORIZON
    rows available after the largest t.

    Y_reg targets scaled returns (regression). Y_dir targets sign(raw return) — the
    sign is taken from the *unscaled* return so it isn't distorted by the scaler's
    mean-centering. X_feat pulls ticker_features[t-1, i, :] — the target ticker's
    RSI/momentum/volume-z as of the last day of the input window (day before the
    forecast horizon begins).
    """
    X_seq, X_tid, X_feat, Y_reg, Y_dir = [], [], [], [], []
    for t in range(t_start, t_end):
        window = scaled[t - LOOKBACK: t, :]
        for i in range(N_ETF):
            X_seq.append(window)
            X_tid.append(i)
            X_feat.append(ticker_features[t - 1, i, :])
            Y_reg.append(scaled[t: t + FORECAST_HORIZON, i])
            Y_dir.append((raw[t: t + FORECAST_HORIZON, i] > 0).astype(np.float32))

    return (
        np.array(X_seq, dtype=np.float32),
        np.array(X_tid, dtype=np.int32),
        np.array(X_feat, dtype=np.float32),
        np.array(Y_reg, dtype=np.float32),
        np.array(Y_dir, dtype=np.float32),
    )


def _evaluate_model(model, full_scaled: np.ndarray, full_raw: np.ndarray,
                     ticker_features: np.ndarray, scaler,
                     tickers: list[str], N_ETF: int, N: int, eval_start: int, eval_end: int):
    """
    Evaluate a trained model on anchor points t in [eval_start, eval_end).
    Returns:
      ticker_metrics: {ticker: {mse, mae, directional_accuracy, test_windows}}
      horizon_acc_by_ticker: {ticker: np.ndarray of shape (FORECAST_HORIZON,)} —
        directional accuracy broken out by day-ahead, so it's visible whether
        the signal is concentrated in the near term and washed out by day 90.
    """
    ticker_metrics = {}
    horizon_acc_by_ticker = {}

    for i, ticker in enumerate(tickers[:N_ETF]):
        y_true_list, y_pred_list = [], []
        for t in range(eval_start, eval_end):
            window = full_scaled[t - LOOKBACK: t, :]
            X_s = window.reshape(1, LOOKBACK, N).astype(np.float32)
            X_t = np.array([[i]], dtype=np.int32)
            X_f = ticker_features[t - 1, i, :].reshape(1, -1).astype(np.float32)
            pred_scaled, _pred_dir_prob = model.predict([X_s, X_t, X_f], verbose=0)
            pred_scaled = pred_scaled[0]

            dummy_pred = np.zeros((FORECAST_HORIZON, N), dtype=np.float32)
            dummy_pred[:, i] = pred_scaled

            y_pred_list.append(scaler.inverse_transform(dummy_pred)[:, i])
            y_true_list.append(full_raw[t: t + FORECAST_HORIZON, i])

        if not y_true_list:
            continue

        y_pred = np.array(y_pred_list)
        y_true = np.array(y_true_list)

        sign_match = np.sign(y_pred) == np.sign(y_true)
        mse     = float(np.mean((y_pred - y_true) ** 2))
        mae     = float(np.mean(np.abs(y_pred - y_true)))
        dir_acc = float(np.mean(sign_match))

        ticker_metrics[ticker] = {
            "mse": round(mse, 8),
            "mae": round(mae, 6),
            "directional_accuracy": round(dir_acc, 4),
            "test_windows": len(y_true_list),
        }
        horizon_acc_by_ticker[ticker] = np.mean(sign_match, axis=0)  # (FORECAST_HORIZON,)

        print(f"[Metrics] {ticker}: MAE={mae:.6f} | DirAcc={dir_acc:.2%}")

    return ticker_metrics, horizon_acc_by_ticker


def _summarize_horizon_accuracy(horizon_acc_by_ticker: dict) -> list[float]:
    """Average per-horizon directional accuracy across tickers. Index 0 = day+1."""
    if not horizon_acc_by_ticker:
        return []
    stacked = np.vstack(list(horizon_acc_by_ticker.values()))  # (n_tickers, FORECAST_HORIZON)
    return [round(float(v), 4) for v in stacked.mean(axis=0)]


def _print_horizon_checkpoints(accuracy_by_horizon: list[float], label: str = "[Transformer]"):
    if not accuracy_by_horizon:
        return
    print(f"{label} Directional accuracy by forecast horizon (day-ahead):")
    for h in (1, 5, 10, 30, 60, 90):
        if h <= len(accuracy_by_horizon):
            print(f"    day +{h:>2}: {accuracy_by_horizon[h - 1]:.2%}")


# ── Training (production model) ────────────────────────────────────────────────

def train_all(db: Session) -> dict:
    """
    Train the production multivariate Transformer on all available ETFs simultaneously,
    using a single chronological 80/20 train/test split. Saves the model used by predict().

    Architecture:
      - Sequence input:  [batch, LOOKBACK, N_TICKERS]
      - Linear projection → [batch, LOOKBACK, D_MODEL]
      - Sinusoidal positional encoding
      - NUM_BLOCKS × Transformer encoder block (MHA + FFN + LayerNorm)
      - Global average pooling → [batch, D_MODEL]
      - Ticker embedding → [batch, EMBEDDING_DIM]
      - Concatenate → two heads: "forecast" (regression) and "direction" (classification)

    Loss: (1 - ALPHA) * MSE + ALPHA * binary_crossentropy(sign).
    """
    from sklearn.preprocessing import StandardScaler

    _force_cpu_if_requested()
    returns_df, ticker_features, tickers, N_ETF, N, T = _load_aligned_returns(db)

    split_idx = int(T * TRAIN_SPLIT)
    train_raw = returns_df.values[:split_idx]
    test_raw  = returns_df.values[split_idx:]

    scaler = StandardScaler()
    train_scaled = scaler.fit_transform(train_raw)
    test_scaled  = scaler.transform(test_raw)

    X_seq, X_tid, X_feat, Y_reg, Y_dir = _build_samples(
        train_scaled, train_raw, ticker_features, N_ETF, N, LOOKBACK, split_idx - FORECAST_HORIZON + 1
    )

    print(f"[Transformer] {N_ETF} ETFs + 2 macro | {N} total channels | "
          f"{split_idx} train / {T - split_idx} test | {len(X_seq)} samples")

    model = _build_model(N, N_ETF)
    history = _fit_model(model, X_seq, X_tid, X_feat, Y_reg, Y_dir, verbose=1)

    full_scaled = np.vstack([train_scaled, test_scaled])
    full_raw    = returns_df.values

    ticker_metrics, horizon_acc_by_ticker = _evaluate_model(
        model, full_scaled, full_raw, ticker_features, scaler, tickers, N_ETF, N,
        eval_start=split_idx, eval_end=T - FORECAST_HORIZON + 1,
    )
    accuracy_by_horizon = _summarize_horizon_accuracy(horizon_acc_by_ticker)
    _print_horizon_checkpoints(accuracy_by_horizon)

    all_mse = [v["mse"] for v in ticker_metrics.values()]
    all_mae = [v["mae"] for v in ticker_metrics.values()]
    all_dir = [v["directional_accuracy"] for v in ticker_metrics.values()]
    train_loss = history.history["loss"]
    val_loss   = history.history.get("val_loss", [])
    train_dir_acc = history.history.get("direction_accuracy", [])
    val_dir_acc   = history.history.get("val_direction_accuracy", [])

    metrics_payload = {
        "model": "transformer",
        "trained_at": pd.Timestamp.utcnow().isoformat(),
        "n_tickers": N,
        "train_timesteps": split_idx,
        "test_timesteps": T - split_idx,
        "total_samples": len(X_seq),
        "epochs": EPOCHS,
        "hyperparameters": {
            "d_model": D_MODEL,
            "num_heads": NUM_HEADS,
            "ff_dim": FF_DIM,
            "num_blocks": NUM_BLOCKS,
            "dropout": DROPOUT_RATE,
            "alpha_direction_weight": ALPHA,
        },
        "final_train_loss": round(float(train_loss[-1]), 8),
        "final_val_loss": round(float(val_loss[-1]), 8) if val_loss else None,
        "final_train_direction_accuracy": round(float(train_dir_acc[-1]), 4) if train_dir_acc else None,
        "final_val_direction_accuracy": round(float(val_dir_acc[-1]), 4) if val_dir_acc else None,
        "overall": {
            "mean_mse": round(float(np.mean(all_mse)), 8),
            "mean_mae": round(float(np.mean(all_mae)), 6),
            "mean_directional_accuracy": round(float(np.mean(all_dir)), 4),
        },
        # Directional accuracy at each day-ahead (index 0 = day+1 ... index 89 = day+90),
        # averaged across all tickers. Lets you see whether the signal is real near-term
        # and just gets diluted by the long end of the 90-day horizon.
        "accuracy_by_horizon": accuracy_by_horizon,
        "per_ticker": ticker_metrics,
    }

    model.save(MODEL_PATH)
    joblib.dump(scaler, SCALER_PATH)
    ticker_index = {
        "_meta": {"n_etf": N_ETF, "n_total": N},
        **{ticker: i for i, ticker in enumerate(tickers)},
    }
    with open(TICKER_INDEX_PATH, "w") as f:
        json.dump(ticker_index, f)
    with open(METRICS_PATH, "w") as f:
        json.dump(metrics_payload, f, indent=2)

    print(f"[Transformer] Done. Mean MAE={np.mean(all_mae):.6f} | Mean DirAcc={np.mean(all_dir):.2%}")
    return {
        "status": "trained",
        "model": "transformer",
        "tickers": tickers,
        "n_tickers": N,
        "samples": len(X_seq),
        "metrics": metrics_payload["overall"],
    }


def train(ticker: str, db: Session) -> dict:
    """Convenience alias — trains the full multivariate Transformer."""
    result = train_all(db)
    result["ticker"] = ticker
    return result


# ── Walk-forward cross-validation ──────────────────────────────────────────────

def train_cv(db: Session, n_folds: int = N_FOLDS) -> dict:
    """
    Expanding-window walk-forward cross-validation. Trains `n_folds` independent
    models, each on a progressively larger training window, and evaluates each on
    the chronological block immediately following its training window.

    This exists because a single 80/20 chronological split only tells you how the
    model did on one ~230-day regime — not nearly enough windows to trust a metric
    like "51.2% directional accuracy" (SE at n=143 is ~4.2 points, so that's not
    distinguishable from a coin flip). Averaging across folds gives a much more
    robust read, and the spread across folds shows how regime-dependent the model is.

    Does NOT touch the production model files (MODEL_PATH/SCALER_PATH/METRICS_PATH) —
    writes CV_METRICS_PATH only.
    """
    import tensorflow as tf
    from sklearn.preprocessing import StandardScaler

    _force_cpu_if_requested()
    returns_df, ticker_features, tickers, N_ETF, N, T = _load_aligned_returns(db)
    full_raw_all = returns_df.values

    # First half of history seeds the initial training window; the remaining half
    # is split into n_folds equal chronological test blocks (classic expanding-window CV).
    initial_train_end = int(T * 0.5)
    remaining = T - initial_train_end - FORECAST_HORIZON
    # Each fold's test block only needs enough days to yield a handful of eval
    # anchors — LOOKBACK context comes from data before the block (already part
    # of that fold's training window), not from this remaining budget. Requiring
    # a modest minimum (a few weeks) per fold is enough of a sanity check.
    MIN_TEST_BLOCK_DAYS = 20
    if remaining < n_folds * MIN_TEST_BLOCK_DAYS:
        raise ValueError(
            f"Not enough data for {n_folds}-fold walk-forward CV "
            f"(have {T} timesteps, {remaining} available for test blocks, "
            f"need at least {n_folds * MIN_TEST_BLOCK_DAYS}; use fewer folds or more history)."
        )
    block_size = remaining // n_folds

    fold_results = []
    horizon_acc_all_folds = []

    for fold in range(n_folds):
        train_end = initial_train_end + fold * block_size
        test_start = train_end
        test_end = (T - FORECAST_HORIZON + 1) if fold == n_folds - 1 else (train_end + block_size)

        train_raw = full_raw_all[:train_end]
        scaler = StandardScaler()
        train_scaled = scaler.fit_transform(train_raw)
        # Transform everything after train_end so evaluation has scaled inputs available
        # through the end of the dataset (no leakage — scaler was fit on train_raw only).
        rest_scaled = scaler.transform(full_raw_all[train_end:])
        full_scaled = np.vstack([train_scaled, rest_scaled])

        X_seq, X_tid, X_feat, Y_reg, Y_dir = _build_samples(
            train_scaled, train_raw, ticker_features, N_ETF, N, LOOKBACK, train_end - FORECAST_HORIZON + 1
        )

        print(f"[Transformer CV] Fold {fold + 1}/{n_folds}: train=[0:{train_end}] "
              f"({train_end} steps) | test=[{test_start}:{test_end}] "
              f"({test_end - test_start} steps) | {len(X_seq)} samples")

        model = _build_model(N, N_ETF)
        _fit_model(model, X_seq, X_tid, X_feat, Y_reg, Y_dir, verbose=0)

        ticker_metrics, horizon_acc_by_ticker = _evaluate_model(
            model, full_scaled, full_raw_all, ticker_features, scaler, tickers, N_ETF, N,
            eval_start=test_start, eval_end=test_end,
        )
        horizon_acc = _summarize_horizon_accuracy(horizon_acc_by_ticker)
        _print_horizon_checkpoints(horizon_acc, label=f"[Transformer CV fold {fold + 1}]")

        fold_dir_accs = [v["directional_accuracy"] for v in ticker_metrics.values()]
        mean_dir_acc = float(np.mean(fold_dir_accs)) if fold_dir_accs else None

        print(
            f"[Transformer CV] Fold {fold + 1} mean directional accuracy: "
            f"{mean_dir_acc:.2%}" if mean_dir_acc is not None else
            f"[Transformer CV] Fold {fold + 1}: no evaluable windows"
        )

        fold_results.append({
            "fold": fold + 1,
            "train_timesteps": train_end,
            "test_timesteps": test_end - test_start,
            "mean_directional_accuracy": round(mean_dir_acc, 4) if mean_dir_acc is not None else None,
            "accuracy_by_horizon": horizon_acc,
            "per_ticker": ticker_metrics,
        })
        if horizon_acc:
            horizon_acc_all_folds.append(horizon_acc)

        # Free the fold's model/graph before building the next one
        del model
        tf.keras.backend.clear_session()

    fold_dir_accs = [f["mean_directional_accuracy"] for f in fold_results if f["mean_directional_accuracy"] is not None]
    horizon_stack = np.array(horizon_acc_all_folds) if horizon_acc_all_folds else np.zeros((0, FORECAST_HORIZON))

    cv_payload = {
        "model": "transformer",
        "n_folds": n_folds,
        "evaluated_at": pd.Timestamp.utcnow().isoformat(),
        "fold_mean_directional_accuracy": [round(v, 4) for v in fold_dir_accs],
        "cv_mean_directional_accuracy": round(float(np.mean(fold_dir_accs)), 4) if fold_dir_accs else None,
        "cv_std_directional_accuracy": round(float(np.std(fold_dir_accs)), 4) if fold_dir_accs else None,
        "cv_mean_accuracy_by_horizon": (
            [round(float(v), 4) for v in horizon_stack.mean(axis=0)] if len(horizon_stack) else []
        ),
        "folds": fold_results,
    }

    with open(CV_METRICS_PATH, "w") as f:
        json.dump(cv_payload, f, indent=2)

    print(
        f"[Transformer CV] Done. {n_folds}-fold mean dir acc = "
        f"{cv_payload['cv_mean_directional_accuracy']} "
        f"(± {cv_payload['cv_std_directional_accuracy']})"
    )
    return cv_payload


# ── Inference ─────────────────────────────────────────────────────────────────

def predict(ticker: str, db: Session) -> dict:
    """
    Generate a 90-day price forecast for `ticker` using the Transformer model.
    Identical output shape to forecast.py so it can be swapped in routes.
    """
    import tensorflow as tf

    if not model_exists():
        raise FileNotFoundError("Transformer model not trained yet. Run train_all first.")

    ticker = ticker.upper()
    ticker_index = _load_ticker_index()

    if ticker not in ticker_index:
        raise ValueError(f"'{ticker}' was not part of the training set.")

    # compile=False — custom loss/heads not needed for inference
    model  = tf.keras.models.load_model(MODEL_PATH, compile=False)
    scaler = joblib.load(SCALER_PATH)

    meta = ticker_index.pop("_meta", {})
    N_ETF  = meta.get("n_etf", len(ticker_index))
    tickers_ordered = [t for t, _ in sorted(ticker_index.items(), key=lambda x: x[1])]
    ticker_idx = ticker_index[ticker]

    prices_df, volume_df = _get_all_prices_and_volume(tickers_ordered, db)
    if prices_df.empty:
        raise ValueError("Could not load aligned price data for inference.")

    etf_returns = _to_log_returns(prices_df)
    if len(etf_returns) < LOOKBACK:
        raise ValueError(f"Not enough history for inference (need {LOOKBACK} rows).")

    # Fetch macro features aligned to price dates
    macro_df      = _get_macro_features(prices_df.index)
    macro_returns = _to_log_returns(macro_df)
    common_idx    = etf_returns.index.intersection(macro_returns.index)
    etf_returns   = etf_returns.loc[common_idx]
    macro_returns = macro_returns.loc[common_idx]
    returns_df    = pd.concat([etf_returns[tickers_ordered], macro_returns], axis=1)

    # Same technical features used in training, evaluated as of the most recent
    # available date for the specific ticker being forecast.
    rsi_df, momentum_df, volume_z_df = _compute_ticker_features(prices_df, volume_df)
    rsi_df = rsi_df.reindex(common_idx)[tickers_ordered].bfill().fillna(0.0)
    momentum_df = momentum_df.reindex(common_idx)[tickers_ordered].bfill().fillna(0.0)
    volume_z_df = volume_z_df.reindex(common_idx)[tickers_ordered].bfill().fillna(0.0)

    last_returns  = returns_df.values[-LOOKBACK:]
    scaled_input  = scaler.transform(last_returns)

    X_seq = scaled_input.reshape(1, LOOKBACK, returns_df.shape[1]).astype(np.float32)
    X_tid = np.array([[ticker_idx]], dtype=np.int32)
    X_feat = np.array([[
        rsi_df[ticker].iloc[-1], momentum_df[ticker].iloc[-1], volume_z_df[ticker].iloc[-1],
    ]], dtype=np.float32)

    predicted_scaled, _predicted_dir_prob = model.predict([X_seq, X_tid, X_feat], verbose=0)
    predicted_scaled = predicted_scaled[0]

    dummy = np.zeros((FORECAST_HORIZON, returns_df.shape[1]), dtype=np.float32)
    dummy[:, ticker_idx] = predicted_scaled
    predicted_returns = scaler.inverse_transform(dummy)[:, ticker_idx]

    prices_series = prices_df[ticker]
    last_price = float(prices_series.iloc[-1])
    forecast_prices = []
    current = last_price
    for r in predicted_returns:
        current = current * np.exp(r)
        forecast_prices.append(round(float(current), 2))

    last_date = prices_series.index[-1]
    forecast_dates = []
    d = last_date
    while len(forecast_dates) < FORECAST_HORIZON:
        d += timedelta(days=1)
        if d.weekday() < 5:
            forecast_dates.append(d.strftime("%Y-%m-%d"))

    historical = [
        {
            "date": prices_series.index[i].strftime("%Y-%m-%d"),
            "price": round(float(prices_series.iloc[i]), 2),
        }
        for i in range(-LOOKBACK, 0)
    ]

    forecast = [
        {"date": forecast_dates[i], "price": forecast_prices[i]}
        for i in range(FORECAST_HORIZON)
    ]

    predicted_price = forecast_prices[-1]
    pct_change = (predicted_price - last_price) / last_price * 100

    return {
        "ticker": ticker,
        "model": "transformer",
        "last_actual_date": last_date.strftime("%Y-%m-%d"),
        "last_actual_price": last_price,
        "predicted_price_90d": round(predicted_price, 2),
        "pct_change_90d": round(pct_change, 2),
        "historical": historical,
        "forecast": forecast,
    }


def predict_all_pct_changes(db: Session) -> dict[str, float]:
    """
    Generate 90-day annualised return forecasts for every ticker in the
    training set, using the Transformer model. Mirrors forecast.py's
    predict_all_pct_changes() (same signature and return shape) so it can be
    swapped in wherever the LSTM version was used — e.g. Black-Litterman view
    generation. Loads the model and shared sequence input once, then predicts
    per-ticker with each ticker's own embedding index and technical features.

    Returns: { ticker: annualised_return_float, ... }
    """
    import tensorflow as tf

    if not model_exists():
        raise FileNotFoundError("Transformer model not trained yet. Run train_all first.")

    ticker_index = _load_ticker_index()
    meta = {k: v for k, v in ticker_index.items() if k != "_meta"}
    meta_info = ticker_index.get("_meta", {})
    N_ETF = meta_info.get("n_etf", len(meta))
    tickers_ordered = [t for t, _ in sorted(meta.items(), key=lambda x: x[1])]

    model  = tf.keras.models.load_model(MODEL_PATH, compile=False)
    scaler = joblib.load(SCALER_PATH)

    prices_df, volume_df = _get_all_prices_and_volume(tickers_ordered, db)
    if prices_df.empty:
        raise ValueError("Could not load aligned price data for inference.")

    etf_returns = _to_log_returns(prices_df)
    if len(etf_returns) < LOOKBACK:
        raise ValueError(f"Not enough history for inference (need {LOOKBACK} rows).")

    macro_df      = _get_macro_features(prices_df.index)
    macro_returns = _to_log_returns(macro_df)
    common_idx    = etf_returns.index.intersection(macro_returns.index)
    etf_returns   = etf_returns.loc[common_idx]
    macro_returns = macro_returns.loc[common_idx]
    returns_df    = pd.concat([etf_returns[tickers_ordered], macro_returns], axis=1)

    rsi_df, momentum_df, volume_z_df = _compute_ticker_features(prices_df, volume_df)
    rsi_df = rsi_df.reindex(common_idx)[tickers_ordered].bfill().fillna(0.0)
    momentum_df = momentum_df.reindex(common_idx)[tickers_ordered].bfill().fillna(0.0)
    volume_z_df = volume_z_df.reindex(common_idx)[tickers_ordered].bfill().fillna(0.0)

    last_returns = returns_df.values[-LOOKBACK:]
    scaled_input = scaler.transform(last_returns)
    X_seq_base   = scaled_input.reshape(1, LOOKBACK, returns_df.shape[1]).astype(np.float32)

    results = {}
    for ticker in tickers_ordered:
        try:
            idx = meta[ticker]
            X_tid = np.array([[idx]], dtype=np.int32)
            X_feat = np.array([[
                rsi_df[ticker].iloc[-1], momentum_df[ticker].iloc[-1], volume_z_df[ticker].iloc[-1],
            ]], dtype=np.float32)

            pred_scaled, _pred_dir_prob = model.predict([X_seq_base, X_tid, X_feat], verbose=0)
            pred_scaled = pred_scaled[0]

            dummy = np.zeros((FORECAST_HORIZON, returns_df.shape[1]), dtype=np.float32)
            dummy[:, idx] = pred_scaled
            pred_returns = scaler.inverse_transform(dummy)[:, idx]

            last_price = float(prices_df[ticker].iloc[-1])
            price = last_price
            for r in pred_returns:
                price *= np.exp(r)

            r_90d    = (price - last_price) / last_price
            r_annual = (1.0 + r_90d) ** (252.0 / 90.0) - 1.0
            results[ticker] = float(r_annual)
        except Exception as e:
            print(f"[predict_all_transformer] Skipping {ticker}: {e}")

    return results
