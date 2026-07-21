import React, { useState, useEffect } from 'react';
import { listETFs, getETFSentiment } from '../api/api';

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
  if (sentiment === 'positive') return { color: '#10b981', fontWeight: '700' };
  if (sentiment === 'negative') return { color: '#ef4444', fontWeight: '700' };
  return { color: '#6b7280', fontWeight: '700' };
};

const SentimentBar = ({ positive, negative, neutral }) => (
  <div style={{ display: 'flex', height: '6px', borderRadius: '999px', overflow: 'hidden', width: '100%', background: '#f3f4f6' }}>
    <div style={{ width: `${positive * 100}%`, background: '#10b981' }} />
    <div style={{ width: `${neutral * 100}%`, background: '#d1d5db' }} />
    <div style={{ width: `${negative * 100}%`, background: '#ef4444' }} />
  </div>
);

function SentimentFeed() {
  const [etfs, setEtfs] = useState([]);
  const [selectedTicker, setSelectedTicker] = useState(null);
  const [sentiment, setSentiment] = useState(null);
  const [daysBack, setDaysBack] = useState(7);
  const [categoryFilter, setCategoryFilter] = useState('All');
  const [sentimentFilter, setSentimentFilter] = useState('All');
  const [loading, setLoading] = useState(false);
  const [summaries, setSummaries] = useState({});
  const [loadingSummaries, setLoadingSummaries] = useState(false);

  useEffect(() => {
    listETFs().then(data => {
      setEtfs(data);
    });
  }, []);

  // Load summary sentiment for all ETFs
  const loadAllSummaries = () => {
    setLoadingSummaries(true);
    const filtered = etfs.filter(e =>
      categoryFilter === 'All' || e.category === categoryFilter
    );

    Promise.allSettled(
      filtered.map(e =>
        getETFSentiment(e.ticker, daysBack).then(s => ({ ticker: e.ticker, data: s }))
      )
    ).then(results => {
      const map = {};
      results.forEach(r => {
        if (r.status === 'fulfilled') {
          map[r.value.ticker] = r.value.data;
        }
      });
      setSummaries(map);
    }).finally(() => setLoadingSummaries(false));
  };

  // Load detail for a specific ETF
  const loadDetail = (ticker) => {
    if (selectedTicker === ticker) {
      setSelectedTicker(null);
      setSentiment(null);
      return;
    }
    setSelectedTicker(ticker);
    setLoading(true);
    getETFSentiment(ticker, daysBack)
      .then(setSentiment)
      .finally(() => setLoading(false));
  };

  const filteredEtfs = etfs.filter(e => {
    const catMatch = categoryFilter === 'All' || e.category === categoryFilter;
    const summary = summaries[e.ticker];
    const sentMatch = sentimentFilter === 'All' || (summary && summary.overall_sentiment === sentimentFilter.toLowerCase());
    return catMatch && sentMatch;
  });

  return (
    <div>
      <div className="page-header">
        <h1>Sentiment Feed</h1>
        <p>FinBERT-powered news sentiment across all ETFs in the universe</p>
      </div>

      {/* Controls */}
      <div style={{ display: 'flex', gap: '12px', marginBottom: '24px', flexWrap: 'wrap', alignItems: 'center' }}>
        {/* Category Filter */}
        <div className="toggle-group" style={{ margin: 0 }}>
          {['All', 'Sector', 'Broad Market', 'Thematic', 'International', 'Commodity', 'Factor'].map(cat => (
            <button
              key={cat}
              className={`toggle-btn ${categoryFilter === cat ? 'active' : ''}`}
              onClick={() => setCategoryFilter(cat)}
            >
              {cat}
            </button>
          ))}
        </div>

        {/* Sentiment Filter */}
        <div className="toggle-group" style={{ margin: 0 }}>
          {['All', 'Positive', 'Neutral', 'Negative'].map(s => (
            <button
              key={s}
              className={`toggle-btn ${sentimentFilter === s ? 'active' : ''}`}
              onClick={() => setSentimentFilter(s)}
              style={sentimentFilter === s && s !== 'All' ? {
                background: s === 'Positive' ? '#10b981' : s === 'Negative' ? '#ef4444' : '#6b7280',
                borderColor: s === 'Positive' ? '#10b981' : s === 'Negative' ? '#ef4444' : '#6b7280',
                color: 'white',
              } : {}}
            >
              {s}
            </button>
          ))}
        </div>

        {/* Days Back */}
        <select
          className="select"
          value={daysBack}
          onChange={e => setDaysBack(Number(e.target.value))}
        >
          <option value={3}>Last 3 days</option>
          <option value={7}>Last 7 days</option>
          <option value={14}>Last 14 days</option>
          <option value={30}>Last 30 days</option>
        </select>

        {/* Load All Button */}
        <button
          className="btn btn-primary"
          onClick={loadAllSummaries}
          disabled={loadingSummaries}
        >
          {loadingSummaries ? 'Loading…' : 'Load All Sentiment'}
        </button>
      </div>

      <div className={selectedTicker ? 'two-col-wide' : ''}>
        {/* ETF Grid */}
        <div>
          <div style={{
            display: 'grid',
            gridTemplateColumns: selectedTicker ? '1fr' : 'repeat(auto-fill, minmax(280px, 1fr))',
            gap: '12px',
          }}>
            {filteredEtfs.map(etf => {
              const summary = summaries[etf.ticker];
              const isSelected = selectedTicker === etf.ticker;

              return (
                <div
                  key={etf.ticker}
                  className="card card-interactive"
                  onClick={() => loadDetail(etf.ticker)}
                  style={{
                    border: isSelected ? '2px solid #7c3aed' : '1px solid #e5e7eb',
                    padding: '16px 20px',
                  }}
                >
                  <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'flex-start', marginBottom: '8px' }}>
                    <div>
                      <div style={{ fontWeight: '700', fontSize: '16px', color: CATEGORY_COLORS[etf.category] }}>
                        {etf.ticker}
                      </div>
                      <div style={{ fontSize: '12px', color: '#6b7280', marginTop: '2px' }}>
                        {etf.name.length > 35 ? etf.name.slice(0, 35) + '...' : etf.name}
                      </div>
                    </div>
                    <span className={getBadgeClass(etf.category)} style={{ fontSize: '11px' }}>
                      {etf.category}
                    </span>
                  </div>

                  {summary && summary.scores ? (
                    <>
                      <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: '8px' }}>
                        <span style={getSentimentStyle(summary.overall_sentiment)}>
                          {summary.overall_sentiment.toUpperCase()}
                        </span>
                        <span style={{ fontSize: '12px', color: '#9ca3af' }}>
                          {summary.articles_analyzed} articles
                        </span>
                      </div>
                      {summary.articles_analyzed > 0 ? (
                        <>
                          <SentimentBar
                            positive={summary.scores.positive}
                            negative={summary.scores.negative}
                            neutral={summary.scores.neutral}
                          />
                          <div style={{ display: 'flex', justifyContent: 'space-between', fontSize: '11px', color: '#9ca3af', marginTop: '4px' }}>
                            <span style={{ color: '#10b981' }}>{summary.sentiment_breakdown?.positive} pos</span>
                            <span>{summary.sentiment_breakdown?.neutral} neu</span>
                            <span style={{ color: '#ef4444' }}>{summary.sentiment_breakdown?.negative} neg</span>
                          </div>
                        </>
                      ) : (
                        <div style={{ fontSize: '12px', color: '#9ca3af', marginTop: '4px' }}>No recent news found</div>
                      )}
                    </>
                  ) : (
                    <div style={{ fontSize: '12px', color: '#9ca3af', marginTop: '8px' }}>
                      Click to load sentiment
                    </div>
                  )}
                </div>
              );
            })}
          </div>
        </div>

        {/* Detail Panel */}
        {selectedTicker && (
          <div>
            <div className="card" style={{ position: 'sticky', top: '80px' }}>
              <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: '16px' }}>
                <h3 style={{ fontSize: '16px', fontWeight: '600' }}>
                  {selectedTicker} — Headlines
                </h3>
                <button
                  className="icon-btn"
                  onClick={() => { setSelectedTicker(null); setSentiment(null); }}
                  aria-label="Close"
                >
                  ✕
                </button>
              </div>

              {loading ? (
                <div className="loading">Analyzing...</div>
              ) : sentiment && sentiment.headlines.length > 0 ? (
                <div style={{ display: 'flex', flexDirection: 'column', gap: '12px', maxHeight: '70vh', overflowY: 'auto' }}>
                  {sentiment.headlines.map((h, i) => (
                    <div key={i} style={{
                      padding: '12px', borderRadius: '8px',
                      background: '#f9fafb', border: '1px solid #f3f4f6',
                    }}>
                      <div style={{ fontSize: '13px', fontWeight: '500', lineHeight: '1.4', marginBottom: '8px', color: '#111827' }}>
                        {h.headline}
                      </div>
                      <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
                        <span style={{ fontSize: '11px', color: '#9ca3af' }}>{h.source}</span>
                        <span style={{ fontSize: '12px', ...getSentimentStyle(h.sentiment) }}>
                          {h.sentiment.charAt(0).toUpperCase() + h.sentiment.slice(1)}{' '}
                          <span style={{ color: '#9ca3af', fontWeight: '400' }}>
                            ({(Math.max(h.positive_score, h.negative_score, h.neutral_score) * 100).toFixed(0)}%)
                          </span>
                        </span>
                      </div>
                    </div>
                  ))}
                </div>
              ) : (
                <div style={{ color: '#6b7280', fontSize: '14px' }}>No headlines found.</div>
              )}
            </div>
          </div>
        )}
      </div>
    </div>
  );
}

export default SentimentFeed;