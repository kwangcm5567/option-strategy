import React, { useState, useEffect } from 'react';
import { RefreshCw, TrendingUp, Zap, Clock, Shield } from 'lucide-react';

const BuyCallsTab = () => {
  const [options, setOptions] = useState([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState(null);

  const fetchBuyCalls = async () => {
    setLoading(true);
    setError(null);
    try {
      const response = await fetch('http://localhost:8000/api/buy-calls');
      if (!response.ok) throw new Error('Failed to fetch Buy Call data');
      const data = await response.json();
      setOptions(data.data);
    } catch (err) {
      setError(err.message);
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    fetchBuyCalls();
  }, []);

  const shortTerm = options.filter(o => o.strategy === 'Short-Term Momentum');
  const longTerm = options.filter(o => o.strategy === 'Long-Term Directional');

  const renderSection = (title, description, data, icon, color) => (
    <div style={{ marginBottom: '3rem' }}>
      <div style={{ marginBottom: '1.5rem', display: 'flex', alignItems: 'center', gap: '1rem' }}>
        {icon}
        <div>
          <h2 style={{ fontSize: '1.5rem', fontWeight: 'bold' }}>{title}</h2>
          <p style={{ color: 'var(--text-secondary)' }}>{description}</p>
        </div>
      </div>
      
      {data.length === 0 ? (
        <p style={{ color: 'var(--text-secondary)' }}>No options found matching this criteria currently.</p>
      ) : (
        <div className="dashboard-grid">
          {data.map((option, idx) => (
            <div key={idx} className="glass-panel option-card" style={{ cursor: 'default' }}>
              <div className="card-header">
                <div className="symbol-container">
                  <span className="symbol">{option.symbol}</span>
                  <span className="current-price">${option.currentPrice.toFixed(2)}</span>
                </div>
                <span className="strategy-badge" style={{ color: color, background: `rgba(${color === 'var(--accent-color)' ? '59,130,246' : '139,92,246'},0.1)`, borderColor: `rgba(${color === 'var(--accent-color)' ? '59,130,246' : '139,92,246'},0.2)` }}>BUY CALL</span>
              </div>
              
              <div className="card-metrics">
                <div className="metric">
                  <span className="metric-label">Strike (ATM/OTM)</span>
                  <span className="metric-value">${option.strike.toFixed(2)}</span>
                </div>
                <div className="metric">
                  <span className="metric-label">Cost (Premium)</span>
                  <span className="metric-value highlight" style={{color}}>${option.premium.toFixed(2)}</span>
                </div>
                <div className="metric">
                  <span className="metric-label">Expiring In</span>
                  <span className="metric-value" style={{ display: 'flex', alignItems: 'center', gap: '4px' }}>
                    <Clock size={16} /> {option.dte} Days
                  </span>
                </div>
                <div className="metric">
                  <span className="metric-label">Volatility Edge</span>
                  <span className="metric-value" style={{ display: 'flex', alignItems: 'center', gap: '4px', color: option.volEdge > 1 ? 'var(--success-color)' : 'var(--text-primary)' }}>
                    <TrendingUp size={16} /> {option.volEdge.toFixed(2)}x
                  </span>
                </div>
              </div>
              
              <div style={{ marginTop: '1rem', paddingTop: '1rem', borderTop: '1px solid var(--card-border)', fontSize: '0.85rem', color: 'var(--text-secondary)' }}>
                <p><strong>CEO Note:</strong> Implied Volatility is {option.iv}%, but Historical Volatility is {option.hv}%. This means the option premium is relatively cheap compared to how much the stock usually moves.</p>
              </div>
            </div>
          ))}
        </div>
      )}
    </div>
  );

  return (
    <div style={{ animation: 'fadeInUp 0.5s ease-out' }}>
      <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: '2rem' }}>
        <div>
          <h2 style={{ fontSize: '2rem', marginBottom: '0.5rem' }}>Buy Call Strategies</h2>
          <p style={{ color: 'var(--text-secondary)' }}>Low probability, theoretically unlimited reward. Filtering for cheap IV vs HV.</p>
        </div>
        <button 
          onClick={fetchBuyCalls} 
          disabled={loading}
          style={{ 
            background: 'var(--card-bg)', border: '1px solid var(--card-border)', color: 'var(--text-primary)',
            padding: '0.5rem 1rem', borderRadius: '8px', cursor: loading ? 'not-allowed' : 'pointer',
            display: 'flex', alignItems: 'center', gap: '0.5rem'
          }}
        >
          <RefreshCw size={16} className={loading ? 'spin' : ''} style={{ animation: loading ? 'spin 1s linear infinite' : 'none' }} />
          Refresh
        </button>
      </div>

      {loading ? (
        <div className="loading-container"><div className="spinner"></div><p>Scanning for cheap Calls...</p></div>
      ) : error ? (
        <div style={{ padding: '1rem', borderLeft: '4px solid var(--danger-color)', backgroundColor: 'rgba(239, 68, 68, 0.1)' }}>Error: {error}</div>
      ) : (
        <>
          {renderSection(
            "Short-Term Momentum (14-45 Days)", 
            "Capitalizing on immediate uptrends where the stock is trading above its 50-day moving average. High risk of Theta decay.", 
            shortTerm, 
            <Zap size={32} color="#f59e0b" />, 
            '#f59e0b'
          )}
          {renderSection(
            "Long-Term Directional (90-180 Days)", 
            "Safer directional bets. Gives the stock ample time to move in your favor without aggressive daily Theta decay.", 
            longTerm, 
            <Shield size={32} color="#8b5cf6" />, 
            '#8b5cf6'
          )}
        </>
      )}
    </div>
  );
};

export default BuyCallsTab;
