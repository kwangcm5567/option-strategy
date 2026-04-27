import {
  ResponsiveContainer, AreaChart, Area, XAxis, YAxis,
  CartesianGrid, Tooltip, ReferenceLine,
} from 'recharts';

/**
 * 到期 P&L 损益图
 * strategy: 'sell_put' | 'buy_call' | 'sell_call' | 'buy_put'
 */
export default function PnLChart({ currentPrice, strike, premium, strategy }) {
  if (!currentPrice || !strike || premium == null) return null;

  // 生成价格区间（当前价 ±35%，100 个点）
  const low = currentPrice * 0.65;
  const high = currentPrice * 1.35;
  const step = (high - low) / 100;

  const data = Array.from({ length: 101 }, (_, i) => {
    const price = low + i * step;
    let pnl;

    switch (strategy) {
      case 'sell_put':
        pnl = price >= strike ? premium * 100 : (premium - (strike - price)) * 100;
        break;
      case 'buy_call':
        pnl = price <= strike ? -premium * 100 : (price - strike - premium) * 100;
        break;
      case 'sell_call':
        pnl = price <= strike ? premium * 100 : (premium - (price - strike)) * 100;
        break;
      case 'buy_put':
        pnl = price >= strike ? -premium * 100 : (strike - price - premium) * 100;
        break;
      default:
        pnl = 0;
    }

    return { price: +price.toFixed(2), pnl: +pnl.toFixed(2) };
  });

  const maxPnl = Math.max(...data.map(d => d.pnl));
  const minPnl = Math.min(...data.map(d => d.pnl));

  // 盈利区绿色、亏损区红色
  const gradientId = `pnl-gradient-${strategy}`;

  return (
    <div>
      <p style={{ fontSize: '0.8rem', color: 'var(--text-secondary)', marginBottom: '0.75rem' }}>
        横轴 = 到期日股价 · 纵轴 = 每合约盈亏（$）· 绿色区域 = 盈利
      </p>
      <ResponsiveContainer width="100%" height={220}>
        <AreaChart data={data} margin={{ top: 10, right: 10, left: 0, bottom: 0 }}>
          <defs>
            <linearGradient id={gradientId} x1="0" y1="0" x2="0" y2="1">
              <stop offset="5%" stopColor="#10b981" stopOpacity={0.3} />
              <stop offset="95%" stopColor="#ef4444" stopOpacity={0.2} />
            </linearGradient>
          </defs>
          <CartesianGrid strokeDasharray="3 3" stroke="rgba(255,255,255,0.06)" />
          <XAxis
            dataKey="price"
            tickFormatter={v => `$${v.toFixed(0)}`}
            stroke="var(--text-secondary)"
            tick={{ fontSize: 11 }}
            minTickGap={40}
          />
          <YAxis
            tickFormatter={v => `$${v >= 0 ? '+' : ''}${v.toFixed(0)}`}
            stroke="var(--text-secondary)"
            tick={{ fontSize: 11 }}
            width={70}
          />
          <Tooltip
            formatter={(val) => [`$${val >= 0 ? '+' : ''}${val.toFixed(2)}`, '盈亏/合约']}
            labelFormatter={(label) => `股价：$${label}`}
            contentStyle={{
              background: '#1e293b',
              border: '1px solid rgba(255,255,255,0.1)',
              borderRadius: '8px',
              fontSize: '0.82rem',
            }}
          />
          {/* 零线 */}
          <ReferenceLine y={0} stroke="rgba(255,255,255,0.3)" strokeDasharray="4 4" />
          {/* 当前股价 */}
          <ReferenceLine
            x={+currentPrice.toFixed(2)}
            stroke="#60a5fa"
            strokeDasharray="4 4"
            label={{ value: `现价 $${currentPrice.toFixed(0)}`, fill: '#60a5fa', fontSize: 11, position: 'top' }}
          />
          {/* 行权价 */}
          <ReferenceLine
            x={+strike.toFixed(2)}
            stroke="#f59e0b"
            strokeDasharray="4 4"
            label={{ value: `行权 $${strike.toFixed(0)}`, fill: '#f59e0b', fontSize: 11, position: 'insideTopRight' }}
          />
          <Area
            type="monotone"
            dataKey="pnl"
            stroke="url(#pnl-color)"
            fill={`url(#${gradientId})`}
            strokeWidth={2}
            dot={false}
            // 正负区颜色分离
            stroke="#10b981"
          />
        </AreaChart>
      </ResponsiveContainer>
    </div>
  );
}
