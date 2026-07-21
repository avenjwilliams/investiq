import React, { useState, useEffect } from 'react';
import { getModelMetrics } from '../api/api';

const CATEGORY_COLORS = {
  'Sector':        '#3b82f6',
  'Broad Market':  '#10b981',
  'Thematic':      '#f97316',
  'International': '#6366f1',
  'Commodity':     '#d97706',
  'Factor':        '#e11d48',
};

const fmt = {
  pct:  v => `${(v * 100).toFixed(1)}%`,
  mse:  v => v.toExponential(2),
  mae:  v => v.toFixed(5),
  date: iso => new Date(iso).toLocaleDateString('en-US', {
    month: 'short', day: 'numeric', year: 'numeric',
    hour: 'numeric', minute: '2-digit',
  }),
};

function StatCard({ label, value, sub, color }) {
  return (
    <div className="card" style={{ padding: '20px 24px', flex: 1, minWidth: '160px' }}>
      <div style={{ fontSize: '12px', color: '#9ca3af', textTransform: 'uppercase', letterSpacing: '0.5px', marginBottom: '6px' }}>
        {label}
      </div>
      <div style={{ fontSize: '26px', fontWeight: '700', color: color || '#111827' }}>
        {value}
      </div>
      {sub && <div style={{ fontSize: '12px', color: '#6b7280', marginTop: '4px' }}>{sub}</div>}
    </div>
  );
}

function DirAccBar({ value }) {
  const pct = value * 100;
  const color = pct >= 55 ? '#10b981' : pct >= 50 ? '#f97316' : '#ef4444';
  return (
    <div style={{ display: 'flex', alignItems: 'center', gap: '8px' }}>
      <div style={{ flex: 1, height: '6px', background: '#f3f4f6', borderRadius: '999px', overflow: 'hidden' }}>
        <div style={{ width: `${pct}%`, height: '100%', background: color, borderRadius: '999px' }} />
      </div>
      <span style={{ fontSize: '12px', fontWeight: '600', color, minWidth: '38px', textAlign: 'right' }}>
        {fmt.pct(value)}
      </span>
    </div>
  );
}

function ModelMetrics() {
  const [metrics, setMetrics] = useState(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState(null);
  const [sortKey, setSortKey] = useState('directional_accuracy');
  const [sortDir, setSortDir] = useState('desc');
  const [categoryFilter, setCategoryFilter] = useState('All');

  useEffect(() => {
    getModelMetrics()
      .then(setMetrics)
      .catch(e => setError(e.response?.data?.detail || e.message))
      .finally(() => setLoading(false));
  }, []);

  const handleSort = (key) => {
    if (sortKey === key) {
      setSortDir(d => d === 'desc' ? 'asc' : 'desc');
    } else {
      setSortKey(key);
      setSortDir('desc');
    }
  };

  const SortHeader = ({ label, field, style }) => {
    const active = sortKey === field;
    return (
      <th
        onClick={() => handleSort(field)}
        style={{
          padding: '10px 14px', textAlign: 'left', fontSize: '11px',
          fontWeight: '600', color: active ? '#7c3aed' : '#6b7280',
          textTransform: 'uppercase', letterSpacing: '0.5px',
          cursor: 'pointer', userSelect: 'none', whiteSpace: 'nowrap',
          ...style,
        }}
      >
        {label} {active ? (sortDir === 'desc' ? '↓' : '↑') : ''}
      </th>
    );
  };

  if (loading) return <div className="loading">Loading metrics…</div>;

  if (error) return (
    <div>
      <div className="page-header">
        <h1>Model Metrics</h1>
        <p>Evaluation results from the last training run</p>
      </div>
      <div style={{
        padding: '40px', textAlign: 'center', color: '#9ca3af',
        background: '#f9fafb', borderRadius: '12px', border: '1px dashed #e5e7eb',
      }}>
        <div style={{ fontSize: '24px', marginBottom: '12px' }}>📊</div>
        <div style={{ fontWeight: '600', color: '#374151', marginBottom: '6px' }}>No metrics available</div>
        <div style={{ fontSize: '13px' }}>Train the model first from the Forecasts page — metrics are computed automatically.</div>
      </div>
    </div>
  );

  const perTicker = Object.entries(metrics.per_ticker).map(([ticker, m]) => ({ ticker, ...m }));

  const categories = ['All', ...Array.from(new Set(perTicker.map(r => r.category))).filter(Boolean).sort()];

  const filtered = perTicker
    .filter(r => categoryFilter === 'All' || r.category === categoryFilter)
    .sort((a, b) => {
      const av = a[sortKey] ?? 0;
      const bv = b[sortKey] ?? 0;
      return sortDir === 'desc' ? bv - av : av - bv;
    });

  const overall = metrics.overall;
  const meanDirAcc = overall.mean_directional_accuracy;
  const dirAccColor = meanDirAcc >= 0.55 ? '#10b981' : meanDirAcc >= 0.50 ? '#f97316' : '#ef4444';

  return (
    <div>
      <div className="page-header">
        <h1>Model Metrics</h1>
        <p>
          Evaluation on held-out test set ({metrics.test_timesteps} trading days) ·
          Trained {fmt.date(metrics.trained_at)}
        </p>
      </div>

      {/* Summary cards */}
      <div style={{ display: 'flex', gap: '16px', marginBottom: '28px', flexWrap: 'wrap' }}>
        <StatCard
          label="Mean Directional Accuracy"
          value={fmt.pct(meanDirAcc)}
          sub="% of forecasted return signs correct"
          color={dirAccColor}
        />
        <StatCard
          label="Mean MAE"
          value={fmt.mae(overall.mean_mae)}
          sub="Mean absolute error on log returns"
        />
        <StatCard
          label="Mean MSE"
          value={fmt.mse(overall.mean_mse)}
          sub="Mean squared error on log returns"
        />
        <StatCard
          label="Train / Test Split"
          value="80 / 20"
          sub={`${metrics.train_timesteps} train · ${metrics.test_timesteps} test days`}
        />
        <StatCard
          label="Final Val Loss"
          value={metrics.final_val_loss != null ? fmt.mse(metrics.final_val_loss) : '—'}
          sub={`Train loss: ${fmt.mse(metrics.final_train_loss)}`}
        />
      </div>

      {/* Directional accuracy note */}
      <div style={{
        padding: '12px 16px', borderRadius: '8px', marginBottom: '20px', fontSize: '13px',
        background: meanDirAcc >= 0.55 ? '#ecfdf5' : meanDirAcc >= 0.50 ? '#fff7ed' : '#fef2f2',
        color: meanDirAcc >= 0.55 ? '#065f46' : meanDirAcc >= 0.50 ? '#92400e' : '#7f1d1d',
        border: `1px solid ${meanDirAcc >= 0.55 ? '#6ee7b7' : meanDirAcc >= 0.50 ? '#fcd34d' : '#fca5a5'}`,
      }}>
        <strong>Directional accuracy interpretation: </strong>
        50% = random chance (coin flip). Above 55% suggests the model has genuine predictive signal.
        Below 50% means the model's direction calls are worse than random on the test set.
      </div>

      {/* Per-ticker table */}
      <div className="card" style={{ padding: 0, overflow: 'hidden' }}>
        <div style={{ padding: '16px 20px', borderBottom: '1px solid #f3f4f6', display: 'flex', alignItems: 'center', gap: '12px', flexWrap: 'wrap' }}>
          <span style={{ fontWeight: '600', fontSize: '14px', color: '#111827' }}>
            Per-Ticker Results
          </span>
          <span style={{ fontSize: '12px', color: '#9ca3af' }}>
            {filtered.length} of {perTicker.length} ETFs · click column headers to sort
          </span>
          <div style={{ flex: 1 }} />
          <div className="toggle-group" style={{ margin: 0 }}>
            {categories.map(cat => (
              <button
                key={cat}
                className={`toggle-btn ${categoryFilter === cat ? 'active' : ''}`}
                onClick={() => setCategoryFilter(cat)}
                style={categoryFilter === cat && cat !== 'All' ? {
                  background: CATEGORY_COLORS[cat] || '#7c3aed',
                  borderColor: CATEGORY_COLORS[cat] || '#7c3aed',
                  color: 'white',
                } : {}}
              >
                {cat}
              </button>
            ))}
          </div>
        </div>

        <div style={{ overflowX: 'auto' }}>
          <table style={{ width: '100%', borderCollapse: 'collapse' }}>
            <thead>
              <tr style={{ background: '#f9fafb', borderBottom: '1px solid #f3f4f6' }}>
                <SortHeader label="Ticker" field="ticker" />
                <th style={{ padding: '10px 14px', fontSize: '11px', fontWeight: '600', color: '#6b7280', textTransform: 'uppercase', letterSpacing: '0.5px' }}>
                  Category
                </th>
                <SortHeader label="Dir. Accuracy" field="directional_accuracy" />
                <SortHeader label="MAE" field="mae" style={{ textAlign: 'right' }} />
                <SortHeader label="MSE" field="mse" style={{ textAlign: 'right' }} />
                <SortHeader label="Test Windows" field="test_windows" style={{ textAlign: 'right' }} />
              </tr>
            </thead>
            <tbody>
              {filtered.map((row, idx) => {
                const catColor = CATEGORY_COLORS[row.category] || '#7c3aed';
                return (
                  <tr
                    key={row.ticker}
                    style={{
                      borderBottom: '1px solid #f3f4f6',
                      background: idx % 2 === 0 ? '#fff' : '#fafafa',
                    }}
                  >
                    <td style={{ padding: '12px 14px', fontWeight: '700', color: catColor, fontSize: '14px' }}>
                      {row.ticker}
                    </td>
                    <td style={{ padding: '12px 14px' }}>
                      <span style={{
                        fontSize: '11px', fontWeight: '600', padding: '2px 8px',
                        borderRadius: '999px', background: catColor + '20', color: catColor,
                        border: `1px solid ${catColor}40`,
                      }}>
                        {row.category || '—'}
                      </span>
                    </td>
                    <td style={{ padding: '12px 14px', minWidth: '160px' }}>
                      <DirAccBar value={row.directional_accuracy} />
                    </td>
                    <td style={{ padding: '12px 14px', textAlign: 'right', fontFamily: 'monospace', fontSize: '13px', color: '#374151' }}>
                      {fmt.mae(row.mae)}
                    </td>
                    <td style={{ padding: '12px 14px', textAlign: 'right', fontFamily: 'monospace', fontSize: '13px', color: '#374151' }}>
                      {fmt.mse(row.mse)}
                    </td>
                    <td style={{ padding: '12px 14px', textAlign: 'right', fontSize: '13px', color: '#6b7280' }}>
                      {row.test_windows}
                    </td>
                  </tr>
                );
              })}
            </tbody>
          </table>
        </div>
      </div>
    </div>
  );
}

export default ModelMetrics;
