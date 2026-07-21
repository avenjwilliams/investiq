import React, { useState, useEffect } from 'react';
import { BrowserRouter as Router, Routes, Route, Navigate } from 'react-router-dom';
import Navbar from './components/Navbar';
import Portfolio from './pages/Portfolio';
import ETFExplorer from './pages/ETFExplorer';
import SentimentFeed from './pages/SentimentFeed';
import Universe from './pages/Universe';
import ForecastDashboard from './pages/ForecastDashboard';
import ModelMetrics from './pages/ModelMetrics';
import './App.css';

const API_URL = process.env.REACT_APP_API_URL || 'http://localhost:8000';
const HEALTH_URL = `${API_URL}/health`;
const POLL_INTERVAL_MS = 2000;

function BackendLoadingScreen() {
  return (
    <div style={{
      display: 'flex', flexDirection: 'column', alignItems: 'center',
      justifyContent: 'center', height: '100vh', gap: '20px',
      background: '#f9fafb',
    }}>
      <div style={{ fontSize: '32px' }}>⚡</div>
      <div style={{ fontWeight: '700', fontSize: '18px', color: '#111827' }}>
        Starting up…
      </div>
      <div style={{ fontSize: '14px', color: '#6b7280' }}>
        Waiting for the backend to come online
      </div>
      <div style={{
        width: '200px', height: '4px', background: '#e5e7eb',
        borderRadius: '999px', overflow: 'hidden', marginTop: '8px',
      }}>
        <div style={{
          height: '100%', width: '40%', background: '#7c3aed',
          borderRadius: '999px',
          animation: 'slide 1.4s ease-in-out infinite',
        }} />
      </div>
      <style>{`
        @keyframes slide {
          0%   { transform: translateX(-100%); }
          50%  { transform: translateX(300%); }
          100% { transform: translateX(-100%); }
        }
      `}</style>
    </div>
  );
}

function App() {
  const [backendReady, setBackendReady] = useState(false);

  useEffect(() => {
    let timer;
    const check = () => {
      fetch(HEALTH_URL)
        .then(r => { if (r.ok) setBackendReady(true); else schedule(); })
        .catch(() => schedule());
    };
    const schedule = () => { timer = setTimeout(check, POLL_INTERVAL_MS); };
    check();
    return () => clearTimeout(timer);
  }, []);

  if (!backendReady) return <BackendLoadingScreen />;

  return (
    <Router>
      <div className="app">
        <Navbar />
        <main className="main-content">
          <Routes>
            <Route path="/" element={<Navigate to="/portfolio" replace />} />
            <Route path="/portfolio" element={<Portfolio />} />
            <Route path="/explorer" element={<ETFExplorer />} />
            <Route path="/sentiment" element={<SentimentFeed />} />
            <Route path="/universe" element={<Universe />} />
            <Route path="/forecasts" element={<ForecastDashboard />} />
            <Route path="/model-metrics" element={<ModelMetrics />} />
          </Routes>
        </main>
      </div>
    </Router>
  );
}

export default App;