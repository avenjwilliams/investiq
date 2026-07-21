import React from 'react';
import { NavLink } from 'react-router-dom';

function Navbar() {
  const navLinkClass = ({ isActive }) => `nav-link${isActive ? ' active' : ''}`;

  return (
    <nav className="navbar">
      <NavLink to="/portfolio" className="navbar-brand">
        <div className="navbar-brand-dot">IQ</div>
        <span className="navbar-brand-name">InvestIQ</span>
      </NavLink>
      <div className="navbar-links">
        <NavLink to="/portfolio" className={navLinkClass}>Portfolio</NavLink>
        <NavLink to="/explorer" className={navLinkClass}>ETF Explorer</NavLink>
        <NavLink to="/sentiment" className={navLinkClass}>Sentiment Feed</NavLink>
        <NavLink to="/universe" className={navLinkClass}>ETF Universe</NavLink>
        <NavLink to="/forecasts" className={navLinkClass}>Forecasts</NavLink>
        <NavLink to="/model-metrics" className={navLinkClass}>Model Metrics</NavLink>
      </div>
    </nav>
  );
}

export default Navbar;
