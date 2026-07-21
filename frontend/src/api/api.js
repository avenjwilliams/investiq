import axios from 'axios';

// Set REACT_APP_API_URL in the deployed environment (e.g. Vercel project
// settings) to point at the hosted backend. CRA only inlines env vars
// prefixed with REACT_APP_ at build time — falls back to localhost for dev.
const BASE_URL = process.env.REACT_APP_API_URL || 'http://localhost:8000';
const api = axios.create({ baseURL: BASE_URL });

export const getPortfolioOptimization = (strategy = 'max_sharpe') =>
  api.get(`/portfolio/optimize?strategy=${strategy}`).then(r => r.data);

export const getBlackLittermanOptimization = () =>
  api.get('/portfolio/optimize/black-litterman').then(r => r.data);

export const listETFs = () =>
  api.get('/etfs/').then(r => r.data);

export const getDatabaseSummary = () =>
  api.get('/etfs/summary').then(r => r.data);

export const getETFPrices = (ticker, start = null) => {
  const params = start ? `?start=${start}` : '';
  return api.get(`/etfs/${ticker}/prices${params}`).then(r => r.data);
};

export const getETFLatest = (ticker) =>
  api.get(`/etfs/${ticker}/latest`).then(r => r.data);

// Forecast Dashboard, Model Metrics, and ETF Explorer all read from the
// Transformer model (direction head + richer features + walk-forward CV).
// The legacy single-output LSTM and its routes have been removed entirely.
export const trainAllForecasts = () =>
  api.post('/forecast/transformer/train-all').then(r => r.data);

export const getModelMetrics = () =>
  api.get('/forecast/transformer/metrics').then(r => r.data);

export const getETFForecast = (ticker) =>
  api.get(`/forecast/transformer/${ticker}`).then(r => r.data);

export const listTrainedModels = () =>
  api.get('/forecast/transformer/').then(r => r.data);

export const getTransformerCVMetrics = () =>
  api.get('/forecast/transformer/cv-metrics').then(r => r.data);

export const getETFSentiment = (ticker, daysBack = 7) =>
  api.get(`/sentiment/${ticker}?days_back=${daysBack}`).then(r => r.data);

export const getSentimentHistory = (ticker) =>
  api.get(`/sentiment/${ticker}/history`).then(r => r.data);