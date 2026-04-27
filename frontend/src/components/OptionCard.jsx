import React from 'react';
import { Shield, ShieldAlert, TrendingUp, Calendar, Activity } from 'lucide-react';

const OptionCard = ({ option, onClick }) => {
  const {
    symbol,
    currentPrice,
    strike,
    premium,
    dte,
    expirationDate,
    annualizedReturn,
    winRateEstimate,
    riskScore
  } = option;

  return (
    <div className="glass-panel option-card" onClick={onClick}>
      <div className="card-header" style={{ marginBottom: option.earningsRisk ? '0.5rem' : '1rem' }}>
        <div className="symbol-container">
          <span className="symbol">{symbol}</span>
          <span className="current-price">${currentPrice.toFixed(2)}</span>
        </div>
        <span className="strategy-badge">SELL PUT</span>
      </div>
      
      {option.earningsRisk && (
        <div style={{ background: 'rgba(239, 68, 68, 0.2)', color: 'var(--danger-color)', padding: '0.25rem 0.5rem', borderRadius: '4px', fontSize: '0.75rem', fontWeight: 'bold', display: 'flex', alignItems: 'center', gap: '0.25rem', marginBottom: '1rem', border: '1px solid rgba(239, 68, 68, 0.3)' }}>
          <ShieldAlert size={14} /> ⚠️ 财报高危 (Earnings Before Expiry)
        </div>
      )}

      <div className="card-metrics">
        <div className="metric">
          <span className="metric-label">Strike</span>
          <span className="metric-value">${strike.toFixed(2)}</span>
        </div>
        <div className="metric">
          <span className="metric-label">Premium</span>
          <span className="metric-value highlight">${premium.toFixed(2)}</span>
        </div>
        <div className="metric">
          <span className="metric-label">Expiring In</span>
          <span className="metric-value" style={{ display: 'flex', alignItems: 'center', gap: '4px' }}>
            <Calendar size={16} /> {dte} Days
          </span>
        </div>
        <div className="metric">
          <span className="metric-label">Annualized Return</span>
          <span className="metric-value success" style={{ display: 'flex', alignItems: 'center', gap: '4px' }}>
            <TrendingUp size={16} /> {annualizedReturn.toFixed(1)}%
          </span>
        </div>
      </div>

      <div className="progress-container">
        <div className="progress-label">
          <span style={{ display: 'flex', alignItems: 'center', gap: '4px', color: winRateEstimate > 85 ? '#10b981' : '#f59e0b' }}>
            {winRateEstimate > 85 ? <Shield size={14} /> : <ShieldAlert size={14} />} 
            Est. Win Rate (Backtest Proxy)
          </span>
          <span>{winRateEstimate.toFixed(1)}%</span>
        </div>
        <div className="progress-bar">
          <div 
            className="progress-fill" 
            style={{ width: `${winRateEstimate}%`, background: winRateEstimate > 85 ? 'linear-gradient(to right, #10b981, #059669)' : 'linear-gradient(to right, #f59e0b, #d97706)' }}
          ></div>
        </div>
      </div>
      
      <div style={{ marginTop: '1rem', fontSize: '0.8rem', color: 'var(--text-secondary)', display: 'flex', justifyContent: 'space-between' }}>
        <span>Exp: {expirationDate}</span>
        <span style={{ display: 'flex', alignItems: 'center', gap: '4px' }}><Activity size={12}/> Risk Score: {riskScore}</span>
      </div>
    </div>
  );
};

export default OptionCard;
