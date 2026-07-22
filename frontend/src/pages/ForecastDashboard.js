import React, { useState, useEffect, useCallback } from 'react';
import {
  ComposedChart, Line, XAxis, YAxis,
  ResponsiveContainer, Tooltip
} from 'recharts';
import { listTrainedModels, getETFForecast, trainAllForecasts } from '../api/api';

const CATEGORY_COLORS = {
  'Sector':        '#3b82f6',
  'Broad Market':  '#10b981',
  'Thematic':      '#f97316',
  'International': '#6366f1',
  'Commodity':     '#d97706',
  'Factor':        '#e11d48',
};

const CATEGORIES = ['All', 'Sector', 'Broad Market', 'Thematic', 'International', 'Commodity', 'Factor'];

const formatDate = (dateStr) => {
  const d = new Date(dateStr);
  return d.toLocaleDateString('en-US', { month: 'short', day: 'numeric' });
};

const formatLastTrained = (isoString) => {
  if (!isoString) return null;
  const d = new Date(isoString);
  return d.toLocaleDateString('en-US', {
    month: 'short', day: 'numeric', year: 'numeric',
    hour: 'numeric', minute: '2-digit',
  });
};

const MiniTooltip = ({ active, payload }) => {
  if (active && payload && payload.length) {
    const p = payload[0];
    return (
      <div style={{
        background: '#fff', border: '1px solid #e5e7eb',
        borderRadius: '6px', padding: '6px 10px', fontSize: '11px',
      }}>
        <div style={{ color: p.color, fontWeight: '600' }}>${p.value?.toFixed(2)}</div>
      </div>
    );
  }
  return null;
};

function ForecastCard({ etf, forecast }) {
  const color = CATEGORY_COLORS[etf.category] || '#7c3aed';
  const isPositive = forecast && forecast.pct_change_90d >= 0;

  const chartData = React.useMemo(() => {
    if (!forecast) return [];
    const historical = forecast.historical.slice(-30).map(h => ({
      date: formatDate(h.date),
      actual: h.price,
      forecast: null,
    }));
    const forecastPoints = forecast.forecast.map(f => ({
      date: formatDate(f.date),
      actual: null,
      forecast: f.price,
    }));
    if (historical.length && forecastPoints.length) {
      forecastPoints[0] = { ...forecastPoints[0], forecast: historical[historical.length - 1].actual };
    }
    return [...historical, ...forecastPoints];
  }, [forecast]);

  return (
    <div className="card" style={{ padding: '16px', display: 'flex', flexDirection: 'column', gap: '12px' }}>
      {/* Header */}
      <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'flex-start' }}>
        <div>
          <div style={{ fontWeight: '700', fontSize: '17px', color }}>{etf.ticker}</div>
          <div style={{ fontSize: '11px', color: '#9ca3af', marginTop: '2px', lineHeight: '1.3' }}>
            {etf.name.length > 32 ? etf.name.slice(0, 32) + '…' : etf.name}
          </div>
        </div>
        <span style={{
          fontSize: '10px', fontWeight: '600', padding: '2px 8px',
          borderRadius: '999px', background: color + '20', color,
          border: `1px solid ${color}40`, whiteSpace: 'nowrap',
        }}>
          {etf.category}
        </span>
      </div>

      {/* Chart or awaiting model */}
      {forecast ? (
        <>
          <ResponsiveContainer width="100%" height={90}>
            <ComposedChart data={chartData} margin={{ top: 2, right: 2, left: 2, bottom: 2 }}>
              <XAxis dataKey="date" hide />
              <YAxis domain={['auto', 'auto']} hide />
              <Tooltip content={<MiniTooltip />} />
              <Line
                type="monotone" dataKey="actual"
                stroke={color} strokeWidth={1.5}
                dot={false} connectNulls={false}
              />
              <Line
                type="monotone" dataKey="forecast"
                stroke="#7c3aed" strokeWidth={1.5}
                strokeDasharray="4 3"
                dot={false} connectNulls={false}
              />
            </ComposedChart>
          </ResponsiveContainer>

          <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
            <div>
              <div style={{ fontSize: '10px', color: '#9ca3af', textTransform: 'uppercase', letterSpacing: '0.5px' }}>
                Current
              </div>
              <div style={{ fontSize: '14px', fontWeight: '600', color: '#111827' }}>
                ${forecast.last_actual_price.toFixed(2)}
              </div>
            </div>
            <div style={{ textAlign: 'center' }}>
              <div style={{ fontSize: '10px', color: '#9ca3af', textTransform: 'uppercase', letterSpacing: '0.5px' }}>
                90-Day Change
              </div>
              <div style={{
                fontSize: '16px', fontWeight: '700',
                color: isPositive ? '#10b981' : '#ef4444',
              }}>
                {isPositive ? '+' : ''}{forecast.pct_change_90d.toFixed(2)}%
              </div>
            </div>
            <div style={{ textAlign: 'right' }}>
              <div style={{ fontSize: '10px', color: '#9ca3af', textTransform: 'uppercase', letterSpacing: '0.5px' }}>
                Target
              </div>
              <div style={{ fontSize: '14px', fontWeight: '600', color: '#111827' }}>
                ${forecast.predicted_price_90d.toFixed(2)}
              </div>
            </div>
          </div>
        </>
      ) : (
        <div style={{
          flex: 1, display: 'flex', alignItems: 'center', justifyContent: 'center',
          padding: '20px 0', background: '#f9fafb', borderRadius: '8px',
          border: '1px dashed #e5e7eb',
        }}>
          <div style={{ fontSize: '12px', color: '#9ca3af' }}>Awaiting forecast results</div>
        </div>
      )}
    </div>
  );
}

function ForecastDashboard() {
  const [etfs, setEtfs] = useState([]);
  const [forecasts, setForecasts] = useState({});
  const [modelReady, setModelReady] = useState(false);
  const [lastTrained, setLastTrained] = useState(null);
  const [trainingEnabled, setTrainingEnabled] = useState(true);
  const [loading, setLoading] = useState(true);
  const [loadingForecasts, setLoadingForecasts] = useState(false);
  const [forecastsLoaded, setForecastsLoaded] = useState(false);
  const [trainingAll, setTrainingAll] = useState(false);
  const [categoryFilter, setCategoryFilter] = useState('All');
  const [sortBy, setSortBy] = useState('category');
  const [statusMsg, setStatusMsg] = useState(null);

  // On mount: only load the ETF list and model status — don't fetch forecasts yet
  const loadModels = useCallback(() => {
    setLoading(true);
    listTrainedModels()
      .then(data => {
        setModelReady(data.model_ready);
        setLastTrained(data.last_trained);
        setTrainingEnabled(data.training_enabled !== false);
        setEtfs(data.etfs);
      })
      .finally(() => setLoading(false));
  }, []);

  useEffect(() => { loadModels(); }, [loadModels]);

  // Fetch all forecasts with a concurrency limit — streams cards in as they resolve
  const loadForecasts = useCallback((etfList) => {
    const list = etfList || etfs;
    if (!list.length) return;
    setLoadingForecasts(true);
    setForecastsLoaded(false);
    setForecasts({});

    const CONCURRENCY = 5;
    let index = 0;
    let completed = 0;

    const runNext = () => {
      if (index >= list.length) return Promise.resolve();
      const etf = list[index++];
      return getETFForecast(etf.ticker)
        .then(f => {
          setForecasts(prev => ({ ...prev, [etf.ticker]: f }));
        })
        .catch(() => { /* silently skip failed tickers */ })
        .finally(() => {
          completed++;
          if (completed === list.length) {
            setForecastsLoaded(true);
            setLoadingForecasts(false);
          } else {
            return runNext();
          }
        });
    };

    // Kick off CONCURRENCY workers
    Array.from({ length: Math.min(CONCURRENCY, list.length) }, runNext);
  }, [etfs]);

  const handleUpdateModel = () => {
    setTrainingAll(true);
    setStatusMsg(null);
    trainAllForecasts()
      .then(() => {
        setStatusMsg('Model update started in the background. Click "Update Forecasts" in a few minutes to see results.');
      })
      .catch(() => setStatusMsg('Failed to start model update.'))
      .finally(() => setTrainingAll(false));
  };

  const visibleEtfs = etfs
    .filter(e => categoryFilter === 'All' || e.category === categoryFilter)
    .sort((a, b) => {
      if (sortBy === 'return') {
        const fa = forecasts[a.ticker]?.pct_change_90d ?? -Infinity;
        const fb = forecasts[b.ticker]?.pct_change_90d ?? -Infinity;
        return fb - fa;
      }
      if (sortBy === 'return_asc') {
        const fa = forecasts[a.ticker]?.pct_change_90d ?? Infinity;
        const fb = forecasts[b.ticker]?.pct_change_90d ?? Infinity;
        return fa - fb;
      }
      if (a.category !== b.category) return a.category.localeCompare(b.category);
      return a.ticker.localeCompare(b.ticker);
    });

  return (
    <div>
      <div className="page-header">
        <h1>Forecast Dashboard</h1>
        <p>90-day Transformer price forecasts across the full ETF universe</p>
      </div>

      {/* Controls bar */}
      <div style={{ display: 'flex', gap: '12px', marginBottom: '20px', flexWrap: 'wrap', alignItems: 'center' }}>

        <button
          className="btn btn-primary"
          onClick={handleUpdateModel}
          disabled={trainingAll || !trainingEnabled}
          title={trainingEnabled ? undefined : "Disabled on this host — training in-process needs more RAM than the free tier's 512MB. The shipped model is trained locally and committed to the repo."}
        >
          {trainingAll ? 'Starting…' : trainingEnabled ? '⚡ Update Model' : '⚡ Update Model (disabled)'}
        </button>

        <button
          className={`btn ${forecastsLoaded ? 'btn-success' : 'btn-dark'}`}
          onClick={() => loadForecasts()}
          disabled={loadingForecasts || !modelReady}
        >
          {loadingForecasts ? 'Loading…' : forecastsLoaded ? '↻ Update Forecasts' : '▶ Forecast'}
        </button>

        {/* Last trained indicator */}
        {lastTrained && (
          <div style={{ fontSize: '13px', color: '#6b7280' }}>
            Model last trained:{' '}
            <span style={{ fontWeight: '600', color: '#374151' }}>
              {formatLastTrained(lastTrained)}
            </span>
          </div>
        )}

        <div style={{ flex: 1 }} />

        <select
          className="select"
          value={sortBy}
          onChange={e => setSortBy(e.target.value)}
        >
          <option value="category">Sort: Category</option>
          <option value="return">Sort: Highest Return</option>
          <option value="return_asc">Sort: Lowest Return</option>
        </select>
      </div>

      {/* Status message */}
      {statusMsg && (
        <div style={{
          padding: '12px 16px', borderRadius: '8px', marginBottom: '16px',
          background: '#ede9fe', color: '#5b21b6', fontSize: '13px', fontWeight: '500',
        }}>
          {statusMsg}
        </div>
      )}

      {/* Category filter */}
      <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: '20px', flexWrap: 'wrap', gap: '12px' }}>
        <div className="toggle-group" style={{ margin: 0, flexWrap: 'wrap' }}>
          {CATEGORIES.map(cat => (
            <button
              key={cat}
              className={`toggle-btn ${categoryFilter === cat ? 'active' : ''}`}
              onClick={() => setCategoryFilter(cat)}
              style={categoryFilter === cat && cat !== 'All' ? {
                background: CATEGORY_COLORS[cat],
                borderColor: CATEGORY_COLORS[cat],
                color: 'white',
              } : {}}
            >
              {cat}
            </button>
          ))}
        </div>

        <div style={{ fontSize: '13px', color: '#6b7280', whiteSpace: 'nowrap' }}>
          {modelReady
            ? <span style={{ color: '#10b981', fontWeight: '600' }}>● Model ready</span>
            : <span style={{ color: '#f97316', fontWeight: '600' }}>● No model trained</span>
          }
        </div>
      </div>

      {/* Grid */}
      {loading ? (
        <div className="loading">Loading…</div>
      ) : !modelReady ? (
        <div style={{
          textAlign: 'center', padding: '60px 20px', color: '#9ca3af', fontSize: '14px',
        }}>
          No model trained yet. Click <strong>Update Model</strong> to train the shared Transformer across all ETFs.
        </div>
      ) : !forecastsLoaded && !loadingForecasts ? (
        <div style={{
          textAlign: 'center', padding: '60px 20px', color: '#9ca3af', fontSize: '14px',
        }}>
          Click <strong style={{ color: '#111827' }}>▶ Forecast</strong> to load 90-day predictions.
        </div>
      ) : (
        <>
          {loadingForecasts && (
            <div style={{ fontSize: '13px', color: '#6b7280', marginBottom: '12px' }}>
              Loading forecasts… ({Object.keys(forecasts).length} / {etfs.length})
            </div>
          )}
          <div style={{
            display: 'grid',
            gridTemplateColumns: 'repeat(auto-fill, minmax(280px, 1fr))',
            gap: '16px',
          }}>
            {visibleEtfs.map(etf => (
              <ForecastCard
                key={etf.ticker}
                etf={etf}
                forecast={forecasts[etf.ticker] || null}
              />
            ))}
          </div>
        </>
      )}
    </div>
  );
}

export default ForecastDashboard;
