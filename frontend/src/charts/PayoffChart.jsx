import {
  ResponsiveContainer, ComposedChart, Line, Area,
  XAxis, YAxis, CartesianGrid, Tooltip, ReferenceLine,
} from 'recharts';

function fmt$(v) {
  const n = Number(v);
  return `${n < 0 ? '-$' : '$'}${Math.abs(n).toLocaleString(undefined, { maximumFractionDigits: 0 })}`;
}

function PayoffTooltip({ active, payload, label }) {
  if (!active || !payload?.length) return null;
  const d = payload[0].payload;
  return (
    <div style={{ background: 'rgba(15,23,42,0.96)', border: '1px solid rgba(255,255,255,0.12)', borderRadius: 8, padding: '0.7rem 0.9rem', fontSize: '0.8rem' }}>
      <div style={{ fontWeight: 700, marginBottom: '0.35rem' }}>股价 ${Number(label).toFixed(2)}</div>
      <div style={{ color: d.expiryPnl >= 0 ? '#10b981' : '#ef4444' }}>到期盈亏：{fmt$(d.expiryPnl)}</div>
      <div style={{ color: '#60a5fa' }}>当前盈亏：{fmt$(d.currentPnl)}</div>
      <div style={{ color: '#a78bfa' }}>中途盈亏：{fmt$(d.midPnl)}</div>
    </div>
  );
}

/**
 * 盈亏图：到期盈亏（实线）+ 当前/中途曲线（虚线）+ 盈亏平衡/现价参考线。
 * data = { curve:[{price,expiryPnl,currentPnl,midPnl}], breakEvens:[], spot, maxProfit, maxLoss }
 */
export default function PayoffChart({ data, height = 300 }) {
  if (!data?.curve?.length) return null;
  const { curve, breakEvens = [], spot } = data;

  return (
    <ResponsiveContainer width="100%" height={height}>
      <ComposedChart data={curve} margin={{ top: 10, right: 12, left: 4, bottom: 4 }}>
        <defs>
          <linearGradient id="pnlPos" x1="0" y1="0" x2="0" y2="1">
            <stop offset="0%" stopColor="#10b981" stopOpacity={0.25} />
            <stop offset="100%" stopColor="#10b981" stopOpacity={0} />
          </linearGradient>
        </defs>
        <CartesianGrid strokeDasharray="3 3" stroke="rgba(255,255,255,0.05)" />
        <XAxis dataKey="price" tick={{ fontSize: 11, fill: 'var(--text-secondary)' }}
          tickFormatter={v => `$${Number(v).toFixed(0)}`} />
        <YAxis tick={{ fontSize: 11, fill: 'var(--text-secondary)' }}
          tickFormatter={v => `$${v}`} />
        <Tooltip content={<PayoffTooltip />} />
        <ReferenceLine y={0} stroke="rgba(255,255,255,0.3)" />
        {spot != null && (
          <ReferenceLine x={curve.reduce((a, c) => Math.abs(c.price - spot) < Math.abs(a - spot) ? c.price : a, curve[0].price)}
            stroke="#f59e0b" strokeDasharray="5 3"
            label={{ value: '现价', fill: '#f59e0b', fontSize: 10, position: 'top' }} />
        )}
        {breakEvens.map((be, i) => (
          <ReferenceLine key={i} x={curve.reduce((a, c) => Math.abs(c.price - be) < Math.abs(a - be) ? c.price : a, curve[0].price)}
            stroke="rgba(255,255,255,0.25)" strokeDasharray="2 2"
            label={{ value: `盈亏平衡 ${be}`, fill: 'var(--text-secondary)', fontSize: 9, position: 'insideBottomLeft' }} />
        ))}
        <Area type="monotone" dataKey="expiryPnl" stroke="none" fill="url(#pnlPos)" />
        <Line type="monotone" dataKey="expiryPnl" stroke="#10b981" strokeWidth={2.5} dot={false} name="到期" />
        <Line type="monotone" dataKey="currentPnl" stroke="#60a5fa" strokeWidth={1.5} strokeDasharray="5 3" dot={false} name="当前" />
        <Line type="monotone" dataKey="midPnl" stroke="#a78bfa" strokeWidth={1.2} strokeDasharray="3 3" dot={false} name="中途" />
      </ComposedChart>
    </ResponsiveContainer>
  );
}
