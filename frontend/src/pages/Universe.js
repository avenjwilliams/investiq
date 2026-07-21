import React, { useState } from 'react';

const CATEGORY_META = [
  {
    name: 'Sector',
    color: '#3b82f6',
    bg: '#dbeafe',
    textColor: '#1d4ed8',
    description:
      'Sector ETFs track one of the 11 official GICS sectors of the US stock market — Technology, Financials, Energy, and so on. They let you overweight or underweight specific industries you have conviction in without picking individual stocks. All 11 SPDR Select Sector ETFs are in the universe, making this group a complete map of the S&P 500\'s building blocks.',
    why: 'Together these 11 ETFs carve the S&P 500 into its component parts. Useful for rotating into sectors that are historically strong at a given point in the economic cycle.',
  },
  {
    name: 'Broad Market',
    color: '#10b981',
    bg: '#d1fae5',
    textColor: '#065f46',
    description:
      'Broad Market ETFs give diversified exposure to large swaths of the market — the whole US stock market, large-cap indices, international developed markets, emerging markets, bonds, and gold. These are the core building blocks of most investment portfolios and serve as the benchmark for performance comparison.',
    why: 'These are the most widely held ETFs in the world for a reason. They serve as the baseline — when you analyze any other ETF, you compare it against these.',
  },
  {
    name: 'Thematic',
    color: '#f97316',
    bg: '#ffedd5',
    textColor: '#9a3412',
    description:
      'Thematic ETFs bet on a specific trend, technology, or cultural shift rather than a traditional sector. Examples include clean energy, cybersecurity, robotics, AI, and fintech. They carry higher risk than sector ETFs but offer targeted exposure to high-growth narratives that cut across multiple traditional sectors.',
    why: 'These ETFs represent the ideas and technologies most likely to define the next decade. Higher risk, but that\'s the point when you\'re investing with a long time horizon.',
  },
  {
    name: 'International',
    color: '#6366f1',
    bg: '#e0e7ff',
    textColor: '#3730a3',
    description:
      'International ETFs provide equity exposure outside the United States — covering developed markets like Japan and Europe, or specific countries like India and China. They add geographic diversification and exposure to different economic cycles, currencies, and growth rates that don\'t always move in sync with the US market.',
    why: 'The US is ~60% of global market cap, meaning 40% of opportunity is elsewhere. International ETFs capture that — especially India and emerging markets, which have strong demographic and growth tailwinds.',
  },
  {
    name: 'Commodity',
    color: '#d97706',
    bg: '#fef3c7',
    textColor: '#92400e',
    description:
      'Commodity ETFs track physical goods — oil, agriculture, or a diversified basket of raw materials. They serve as inflation hedges and portfolio diversifiers, often moving independently from stocks. Most commodity ETFs use futures contracts rather than holding the physical asset directly.',
    why: 'Commodities have near-zero correlation with equities in many market environments. Oil and agriculture in particular respond to macro forces — inflation, geopolitics, supply shocks — that equities don\'t always capture.',
  },
  {
    name: 'Factor',
    color: '#e11d48',
    bg: '#ffe4e6',
    textColor: '#9f1239',
    description:
      'Factor ETFs (also called Smart Beta) tilt toward stocks with specific quantitative characteristics — value, growth, momentum, or quality — that have historically outperformed the broad market over long periods. They sit between passive index funds and active management, applying rules-based screens to capture a risk premium.',
    why: 'Each factor has decades of academic evidence behind it. Value and momentum in particular have shown persistent outperformance. Having all four lets the optimizer pick the right blend for a given market regime.',
  },
];

const ETFS = [
  // Sector
  { ticker: 'XLK',  name: 'Technology Select Sector SPDR',             category: 'Sector',        focus: 'Technology',                   description: 'Tracks the technology sector of the S&P 500. Top holdings include Apple, Microsoft, and NVIDIA.', why: 'The largest and most liquid sector ETF. Tech drives the majority of S&P 500 returns.' },
  { ticker: 'XLF',  name: 'Financial Select Sector SPDR',              category: 'Sector',        focus: 'Financials',                   description: 'Covers banks, insurance, and financial services within the S&P 500.', why: 'Financials are highly sensitive to interest rate movements — a key macro signal.' },
  { ticker: 'XLE',  name: 'Energy Select Sector SPDR',                 category: 'Sector',        focus: 'Energy',                       description: 'Tracks oil, gas, and energy companies in the S&P 500.', why: 'Energy is the most macro-driven sector, reflecting global commodity cycles and geopolitics.' },
  { ticker: 'XLV',  name: 'Health Care Select Sector SPDR',            category: 'Sector',        focus: 'Health Care',                  description: 'Covers pharmaceuticals, biotech, medical devices, and health services.', why: 'Considered defensive — health care demand persists regardless of economic conditions.' },
  { ticker: 'XLI',  name: 'Industrial Select Sector SPDR',             category: 'Sector',        focus: 'Industrials',                  description: 'Tracks aerospace, defense, transportation, and industrial manufacturing.', why: 'A reliable proxy for economic activity and infrastructure spending cycles.' },
  { ticker: 'XLB',  name: 'Materials Select Sector SPDR',              category: 'Sector',        focus: 'Materials',                    description: 'Covers mining, chemicals, and construction materials companies.', why: 'Materials lead the market during commodity supercycles and infrastructure buildouts.' },
  { ticker: 'XLY',  name: 'Consumer Discretionary Select Sector SPDR', category: 'Sector',        focus: 'Consumer Discretionary',       description: 'Tracks non-essential consumer goods — retail, autos, restaurants, and leisure.', why: 'Highly sensitive to consumer confidence. Leads the market in early recovery phases.' },
  { ticker: 'XLP',  name: 'Consumer Staples Select Sector SPDR',       category: 'Sector',        focus: 'Consumer Staples',             description: 'Covers essential goods — food, beverages, household products, and tobacco.', why: 'The classic defensive sector. Holds up when the market sells off.' },
  { ticker: 'XLU',  name: 'Utilities Select Sector SPDR',              category: 'Sector',        focus: 'Utilities',                    description: 'Tracks electric, gas, and water utilities. Known for stable dividends and low volatility.', why: 'Treated like a bond proxy — outperforms when rates fall. Increasingly relevant for AI power demand.' },
  { ticker: 'XLRE', name: 'Real Estate Select Sector SPDR',            category: 'Sector',        focus: 'Real Estate',                  description: 'Covers REITs and real estate companies in the S&P 500.', why: 'Provides real estate exposure with stock-market liquidity, without buying property.' },
  { ticker: 'XLC',  name: 'Communication Services Select Sector SPDR', category: 'Sector',        focus: 'Communication Services',       description: 'Tracks telecom, media, and internet — Meta, Alphabet, Netflix.', why: 'Captures the intersection of old media and new internet giants in one ETF.' },
  // Broad Market
  { ticker: 'SPY',  name: 'SPDR S&P 500 ETF Trust',                   category: 'Broad Market',  focus: 'US Large-Cap',                 description: 'The original and most traded ETF in the world. Tracks the S&P 500 — 500 of the largest US companies.', why: 'The gold standard benchmark. Every other ETF is compared against this.' },
  { ticker: 'QQQ',  name: 'Invesco QQQ Trust',                         category: 'Broad Market',  focus: 'US Tech-Heavy Large-Cap',      description: 'Tracks the Nasdaq-100 — the 100 largest non-financial Nasdaq companies.', why: 'More concentrated in growth/tech than SPY. Outperforms in bull markets, sells off harder in bears.' },
  { ticker: 'IWM',  name: 'iShares Russell 2000 ETF',                  category: 'Broad Market',  focus: 'US Small-Cap',                 description: 'Tracks 2,000 small-cap US companies. More domestically focused than large-cap indices.', why: 'Small-caps are a leading indicator of domestic economic health and tend to lead recoveries.' },
  { ticker: 'VTI',  name: 'Vanguard Total Stock Market ETF',           category: 'Broad Market',  focus: 'US Total Market',              description: 'Covers the entire US equity market — large, mid, and small-cap stocks.', why: 'The most complete single-fund view of the US market. Ultra-low expense ratio.' },
  { ticker: 'EFA',  name: 'iShares MSCI EAFE ETF',                     category: 'Broad Market',  focus: 'International Developed',      description: 'Tracks stocks in Europe, Australasia, and the Far East (EAFE).', why: 'The standard benchmark for developed international equity exposure.' },
  { ticker: 'EEM',  name: 'iShares MSCI Emerging Markets ETF',         category: 'Broad Market',  focus: 'Emerging Markets',             description: 'Covers large and mid-cap stocks across 24 emerging market countries.', why: 'Higher growth potential — China, India, Taiwan all in one. Higher risk too.' },
  { ticker: 'BND',  name: 'Vanguard Total Bond Market ETF',            category: 'Broad Market',  focus: 'US Bonds',                     description: 'Tracks the entire US investment-grade bond market — government, corporate, and mortgage-backed.', why: 'The bond baseline. Included so the optimizer can allocate defensively when the math calls for it.' },
  { ticker: 'GLD',  name: 'SPDR Gold Shares',                          category: 'Broad Market',  focus: 'Gold',                         description: 'Tracks the price of gold bullion. Safe haven during market stress and inflation hedge.', why: 'Gold has near-zero long-run correlation with equities. A diversifier unlike anything else.' },
  // Thematic
  { ticker: 'ARKK', name: 'ARK Innovation ETF',                        category: 'Thematic',      focus: 'Disruptive Innovation',        description: 'Actively managed ETF targeting disruptive innovation across AI, genomics, fintech, and robotics.', why: 'The highest-beta innovation play available. High risk, high reward — pure growth conviction.' },
  { ticker: 'ICLN', name: 'iShares Global Clean Energy ETF',           category: 'Thematic',      focus: 'Clean Energy',                 description: 'Tracks global clean energy companies — solar, wind, and other renewables.', why: 'The energy transition is a multi-decade structural theme. Policy tailwinds from the IRA and global climate commitments.' },
  { ticker: 'CIBR', name: 'First Trust Cybersecurity ETF',             category: 'Thematic',      focus: 'Cybersecurity',                description: 'Covers companies providing cybersecurity hardware, software, and services.', why: 'Cyber threats are growing exponentially. This is non-discretionary enterprise spend — it only goes up.' },
  { ticker: 'ROBO', name: 'Robo Global Robotics & Automation ETF',     category: 'Thematic',      focus: 'Robotics & Automation',        description: 'Tracks the full robotics and automation value chain — components to end applications.', why: 'Automation is the answer to aging workforces globally. Broader and more diversified than BOTZ.' },
  { ticker: 'HERO', name: 'Global X Video Games & Esports ETF',        category: 'Thematic',      focus: 'Gaming & Esports',             description: 'Covers video game developers, publishers, and esports companies globally.', why: 'Gaming is now larger than film and music combined. A maturing but durable consumer trend.' },
  { ticker: 'AWAY', name: 'ETFMG Travel Tech ETF',                     category: 'Thematic',      focus: 'Travel Technology',            description: 'Tracks companies enabling travel through technology — booking, ridesharing, vacation rentals.', why: 'Travel tech rebounded strongly post-pandemic and benefits from structural shift to digital booking.' },
  { ticker: 'BOTZ', name: 'Global X Robotics & Artificial Intelligence ETF', category: 'Thematic', focus: 'Robotics & AI',              description: 'Covers companies developing or using robotics and AI — industrial and autonomous systems.', why: 'More concentrated AI/robotics exposure than ROBO. Directly captures the AI infrastructure buildout.' },
  { ticker: 'FINX', name: 'Global X FinTech ETF',                      category: 'Thematic',      focus: 'Financial Technology',         description: 'Tracks fintech companies disrupting traditional financial services — payments, lending, digital banking.', why: 'Fintech is hollowing out traditional banking. Long runway as global banking penetration increases.' },
  { ticker: 'BITO', name: 'ProShares Bitcoin Strategy ETF',            category: 'Thematic',      focus: 'Cryptocurrency',               description: 'The first US Bitcoin ETF — holds Bitcoin futures, providing regulated crypto exposure.', why: 'Crypto is a legitimate asset class. BITO lets us include it without a separate wallet or exchange.' },
  // International
  { ticker: 'VEU',  name: 'Vanguard FTSE All-World ex-US ETF',         category: 'International', focus: 'Global ex-US',                 description: 'Tracks the entire world equity market outside the United States — developed and emerging combined.', why: 'The single most efficient way to get broad international exposure in one ticker.' },
  { ticker: 'EWJ',  name: 'iShares MSCI Japan ETF',                    category: 'International', focus: 'Japan',                        description: 'Covers large and mid-cap Japanese equities. Third-largest economy, major tech and automotive hub.', why: 'Japan is undergoing a historic corporate governance overhaul, driving a multi-year re-rating of Japanese stocks.' },
  { ticker: 'INDA', name: 'iShares MSCI India ETF',                    category: 'International', focus: 'India',                        description: 'Tracks Indian equities — one of the world\'s fastest-growing major economies.', why: 'India has the demographics, growth rate, and digital infrastructure to be the defining emerging market of the 2030s.' },
  { ticker: 'FXI',  name: 'iShares China Large-Cap ETF',               category: 'International', focus: 'China',                        description: 'Covers the 50 largest Chinese companies listed in Hong Kong.', why: 'China is the second-largest economy. Even with geopolitical risk, it\'s too large to ignore in a global portfolio.' },
  { ticker: 'VWO',  name: 'Vanguard FTSE Emerging Markets ETF',        category: 'International', focus: 'Diversified Emerging Markets',  description: 'Vanguard\'s broad emerging markets ETF — lower cost than EEM with slightly different country weights.', why: 'Pairs with EEM to give a complete picture of EM exposure. The optimizer can differentiate between them.' },
  // Commodity
  { ticker: 'USO',  name: 'United States Oil Fund',                    category: 'Commodity',     focus: 'Crude Oil',                    description: 'Tracks the price of WTI crude oil via futures. Highly sensitive to OPEC, geopolitics, and global demand.', why: 'Oil is still the world\'s most important commodity. It\'s a direct macro signal and inflation driver.' },
  { ticker: 'DBA',  name: 'Invesco DB Agriculture Fund',               category: 'Commodity',     focus: 'Agriculture',                  description: 'Tracks a basket of agricultural commodity futures — corn, wheat, soybeans, and sugar.', why: 'Food commodities are an inflation hedge with near-zero correlation to equities. Climate risk makes this increasingly relevant.' },
  { ticker: 'PDBC', name: 'Invesco Optimum Yield Diversified Commodity ETF', category: 'Commodity', focus: 'Diversified Commodities',   description: 'Covers a broad basket of energy, metals, and agricultural futures, designed to minimize roll yield drag.', why: 'The most efficient broad commodity ETF available — better futures mechanics than most alternatives.' },
  // Factor
  { ticker: 'VTV',  name: 'Vanguard Value ETF',                        category: 'Factor',        focus: 'Value',                        description: 'Tracks large and mid-cap US stocks with low price-to-book and price-to-earnings ratios.', why: 'The value premium has persisted for over 90 years. After a decade of underperformance, valuations are compelling again.' },
  { ticker: 'VUG',  name: 'Vanguard Growth ETF',                       category: 'Factor',        focus: 'Growth',                       description: 'Tracks large and mid-cap US stocks with high earnings growth expectations.', why: 'The natural counterpart to VTV. Together they let the optimizer express a value/growth preference.' },
  { ticker: 'MTUM', name: 'iShares MSCI USA Momentum Factor ETF',      category: 'Factor',        focus: 'Momentum',                     description: 'Tilts toward stocks with strong recent price performance.', why: 'Momentum is one of the most robust factors in finance. Recent winners tend to keep winning over the medium term.' },
  { ticker: 'QUAL', name: 'iShares MSCI USA Quality Factor ETF',       category: 'Factor',        focus: 'Quality',                      description: 'Focuses on companies with high return on equity, stable earnings, and low leverage.', why: 'Quality outperforms in late-cycle and recessionary environments. A defensive factor with equity-like returns.' },
];

const CATEGORY_COLORS = {
  'Sector':        '#3b82f6',
  'Broad Market':  '#10b981',
  'Thematic':      '#f97316',
  'International': '#6366f1',
  'Commodity':     '#d97706',
  'Factor':        '#e11d48',
};


function ETFRow({ etf, isEven }) {
  const [expanded, setExpanded] = useState(false);
  const color = CATEGORY_COLORS[etf.category] || '#6b7280';

  return (
    <div
      onClick={() => setExpanded(e => !e)}
      style={{
        padding: '12px 20px',
        background: isEven ? '#fafafa' : '#ffffff',
        borderBottom: '1px solid #f3f4f6',
        cursor: 'pointer',
        transition: 'background 0.1s',
      }}
      onMouseEnter={e => e.currentTarget.style.background = '#f5f3ff'}
      onMouseLeave={e => e.currentTarget.style.background = isEven ? '#fafafa' : '#ffffff'}
    >
      <div style={{ display: 'flex', alignItems: 'center', gap: '16px' }}>
        {/* Ticker */}
        <div style={{
          fontWeight: '700', fontSize: '15px', color,
          minWidth: '52px',
        }}>
          {etf.ticker}
        </div>

        {/* Name + focus */}
        <div style={{ flex: 1, minWidth: 0 }}>
          <div style={{ fontWeight: '500', fontSize: '13px', color: '#111827', lineHeight: '1.3' }}>
            {etf.name}
          </div>
          <div style={{ fontSize: '12px', color: '#9ca3af', marginTop: '2px' }}>
            {etf.focus}
          </div>
        </div>

        {/* Expand chevron */}
        <div style={{ color: '#9ca3af', fontSize: '12px', flexShrink: 0 }}>
          {expanded ? '▲' : '▼'}
        </div>
      </div>

      {/* Expanded detail */}
      {expanded && (
        <div style={{ marginTop: '12px', paddingTop: '12px', borderTop: '1px solid #f3f4f6', display: 'flex', gap: '24px' }}>
          <div style={{ flex: 1 }}>
            <div style={{ fontSize: '11px', fontWeight: '600', color: '#9ca3af', textTransform: 'uppercase', letterSpacing: '0.5px', marginBottom: '4px' }}>
              What it holds
            </div>
            <div style={{ fontSize: '13px', color: '#374151', lineHeight: '1.5' }}>
              {etf.description}
            </div>
          </div>
          <div style={{ flex: 1 }}>
            <div style={{ fontSize: '11px', fontWeight: '600', color, textTransform: 'uppercase', letterSpacing: '0.5px', marginBottom: '4px' }}>
              Why we included it
            </div>
            <div style={{ fontSize: '13px', color: '#374151', lineHeight: '1.5' }}>
              {etf.why}
            </div>
          </div>
        </div>
      )}
    </div>
  );
}

function CategorySection({ meta, etfs }) {
  const [collapsed, setCollapsed] = useState(false);
  const categoryEtfs = etfs.filter(e => e.category === meta.name);

  return (
    <div style={{ marginBottom: '24px' }}>
      {/* Category Header */}
      <div
        onClick={() => setCollapsed(c => !c)}
        style={{
          display: 'flex', alignItems: 'center', gap: '12px',
          padding: '14px 20px',
          background: meta.color,
          borderRadius: collapsed ? '12px' : '12px 12px 0 0',
          cursor: 'pointer',
          userSelect: 'none',
          transition: 'filter 0.15s',
        }}
        onMouseEnter={e => e.currentTarget.style.filter = 'brightness(1.08)'}
        onMouseLeave={e => e.currentTarget.style.filter = 'brightness(1)'}
      >
        <span style={{ fontWeight: '700', fontSize: '15px', color: 'white', flex: 1 }}>
          {meta.name}
          <span style={{ fontWeight: '400', fontSize: '13px', marginLeft: '8px', opacity: 0.85 }}>
            — {categoryEtfs.length} ETF{categoryEtfs.length !== 1 ? 's' : ''}
          </span>
        </span>
        <span style={{ color: 'rgba(255,255,255,0.7)', fontSize: '13px' }}>
          {collapsed ? '▼ Show' : '▲ Hide'}
        </span>
      </div>

      {!collapsed && (
        <div style={{ border: '1px solid #e5e7eb', borderTop: 'none', borderRadius: '0 0 12px 12px', overflow: 'hidden' }}>
          {/* Category description */}
          <div style={{ padding: '16px 20px', background: meta.bg, display: 'flex', gap: '32px' }}>
            <div style={{ flex: 2 }}>
              <div style={{ fontSize: '11px', fontWeight: '700', color: meta.textColor, textTransform: 'uppercase', letterSpacing: '0.5px', marginBottom: '6px' }}>
                What is a {meta.name} ETF?
              </div>
              <p style={{ fontSize: '13px', color: '#374151', lineHeight: '1.6', margin: 0 }}>
                {meta.description}
              </p>
            </div>
            <div style={{ flex: 1, borderLeft: `3px solid ${meta.color}`, paddingLeft: '16px' }}>
              <div style={{ fontSize: '11px', fontWeight: '700', color: meta.textColor, textTransform: 'uppercase', letterSpacing: '0.5px', marginBottom: '6px' }}>
                Why it's in InvestIQ
              </div>
              <p style={{ fontSize: '13px', color: '#374151', lineHeight: '1.6', margin: 0 }}>
                {meta.why}
              </p>
            </div>
          </div>

          {/* Column headers */}
          <div style={{
            display: 'flex', gap: '16px', padding: '8px 20px',
            background: '#f9fafb', borderTop: '1px solid #e5e7eb', borderBottom: '1px solid #e5e7eb',
          }}>
            <div style={{ minWidth: '52px', fontSize: '11px', fontWeight: '600', color: '#9ca3af', textTransform: 'uppercase', letterSpacing: '0.5px' }}>Ticker</div>
            <div style={{ flex: 1, fontSize: '11px', fontWeight: '600', color: '#9ca3af', textTransform: 'uppercase', letterSpacing: '0.5px' }}>Name · Focus — click any row to expand</div>
          </div>

          {/* ETF rows */}
          {categoryEtfs.map((etf, i) => (
            <ETFRow key={etf.ticker} etf={etf} isEven={i % 2 === 0} />
          ))}
        </div>
      )}
    </div>
  );
}

function Universe() {
  const [activeFilter, setActiveFilter] = useState('All');
  const categories = ['All', ...CATEGORY_META.map(c => c.name)];
  const visibleMeta = activeFilter === 'All'
    ? CATEGORY_META
    : CATEGORY_META.filter(c => c.name === activeFilter);

  return (
    <div>
      <div className="page-header">
        <h1>ETF Universe</h1>
        <p>What we hold, why we hold it, and how every ETF fits into the bigger picture</p>
      </div>

      {/* What is an ETF */}
      <div className="card" style={{ marginBottom: '28px' }}>
        <h2 style={{ fontSize: '18px', fontWeight: '700', color: '#7c3aed', marginBottom: '12px' }}>
          What is an ETF?
        </h2>
        <div style={{ display: 'flex', gap: '32px' }}>
          <p style={{ flex: 1, fontSize: '14px', color: '#374151', lineHeight: '1.7', margin: 0 }}>
            An <strong>Exchange-Traded Fund (ETF)</strong> is a basket of securities — stocks, bonds, or commodities — that trades on a stock exchange just like a single share of stock. When you buy one share of SPY, you're effectively buying a tiny slice of all 500 companies in the S&P 500 at once.
          </p>
          <p style={{ flex: 1, fontSize: '14px', color: '#374151', lineHeight: '1.7', margin: 0 }}>
            ETFs offer three key advantages: <strong>instant diversification</strong> (you own dozens or hundreds of companies), <strong>low cost</strong> (expense ratios are typically 0.03–0.75%), and <strong>liquidity</strong> (buy or sell any time the market is open, just like a stock).
          </p>
          <p style={{ flex: 1, fontSize: '14px', color: '#374151', lineHeight: '1.7', margin: 0 }}>
            InvestIQ organizes its universe into <strong>6 categories</strong>, each representing a different type of market exposure with its own risk profile, return drivers, and role in a portfolio. Together they span{' '}
            <strong style={{ color: '#7c3aed' }}>40 ETFs</strong> across every major asset class.
          </p>
        </div>
      </div>

      {/* Stats bar */}
      <div style={{ display: 'flex', gap: '12px', marginBottom: '28px', flexWrap: 'wrap' }}>
        {CATEGORY_META.map(cat => {
          const count = ETFS.filter(e => e.category === cat.name).length;
          return (
            <div key={cat.name} style={{
              display: 'flex', alignItems: 'center', gap: '8px',
              padding: '8px 16px', borderRadius: '999px',
              background: cat.bg, border: `1px solid ${cat.color}33`,
            }}>
              <div style={{ width: '8px', height: '8px', borderRadius: '50%', background: cat.color }} />
              <span style={{ fontSize: '13px', fontWeight: '600', color: cat.textColor }}>{cat.name}</span>
              <span style={{ fontSize: '13px', color: cat.textColor, opacity: 0.7 }}>{count}</span>
            </div>
          );
        })}
      </div>

      {/* Category filter */}
      <div className="toggle-group" style={{ marginBottom: '24px', flexWrap: 'wrap' }}>
        {categories.map(cat => (
          <button
            key={cat}
            className={`toggle-btn ${activeFilter === cat ? 'active' : ''}`}
            onClick={() => setActiveFilter(cat)}
            style={activeFilter === cat && cat !== 'All' ? {
              background: CATEGORY_COLORS[cat],
              borderColor: CATEGORY_COLORS[cat],
              color: 'white',
            } : {}}
          >
            {cat}
          </button>
        ))}
      </div>

      {/* Category sections */}
      {visibleMeta.map(meta => (
        <CategorySection key={meta.name} meta={meta} etfs={ETFS} />
      ))}
    </div>
  );
}

export default Universe;
