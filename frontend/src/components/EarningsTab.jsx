import React, { useState, useEffect } from 'react';
import { Calendar, AlertTriangle } from 'lucide-react';

const EarningsTab = () => {
  const [earnings, setEarnings] = useState([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState(null);

  useEffect(() => {
    const fetchEarnings = async () => {
      try {
        const response = await fetch('http://localhost:8000/api/earnings');
        if (!response.ok) throw new Error('Failed to fetch earnings calendar');
        const data = await response.json();
        setEarnings(data.data);
      } catch (err) {
        setError(err.message);
      } finally {
        setLoading(false);
      }
    };
    
    fetchEarnings();
  }, []);

  const today = new Date();
  
  return (
    <div style={{ animation: 'fadeInUp 0.5s ease-out' }}>
      <div style={{ marginBottom: '2rem' }}>
        <h2 style={{ fontSize: '2rem', marginBottom: '0.5rem', display: 'flex', alignItems: 'center', gap: '1rem' }}>
          <Calendar color="var(--accent-color)" /> Earnings Avoidance Radar
        </h2>
        <p style={{ color: 'var(--text-secondary)' }}>
          <strong>CEO Advice:</strong> Selling options through an earnings event is gambling, not quantitative trading. The implied volatility crush and unpredictable price gaps destroy mathematical expectancy. 
          <span style={{ color: 'var(--warning-color)', marginLeft: '0.5rem' }}>Do not sell short-term Cash-Secured Puts if the expiration date is after these dates.</span>
        </p>
      </div>

      {loading ? (
        <div className="loading-container"><div className="spinner"></div><p>Fetching earnings calendar...</p></div>
      ) : error ? (
        <div style={{ padding: '1rem', borderLeft: '4px solid var(--danger-color)', backgroundColor: 'rgba(239, 68, 68, 0.1)' }}>Error: {error}</div>
      ) : (
        <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fill, minmax(250px, 1fr))', gap: '1.5rem' }}>
          {earnings.map((item, idx) => {
            const earnDate = new Date(item.earnings_date);
            const daysAway = Math.floor((earnDate - today) / (1000 * 60 * 60 * 24));
            
            const isDanger = daysAway >= 0 && daysAway <= 14;
            
            return (
              <div key={idx} className="glass-panel" style={{ 
                padding: '1.5rem', 
                borderLeft: isDanger ? '4px solid var(--danger-color)' : '4px solid var(--success-color)',
                backgroundColor: isDanger ? 'rgba(239, 68, 68, 0.05)' : 'var(--card-bg)'
              }}>
                <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: '1rem' }}>
                  <span style={{ fontSize: '1.5rem', fontWeight: 'bold' }}>{item.symbol}</span>
                  {isDanger && <AlertTriangle size={20} color="var(--danger-color)" />}
                </div>
                <div style={{ display: 'flex', flexDirection: 'column', gap: '0.5rem' }}>
                  <span style={{ color: 'var(--text-secondary)', fontSize: '0.9rem' }}>Next Earnings:</span>
                  <span style={{ fontSize: '1.2rem', fontWeight: '600' }}>{item.earnings_date}</span>
                  <span style={{ 
                    fontSize: '0.85rem', 
                    color: isDanger ? 'var(--danger-color)' : 'var(--success-color)',
                    fontWeight: 'bold',
                    marginTop: '0.5rem'
                  }}>
                    {daysAway < 0 ? 'Passed' : `In ${daysAway} Days`}
                  </span>
                </div>
              </div>
            );
          })}
        </div>
      )}
    </div>
  );
};

export default EarningsTab;
