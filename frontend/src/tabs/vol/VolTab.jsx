import { useState } from 'react';
import { Activity, Search } from 'lucide-react';
import {
  ResponsiveContainer, LineChart, Line, XAxis, YAxis,
  CartesianGrid, Tooltip, ReferenceLine,
} from 'recharts';
import { useApi } from '../../hooks/useApi';
import LoadingSpinner, { ErrorBox } from '../../components/ui/LoadingSpinner';

function StatTile({ label, value, sub, color }) {
  return (
    <div className="glass-panel" style={{ padding: '0.9rem 1rem', flex: '1 1 130px' }}>
      <div style={{ fontSize: '0.72rem', color: 'var(--text-secondary)', marginBottom: 4 }}>{label}</div>
      <div style={{ fontSize: '1.5rem', fontWeight: 800, color: color || 'var(--text-primary)' }}>{value}</div>
      {sub && <div style={{ fontSize: '0.7rem', color: 'var(--text-secondary)', marginTop: 2 }}>{sub}</div>}
    </div>
  );
}

function TermStructureChart({ term, shape }) {
  if (!term?.length) return null;
  const shapeLabel = { contango: 'Contango（远月更贵·正常）', backwardation: 'Backwardation（近月更贵·紧张）', flat: '平坦' }[shape] || '';
  const shapeColor = shape === 'backwardation' ? '#ef4444' : shape === 'contango' ? '#10b981' : 'var(--text-secondary)';
  return (
    <div className="glass-panel" style={{ padding: '1.1rem', marginBottom: '1.2rem' }}>
      <div style={{ display: 'flex', justifyContent: 'space-between', marginBottom: '0.6rem' }}>
        <h3 style={{ fontSize: '0.95rem', fontWeight: 700 }}>IV 期限结构</h3>
        <span style={{ fontSize: '0.75rem', fontWeight: 600, color: shapeColor }}>{shapeLabel}</span>
      </div>
      <ResponsiveContainer width="100%" height={220}>
        <LineChart data={term} margin={{ top: 8, right: 12, left: 0, bottom: 0 }}>
          <CartesianGrid strokeDasharray="3 3" stroke="rgba(255,255,255,0.05)" />
          <XAxis dataKey="dte" tick={{ fontSize: 11, fill: 'var(--text-secondary)' }} tickFormatter={v => `${v}天`} />
          <YAxis tick={{ fontSize: 11, fill: 'var(--text-secondary)' }} tickFormatter={v => `${v}%`}
            domain={['dataMin - 2', 'dataMax + 2']} />
          <Tooltip
            contentStyle={{ background: 'rgba(15,23,42,0.96)', border: '1px solid rgba(255,255,255,0.12)', borderRadius: 8, fontSize: '0.8rem' }}
            formatter={(v) => [`${v}%`, 'ATM IV']} labelFormatter={l => `${l} 天到期`} />
          <Line type="monotone" dataKey="atmIv" stroke="#a78bfa" strokeWidth={2.5} dot={{ r: 3, fill: '#a78bfa' }} />
        </LineChart>
      </ResponsiveContainer>
    </div>
  );
}

function SkewChart({ skew }) {
  if (!skew) return null;
  const merged = {};
  (skew.putCurve || []).forEach(p => { merged[p.moneyness] = { moneyness: p.moneyness, putIv: p.iv }; });
  (skew.callCurve || []).forEach(c => { merged[c.moneyness] = { ...(merged[c.moneyness] || { moneyness: c.moneyness }), callIv: c.iv }; });
  const rows = Object.values(merged).sort((a, b) => a.moneyness - b.moneyness);

  return (
    <div className="glass-panel" style={{ padding: '1.1rem' }}>
      <div style={{ display: 'flex', justifyContent: 'space-between', marginBottom: '0.6rem' }}>
        <h3 style={{ fontSize: '0.95rem', fontWeight: 700 }}>波动率偏斜 Skew（{skew.expiration}）</h3>
        <div style={{ display: 'flex', gap: '1rem', fontSize: '0.72rem', color: 'var(--text-secondary)' }}>
          {skew.riskReversal25d != null && <span>25Δ RR：<b style={{ color: skew.riskReversal25d < 0 ? '#ef4444' : '#10b981' }}>{skew.riskReversal25d > 0 ? '+' : ''}{skew.riskReversal25d}</b></span>}
          {skew.putSkew != null && <span>Put 偏斜：<b>{skew.putSkew > 0 ? '+' : ''}{skew.putSkew}</b></span>}
        </div>
      </div>
      <ResponsiveContainer width="100%" height={240}>
        <LineChart data={rows} margin={{ top: 8, right: 12, left: 0, bottom: 0 }}>
          <CartesianGrid strokeDasharray="3 3" stroke="rgba(255,255,255,0.05)" />
          <XAxis dataKey="moneyness" tick={{ fontSize: 11, fill: 'var(--text-secondary)' }}
            tickFormatter={v => `${(v * 100).toFixed(0)}%`} type="number" domain={['dataMin', 'dataMax']} />
          <YAxis tick={{ fontSize: 11, fill: 'var(--text-secondary)' }} tickFormatter={v => `${v}%`} />
          <Tooltip
            contentStyle={{ background: 'rgba(15,23,42,0.96)', border: '1px solid rgba(255,255,255,0.12)', borderRadius: 8, fontSize: '0.8rem' }}
            labelFormatter={l => `行权价/现价 ${(l * 100).toFixed(1)}%`} />
          <ReferenceLine x={1.0} stroke="#f59e0b" strokeDasharray="4 3" label={{ value: 'ATM', fill: '#f59e0b', fontSize: 10, position: 'top' }} />
          <Line type="monotone" dataKey="putIv" stroke="#ef4444" strokeWidth={2} dot={false} name="Put IV" connectNulls />
          <Line type="monotone" dataKey="callIv" stroke="#10b981" strokeWidth={2} dot={false} name="Call IV" connectNulls />
        </LineChart>
      </ResponsiveContainer>
      <div style={{ fontSize: '0.72rem', color: 'var(--text-secondary)', marginTop: '0.5rem' }}>
        🔴 Put IV · 🟢 Call IV。左侧（OTM Put）更高 = 市场为下行买保险，典型股票偏斜。
      </div>
    </div>
  );
}

export default function VolTab() {
  const [input, setInput] = useState('AAPL');
  const { data, loading, error, refetch } = useApi(null);
  const [queried, setQueried] = useState(false);

  const go = () => {
    const sym = input.trim().toUpperCase();
    if (!sym) return;
    setQueried(true);
    refetch(`/api/vol-surface/${sym}`);
  };

  const ivRank = data?.ivRank;

  return (
    <div style={{ animation: 'fadeInUp 0.4s ease-out' }}>
      <div style={{ marginBottom: '1.2rem' }}>
        <h2 style={{ fontSize: '1.4rem', fontWeight: 700, marginBottom: '0.2rem', display: 'flex', alignItems: 'center', gap: '0.5rem' }}>
          <Activity size={22} /> 波动率分析
        </h2>
        <p style={{ color: 'var(--text-secondary)', fontSize: '0.85rem' }}>
          IV 期限结构、偏斜（skew）与真实 IV Rank。判断该卖还是该买、选哪个到期。
        </p>
      </div>

      <div style={{ display: 'flex', gap: '0.5rem', marginBottom: '1.2rem', maxWidth: 360 }}>
        <input value={input} onChange={e => setInput(e.target.value)} onKeyDown={e => e.key === 'Enter' && go()}
          placeholder="输入代码，如 AAPL"
          style={{ flex: 1, padding: '0.55rem 0.9rem', borderRadius: 8, background: 'rgba(255,255,255,0.05)',
            border: '1px solid rgba(255,255,255,0.12)', color: 'var(--text-primary)', fontSize: '0.9rem' }} />
        <button onClick={go} disabled={loading}
          style={{ display: 'flex', alignItems: 'center', gap: '0.4rem', padding: '0.55rem 1.1rem', borderRadius: 8,
            background: 'var(--accent-color)', border: 'none', color: '#fff', fontWeight: 600,
            cursor: loading ? 'not-allowed' : 'pointer' }}>
          <Search size={15} /> 分析
        </button>
      </div>

      {!queried ? (
        <div style={{ textAlign: 'center', padding: '3rem', color: 'var(--text-secondary)', fontSize: '0.9rem' }}>
          输入股票代码，查看其波动率结构。
        </div>
      ) : loading ? (
        <LoadingSpinner message="获取期权链并分析波动率…" />
      ) : error ? (
        <ErrorBox message={error} />
      ) : data ? (
        <>
          <div style={{ display: 'flex', flexWrap: 'wrap', gap: '0.8rem', marginBottom: '1.2rem' }}>
            <StatTile label={`${data.symbol} 现价`} value={`$${data.spot}`} />
            <StatTile label="IV30" value={data.iv30 ? `${data.iv30}%` : '—'} />
            {ivRank ? (
              <>
                <StatTile label="真实 IV Rank" value={`${ivRank.ivRank}%`}
                  sub={`${ivRank.sampleDays}天样本 · ${ivRank.ivLow}~${ivRank.ivHigh}%`}
                  color={ivRank.ivRank >= 50 ? '#ef4444' : '#10b981'} />
                <StatTile label="IV 百分位" value={`${ivRank.ivPercentile}%`}
                  color={ivRank.ivPercentile >= 50 ? '#f59e0b' : '#10b981'} />
              </>
            ) : (
              <StatTile label="IV Rank" value="积累中" sub="需 ≥20 天快照，每次分析自动记录" color="var(--text-secondary)" />
            )}
          </div>
          <TermStructureChart term={data.termStructure} shape={data.structureShape} />
          <SkewChart skew={data.skew} />
        </>
      ) : null}
    </div>
  );
}
