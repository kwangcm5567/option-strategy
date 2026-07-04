import { Shield, RefreshCw } from 'lucide-react';
import { useApi } from '../../hooks/useApi';
import LoadingSpinner, { ErrorBox } from '../../components/ui/LoadingSpinner';

function fmt$(v) {
  if (v == null) return '—';
  const n = Number(v);
  return `${n < 0 ? '-$' : '$'}${Math.abs(n).toLocaleString(undefined, { maximumFractionDigits: 0 })}`;
}

function StatTile({ label, value, sub, color, tip }) {
  return (
    <div className="glass-panel" style={{ padding: '0.9rem 1rem', flex: '1 1 150px' }} title={tip}>
      <div style={{ fontSize: '0.72rem', color: 'var(--text-secondary)', marginBottom: 4 }}>{label}</div>
      <div style={{ fontSize: '1.45rem', fontWeight: 800, color: color || 'var(--text-primary)' }}>{value}</div>
      {sub && <div style={{ fontSize: '0.7rem', color: 'var(--text-secondary)', marginTop: 2 }}>{sub}</div>}
    </div>
  );
}

function StressBars({ stress }) {
  if (!stress?.length) return null;
  const maxAbs = Math.max(...stress.map(s => Math.abs(s.pnl)), 1);
  return (
    <div className="glass-panel" style={{ padding: '1.1rem', marginBottom: '1.2rem' }}>
      <h3 style={{ fontSize: '0.95rem', fontWeight: 700, marginBottom: '0.2rem' }}>情景压力测试</h3>
      <p style={{ fontSize: '0.72rem', color: 'var(--text-secondary)', marginBottom: '0.9rem' }}>
        历史极端行情下，当前组合的估算盈亏（Black-Scholes 全重估）。
      </p>
      {stress.map(s => {
        const pos = s.pnl >= 0;
        const w = Math.abs(s.pnl) / maxAbs * 100;
        return (
          <div key={s.scenario} style={{ marginBottom: '0.7rem' }}>
            <div style={{ display: 'flex', justifyContent: 'space-between', fontSize: '0.78rem', marginBottom: 3 }}>
              <span>{s.scenario} <span style={{ color: 'var(--text-secondary)', fontSize: '0.68rem' }}>
                （价{s.priceShock > 0 ? '+' : ''}{(s.priceShock * 100).toFixed(0)}% · IV{s.ivShock > 0 ? '+' : ''}{(s.ivShock * 100).toFixed(0)}）</span></span>
              <b style={{ color: pos ? '#10b981' : '#ef4444' }}>{fmt$(s.pnl)}</b>
            </div>
            <div style={{ height: 6, background: 'rgba(255,255,255,0.06)', borderRadius: 3, position: 'relative' }}>
              <div style={{ position: 'absolute', left: '50%', top: 0, bottom: 0, width: 1, background: 'rgba(255,255,255,0.2)' }} />
              <div style={{
                position: 'absolute', height: '100%', borderRadius: 3,
                background: pos ? '#10b981' : '#ef4444',
                width: `${w / 2}%`, [pos ? 'left' : 'right']: '50%',
              }} />
            </div>
          </div>
        );
      })}
    </div>
  );
}

function CorrelationMatrix({ correlation }) {
  if (!correlation?.symbols?.length || correlation.symbols.length < 2) return null;
  const { symbols, matrix } = correlation;
  const cellColor = (v) => {
    if (v >= 0.7) return 'rgba(239,68,68,0.55)';
    if (v >= 0.4) return 'rgba(245,158,11,0.4)';
    if (v >= 0) return 'rgba(16,185,129,0.25)';
    return 'rgba(96,165,250,0.35)';
  };
  return (
    <div className="glass-panel" style={{ padding: '1.1rem', marginBottom: '1.2rem', overflowX: 'auto' }}>
      <h3 style={{ fontSize: '0.95rem', fontWeight: 700, marginBottom: '0.2rem' }}>持仓相关性矩阵</h3>
      <p style={{ fontSize: '0.72rem', color: 'var(--text-secondary)', marginBottom: '0.9rem' }}>
        🔴 高相关（&gt;0.7，同涨同跌，分散不足） · 🟢 低相关 · 🔵 负相关（天然对冲）
      </p>
      <table style={{ borderCollapse: 'collapse', fontSize: '0.72rem' }}>
        <thead>
          <tr>
            <th style={{ padding: 4 }}></th>
            {symbols.map(s => <th key={s} style={{ padding: '4px 6px', color: 'var(--text-secondary)' }}>{s}</th>)}
          </tr>
        </thead>
        <tbody>
          {symbols.map((s, i) => (
            <tr key={s}>
              <td style={{ padding: '4px 6px', fontWeight: 700, color: 'var(--text-secondary)' }}>{s}</td>
              {matrix[i].map((v, j) => (
                <td key={j} style={{
                  padding: '4px 6px', textAlign: 'center', fontWeight: 600,
                  background: i === j ? 'rgba(255,255,255,0.06)' : cellColor(v),
                  borderRadius: 3,
                }}>{v.toFixed(2)}</td>
              ))}
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}

function ConcentrationPanel({ concentration }) {
  if (!concentration) return null;
  const sectors = Object.entries(concentration.bySector || {});
  const hhiColor = concentration.hhiLabel === '高度集中' ? '#ef4444' : concentration.hhiLabel === '中度集中' ? '#f59e0b' : '#10b981';
  return (
    <div className="glass-panel" style={{ padding: '1.1rem', marginBottom: '1.2rem' }}>
      <div style={{ display: 'flex', justifyContent: 'space-between', marginBottom: '0.9rem' }}>
        <h3 style={{ fontSize: '0.95rem', fontWeight: 700 }}>集中度分析</h3>
        <span style={{ fontSize: '0.78rem', fontWeight: 700, color: hhiColor }}>
          {concentration.hhiLabel}（HHI {concentration.hhi}）
        </span>
      </div>
      <div style={{ fontSize: '0.75rem', color: 'var(--text-secondary)', marginBottom: '0.8rem' }}>
        最大单一敞口：<b style={{ color: 'var(--text-primary)' }}>{concentration.topSymbol}</b> 占 {concentration.topSymbolPct}%
      </div>
      {sectors.map(([sec, pct]) => (
        <div key={sec} style={{ marginBottom: '0.55rem' }}>
          <div style={{ display: 'flex', justifyContent: 'space-between', fontSize: '0.76rem', marginBottom: 2 }}>
            <span>{sec}</span><b>{pct}%</b>
          </div>
          <div style={{ height: 6, background: 'rgba(255,255,255,0.06)', borderRadius: 3, overflow: 'hidden' }}>
            <div style={{ height: '100%', width: `${pct}%`, background: pct > 50 ? '#ef4444' : pct > 30 ? '#f59e0b' : '#8b5cf6', borderRadius: 3 }} />
          </div>
        </div>
      ))}
    </div>
  );
}

export default function RiskTab() {
  const { data, loading, error, refetch } = useApi('/api/portfolio/risk');
  const r = data?.data;

  return (
    <div style={{ animation: 'fadeInUp 0.4s ease-out' }}>
      <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: '1.2rem' }}>
        <div>
          <h2 style={{ fontSize: '1.4rem', fontWeight: 700, marginBottom: '0.2rem', display: 'flex', alignItems: 'center', gap: '0.5rem' }}>
            <Shield size={22} /> 组合风险台
          </h2>
          <p style={{ color: 'var(--text-secondary)', fontSize: '0.85rem' }}>
            Beta 加权敞口、相关性、集中度、VaR 与压力测试 —— 机构级组合视角。
          </p>
        </div>
        <button onClick={() => refetch()} disabled={loading}
          style={{ display: 'flex', alignItems: 'center', gap: '0.4rem', background: 'rgba(255,255,255,0.06)',
            border: '1px solid rgba(255,255,255,0.1)', color: 'var(--text-primary)', padding: '0.45rem 0.9rem',
            borderRadius: 8, cursor: loading ? 'not-allowed' : 'pointer', fontSize: '0.82rem' }}>
          <RefreshCw size={14} style={{ animation: loading ? 'spin 1s linear infinite' : 'none' }} /> 刷新
        </button>
      </div>

      {loading ? (
        <LoadingSpinner message="计算组合风险指标（含 Beta 回归与历史模拟）…" />
      ) : error ? (
        <ErrorBox message={error} />
      ) : !r || r.empty ? (
        <div style={{ textAlign: 'center', padding: '3rem', color: 'var(--text-secondary)', fontSize: '0.9rem' }}>
          暂无未平仓持仓。在「持仓追踪」添加持仓后，此处显示组合风险分析。
        </div>
      ) : (
        <>
          <div style={{ display: 'flex', flexWrap: 'wrap', gap: '0.8rem', marginBottom: '1.2rem' }}>
            <StatTile label="Beta 加权 Delta" value={r.greeks.betaWeightedDelta}
              sub={`≈ ${fmt$(r.greeks.spyEquivalent)} SPY 等价敞口`}
              color={Math.abs(r.greeks.betaWeightedDelta) > 100 ? '#f59e0b' : '#10b981'}
              tip="全组合折算成 SPY 股数的方向性敞口。>0 偏多，<0 偏空。" />
            <StatTile label="裸 Delta" value={r.greeks.totalDelta} />
            <StatTile label="日 Theta" value={fmt$(r.greeks.totalTheta)}
              color={r.greeks.totalTheta >= 0 ? '#10b981' : '#ef4444'} sub="每日时间价值收益" />
            <StatTile label="Vega" value={r.greeks.totalVega}
              sub="IV 每+1% 的盈亏" color={r.greeks.totalVega >= 0 ? '#60a5fa' : '#ef4444'} />
            <StatTile label="1日 VaR (95%)" value={fmt$(r.var?.oneDayVar95)}
              color="#ef4444" sub={r.var?.expectedShortfall ? `ES ${fmt$(r.var.expectedShortfall)}` : null}
              tip="95% 置信下，单日最大可能亏损（历史模拟法）。" />
          </div>

          <StressBars stress={r.stress} />
          <ConcentrationPanel concentration={r.concentration} />
          <CorrelationMatrix correlation={r.correlation} />
        </>
      )}
    </div>
  );
}
