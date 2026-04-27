import { RefreshCw } from 'lucide-react';
import { useApi } from '../../hooks/useApi';
import LoadingSpinner, { ErrorBox } from '../../components/ui/LoadingSpinner';
import Tooltip from '../../components/ui/Tooltip';
import { TIPS } from '../../constants/tooltips';

function VIXGauge({ vix }) {
  if (!vix) return null;
  const pct = Math.min((vix.current / 50) * 100, 100);
  const color = vix.current < 15 ? '#10b981' : vix.current < 25 ? '#f59e0b' : vix.current < 35 ? '#f97316' : '#ef4444';

  return (
    <div className="glass-panel" style={{ padding: '1.25rem', marginBottom: '1.5rem' }}>
      <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'flex-start', marginBottom: '1rem' }}>
        <div>
          <h3 style={{ fontSize: '0.85rem', color: 'var(--text-secondary)', marginBottom: '4px' }}>VIX 恐慌指数</h3>
          <div style={{ display: 'flex', alignItems: 'baseline', gap: '0.5rem' }}>
            <span style={{ fontSize: '2.5rem', fontWeight: 800, color }}>{vix.current.toFixed(2)}</span>
            <span style={{ color: 'var(--text-secondary)', fontSize: '0.82rem' }}>52周：{vix.weekLow52} – {vix.weekHigh52}</span>
          </div>
        </div>
        <div style={{ textAlign: 'right' }}>
          <div style={{ fontSize: '0.75rem', color: 'var(--text-secondary)', marginBottom: '4px' }}>
            <Tooltip text="VIX = 市场对未来 30 天波动的预期。数值越高，市场越恐慌，期权越贵。" width={260}>
              <span>52周 Rank</span>
            </Tooltip>
          </div>
          <span style={{ fontSize: '1.4rem', fontWeight: 700, color }}>{vix.rank52w}%</span>
        </div>
      </div>
      <div style={{ height: '8px', background: 'rgba(255,255,255,0.08)', borderRadius: '4px', overflow: 'hidden', marginBottom: '0.75rem' }}>
        <div style={{ height: '100%', width: `${pct}%`, background: `linear-gradient(to right, #10b981, ${color})`, borderRadius: '4px', transition: 'width 0.8s ease' }} />
      </div>
      <p style={{ fontSize: '0.85rem', color, fontWeight: 600, lineHeight: '1.5' }}>{vix.description}</p>
      <div style={{ display: 'flex', gap: '1.5rem', marginTop: '0.75rem', fontSize: '0.75rem', color: 'var(--text-secondary)' }}>
        <span>🟢 &lt;15 平静</span>
        <span>🟡 15–25 正常</span>
        <span>🟠 25–35 紧张</span>
        <span>🔴 &gt;35 恐慌（卖期权最佳）</span>
      </div>
    </div>
  );
}

function IVHeatMap({ ivRanks }) {
  if (!ivRanks?.length) return null;

  return (
    <div>
      <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: '0.75rem' }}>
        <h3 style={{ fontSize: '0.95rem', fontWeight: 700 }}>
          <Tooltip text={TIPS.ivRank} width={300}><span>20 只股票 IV Rank 热力图</span></Tooltip>
        </h3>
        <div style={{ display: 'flex', gap: '1rem', fontSize: '0.73rem', color: 'var(--text-secondary)' }}>
          <span>🟢 &lt;30% 便宜（适合买）</span>
          <span>🟡 30–60% 正常</span>
          <span>🔴 &gt;60% 贵（适合卖）</span>
        </div>
      </div>
      <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fill, minmax(160px, 1fr))', gap: '0.6rem' }}>
        {ivRanks.map(({ symbol, currentPrice, currentIV, ivRank }) => {
          const color = ivRank >= 60 ? '#ef4444' : ivRank >= 30 ? '#f59e0b' : '#10b981';
          const bg = ivRank >= 60 ? 'rgba(239,68,68,0.08)' : ivRank >= 30 ? 'rgba(245,158,11,0.08)' : 'rgba(16,185,129,0.08)';
          return (
            <div key={symbol} style={{ background: bg, border: `1px solid ${color}22`, borderRadius: '10px', padding: '0.75rem', borderLeft: `3px solid ${color}` }}>
              <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: '0.4rem' }}>
                <span style={{ fontWeight: 700, fontSize: '0.95rem' }}>{symbol}</span>
                <span style={{ fontSize: '1rem', fontWeight: 700, color }}>{ivRank}%</span>
              </div>
              <div style={{ fontSize: '0.72rem', color: 'var(--text-secondary)', marginBottom: '6px' }}>
                ${currentPrice.toFixed(0)} · IV {currentIV}%
              </div>
              <div style={{ height: '4px', background: 'rgba(255,255,255,0.08)', borderRadius: '2px', overflow: 'hidden' }}>
                <div style={{ height: '100%', width: `${ivRank}%`, background: color, borderRadius: '2px' }} />
              </div>
            </div>
          );
        })}
      </div>
    </div>
  );
}

export default function MarketTab() {
  const { data, loading, error, refetch } = useApi('/api/market-overview');
  const overview = data?.data;

  return (
    <div style={{ animation: 'fadeInUp 0.4s ease-out' }}>
      <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: '1.5rem' }}>
        <div>
          <h2 style={{ fontSize: '1.4rem', fontWeight: 700, marginBottom: '0.2rem' }}>市场情绪</h2>
          <p style={{ color: 'var(--text-secondary)', fontSize: '0.85rem' }}>快速判断当前市场环境，决定是否适合卖出期权。</p>
        </div>
        <button
          onClick={() => refetch()}
          disabled={loading}
          style={{
            display: 'flex', alignItems: 'center', gap: '0.4rem',
            background: 'rgba(255,255,255,0.06)', border: '1px solid rgba(255,255,255,0.1)',
            color: 'var(--text-primary)', padding: '0.45rem 0.9rem',
            borderRadius: '8px', cursor: loading ? 'not-allowed' : 'pointer', fontSize: '0.82rem',
          }}
        >
          <RefreshCw size={14} style={{ animation: loading ? 'spin 1s linear infinite' : 'none' }} /> 刷新
        </button>
      </div>

      {loading ? (
        <LoadingSpinner message="正在获取市场数据，请稍候…" />
      ) : error ? (
        <ErrorBox message={error} />
      ) : overview ? (
        <>
          <VIXGauge vix={overview.vix} />
          <IVHeatMap ivRanks={overview.ivRanks} />
        </>
      ) : null}
    </div>
  );
}
