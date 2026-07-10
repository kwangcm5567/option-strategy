import { useState } from 'react';
import { Layers, ChevronDown } from 'lucide-react';
import { useApi, apiFetch } from '../../hooks/useApi';
import LoadingSpinner, { ErrorBox } from '../../components/ui/LoadingSpinner';
import PayoffChart from '../../charts/PayoffChart';

const STRATEGIES = [
  { id: 'bull_put', label: '牛市看跌价差', desc: '看涨/中性 · 信用', kind: 'credit' },
  { id: 'bear_call', label: '熊市看涨价差', desc: '看跌/中性 · 信用', kind: 'credit' },
  { id: 'iron_condor', label: '铁鹰', desc: '区间震荡 · 双边信用', kind: 'condor' },
  { id: 'bull_call', label: '牛市看涨价差', desc: '看涨 · 借记', kind: 'debit' },
  { id: 'bear_put', label: '熊市看跌价差', desc: '看跌 · 借记', kind: 'debit' },
  { id: 'long_straddle', label: '买入跨式', desc: '预期大波动 · 财报', kind: 'vol' },
  { id: 'long_strangle', label: '买入宽跨', desc: '预期大波动 · 便宜', kind: 'vol' },
];

function fmt$(v) {
  if (v == null) return '—';
  const n = Number(v);
  return `${n < 0 ? '-$' : '$'}${Math.abs(n).toLocaleString(undefined, { maximumFractionDigits: 0 })}`;
}

function Metric({ label, value, color }) {
  return (
    <div>
      <div style={{ fontSize: '0.68rem', color: 'var(--text-secondary)', marginBottom: 2 }}>{label}</div>
      <div style={{ fontSize: '0.92rem', fontWeight: 700, color: color || 'var(--text-primary)' }}>{value}</div>
    </div>
  );
}

function LegBadge({ leg }) {
  const isBuy = leg.action === 'buy';
  return (
    <span style={{
      fontSize: '0.68rem', padding: '2px 7px', borderRadius: 5, fontWeight: 600,
      background: isBuy ? 'rgba(96,165,250,0.12)' : 'rgba(245,158,11,0.12)',
      color: isBuy ? '#60a5fa' : '#f59e0b',
      border: `1px solid ${isBuy ? 'rgba(96,165,250,0.3)' : 'rgba(245,158,11,0.3)'}`,
    }}>
      {isBuy ? '买' : '卖'} {leg.type === 'put' ? 'P' : 'C'}{leg.strike}
    </span>
  );
}

const today = () => new Date().toISOString().slice(0, 10);

function legToPosition(leg, s) {
  return {
    symbol: s.symbol,
    strategy: `${leg.action}_${leg.type}`,       // buy/sell × call/put
    strike: leg.strike,
    premium: leg.premium,
    quantity: leg.quantity || 1,
    expiration_date: s.expiration,
    open_date: today(),
    notes: `价差腿：${s.strategy} ${s.legs.map(l => `${l.action === 'buy' ? '买' : '卖'}${l.type === 'put' ? 'P' : 'C'}${l.strike}`).join('/')}`,
  };
}

function AddToPositionsButton({ s }) {
  const [state, setState] = useState('idle');   // idle | saving | done | error

  const add = async (e) => {
    e.stopPropagation();
    if (state === 'saving' || state === 'done') return;
    setState('saving');
    try {
      for (const leg of s.legs) {
        await apiFetch('POST', '/api/positions', legToPosition(leg, s));
      }
      setState('done');
    } catch {
      setState('error');
    }
  };

  const label = { idle: '+ 加入持仓', saving: '保存中…', done: '✓ 已加入', error: '失败，重试' }[state];
  const color = state === 'done' ? '#10b981' : state === 'error' ? '#ef4444' : '#60a5fa';
  return (
    <button onClick={add} disabled={state === 'saving' || state === 'done'}
      style={{
        background: 'rgba(96,165,250,0.1)', border: `1px solid ${color}55`, color,
        padding: '0.3rem 0.6rem', borderRadius: 6, cursor: state === 'done' ? 'default' : 'pointer',
        fontSize: '0.74rem', fontWeight: 600, whiteSpace: 'nowrap',
      }}>
      {label}
    </button>
  );
}

function SpreadCard({ s }) {
  const [open, setOpen] = useState(false);
  const [payoff, setPayoff] = useState(null);
  const [loadingPayoff, setLoadingPayoff] = useState(false);

  const toggle = async () => {
    const next = !open;
    setOpen(next);
    if (next && !payoff && s.legs) {
      setLoadingPayoff(true);
      try {
        const res = await apiFetch('POST', '/api/payoff', {
          legs: s.legs, spot: s.spot, dte: s.dte, priceRangePct: 0.30,
        });
        setPayoff(res);
      } catch { /* 忽略 */ }
      setLoadingPayoff(false);
    }
  };

  const isCredit = s.netCredit != null;
  const scoreColor = s.score >= 0.7 ? '#10b981' : s.score >= 0.5 ? '#f59e0b' : 'var(--text-secondary)';

  return (
    <div className="glass-panel" style={{ padding: '1rem 1.1rem', marginBottom: '0.8rem' }}>
      <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', cursor: 'pointer' }} onClick={toggle}>
        <div style={{ display: 'flex', alignItems: 'center', gap: '0.7rem' }}>
          <span style={{ fontSize: '1.05rem', fontWeight: 800 }}>{s.symbol}</span>
          <span style={{ fontSize: '0.72rem', color: 'var(--text-secondary)' }}>${s.spot} · {s.dte}天</span>
          <div style={{ display: 'flex', gap: '0.35rem' }}>
            {s.legs?.map((l, i) => <LegBadge key={i} leg={l} />)}
          </div>
        </div>
        <div style={{ display: 'flex', alignItems: 'center', gap: '0.8rem' }}>
          {s.legs?.length > 0 && <AddToPositionsButton s={s} />}
          <div style={{ textAlign: 'right' }}>
            <div style={{ fontSize: '0.66rem', color: 'var(--text-secondary)' }}>评分</div>
            <div style={{ fontSize: '1.05rem', fontWeight: 800, color: scoreColor }}>{(s.score * 100).toFixed(0)}</div>
          </div>
          <ChevronDown size={16} style={{ transform: open ? 'rotate(180deg)' : 'none', transition: 'transform 0.2s', color: 'var(--text-secondary)' }} />
        </div>
      </div>

      <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(80px, 1fr))', gap: '0.7rem', marginTop: '0.8rem' }}>
        {isCredit
          ? <Metric label="净信用" value={fmt$((s.netCredit || 0) * 100)} color="#10b981" />
          : <Metric label="净借记" value={fmt$((s.netDebit || 0) * 100)} color="#60a5fa" />}
        <Metric label="最大盈利" value={fmt$(s.maxProfit)} color="#10b981" />
        <Metric label="最大亏损" value={fmt$(s.maxLoss)} color="#ef4444" />
        {s.pop != null && <Metric label="POP" value={`${s.pop}%`} />}
        {s.creditWidthPct != null && <Metric label="信用/宽度" value={`${s.creditWidthPct}%`} color={s.creditWidthPct >= 33 ? '#10b981' : undefined} />}
        {s.riskReward != null && <Metric label="盈亏比" value={s.riskReward} />}
        {s.moveEdge != null && <Metric label="波动优势" value={`${s.moveEdge}%`} color={s.moveEdge > 0 ? '#10b981' : '#ef4444'} />}
        {s.netTheta != null && <Metric label="净Theta/日" value={fmt$(s.netTheta)} color={s.netTheta >= 0 ? '#10b981' : '#ef4444'} />}
        {s.netDelta != null && <Metric label="净Delta" value={s.netDelta} />}
      </div>

      {open && (
        <div style={{ marginTop: '1rem', borderTop: '1px solid rgba(255,255,255,0.08)', paddingTop: '1rem' }}>
          <div style={{ fontSize: '0.78rem', color: 'var(--text-secondary)', marginBottom: '0.5rem' }}>
            盈亏图（🟢到期 · 🔵当前 · 🟣中途）
            {(s.lowerBreakEven != null || s.upperBreakEven != null) &&
              <span> · 盈亏平衡 {s.lowerBreakEven ?? s.breakEven}{s.upperBreakEven ? ` ~ ${s.upperBreakEven}` : ''}</span>}
          </div>
          {loadingPayoff ? <LoadingSpinner message="计算盈亏曲线…" />
            : payoff ? <PayoffChart data={payoff} />
            : <div style={{ color: 'var(--text-secondary)', fontSize: '0.8rem' }}>无法加载盈亏图</div>}
        </div>
      )}
    </div>
  );
}

export default function SpreadsTab() {
  const [strategy, setStrategy] = useState('bull_put');
  const { data, loading, error, refetch } = useApi(null, { timeout: 120_000 });
  const [scanned, setScanned] = useState(false);

  const runScan = (strat) => {
    setScanned(true);
    refetch(`/api/scan-spreads?strategy=${strat}`);
  };

  const results = data?.results || [];

  return (
    <div style={{ animation: 'fadeInUp 0.4s ease-out' }}>
      <div style={{ marginBottom: '1.2rem' }}>
        <h2 style={{ fontSize: '1.4rem', fontWeight: 700, marginBottom: '0.2rem', display: 'flex', alignItems: 'center', gap: '0.5rem' }}>
          <Layers size={22} /> 价差扫描
        </h2>
        <p style={{ color: 'var(--text-secondary)', fontSize: '0.85rem' }}>
          多腿组合策略：定义风险的信用价差、铁鹰、以及财报波动率交易。点击卡片展开盈亏图。
        </p>
      </div>

      <div style={{ display: 'flex', flexWrap: 'wrap', gap: '0.5rem', marginBottom: '1.2rem' }}>
        {STRATEGIES.map(s => {
          const active = s.id === strategy;
          return (
            <button key={s.id}
              onClick={() => { setStrategy(s.id); runScan(s.id); }}
              disabled={loading}
              style={{
                textAlign: 'left', padding: '0.5rem 0.8rem', borderRadius: 8, cursor: loading ? 'not-allowed' : 'pointer',
                background: active ? 'rgba(139,92,246,0.15)' : 'rgba(255,255,255,0.04)',
                border: `1px solid ${active ? 'rgba(139,92,246,0.4)' : 'rgba(255,255,255,0.08)'}`,
                color: active ? '#a78bfa' : 'var(--text-primary)',
              }}>
              <div style={{ fontSize: '0.82rem', fontWeight: 700 }}>{s.label}</div>
              <div style={{ fontSize: '0.66rem', color: 'var(--text-secondary)' }}>{s.desc}</div>
            </button>
          );
        })}
      </div>

      {!scanned ? (
        <div style={{ textAlign: 'center', padding: '3rem', color: 'var(--text-secondary)', fontSize: '0.9rem' }}>
          选择一种策略开始扫描（约需 20–40 秒）。
        </div>
      ) : loading ? (
        <LoadingSpinner message="正在扫描全市场价差组合，请稍候…" />
      ) : error ? (
        <ErrorBox message={error} />
      ) : results.length ? (
        <>
          <div style={{ fontSize: '0.78rem', color: 'var(--text-secondary)', marginBottom: '0.8rem' }}>
            找到 {results.length} 个组合，按甜点评分排序{data?.cached ? '（缓存）' : ''}。
          </div>
          {results.map((s, i) => <SpreadCard key={`${s.symbol}-${i}`} s={s} />)}
        </>
      ) : (
        <div style={{ textAlign: 'center', padding: '3rem', color: 'var(--text-secondary)', fontSize: '0.9rem' }}>
          未找到符合条件的组合，换个策略或稍后再试。
        </div>
      )}
    </div>
  );
}
