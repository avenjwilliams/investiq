import React, { useState, useEffect } from 'react';
import {
  PieChart, Pie, Cell, Tooltip, Legend, ResponsiveContainer,
  BarChart, Bar, XAxis, YAxis, CartesianGrid
} from 'recharts';
import { getPortfolioOptimization, getBlackLittermanOptimization } from '../api/api';

const CATEGORY_COLORS = {
  'Sector':        '#3b82f6',
  'Broad Market':  '#10b981',
  'Thematic':      '#f97316',
  'International': '#6366f1',
  'Commodity':     '#d97706',
  'Factor':        '#e11d48',
};

const PIE_COLORS = [
  '#7c3aed','#3b82f6','#10b981','#f97316','#ef4444',
  '#8b5cf6','#06b6d4','#84cc16','#f59e0b','#ec4899',
  '#6366f1','#14b8a6','#a3e635','#fb923c','#f43f5e',
];

const getBadgeClass = (category) => {
  if (category === 'Sector') return 'badge badge-sector';
  if (category === 'Broad Market') return 'badge badge-broad';
  return 'badge badge-thematic';
};

const CustomTooltip = ({ active, payload }) => {
  if (active && payload && payload.length) {
    const d = payload[0].payload;
    return (
      <div style={{
        background: '#fff', border: '1px solid #e5e7eb',
        borderRadius: '8px', padding: '12px 16px', fontSize: '13px'
      }}>
        <div style={{ fontWeight: '600', marginBottom: '4px' }}>{d.name}</div>
        <div style={{ color: '#7c3aed', fontWeight: '700' }}>{d.weight_pct}</div>
        <div style={{ color: '#6b7280' }}>{d.category}</div>
      </div>
    );
  }
  return null;
};

function Portfolio() {
  const [strategy, setStrategy] = useState('max_sharpe');
  const [data, setData] = useState(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState(null);

  const isBL = strategy === 'black_litterman';

  useEffect(() => {
    let cancelled = false;
    setLoading(true);
    setError(null);
    setData(null);
    const fetch = isBL
      ? getBlackLittermanOptimization()
      : getPortfolioOptimization(strategy);
    fetch
      .then(result => { if (!cancelled) setData(result); })
      .catch(e => { if (!cancelled) setError(e.message); })
      .finally(() => { if (!cancelled) setLoading(false); });
    return () => { cancelled = true; };
  }, [strategy]); // eslint-disable-line react-hooks/exhaustive-deps

  const categoryData = data
    ? Object.entries(data.category_breakdown).map(([name, pct]) => ({
        name,
        value: parseFloat(pct),
        fill: CATEGORY_COLORS[name] || '#8b5cf6',
      }))
    : [];

  return (
    <div>
      <div className="page-header">
        <h1>Portfolio Optimization</h1>
        <p>Mean-variance optimized allocations across 40 ETFs using Modern Portfolio Theory</p>
      </div>

      {/* Strategy Toggle */}
      <div className="toggle-group">
        <button
          className={`toggle-btn ${strategy === 'max_sharpe' ? 'active' : ''}`}
          onClick={() => setStrategy('max_sharpe')}
        >
          Max Sharpe Ratio
        </button>
        <button
          className={`toggle-btn ${strategy === 'min_volatility' ? 'active' : ''}`}
          onClick={() => setStrategy('min_volatility')}
        >
          Min Volatility
        </button>
        <button
          className={`toggle-btn ${strategy === 'black_litterman' ? 'active' : ''}`}
          onClick={() => setStrategy('black_litterman')}
        >
          ✦ Black-Litterman
        </button>
      </div>

      {/* BL info banner */}
      {isBL && !loading && !error && (
        <div style={{
          background: 'linear-gradient(135deg, #f5f3ff 0%, #ede9fe 100%)',
          border: '1px solid #c4b5fd',
          borderRadius: '10px',
          padding: '12px 16px',
          marginBottom: '20px',
          fontSize: '13px',
          color: '#5b21b6',
          display: 'flex',
          alignItems: 'flex-start',
          gap: '10px',
        }}>
          <span style={{ fontSize: '16px', marginTop: '1px' }}>✦</span>
          <div>
            <strong>AI-Enhanced Allocation</strong> — weights are blended from two sources:
            market equilibrium (derived from ETF AUM) and Transformer 90-day return forecasts.
            Each forecast is trusted proportionally to the model's per-ticker directional accuracy.
            {data && <span style={{ marginLeft: '6px', opacity: 0.8 }}>({data.n_views} views active)</span>}
          </div>
        </div>
      )}

      {loading && (
        <div className="loading">
          {isBL ? 'Running AI-enhanced optimization — fetching forecasts for all ETFs...' : 'Running optimization...'}
        </div>
      )}
      {error && <div className="error">Error: {error}</div>}

      {data && !loading && (
        <>
          {/* Fallback warning */}
          {isBL && data.optimization === 'min_volatility_fallback' && (
            <div style={{
              background: '#fffbeb', border: '1px solid #fcd34d',
              borderRadius: '10px', padding: '10px 16px',
              marginBottom: '16px', fontSize: '13px', color: '#92400e',
              display: 'flex', gap: '8px', alignItems: 'center',
            }}>
              <span>⚠️</span>
              <span>Transformer views were broadly negative — Max Sharpe was infeasible at all risk-free rates. Showing <strong>Min Volatility</strong> on the BL posterior instead.</span>
            </div>
          )}

          {/* Metric Cards */}
          <div className="metrics-row">
            <div className="metric-card">
              <div className="metric-label">Expected Annual Return</div>
              <div className="metric-value">{data.performance.expected_annual_return_pct}</div>
              <div className="metric-sub">
                {isBL ? 'Based on Black-Litterman posterior returns' : 'Based on 3-year historical returns'}
              </div>
            </div>
            <div className="metric-card">
              <div className="metric-label">Annual Volatility</div>
              <div className="metric-value" style={{ color: '#f97316' }}>
                {data.performance.annual_volatility_pct}
              </div>
              <div className="metric-sub">Portfolio standard deviation</div>
            </div>
            <div className="metric-card">
              <div className="metric-label">Sharpe Ratio</div>
              <div className="metric-value" style={{ color: '#10b981' }}>
                {data.performance.sharpe_ratio}
              </div>
              <div className="metric-sub">Risk-adjusted return ({">"} 1.0 is strong)</div>
            </div>
          </div>

          {/* Charts Row */}
          <div className="two-col" style={{ marginBottom: '24px' }}>
            {/* Allocation Pie Chart */}
            <div className="card">
              <h3 style={{ marginBottom: '16px', fontSize: '16px', fontWeight: '600' }}>
                Allocation by ETF
              </h3>
              <ResponsiveContainer width="100%" height={280}>
                <PieChart>
                  <Pie
                    data={data.allocations}
                    dataKey="weight"
                    nameKey="ticker"
                    cx="50%"
                    cy="50%"
                    outerRadius={100}
                    innerRadius={50}
                  >
                    {data.allocations.map((_, i) => (
                      <Cell key={i} fill={PIE_COLORS[i % PIE_COLORS.length]} />
                    ))}
                  </Pie>
                  <Tooltip content={<CustomTooltip />} />
                  <Legend
                    formatter={(value) => <span style={{ fontSize: '12px' }}>{value}</span>}
                  />
                </PieChart>
              </ResponsiveContainer>
            </div>

            {/* Category Breakdown Bar Chart */}
            <div className="card">
              <h3 style={{ marginBottom: '16px', fontSize: '16px', fontWeight: '600' }}>
                Category Breakdown
              </h3>
              <ResponsiveContainer width="100%" height={280}>
                <BarChart data={categoryData} layout="vertical" margin={{ left: 20 }}>
                  <CartesianGrid strokeDasharray="3 3" horizontal={false} />
                  <XAxis type="number" tickFormatter={v => `${v}%`} fontSize={12} />
                  <YAxis type="category" dataKey="name" fontSize={12} width={100} />
                  <Tooltip formatter={(v) => `${v}%`} />
                  <Bar dataKey="value" radius={[0, 6, 6, 0]}>
                    {categoryData.map((entry, i) => (
                      <Cell key={i} fill={entry.fill} />
                    ))}
                  </Bar>
                </BarChart>
              </ResponsiveContainer>
            </div>
          </div>

          {/* Allocations Table */}
          <div className="card">
            <h3 style={{ marginBottom: '16px', fontSize: '16px', fontWeight: '600' }}>
              Full Allocation Breakdown
            </h3>
            <div className="table-wrapper">
              <table>
                <thead>
                  <tr>
                    <th>Ticker</th>
                    <th>Name</th>
                    <th>Category</th>
                    <th>Weight</th>
                    {isBL && <th>Transformer View</th>}
                    {isBL && <th>Confidence</th>}
                  </tr>
                </thead>
                <tbody>
                  {data.allocations.map((alloc, i) => (
                    <tr key={alloc.ticker}>
                      <td>
                        <span style={{
                          fontWeight: '700',
                          color: PIE_COLORS[i % PIE_COLORS.length],
                        }}>
                          {alloc.ticker}
                        </span>
                      </td>
                      <td style={{ color: '#374151' }}>{alloc.name}</td>
                      <td>
                        <span className={getBadgeClass(alloc.category)}>
                          {alloc.category}
                        </span>
                      </td>
                      <td>
                        <div style={{ display: 'flex', alignItems: 'center', gap: '10px' }}>
                          <div style={{
                            height: '6px',
                            width: `${alloc.weight * 300}px`,
                            maxWidth: '200px',
                            background: PIE_COLORS[i % PIE_COLORS.length],
                            borderRadius: '999px',
                          }} />
                          <span style={{ fontWeight: '600' }}>{alloc.weight_pct}</span>
                        </div>
                      </td>
                      {isBL && (
                        <td style={{
                          fontWeight: '600',
                          color: alloc.view_return && parseFloat(alloc.view_return) >= 0 ? '#10b981' : '#ef4444',
                        }}>
                          {alloc.view_return ?? '—'}
                        </td>
                      )}
                      {isBL && (
                        <td>
                          {alloc.view_confidence != null ? (
                            <div style={{ display: 'flex', alignItems: 'center', gap: '8px' }}>
                              <div style={{
                                height: '6px',
                                width: `${alloc.view_confidence * 80}px`,
                                maxWidth: '80px',
                                background: '#7c3aed',
                                borderRadius: '999px',
                                opacity: 0.7,
                              }} />
                              <span style={{ fontSize: '12px', color: '#6b7280' }}>
                                {Math.round(alloc.view_confidence * 100)}%
                              </span>
                            </div>
                          ) : '—'}
                        </td>
                      )}
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          </div>
        </>
      )}
    </div>
  );
}

export default Portfolio;