import React, { useState, useEffect } from 'react';
import { X, TrendingUp, TrendingDown, Minus, Clock, ShieldCheck, Newspaper } from 'lucide-react';
import { LineChart, Line, XAxis, YAxis, CartesianGrid, Tooltip, ReferenceLine, ResponsiveContainer } from 'recharts';
import '../index.css';

const AnalysisModal = ({ option, onClose }) => {
  const [data, setData] = useState(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState(null);
  const [showTriggers, setShowTriggers] = useState(false);

  useEffect(() => {
    const fetchData = async () => {
      try {
        const response = await fetch(`http://localhost:8000/api/analyze-option/${option.symbol}?strike=${option.strike}&dte=${option.dte}&current_price=${option.currentPrice}`);
        if (!response.ok) throw new Error('Failed to fetch detailed analysis');
        const result = await response.json();
        setData(result);
      } catch (err) {
        setError(err.message);
      } finally {
        setLoading(false);
      }
    };
    
    fetchData();
  }, [option]);

  if (!option) return null;

  return (
    <div className="modal-overlay" onClick={onClose} style={{
      position: 'fixed', top: 0, left: 0, right: 0, bottom: 0, 
      backgroundColor: 'rgba(0,0,0,0.7)', backdropFilter: 'blur(5px)',
      display: 'flex', justifyContent: 'center', alignItems: 'center', zIndex: 1000
    }}>
      <div className="glass-panel modal-content" onClick={e => e.stopPropagation()} style={{
        width: '90%', maxWidth: '900px', maxHeight: '90vh', overflowY: 'auto',
        padding: '2rem', position: 'relative'
      }}>
        <button onClick={onClose} style={{
          position: 'absolute', top: '1rem', right: '1rem', 
          background: 'transparent', border: 'none', color: 'var(--text-secondary)', cursor: 'pointer'
        }}>
          <X size={24} />
        </button>

        <h2 style={{ marginBottom: '0.5rem', display: 'flex', alignItems: 'center', gap: '1rem' }}>
          {option.symbol} Detailed Analysis
          <span className="strategy-badge">STRIKE: ${option.strike.toFixed(2)}</span>
        </h2>
        <p style={{ color: 'var(--text-secondary)', marginBottom: '2rem' }}>
          Historical verification and authoritative news analysis.
        </p>

        {loading ? (
          <div className="loading-container" style={{ minHeight: '300px' }}>
            <div className="spinner"></div>
            <p>Fetching historical prices and latest news...</p>
          </div>
        ) : error ? (
          <div style={{ padding: '1rem', borderLeft: '4px solid var(--danger-color)', backgroundColor: 'rgba(239, 68, 68, 0.1)' }}>
            Error: {error}
          </div>
        ) : (
          <div style={{ display: 'flex', flexDirection: 'column', gap: '2rem' }}>
            
            {/* Historical Verification Section */}
            <div>
              <h3 style={{ display: 'flex', alignItems: 'center', gap: '0.5rem', marginBottom: '1rem' }}>
                <ShieldCheck size={20} color="var(--success-color)" /> Historical Verification (1 Year)
              </h3>
              
              <div style={{ display: 'flex', gap: '1rem', marginBottom: '1rem' }}>
                <div style={{ flex: 1, padding: '1rem', background: 'rgba(255,255,255,0.05)', borderRadius: '8px' }}>
                  <p style={{ color: 'var(--text-secondary)', fontSize: '0.9rem' }}>Days Safe (Above Strike)</p>
                  <p style={{ fontSize: '1.5rem', fontWeight: 'bold', color: 'var(--success-color)' }}>
                    {data.historical_stats.days_safe} / {data.historical_stats.total_trading_days}
                  </p>
                </div>
                <div 
                  style={{ flex: 1, padding: '1rem', background: 'rgba(255,255,255,0.05)', borderRadius: '8px', cursor: 'pointer', transition: 'all 0.2s ease', border: showTriggers ? '1px solid var(--warning-color)' : '1px solid transparent' }}
                  onClick={() => setShowTriggers(!showTriggers)}
                  onMouseEnter={(e) => e.currentTarget.style.background = 'rgba(255,255,255,0.1)'}
                  onMouseLeave={(e) => e.currentTarget.style.background = 'rgba(255,255,255,0.05)'}
                >
                  <p style={{ color: 'var(--text-secondary)', fontSize: '0.9rem' }}>Days Triggered <span style={{fontSize: '0.75rem', color: 'var(--accent-color)'}}>(Click Details)</span></p>
                  <p style={{ fontSize: '1.5rem', fontWeight: 'bold', color: data.historical_stats.days_below_strike > 0 ? 'var(--warning-color)' : 'var(--text-primary)' }}>
                    {data.historical_stats.days_below_strike}
                  </p>
                </div>
                <div style={{ flex: 1, padding: '1rem', background: 'rgba(255,255,255,0.05)', borderRadius: '8px' }}>
                  <p style={{ color: 'var(--text-secondary)', fontSize: '0.9rem' }}>Actual Historical Win Rate</p>
                  <p style={{ fontSize: '1.5rem', fontWeight: 'bold' }}>
                    {data.historical_stats.historical_win_rate}%
                  </p>
                </div>
              </div>

              {showTriggers && data.historical_stats.triggered_events && data.historical_stats.triggered_events.length > 0 && (
                <div style={{ padding: '1rem', background: 'rgba(255,255,255,0.05)', borderRadius: '8px', marginBottom: '1rem', borderLeft: '4px solid var(--warning-color)' }}>
                  <h4 style={{ marginBottom: '0.5rem', color: 'var(--text-primary)' }}>Triggered Crash Events Details</h4>
                  <p style={{ fontSize: '0.9rem', color: 'var(--text-secondary)', marginBottom: '1rem', lineHeight: '1.5' }}>
                    <strong>💼 CEO Advice:</strong> While these historical windows breached your strike, a "trigger" is not an immediate realized loss. Because you are willing to employ the <strong>Wheel Strategy</strong> or <strong>Roll out in time</strong>, you turn a capital loss into a time loss. By rolling down and out for a net credit, or taking assignment to sell Covered Calls, these temporary drawdowns can still result in long-term profitability.
                  </p>
                  <div style={{ maxHeight: '250px', overflowY: 'auto', display: 'flex', flexDirection: 'column', gap: '0.5rem', paddingRight: '0.5rem' }}>
                    {data.historical_stats.triggered_events.map((ev, i) => (
                      <div key={i} style={{ display: 'flex', justifyContent: 'space-between', padding: '0.75rem', background: 'rgba(0,0,0,0.2)', borderRadius: '4px', fontSize: '0.9rem' }}>
                        <span style={{ color: 'var(--text-secondary)' }}>Started: <strong style={{ color: 'var(--text-primary)' }}>{ev.date}</strong></span>
                        <span>Drop: ${ev.start_price} → <span style={{ color: 'var(--danger-color)' }}>${ev.min_price}</span></span>
                        <span style={{ color: 'var(--danger-color)', fontWeight: 'bold' }}>-{ev.drawdown_pct}%</span>
                      </div>
                    ))}
                  </div>
                </div>
              )}

              <div style={{ height: '300px', width: '100%', background: 'rgba(0,0,0,0.2)', borderRadius: '8px', padding: '1rem' }}>
                <ResponsiveContainer width="100%" height="100%">
                  <LineChart data={data.chart_data}>
                    <CartesianGrid strokeDasharray="3 3" stroke="rgba(255,255,255,0.1)" vertical={false} />
                    <XAxis dataKey="date" stroke="var(--text-secondary)" tick={{fontSize: 12}} minTickGap={30} />
                    <YAxis domain={['auto', 'auto']} stroke="var(--text-secondary)" tick={{fontSize: 12}} />
                    <Tooltip 
                      contentStyle={{ backgroundColor: 'var(--bg-color)', borderColor: 'var(--card-border)', borderRadius: '8px' }}
                      itemStyle={{ color: 'var(--text-primary)' }}
                    />
                    <ReferenceLine y={option.strike} label={{ position: 'top', value: `Strike $${option.strike}`, fill: 'var(--danger-color)', fontSize: 12 }} stroke="var(--danger-color)" strokeDasharray="3 3" />
                    <Line type="monotone" dataKey="price" stroke="var(--accent-color)" dot={false} strokeWidth={2} />
                  </LineChart>
                </ResponsiveContainer>
              </div>
            </div>

            {/* News Analysis Section */}
            <div>
              <h3 style={{ display: 'flex', alignItems: 'center', gap: '0.5rem', marginBottom: '1rem' }}>
                <Newspaper size={20} color="var(--accent-color)" /> Recent Authoritative News & Sentiment
              </h3>
              
              <div style={{ display: 'flex', alignItems: 'center', gap: '1rem', padding: '1rem', background: 'rgba(255,255,255,0.05)', borderRadius: '8px', marginBottom: '1rem' }}>
                <span style={{ color: 'var(--text-secondary)' }}>Overall Sentiment:</span>
                <span style={{ 
                  display: 'flex', alignItems: 'center', gap: '0.5rem', fontWeight: 'bold', fontSize: '1.2rem',
                  color: data.news_analysis.overall_sentiment === 'Bullish' ? 'var(--success-color)' : 
                         data.news_analysis.overall_sentiment === 'Bearish' ? 'var(--danger-color)' : 'var(--warning-color)'
                }}>
                  {data.news_analysis.overall_sentiment === 'Bullish' && <TrendingUp />}
                  {data.news_analysis.overall_sentiment === 'Bearish' && <TrendingDown />}
                  {data.news_analysis.overall_sentiment === 'Neutral' && <Minus />}
                  {data.news_analysis.overall_sentiment}
                </span>
              </div>

              <div style={{ display: 'flex', flexDirection: 'column', gap: '0.5rem' }}>
                {data.news_analysis.articles.length > 0 ? (
                  data.news_analysis.articles.map((article, idx) => (
                    <div key={idx} style={{ padding: '1rem', border: '1px solid var(--card-border)', borderRadius: '8px' }}>
                      <a href={article.link} target="_blank" rel="noreferrer" style={{ color: 'var(--text-primary)', textDecoration: 'none', fontWeight: 'bold', display: 'block', marginBottom: '0.5rem' }}>
                        {article.title}
                      </a>
                      <div style={{ display: 'flex', justifyContent: 'space-between', fontSize: '0.85rem', color: 'var(--text-secondary)' }}>
                        <span>Source: <span style={{ color: 'var(--accent-color)' }}>{article.publisher || 'Financial News'}</span></span>
                        <span>Sentiment Score: {(article.sentiment_score > 0 ? '+' : '') + article.sentiment_score.toFixed(2)}</span>
                      </div>
                    </div>
                  ))
                ) : (
                  <p style={{ color: 'var(--text-secondary)' }}>No recent authoritative news found.</p>
                )}
              </div>
            </div>

          </div>
        )}
      </div>
    </div>
  );
};

export default AnalysisModal;
