import React, { useState, useEffect } from 'react';
import {
  ComposedChart, Line, XAxis, YAxis, CartesianGrid,
  Tooltip, Legend, ResponsiveContainer, ReferenceLine
} from 'recharts';
import {
  listETFs, getETFPrices, getETFForecast,
  getETFSentiment, listTrainedModels
} from '../api/api';

const CATEGORY_COLORS = {
  'Sector':        '#3b82f6',
  'Broad Market':  '#10b981',
  'Thematic':      '#f97316',
  'International': '#6366f1',
  'Commodity':     '#d97706',
  'Factor':        '#e11d48',
};

const getBadgeClass = (category) => {
  if (category === 'Sector')        return 'badge badge-sector';
  if (category === 'Broad Market')  return 'badge badge-broad';
  if (category === 'International') return 'badge badge-international';
  if (category === 'Commodity')     return 'badge badge-commodity';
  if (category === 'Factor')        return 'badge badge-factor';
  return 'badge badge-thematic';
};

const getSentimentStyle = (sentiment) => {
  if (sentiment === 'positive') return { color: '#10b981', fontWeight: '600' };
  if (sentiment === 'negative') return { color: '#ef4444', fontWeight: '600' };
  return { color: '#6b7280', fontWeight: '600' };
};

const formatDate = (dateStr) => {
  const d = new Date(dateStr);
  return d.toLocaleDateString('en-US', { month: 'short', day: 'numeric' });
};

const CustomTooltip = ({ active, payload, label }) => {
  if (active && payload && payload.length) {
    return (
      <div style={{
        background: '#fff', border: '1px solid #e5e7eb',
        borderRadius: '8px', padding: '12px 16px', fontSize: '13px'
      }}>
        <div style={{ fontWeight: '600', marginBottom: '6px' }}>{label}</div>
        {payload.map((p, i) => (
          <div key={i} style={{ color: p.color }}>
            {p.name}: ${p.value?.toFixed(2)}
          </div>
        ))}
      </div>
    );
  }
  return null;
};

function ETFExplorer() {
  const [etfs, setEtfs] = useState([]);
  const [selectedTicker, setSelectedTicker] = useState('SPY');
  const [prices, setPrices] = useState(null);
  const [forecast, setForecast] = useState(null);
  const [sentiment, setSentiment] = useState(null);
  const [sentimentError, setSentimentError] = useState(null);
  const [trainedModels, setTrainedModels] = useState({});
  const [loading, setLoading] = useState({ prices: false, forecast: false, sentiment: false });
  const [error, setError] = useState(null);

  // Load ETF list and model status on mount
  useEffect(() => {
    listETFs().then(setEtfs);
    listTrainedModels().then(data => {
      const map = {};
      data.etfs.forEach(m => { map[m.ticker] = m.model_ready; });
      setTrainedModels(map);
    });
  }, []);

  // Load data when ticker changes
  useEffect(() => {
    if (!selectedTicker) return;
    setError(null);
    setPrices(null);
    setForecast(null);
    setSentiment(null);
    setSentimentError(null);

    // Fetch price history (last 6 months)
    const sixMonthsAgo = new Date();
    sixMonthsAgo.setMonth(sixMonthsAgo.getMonth() - 6);
    const start = sixMonthsAgo.toISOString().split('T')[0];

    setLoading(l => ({ ...l, prices: true }));
    getETFPrices(selectedTicker, start)
      .then(setPrices)
      .catch(e => setError(e.message))
      .finally(() => setLoading(l => ({ ...l, prices: false })));

    // Fetch forecast if model exists
    if (trainedModels[selectedTicker]) {
      setLoading(l => ({ ...l, forecast: true }));
      getETFForecast(selectedTicker)
        .then(setForecast)
        .catch(() => {})
        .finally(() => setLoading(l => ({ ...l, forecast: false })));
    }

    // Fetch sentiment
    setLoading(l => ({ ...l, sentiment: true }));
    getETFSentiment(selectedTicker, 7)
      .then(setSentiment)
      .catch(e => setSentimentError(e.response?.data?.detail || e.message || 'Failed to load sentiment.'))
      .finally(() => setLoading(l => ({ ...l, sentiment: false })));

  }, [selectedTicker, trainedModels]);

  // Build combined chart data (historical + forecast)
  const chartData = React.useMemo(() => {
    if (!prices) return [];

    const historical = prices.prices.map(p => ({
      date: formatDate(p.date),
      actual: p.adj_close,
      predicted: null,
    }));

    if (!forecast) return historical;

    const forecastPoints = forecast.forecast.map(f => ({
      date: formatDate(f.date),
      actual: null,
      predicted: f.price,
    }));

    // Add the last actual point as the first forecast point for visual continuity
    const lastActual = historical[historical.length - 1];
    forecastPoints[0] = { ...forecastPoints[0], predicted: lastActual.actual };

    return [...historical, ...forecastPoints];
  }, [prices, forecast]);

  const selectedETF = etfs.find(e => e.ticker === selectedTicker);
  const categoryColor = selectedETF ? CATEGORY_COLORS[selectedETF.category] || '#7c3aed' : '#7c3aed';

  return (
    <div>
      <div className="page-header">
        <h1>ETF Explorer</h1>
        <p>Price history, 90-day forecast, and sentiment analysis for any ETF in the universe</p>
      </div>

      {/* ETF Selector */}
      <div style={{ display: 'flex', alignItems: 'center', gap: '16px', marginBottom: '24px' }}>
        <select
          className="select"
          value={selectedTicker}
          onChange={e => setSelectedTicker(e.target.value)}
          style={{ fontWeight: '500', minWidth: '280px', padding: '10px 16px' }}
        >
          {etfs.map(etf => (
            <option key={etf.ticker} value={etf.ticker}>
              {etf.ticker} — {etf.name}
            </option>
          ))}
        </select>

        {selectedETF && (
          <span className={getBadgeClass(selectedETF.category)} style={{ fontSize: '13px', padding: '5px 12px' }}>
            {selectedETF.category}
          </span>
        )}
      </div>

      {error && <div className="error" style={{ marginBottom: '16px' }}>Error: {error}</div>}

      {/* Price + Forecast Chart */}
      <div className="card" style={{ marginBottom: '20px' }}>
        <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: '20px' }}>
          <div>
            <h3 style={{ fontSize: '16px', fontWeight: '600' }}>
              {selectedTicker} — Price History & 90-Day Forecast
            </h3>
            {forecast && (
              <p style={{ fontSize: '13px', color: '#6b7280', marginTop: '4px' }}>
                Predicted price in 90 days:{' '}
                <span style={{ fontWeight: '700', color: '#7c3aed' }}>
                  ${forecast.predicted_price_90d}
                </span>
                {' '}
                <span style={{
                  color: forecast.pct_change_90d < 0 ? '#ef4444' : '#10b981',
                  fontWeight: '600'
                }}>
                  ({forecast.pct_change_90d > 0 ? '+' : ''}{forecast.pct_change_90d?.toFixed(2)}%)
                </span>
              </p>
            )}
          </div>

          {!trainedModels[selectedTicker] && (
            <div style={{ fontSize: '13px', color: '#9ca3af' }}>
              No forecast available — train the model from the{' '}
              <a href="/forecasts" style={{ color: '#7c3aed', fontWeight: '500', textDecoration: 'underline', textUnderlineOffset: '2px' }}>Forecast Dashboard</a>.
            </div>
          )}
        </div>

        {loading.prices ? (
          <div className="loading">Loading price data...</div>
        ) : (
          <ResponsiveContainer width="100%" height={320}>
            <ComposedChart data={chartData} margin={{ top: 5, right: 20, left: 10, bottom: 5 }}>
              <CartesianGrid strokeDasharray="3 3" stroke="#f3f4f6" />
              <XAxis
                dataKey="date"
                tick={{ fontSize: 11 }}
                interval={Math.floor(chartData.length / 8)}
              />
              <YAxis
                tick={{ fontSize: 11 }}
                tickFormatter={v => `$${v}`}
                domain={['auto', 'auto']}
              />
              <Tooltip content={<CustomTooltip />} />
              <Legend />
              {forecast && (
                <ReferenceLine
                  x={formatDate(forecast.last_actual_date)}
                  stroke="#d1d5db"
                  strokeDasharray="4 4"
                  label={{ value: 'Today', fontSize: 11, fill: '#9ca3af' }}
                />
              )}
              <Line
                type="monotone"
                dataKey="actual"
                name="Actual Price"
                stroke={categoryColor}
                dot={false}
                strokeWidth={2}
                connectNulls={false}
              />
              <Line
                type="monotone"
                dataKey="predicted"
                name="Forecast"
                stroke="#7c3aed"
                dot={false}
                strokeWidth={2}
                strokeDasharray="5 5"
                connectNulls={false}
              />
            </ComposedChart>
          </ResponsiveContainer>
        )}
      </div>

      {/* Sentiment Panel */}
      <div className="card">
        <h3 style={{ fontSize: '16px', fontWeight: '600', marginBottom: '16px' }}>
          Sentiment Analysis — Last 7 Days
        </h3>

        {loading.sentiment ? (
          <div className="loading">Analyzing sentiment... (first request per server restart can take a couple minutes — FinBERT downloads fresh each time on the free tier)</div>
        ) : sentimentError ? (
          <div style={{ color: '#ef4444', fontSize: '14px' }}>
            Couldn't load sentiment: {sentimentError}
          </div>
        ) : sentiment && sentiment.articles_analyzed > 0 ? (
          <>
            {/* Sentiment Summary */}
            <div style={{ display: 'flex', gap: '24px', marginBottom: '20px', flexWrap: 'wrap' }}>
              <div style={{ textAlign: 'center' }}>
                <div style={{ fontSize: '12px', color: '#6b7280', marginBottom: '4px' }}>OVERALL</div>
                <div style={{ fontSize: '20px', fontWeight: '700', ...getSentimentStyle(sentiment.overall_sentiment) }}>
                  {sentiment.overall_sentiment.toUpperCase()}
                </div>
              </div>
              <div style={{ textAlign: 'center' }}>
                <div style={{ fontSize: '12px', color: '#6b7280', marginBottom: '4px' }}>POSITIVE</div>
                <div style={{ fontSize: '20px', fontWeight: '700', color: '#10b981' }}>
                  {sentiment.sentiment_breakdown.positive}
                </div>
              </div>
              <div style={{ textAlign: 'center' }}>
                <div style={{ fontSize: '12px', color: '#6b7280', marginBottom: '4px' }}>NEUTRAL</div>
                <div style={{ fontSize: '20px', fontWeight: '700', color: '#6b7280' }}>
                  {sentiment.sentiment_breakdown.neutral}
                </div>
              </div>
              <div style={{ textAlign: 'center' }}>
                <div style={{ fontSize: '12px', color: '#6b7280', marginBottom: '4px' }}>NEGATIVE</div>
                <div style={{ fontSize: '20px', fontWeight: '700', color: '#ef4444' }}>
                  {sentiment.sentiment_breakdown.negative}
                </div>
              </div>
              <div style={{ textAlign: 'center' }}>
                <div style={{ fontSize: '12px', color: '#6b7280', marginBottom: '4px' }}>ARTICLES</div>
                <div style={{ fontSize: '20px', fontWeight: '700', color: '#111827' }}>
                  {sentiment.articles_analyzed}
                </div>
              </div>
            </div>

            {/* Headlines Table */}
            <div className="table-wrapper">
              <table>
                <thead>
                  <tr>
                    <th>Headline</th>
                    <th>Source</th>
                    <th>Sentiment</th>
                    <th>Confidence</th>
                  </tr>
                </thead>
                <tbody>
                  {sentiment.headlines.map((h, i) => {
                    const confidence = Math.max(h.positive_score, h.negative_score, h.neutral_score);
                    return (
                      <tr key={i}>
                        <td style={{ maxWidth: '500px', lineHeight: '1.4' }}>{h.headline}</td>
                        <td style={{ color: '#6b7280', whiteSpace: 'nowrap' }}>{h.source}</td>
                        <td>
                          <span style={getSentimentStyle(h.sentiment)}>
                            {h.sentiment.charAt(0).toUpperCase() + h.sentiment.slice(1)}
                          </span>
                        </td>
                        <td style={{ color: '#374151' }}>{(confidence * 100).toFixed(1)}%</td>
                      </tr>
                    );
                  })}
                </tbody>
              </table>
            </div>
          </>
        ) : (
          <div style={{ color: '#6b7280', fontSize: '14px' }}>
            No recent news found for {selectedTicker}.
          </div>
        )}
      </div>
    </div>
  );
}

export default ETFExplorer;